"""Fatia 1 do motor 2D (ADR 0011): pista como faixa com largura e lateral.

Esta camada envolve a linha de centro de ``track_geometry`` numa faixa 2D: cada
ponto ganha um vetor normal (perpendicular ao traçado) e a pista ganha uma
largura. Com isso, um ponto da pista passa a ser descrito por duas coordenadas,
``(distancia_longitudinal, deslocamento_lateral)``, e convertido para ``(x, y)``
no mesmo plano normalizado do desenho.

Fronteiras (ADR 0011): esta é geometria de física, isolada do motor por volta e
da ``track_geometry`` de desenho, que permanece intocada. A largura e as
dimensões de carro são hipóteses assumidas e não calibradas; os eixos x,y
continuam adimensionais (herdados do desenho), enquanto a distância longitudinal
está em metros, como em ``cumulative_distance_m``.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, replace
from math import ceil, hypot

from f1_simulator.domain.pit_lane import (
    PitLaneParameters,
    PitLanePath,
    PitLaneState,
    PitStopRequest,
)
from f1_simulator.domain.random_source import RandomSource
from f1_simulator.domain.spatial_contact import (
    ASSUMED_CONTACT,
    ContactTracker,
    contact_consequence,
)
from f1_simulator.domain.speed_dynamics import (
    DEFAULT_CAR_PHYSICS,
    CarPhysics,
    speed_ceiling,
)
from f1_simulator.domain.track_geometry import TrackGeometry

#: Passo de tempo da integracao sub-volta (s). Hipotese assumida (ADR 0011):
#: menor passo aproxima melhor o continuo e custa mais. 100 ms (era 50 ms ate a
#: otimizacao de desempenho do commit 9c94abd) equilibra as duas coisas para o
#: uso educacional.
ASSUMED_TIME_STEP_S = 0.1

#: Velocidade lateral maxima de troca de faixa (m/s). Hipotese assumida: um
#: carro leva cerca de um segundo para cruzar a pista inteira. Governa quao
#: rapido a manobra de ultrapassagem se desloca para o lado.
ASSUMED_LANE_CHANGE_MS = 6.0

#: Folga longitudinal (m) a partir da qual um carro mais rapido "sente" o da
#: frente e considera tentar passar. Ordem de grandeza de alguns comprimentos
#: de carro; nao calibrada.
ASSUMED_FOLLOW_TRIGGER_M = 20.0
#: Histerese: encerra uma tentativa cujo alvo escapou para alem da janela
#: inicial, sem alternar entre atacar e desistir a cada cruzamento de 20 m.
ASSUMED_PASS_ABORT_GAP_M = 2 * ASSUMED_FOLLOW_TRIGGER_M
PASS_OPPORTUNITY_VERSION = "passing-opportunity-revalidation-assumed-v1"

#: Margem lateral (m) abaixo da qual os corpos lado a lado "roçam": soma das
#: meias-larguras mais esta folga. Nao calibrada.
ASSUMED_RUBBING_MARGIN_M = 0.3

#: Largura de pista assumida (m). Hipótese não calibrada: ordem de grandeza de
#: uma pista de F1, suficiente para dois carros lado a lado. Vira parâmetro
#: versionado quando o motor 2D consumir larguras por circuito.
ASSUMED_TRACK_WIDTH_M = 12.0

#: Distancia (m) a partir da largada em que a colisao fica suprimida numa
#: largada parada. O grid parte com os carros emparelhados e lentos; sem esta
#: zona neutra eles se tocariam ao se desenrolar do grid, gerando abandonos
#: irreais na largada. Cobre a aceleracao inicial ate o pelotao se espalhar;
#: depois dela a colisao volta. Hipotese de apresentacao, nao calibrada.
ASSUMED_START_ZONE_M = 500.0

#: Dimensões assumidas de um carro (m), para a exclusão espacial e a colisão das
#: fatias seguintes. Não calibradas; ordem de grandeza de um F1 moderno.
ASSUMED_CAR_LENGTH_M = 5.0
ASSUMED_CAR_WIDTH_M = 2.0


@dataclass(frozen=True, slots=True)
class LateralBounds:
    """Faixa lateral utilizável, em metros a partir da linha de centro.

    ``half_width`` é o afastamento máximo para cada lado; um carro de largura
    ``car_width`` pode centrar-se em ``[-usable, +usable]`` sem sair da pista.
    """

    half_width_m: float
    car_width_m: float

    def __post_init__(self) -> None:
        if self.half_width_m <= 0:
            raise ValueError("half_width_m deve ser positivo")
        if not 0 < self.car_width_m <= 2 * self.half_width_m:
            raise ValueError("car_width_m deve caber na largura da pista")

    @property
    def usable_m(self) -> float:
        """Maior deslocamento lateral do centro do carro sem sair da pista."""

        return self.half_width_m - self.car_width_m / 2


@dataclass(frozen=True, slots=True)
class SpacePoint:
    """Ponto da linha de centro com a normal unitaria para o lado esquerdo.

    ``nx, ny`` apontam para a esquerda do sentido de corrida, de modo que um
    deslocamento lateral positivo leva o carro para esse lado. A escala xy é a
    normalizada do desenho; a largura real entra como fator ao converter metros
    de deslocamento em unidades xy.
    """

    distance_m: float
    cx: float
    cy: float
    nx: float
    ny: float


@dataclass(frozen=True, slots=True)
class TrackSpace:
    """Faixa 2D da pista: linha de centro, normais e largura.

    Converte ``(distancia, deslocamento_lateral_em_m)`` para ``(x, y)`` no plano
    do desenho. A conversão de metros laterais para unidades xy usa a escala que
    relaciona o comprimento real da volta ao perimetro normalizado, para que a
    largura não dependa do tamanho arbitrario do desenho.
    """

    points: tuple[SpacePoint, ...]
    lap_length_m: float
    width_m: float
    xy_per_metre: float
    geometry: TrackGeometry

    @property
    def bounds(self) -> LateralBounds:
        return LateralBounds(self.width_m / 2, ASSUMED_CAR_WIDTH_M)

    def position(self, distance_m: float, lateral_m: float) -> tuple[float, float]:
        """Ponto ``(x, y)`` a ``distance_m`` ao longo da volta e ``lateral_m`` do centro."""

        d = distance_m % self.lap_length_m if self.lap_length_m else 0.0
        pts = self.points
        lo, hi = 0, len(pts) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if pts[mid].distance_m < d:
                lo = mid + 1
            else:
                hi = mid
        i = max(1, lo)
        a, b = pts[i - 1], pts[i]
        span = b.distance_m - a.distance_m
        f = (d - a.distance_m) / span if span > 0 else 0.0
        cx = a.cx + (b.cx - a.cx) * f
        cy = a.cy + (b.cy - a.cy) * f
        nx = a.nx + (b.nx - a.nx) * f
        ny = a.ny + (b.ny - a.ny) * f
        # Interpolar normais unitarias reduz seu modulo nas curvas. Sem esta
        # normalizacao, um deslocamento em metros encolhe em relacao ao frontend
        # e a projecao usada na exclusao, embora o eixo de distancia seja igual.
        norm = hypot(nx, ny)
        if norm <= 1e-12:
            nx, ny = a.nx, a.ny
        else:
            nx, ny = nx / norm, ny / norm
        offset = lateral_m * self.xy_per_metre
        return (cx + nx * offset, cy + ny * offset)


def build_track_space(
    geometry: TrackGeometry,
    width_m: float = ASSUMED_TRACK_WIDTH_M,
) -> TrackSpace:
    """Envolva a linha de centro numa faixa com largura e normais por ponto.

    A normal de cada ponto vem da direcao media dos segmentos vizinhos, girada
    90 graus para a esquerda e normalizada. O fechamento do anel usa o primeiro
    ponto como vizinho do ultimo, coerente com a polilinha fechada do desenho.
    """

    if width_m <= 0:
        raise ValueError("width_m deve ser positivo")
    tp = geometry.track_points
    if len(tp) < 2:
        raise ValueError("geometria precisa de pelo menos dois pontos")

    unique = len(tp) - 1  # ultimo ponto repete o primeiro
    lap_length_m = geometry.lap_length_m

    # Perimetro normalizado, para relacionar metros reais a unidades xy.
    perimeter_xy = 0.0
    for i in range(unique):
        dx = tp[i + 1].x_normalized - tp[i].x_normalized
        dy = tp[i + 1].y_normalized - tp[i].y_normalized
        perimeter_xy += (dx * dx + dy * dy) ** 0.5
    xy_per_metre = perimeter_xy / lap_length_m if lap_length_m else 0.0

    points: list[SpacePoint] = []
    for i in range(len(tp)):
        prev_i = (i - 1) % unique
        next_i = (i + 1) % unique if i < unique else 1 % unique
        tx = tp[next_i].x_normalized - tp[prev_i].x_normalized
        ty = tp[next_i].y_normalized - tp[prev_i].y_normalized
        length = (tx * tx + ty * ty) ** 0.5 or 1.0
        tx, ty = tx / length, ty / length
        # Normal para a esquerda do sentido de corrida: gira a tangente 90 graus.
        nx, ny = -ty, tx
        points.append(
            SpacePoint(
                distance_m=tp[i].cumulative_distance_m,
                cx=tp[i].x_normalized,
                cy=tp[i].y_normalized,
                nx=nx,
                ny=ny,
            )
        )
    return TrackSpace(tuple(points), lap_length_m, width_m, xy_per_metre, geometry)


@dataclass(slots=True)
class CarSpaceState:
    """Estado espacial mutavel de um carro no motor 2D (fatia 1).

    ``distance_m`` e a posicao longitudinal acumulada (pode exceder o
    comprimento da volta; a volta e ``distance_m // lap_length``).
    ``lateral_m`` e o deslocamento do centro da pista, positivo para a esquerda,
    limitado por ``LateralBounds.usable_m``. ``speed_ms`` e a velocidade escalar
    ao longo do traçado. As fatias seguintes acrescentam exclusao, disputa e
    colisao sobre este estado.
    """

    driver_id: str
    distance_m: float = 0.0
    lateral_m: float = 0.0
    speed_ms: float = 0.0
    length_m: float = ASSUMED_CAR_LENGTH_M
    width_m: float = ASSUMED_CAR_WIDTH_M
    #: Faixa lateral que o carro procura ocupar. A ultrapassagem move este alvo;
    #: ``lateral_m`` caminha ate ele, limitado por ``ASSUMED_LANE_CHANGE_MS``.
    target_lateral_m: float = 0.0
    #: ``driver_id`` do carro que esta sendo ultrapassado agora. Enquanto nao
    #: nulo, o atacante mantem a faixa de ataque ate completar a passagem, em vez
    #: de reavaliar do zero e oscilar ao lado do adversario.
    overtaking: str | None = None
    #: ``True`` quando o carro abandonou por contato; para de andar e deixa de
    #: bloquear ou disputar.
    retired: bool = False
    retired_time_s: float | None = None
    #: Fator (<=1 tipico) aplicado ao teto de velocidade neste trecho. E o gancho
    #: por onde pneu, combustivel e clima reduzem o ritmo do carro no motor 2D,
    #: atualizado volta a volta por quem orquestra a corrida. 1.0 e neutro.
    speed_scale: float = 1.0
    #: Pedido ainda em pista e estado no caminho aberto dos boxes. A distância
    #: classificatória continua em ``distance_m``; não é a extensão do atalho.
    pit_request: PitStopRequest | None = None
    pit_state: PitLaneState | None = None
    #: Estado de recursos emitido nos snapshots; atualizado pelo domínio a
    #: cada movimento, inclusive serviço/fila dos boxes.
    fuel_kg: float | None = None
    tyre_wear_laps: float | None = None
    #: Dano fisico acumulado [0,1], separado de pneu, combustivel e margem de seguranca.
    contact_damage: float = 0.0

    def clamp_lateral(self, bounds: LateralBounds) -> None:
        """Mantenha o carro dentro da pista, sem estourar a borda."""

        limit = bounds.usable_m
        self.lateral_m = max(-limit, min(limit, self.lateral_m))
        self.target_lateral_m = max(-limit, min(limit, self.target_lateral_m))


@dataclass(frozen=True, slots=True)
class MotionSample:
    """Estado de um carro num instante da integracao sub-volta."""

    time_s: float
    distance_m: float
    speed_ms: float


def _ceiling_at(cum: list[float], ceiling: list[float], distance_m: float) -> float:
    """Velocidade-teto interpolada numa distancia dentro da volta."""

    lap_length = cum[-1]
    d = distance_m % lap_length if lap_length else 0.0
    i = max(1, min(bisect_right(cum, d), len(cum) - 1))
    d0, d1 = cum[i - 1], cum[i]
    f = (d - d0) / (d1 - d0) if d1 > d0 else 0.0
    return ceiling[i - 1] + (ceiling[i] - ceiling[i - 1]) * f


def integrate_single_car(
    geometry: TrackGeometry,
    physics: CarPhysics = DEFAULT_CAR_PHYSICS,
    *,
    dt_s: float = ASSUMED_TIME_STEP_S,
    initial_speed_ms: float | None = None,
    max_steps: int = 1_000_000,
) -> tuple[MotionSample, ...]:
    """Integre uma volta de um carro por passos de tempo (fatia 2 do ADR 0011).

    A cada passo o carro ajusta a velocidade em direcao ao teto da curvatura,
    limitado pela tracao e pela freada que o envelope permite naquela
    velocidade (``accel_limit_ms2``/``brake_limit_ms2``), e avanca
    ``speed * dt`` metros. Para quando
    completa uma volta (``distance_m >= lap_length``). O tempo de volta emerge da
    soma dos passos; com ``dt`` pequeno, aproxima o ``steady_lap`` por distancia
    do ADR 0010. Um unico carro, sem lateral nem disputa: essas entram nas
    fatias seguintes.
    """

    if dt_s <= 0:
        raise ValueError("dt_s deve ser positivo")
    cum, ceiling = speed_ceiling(geometry, physics)
    lap_length = cum[-1]

    # Velocidade inicial de regime: o teto no ponto de partida evita largada
    # parada e aproxima o giro continuo de ``steady_lap``.
    speed = ceiling[0] if initial_speed_ms is None else max(0.0, initial_speed_ms)
    distance = 0.0
    time_s = 0.0
    samples = [MotionSample(time_s, distance, speed)]
    steps = 0
    while distance < lap_length and steps < max_steps:
        target = _ceiling_at(cum, ceiling, distance)
        if speed < target:
            speed = min(target, speed + physics.accel_limit_ms2(speed) * dt_s)
        elif speed > target:
            speed = max(target, speed - physics.brake_limit_ms2(speed) * dt_s)
        distance += speed * dt_s
        time_s += dt_s
        samples.append(MotionSample(time_s, distance, speed))
        steps += 1
    return tuple(samples)


def lap_time_ms_2d(samples: tuple[MotionSample, ...], lap_length_m: float) -> float:
    """Tempo de volta (ms) interpolado no instante em que cruza ``lap_length_m``.

    Interpola no ultimo passo para nao herdar o erro de ter ultrapassado a linha
    dentro de ``dt``; e a comparacao justa com o tempo por distancia do ADR 0010.
    """

    if len(samples) < 2:
        return 0.0
    before, after = samples[-2], samples[-1]
    span = after.distance_m - before.distance_m
    if span <= 0:
        return after.time_s * 1000.0
    f = (lap_length_m - before.distance_m) / span
    f = max(0.0, min(1.0, f))
    return (before.time_s + (after.time_s - before.time_s) * f) * 1000.0


@dataclass(frozen=True, slots=True)
class FieldSample:
    """Retrato de todos os carros num instante da integracao multi-carro."""

    time_s: float
    cars: tuple[CarSpaceState, ...]


@dataclass(frozen=True, slots=True)
class MotionIncrement:
    """Movimento efetivo de um subpasso, antes de serviço ou fim de volta.

    ``distance_m`` é extensão física, distinta do progresso classificatório
    nos boxes. A velocidade média usa essa distância/tempo; o esforço
    longitudinal vem da mudança de velocidade, não do teto desejado.
    """

    start_distance_m: float
    distance_m: float
    dt_s: float
    speed_ms: float
    acceleration_ms2: float
    time_s: float
    in_pit: bool


def _notify_motion(
    car: CarSpaceState,
    callback: Callable[[CarSpaceState, MotionIncrement], None] | None,
    start_distance: float,
    start_speed: float,
    dt_s: float,
    time_s: float,
    physical_distance: float | None = None,
    in_pit: bool = False,
) -> None:
    if callback is None or dt_s <= 1e-10:
        return
    distance = (
        max(0.0, car.distance_m - start_distance)
        if physical_distance is None
        else physical_distance
    )
    callback(
        car,
        MotionIncrement(
            start_distance,
            distance,
            dt_s,
            distance / dt_s,
            0.0 if in_pit else (car.speed_ms - start_speed) / dt_s,
            time_s,
            in_pit,
        ),
    )


def _same_lane(a: CarSpaceState, b: CarSpaceState) -> bool:
    """Duas faixas se sobrepoem se os corpos se cruzam lateralmente."""

    return (
        a.pit_state is None
        and b.pit_state is None
        and abs(a.lateral_m - b.lateral_m) < (a.width_m + b.width_m) / 2.0
    )


def _advance_pit_lane(
    car: CarSpaceState,
    cars: list[CarSpaceState],
    path: PitLanePath,
    parameters: PitLaneParameters,
    dt_s: float,
    time_s: float,
    on_event,
    race_distance_m: float,
    on_motion=None,
) -> None:
    """Consuma movimento e serviço sem custo temporal adicional por volta.

    Carros em boxes fazem fila no mesmo caminho. Na saída, aguardam uma folga
    na pista principal (inclusive de retardatários) antes de se reinserir.
    A espera e o serviço mantêm a distância de corrida constante.
    """

    assert car.pit_request is not None and car.pit_state is not None
    request = car.pit_request
    remaining = dt_s

    def event(name: str) -> None:
        if on_event is not None:
            on_event(car, name, time_s - remaining)

    while remaining > 1e-10:
        state = car.pit_state
        assert state is not None
        if (
            not state.serviced
            and state.path_distance_m >= path.service_distance_m - 1e-9
        ):
            if state.service_remaining_s == 0:
                state = replace(state, service_remaining_s=request.service_time_s)
                car.pit_state = state
                car.speed_ms = 0.0
                event("service_started")
                # O callback pode ampliar o serviço para o abastecimento.
                state = car.pit_state
                assert state is not None
            used = min(remaining, state.service_remaining_s)
            remaining -= used
            car.speed_ms = 0.0
            car.pit_state = replace(
                state, service_remaining_s=state.service_remaining_s - used
            )
            _notify_motion(
                car,
                on_motion,
                car.distance_m,
                0.0,
                used,
                time_s - remaining,
                physical_distance=0.0,
                in_pit=True,
            )
            if car.retired:
                return
            if car.pit_state.service_remaining_s <= 1e-9:
                car.pit_state = replace(
                    car.pit_state, serviced=True, service_remaining_s=0.0
                )
                event("service_completed")
            continue

        if state.path_distance_m >= path.length_m - 1e-9:
            exit_at = path.race_distance(request.entry_distance_m, path.length_m)
            blocked = any(
                other is not car
                and not other.retired
                and other.pit_state is None
                and other.distance_m < race_distance_m
                and abs(
                    (other.distance_m - exit_at + path.lap_length_m / 2)
                    % path.lap_length_m
                    - path.lap_length_m / 2
                )
                < (car.length_m + other.length_m) / 2 + parameters.merge_gap_m
                for other in cars
            )
            car.speed_ms = 0.0 if blocked else parameters.speed_limit_kmh / 3.6
            _notify_motion(
                car,
                on_motion,
                car.distance_m,
                0.0,
                remaining,
                time_s,
                physical_distance=0.0,
                in_pit=True,
            )
            if car.retired:
                return
            if not blocked:
                car.pit_state = None
                car.pit_request = None
                car.lateral_m = car.target_lateral_m = 0.0
                event("exit")
            break

        target = path.length_m if state.serviced else path.service_distance_m
        for other in cars:
            if other is car or other.retired or other.pit_state is None:
                continue
            ahead = other.pit_state.path_distance_m
            if ahead > state.path_distance_m:
                target = min(target, ahead - (car.length_m + other.length_m) / 2)
        step = max(
            0.0,
            min(
                target - state.path_distance_m,
                remaining * parameters.speed_limit_kmh / 3.6,
            ),
        )
        if step <= 1e-10:
            car.speed_ms = 0.0
            _notify_motion(
                car,
                on_motion,
                car.distance_m,
                0.0,
                remaining,
                time_s,
                physical_distance=0.0,
                in_pit=True,
            )
            break
        elapsed = step / (parameters.speed_limit_kmh / 3.6)
        remaining -= elapsed
        start_distance = car.distance_m
        car.speed_ms = parameters.speed_limit_kmh / 3.6
        car.pit_state = replace(state, path_distance_m=state.path_distance_m + step)
        car.distance_m = path.race_distance(
            request.entry_distance_m, car.pit_state.path_distance_m
        )
        _notify_motion(
            car,
            on_motion,
            start_distance,
            car.speed_ms,
            elapsed,
            time_s - remaining,
            physical_distance=step,
            in_pit=True,
        )
        if car.retired:
            return


def integrate_field(
    cars: list[CarSpaceState],
    track: TrackSpace,
    physics_by_id: dict[str, CarPhysics],
    *,
    total_laps: int,
    dt_s: float = ASSUMED_TIME_STEP_S,
    aggression_by_id: dict[str, float] | None = None,
    rng: RandomSource | None = None,
    on_lap_complete=None,
    neutralized_lap=None,
    standing_start: bool = False,
    pit_lane: PitLanePath | None = None,
    pit_parameters: PitLaneParameters = PitLaneParameters(),
    on_pit_event=None,
    on_motion=None,
    check_cancelled=None,
    contact_events: list[dict] | None = None,
    max_steps: int = 10_000_000,
) -> tuple[FieldSample, ...]:
    """Avance varios carros por passos de tempo, com ultrapassagem e colisao (fatia 5).

    ``check_cancelled``, quando fornecido, e chamado a cada passo e pode
    interromper o calculo por excecao; o integrador nao conhece transporte ou
    persistencia e nao devolve uma corrida parcial como resultado completo.

    A cada passo, um carro preso atras de outro mais lento na sua faixa tenta se
    deslocar para um lado livre e passar; a passagem acontece pela posicao, nao
    por sorteio. ``aggression_by_id`` (1.0 neutro) antecipa e alarga a tentativa:
    um carro mais agressivo busca o espaco mais cedo. Carro livre retorna suave
    ao centro.

    Contatos exigem encontro dos corpos projetados. Cada episodio e avaliado
    uma vez pela velocidade relativa: toque leve nao causa abandono. A margem
    lateral pertence ao planejamento, nao ao sorteio de acidentes. ``rng``
    controla a consequencia de impactos, nunca a existencia geometrica deles.

    ``neutralized_lap(lap)`` (ADR 0011, controle de prova) informa se a volta em
    curso esta sob neutralizacao (SC/VSC/vermelha). Em volta neutralizada nao ha
    disputa por faixa nem sorteio de colisao: os carros seguem a fila no ritmo
    reduzido que o orquestrador impoe via ``speed_scale``, como numa corrida
    real atras do Safety Car. ``None`` preserva o comportamento sem controle de
    prova. A volta de cada carro e a sua propria (``distance_m // lap_length``),
    o que mantem o gancho local ao carro.

    ``standing_start`` (ADR 0011) faz o pelotao largar parado: cada carro parte
    de ``speed_ms=0`` e acelera pela propria fisica, como um grid real. O default
    ``False`` preserva a largada de regime do ADR 0010 (inicia no teto do ponto
    de partida), usada por ``integrate_single_car`` e pelos testes das fatias.

    Com ``pit_lane``, um ``pit_request`` reserva a entrada absoluta do carro.
    Os boxes têm movimento separado, fila, serviço e reinserção por folga. O
    callback ``on_pit_event(car, tipo, time_s)`` informa os instantes de entrada,
    início/fim de serviço e saída; ele permite aplicar pneus sem usar a janela.
    """

    if dt_s <= 0:
        raise ValueError("dt_s deve ser positivo")
    if total_laps < 1:
        raise ValueError("total_laps deve ser positivo")
    aggression_by_id = aggression_by_id or {}

    ceilings: dict[str, tuple[list[float], list[float]]] = {}
    for car in cars:
        physics = physics_by_id[car.driver_id]
        ceilings[car.driver_id] = speed_ceiling(track.geometry, physics)
        car.clamp_lateral(track.bounds)
        # Largada parada (opt-in): o carro parte de zero e acelera pela propria
        # fisica, como um grid real. Sem ela, mantem-se a largada de regime do
        # ADR 0010, que inicia no teto do ponto de partida para o tempo de volta
        # emergir de um giro continuo comparavel ao ``steady_lap``.
        if not standing_start and car.speed_ms == 0.0 and car.pit_state is None:
            car.speed_ms = ceilings[car.driver_id][1][0]

    race_distance = total_laps * track.lap_length_m
    lap_length = track.lap_length_m
    usable = track.bounds.usable_m
    by_id = {c.driver_id: c for c in cars}
    laps_done = {c.driver_id: 0 for c in cars}
    # Ordem estavel por ``driver_id`` para o retrato (``FieldSample``) e para a
    # montagem do ``plan_by_id``. Nao e a ordem de PROCESSAMENTO do passo, que e
    # por posicao (ver o laco abaixo).
    order = sorted(cars, key=lambda c: c.driver_id)
    # Fisica e teto por carro nao mudam: resolve-se o lookup uma vez, nao a cada
    # um dos milhoes de passos. A ORDEM de processamento, porem, e por posicao
    # (frente para tras) dentro do laco -- ver abaixo.
    plan_by_id = {
        car.driver_id: (physics_by_id[car.driver_id], *ceilings[car.driver_id])
        for car in order
    }
    # Passo lateral maximo por iteracao: invariante no laco (constantes).
    max_step_lat = ASSUMED_LANE_CHANGE_MS * dt_s
    samples = [FieldSample(0.0, tuple(_frozen(c) for c in order))]
    time_s = 0.0
    steps = 0
    contact_tracker = ContactTracker()
    while steps < max_steps and any(
        c.distance_m < race_distance and not c.retired for c in cars
    ):
        if check_cancelled is not None:
            check_cancelled()
        time_s += dt_s
        previous = {c.driver_id: _frozen(c) for c in cars}
        # Projecoes dos vizinhos sao compartilhadas pelo passo e atualizadas
        # depois de cada movimento, evitando uma nova busca por par de carros.
        projected_poses = {c.driver_id: _projected_rectangle(track, c, c.distance_m)
                           for c in cars if c.pit_state is None and not c.retired}
        by_distance = sorted((c for c in cars if c.pit_state is None), key=lambda c: c.distance_m)
        # Ordem fisica no anel, da frente para tras, inclusive em dobragens:
        # cada seguidor reage a posicao ja atualizada do carro a sua frente.
        for car in _front_to_back(cars, lap_length, race_distance):
            if car.retired or car.distance_m >= race_distance:
                continue
            physics, cum, ceiling = plan_by_id[car.driver_id]
            if car.pit_state is not None:
                assert pit_lane is not None
                _advance_pit_lane(
                    car,
                    cars,
                    pit_lane,
                    pit_parameters,
                    dt_s,
                    time_s,
                    on_pit_event,
                    race_distance, on_motion,
                )
                completed = int(car.distance_m // lap_length)
                if not car.retired and on_lap_complete is not None and completed > laps_done[car.driver_id]:
                    laps_done[car.driver_id] = completed
                    if completed <= total_laps:
                        on_lap_complete(car, completed)
                if car.pit_state is None:
                    projected_poses[car.driver_id] = _projected_rectangle(track, car, car.distance_m)
                continue
            start_distance, start_speed = car.distance_m, car.speed_ms
            start_lateral = car.lateral_m
            car_lap = int(car.distance_m // lap_length) + 1
            neutralized = neutralized_lap is not None and neutralized_lap(car_lap)

            # (1) decisao de faixa: tenta passar quem segura, senao volta ao centro.
            # Sob neutralizacao a fila se mantem: o carro converge ao centro e
            # nao busca ultrapassagem, como atras do Safety Car.
            if neutralized:
                car.overtaking = None
                car.target_lateral_m = 0.0
            else:
                car.target_lateral_m = _lane_decision(
                    car,
                    by_id,
                    by_distance,
                    ceilings,
                    race_distance,
                    usable,
                    aggression_by_id.get(car.driver_id, 1.0),
                    lap_length,
                )
            # (2) move a lateral em direcao ao alvo, limitada pela velocidade
            # lateral (``max_step_lat`` e invariante, calculado antes do laco).
            delta = car.target_lateral_m - car.lateral_m
            lateral = car.lateral_m + max(-max_step_lat, min(max_step_lat, delta))
            if lateral != car.lateral_m:
                car.lateral_m = _limit_lateral_move(
                    car, lateral, by_distance, race_distance, lap_length
                )
            car.clamp_lateral(track.bounds)

            # (3) velocidade longitudinal: acelera/freia em direcao ao teto.
            # O teto e reduzido por ``speed_scale`` (pneu, combustivel, clima).
            # Os limites dependem da velocidade (downforce), como no ADR 0015.
            target = (_ceiling_at(cum, ceiling, car.distance_m) * car.speed_scale
                      * (1.0 - ASSUMED_CONTACT.maximum_speed_loss * car.contact_damage))
            speed = car.speed_ms
            if speed < target:
                car.speed_ms = min(target, speed + physics.accel_limit_ms2(speed) * dt_s)
            elif speed > target:
                car.speed_ms = max(target, speed - physics.brake_limit_ms2(speed) * dt_s)

            # (4) avanco com exclusao: usa a faixa lateral JA atualizada, entao
            # um carro que saiu da esteira do da frente deixa de ser bloqueado.
            proposed = car.distance_m + car.speed_ms * dt_s
            ahead = _nearest_ahead_same_lane(car, by_distance, race_distance, lap_length)
            if ahead is not None:
                gap = _forward_gap(car.distance_m, ahead.distance_m, lap_length)
                limit = car.distance_m + gap - (ahead.length_m + car.length_m) / 2.0
                if proposed > limit:
                    proposed = max(car.distance_m, limit)
                    car.speed_ms = min(car.speed_ms, ahead.speed_ms)
            # O planejamento considera faixas; a ultima barreira usa os mesmos
            # corpos projetados em qualquer direcao, inclusive durante a troca.
            proposed, lateral, _ = _limit_projected_motion(
                track, car, start_distance, start_lateral, proposed,
                car.lateral_m, cars, race_distance,
                pose_cache=projected_poses,
            )
            car.lateral_m = lateral
            if proposed < start_distance + car.speed_ms * dt_s - 1e-7:
                car.speed_ms = min(car.speed_ms, max(0.0, (proposed-start_distance)/dt_s))
            request = car.pit_request
            if request is not None and proposed >= request.entry_distance_m:
                if pit_lane is None:
                    raise ValueError("pedido de parada sem geometria de pit lane")
                # A entrada também faz fila: dois pedidos no mesmo passo não
                # podem criar dois carros na mesma posição do caminho aberto.
                entry_blocked = any(
                    other is not car
                    and not other.retired
                    and other.pit_state is not None
                    and other.pit_state.path_distance_m
                    < (car.length_m + other.length_m) / 2
                    for other in cars
                )
                if entry_blocked:
                    car.distance_m = max(
                        car.distance_m, request.entry_distance_m - 1e-6
                    )
                    car.speed_ms = 0.0
                    _notify_motion(car, on_motion, start_distance, start_speed, dt_s, time_s)
                    continue
                travel_s = max(
                    0.0,
                    (request.entry_distance_m - car.distance_m)
                    / max(car.speed_ms, 1e-9),
                )
                car.distance_m = request.entry_distance_m
                _notify_motion(
                    car,
                    on_motion,
                    start_distance,
                    start_speed,
                    travel_s,
                    time_s - dt_s + travel_s,
                )
                if car.retired:
                    continue
                car.lateral_m = car.target_lateral_m = 0.0
                car.overtaking = None
                car.pit_state = PitLaneState()
                car.speed_ms = min(car.speed_ms, pit_parameters.speed_limit_kmh / 3.6)
                if on_pit_event is not None:
                    on_pit_event(car, "entry", time_s - dt_s + travel_s)
                _advance_pit_lane(
                    car,
                    cars,
                    pit_lane,
                    pit_parameters,
                    max(0.0, dt_s - travel_s),
                    time_s,
                    on_pit_event,
                    race_distance, on_motion,
                )
            else:
                car.distance_m = proposed
                _notify_motion(car, on_motion, start_distance, start_speed, dt_s, time_s)

            if car.pit_state is None:
                projected_poses[car.driver_id] = _projected_rectangle(track, car, car.distance_m)

            # Volta concluida: avisa o orquestrador (pneu, combustivel, clima
            # atualizam ``speed_scale`` do carro para a proxima volta).
            completed = int(car.distance_m // lap_length)
            if not car.retired and on_lap_complete is not None and completed > laps_done[car.driver_id]:
                laps_done[car.driver_id] = completed
                if completed <= total_laps:
                    on_lap_complete(car, completed)

        # (5) colisao: pares lado a lado com corpos rocando podem se tocar.
        # Sob neutralizacao nao ha contato de disputa: o pelotao anda em fila.
        # Na zona de largada parada tambem nao: o grid parte emparelhado e lento,
        # e os carros se tocariam ao se desenrolar, gerando abandonos irreais.
        # A supressao e por par (dentro de ``_resolve_collisions``): vale
        # enquanto QUALQUER dos dois ainda esta na zona, para um retardatario
        # agrupado nao colidir so porque o lider ja saiu dela.
        field_neutralized = neutralized_lap is not None and any(
            neutralized_lap(int(c.distance_m // lap_length) + 1)
            for c in cars
            if not c.retired and c.distance_m < race_distance
        )
        start_zone_m = ASSUMED_START_ZONE_M if standing_start else 0.0
        if not field_neutralized:
            _resolve_collisions(
                cars, race_distance, aggression_by_id, rng, dt_s, start_zone_m,
                lap_length, track=track, previous=previous, tracker=contact_tracker,
                events=contact_events, time_s=time_s,
            )
        else:
            contact_tracker.active.clear()

        samples.append(FieldSample(time_s, tuple(_frozen(c) for c in order)))
        steps += 1
    return tuple(samples)


def _forward_gap(origin: float, destination: float, lap_length_m: float) -> float:
    """Distancia para a frente no anel, sem alterar o progresso da corrida."""

    return (destination - origin) % lap_length_m


def _limit_projected_motion(track, car, start_distance, start_lateral,
                            proposed_distance, proposed_lateral, cars, race_distance_m,
                            *, pose_cache=None):
    """Percorra o movimento e limite a primeira entrada em outro corpo.

    A exclusao consulta XY e retangulos orientados, preservando o eixo
    classificatorio original. Subpassos de no maximo meia largura reduzem
    atravessamentos entre extremos livres. Estados inicialmente invalidos nao
    sao reparados por salto; sao tratados pelo detector de contato.
    """
    probe = replace(car, distance_m=start_distance, lateral_m=start_lateral)
    start_pose = _projected_rectangle(track, probe, start_distance)
    travel = abs(proposed_distance-start_distance) + abs(proposed_lateral-start_lateral)
    reach = travel * 2 + hypot(car.length_m, car.width_m)
    neighbors = []
    rear_neighbors = []
    for other in cars:
        if (other is car or other.retired or other.pit_state is not None
                or other.distance_m >= race_distance_m):
            continue
        pose = (pose_cache.get(other.driver_id) if pose_cache is not None else None)
        if pose is None:
            pose = _projected_rectangle(track, other, other.distance_m)
        if hypot(pose[0]-start_pose[0], pose[1]-start_pose[1]) > reach + other.length_m:
            continue
        if _rectangles_overlap(probe, start_pose, other, pose):
            continue
        if _signed_gap(start_distance, other.distance_m, track.lap_length_m) < 0:
            rear_neighbors.append((other, pose))
            continue
        neighbors.append((other, pose))
    # Um carro traseiro restringe a troca lateral, nao o avanco do lider. O
    # seguidor reagira ao lider atualizado ao ser processado neste passo.
    # Misturar as duas restricoes cria espera circular em curvas apertadas.
    rear_touched = set()
    if rear_neighbors and proposed_lateral != start_lateral:
        def rear_hits(fraction):
            probe.lateral_m = start_lateral + (proposed_lateral-start_lateral)*fraction
            pose = _projected_rectangle(track, probe, start_distance)
            return {other.driver_id for other, other_pose in rear_neighbors
                    if _rectangles_overlap(probe, pose, other, other_pose)}

        lateral_steps = max(1, ceil(abs(proposed_lateral-start_lateral)/max(.25, car.width_m/2)))
        last_clear = 0.0
        for index in range(1, lateral_steps+1):
            fraction = index/lateral_steps
            rear_touched = rear_hits(fraction)
            if rear_touched:
                lo, hi = last_clear, fraction
                for _ in range(16):
                    mid = (lo+hi)/2
                    if rear_hits(mid):
                        hi = mid
                    else:
                        lo = mid
                proposed_lateral = start_lateral + (proposed_lateral-start_lateral)*lo
                break
            last_clear = fraction
    if not neighbors:
        return proposed_distance, proposed_lateral, rear_touched

    def hits(fraction, lateral_target):
        probe.lateral_m = start_lateral + (lateral_target-start_lateral)*fraction
        distance = start_distance + (proposed_distance-start_distance)*fraction
        pose = _projected_rectangle(track, probe, distance)
        return {other.driver_id for other, other_pose in neighbors
                if _rectangles_overlap(probe, pose, other, other_pose)}

    steps = max(1, ceil(travel / max(0.25, car.width_m / 2)))
    last = 0.0
    for index in range(1, steps+1):
        fraction = index/steps
        touched = hits(fraction, proposed_lateral)
        if touched:
            # Bloqueio lateral permite continuar na faixa atual quando o
            # percurso longitudinal esta livre; evita parar toda a fila.
            if proposed_lateral != start_lateral and all(
                not hits(k/steps, start_lateral) for k in range(1, steps+1)
            ):
                return proposed_distance, start_lateral, touched
            lo, hi = last, fraction
            for _ in range(16):
                mid = (lo+hi)/2
                if hits(mid, proposed_lateral):
                    hi = mid
                else:
                    lo = mid
            return (start_distance+(proposed_distance-start_distance)*lo,
                    start_lateral+(proposed_lateral-start_lateral)*lo, touched)
        last = fraction
    return proposed_distance, proposed_lateral, set()


def _projected_rectangle(
    track: TrackSpace, car: CarSpaceState, distance_m: float
) -> tuple[float, float, float, float]:
    """Centro em metros e normal unitaria, como na projecao do frontend.

    A distancia de corrida permanece no eixo original: so a consulta espacial
    usa a escala media XY. Normalizar a normal interpolada corresponde ao
    desenho dos corpos; a geometria e a calibracao nao sao reparametrizadas.
    """
    d = distance_m % track.lap_length_m
    points = track.points
    lo, hi = 0, len(points) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if points[mid].distance_m < d:
            lo = mid + 1
        else:
            hi = mid
    a, b = points[max(1, lo) - 1], points[max(1, lo)]
    span = b.distance_m - a.distance_m
    f = (d - a.distance_m) / span if span > 0 else 0.0
    nx = a.nx + (b.nx - a.nx) * f
    ny = a.ny + (b.ny - a.ny) * f
    length = hypot(nx, ny)
    if length <= 1e-12:
        nx, ny = a.nx, a.ny
    else:
        nx, ny = nx / length, ny / length
    return (
        (a.cx + (b.cx - a.cx) * f) / track.xy_per_metre + nx * car.lateral_m,
        (a.cy + (b.cy - a.cy) * f) / track.xy_per_metre + ny * car.lateral_m,
        nx,
        ny,
    )


def _rectangles_overlap(
    a: CarSpaceState, pose_a: tuple[float, float, float, float],
    b: CarSpaceState, pose_b: tuple[float, float, float, float],
) -> bool:
    """Intersecao estrita de retangulos orientados; tangencia e permitida."""
    x, y, nx, ny = pose_a
    bx, by, mx, my = pose_b
    dx, dy = bx - x, by - y
    for ax, ay in ((nx, ny), (-ny, nx), (mx, my), (-my, mx)):
        radius_a = (abs(ax * nx + ay * ny) * a.width_m / 2
                    + abs(-ax * ny + ay * nx) * a.length_m / 2)
        radius_b = (abs(ax * mx + ay * my) * b.width_m / 2
                    + abs(-ax * my + ay * mx) * b.length_m / 2)
        if abs(dx * ax + dy * ay) >= radius_a + radius_b - 1e-9:
            return False
    return True


def _limit_projected_advance(
    track: TrackSpace, car: CarSpaceState, ahead: CarSpaceState, proposed: float
) -> float:
    """Limite sobreposicao final com o proximo carro da mesma faixa.

    Busca um limite entre o estado atual livre e a posicao proposta
    sobreposta, supondo uma unica transicao nesse intervalo. Estados ja sobrepostos nao sao corrigidos por teletransporte.
    Este recorte nao detecta atravessamentos entre extremos livres, nem
    substitui a regra de contato ou a exclusao lateral.
    """
    if track.xy_per_metre <= 0:
        return proposed
    ahead_pose = _projected_rectangle(track, ahead, ahead.distance_m)
    end_pose = _projected_rectangle(track, car, proposed)
    # Círculos envolventes evitam SAT e busca binaria para carros distantes.
    reach = (hypot(car.length_m, car.width_m)
             + hypot(ahead.length_m, ahead.width_m)) / 2
    if hypot(end_pose[0] - ahead_pose[0], end_pose[1] - ahead_pose[1]) >= reach:
        return proposed
    if not _rectangles_overlap(car, end_pose, ahead, ahead_pose):
        return proposed
    if _rectangles_overlap(car, _projected_rectangle(track, car, car.distance_m),
                           ahead, ahead_pose):
        return proposed
    lo, hi = car.distance_m, proposed
    # A extremidade livre e conservada; a precisao e de cerca de 5 mm para
    # um avanco de 20 m, sem custo de dezenas de projecoes por contato.
    for _ in range(12):
        mid = (lo + hi) / 2
        if _rectangles_overlap(car, _projected_rectangle(track, car, mid),
                               ahead, ahead_pose):
            hi = mid
        else:
            lo = mid
    return lo


def _signed_gap(origin: float, destination: float, lap_length_m: float) -> float:
    """Separacao local assinada; uma volta inteira nao separa corpos na pista."""

    return (destination - origin + lap_length_m / 2) % lap_length_m - lap_length_m / 2


def _front_to_back(
    cars: list[CarSpaceState], lap_length_m: float, race_distance_m: float
) -> list[CarSpaceState]:
    """Corte o anel na maior folga e processe cada pelotao da frente para tras.

    Isso faz um retardatario ser atualizado antes do carro que o alcanca, sem
    confundir posicao fisica com voltas completas. O corte deixa de assegurar
    essa ordem se o pelotao ocupar todo o anel; esse caso nao cabe neste modelo.
    Desempates por ID tornam a ordem independente da lista de entrada.
    """

    active = sorted(
        (c for c in cars if not c.retired and c.pit_state is None
         and c.distance_m < race_distance_m),
        key=lambda c: (c.distance_m % lap_length_m, c.driver_id),
    )
    if not active:
        return sorted(cars, key=lambda c: c.driver_id)
    gaps = [
        _forward_gap(active[i].distance_m, active[(i + 1) % len(active)].distance_m,
                     lap_length_m)
        for i in range(len(active))
    ]
    cut = max(range(len(active)), key=gaps.__getitem__)
    ordered = list(reversed(active[cut + 1:] + active[:cut + 1]))
    active_ids = {id(c) for c in active}
    ordered.extend(sorted((c for c in cars if id(c) not in active_ids),
                          key=lambda c: c.driver_id))
    return ordered


def _limit_lateral_move(
    car: CarSpaceState,
    lateral: float,
    cars: list[CarSpaceState],
    race_distance_m: float,
    lap_length_m: float,
) -> float:
    """Nao atravesse lateralmente um corpo ja emparelhado no anel.

    Estados iniciais ja sobrepostos nao sao reparados por teletransporte: o
    bloqueio se aplica aos pares que iniciam o movimento com folga valida.
    """

    for other in cars:
        if (other is car or other.retired or other.pit_state is not None
                or other.distance_m >= race_distance_m):
            continue
        if abs(_signed_gap(car.distance_m, other.distance_m, lap_length_m)) >= (
            car.length_m + other.length_m
        ) / 2:
            continue
        width = (car.width_m + other.width_m) / 2
        # Arredondamento em ponto flutuante nao deve trazer a folga de volta
        # para dentro do limiar estrito de rocamento.
        clearance = width + ASSUMED_RUBBING_MARGIN_M + 1e-9
        # Parar exatamente na largura dos corpos os prenderia dentro da zona
        # de rocamento e fabricaria sorteios de contato a cada passo. Preserve a
        # margem existente; se ja estiver nela, nao teletransporte o carro.
        if car.lateral_m <= other.lateral_m - width:
            lateral = min(lateral, max(car.lateral_m, other.lateral_m - clearance))
        elif car.lateral_m >= other.lateral_m + width:
            lateral = max(lateral, min(car.lateral_m, other.lateral_m + clearance))
    return lateral


def _side_by_side(a: CarSpaceState, b: CarSpaceState, lap_length_m: float | None = None) -> bool:
    """Se os dois carros se sobrepoem longitudinalmente (andam emparelhados)."""

    gap = (b.distance_m - a.distance_m if lap_length_m is None else
           _signed_gap(a.distance_m, b.distance_m, lap_length_m))
    # Subtrair distancias acumuladas grandes introduz erro de arredondamento:
    # dois carros em fila com exatos 5 m de intervalo nao estao lado a lado.
    return abs(gap) < (a.length_m + b.length_m) / 2.0 - 1e-7


def _rubbing(a: CarSpaceState, b: CarSpaceState, lap_length_m: float | None = None) -> bool:
    """Se os corpos quase se encostam lateralmente estando emparelhados."""

    lateral_clearance = abs(a.lateral_m - b.lateral_m) - (a.width_m + b.width_m) / 2.0
    return _side_by_side(a, b, lap_length_m) and lateral_clearance < ASSUMED_RUBBING_MARGIN_M


def _resolve_collisions(
    cars: list[CarSpaceState],
    race_distance_m: float,
    aggression_by_id: dict[str, float],
    rng: RandomSource | None,
    dt_s: float,
    start_zone_m: float = 0.0,
    lap_length_m: float | None = None,
    *,
    track: TrackSpace | None = None,
    previous: dict[str, CarSpaceState] | None = None,
    tracker: ContactTracker | None = None,
    events: list[dict] | None = None,
    time_s: float = 0.0,
) -> None:
    """Detecte corpos, registre o episodio e avalie sua consequencia uma vez.

    O motor sempre fornece ``track``. A projeção retilinea sem pista permite
    testes unitarios da regra, inclusive de pares separados por uma volta.
    A zona de largada preserva a supressao de acidentes preexistente.
    Tocar lentamente nao e o mesmo que sofrer um impacto de alta energia.
    """
    tracker = tracker if tracker is not None else ContactTracker()
    active = sorted(
        (c for c in cars if not c.retired and c.pit_state is None and c.distance_m < race_distance_m),
        key=lambda c: c.driver_id,
    )

    def pose(car, distance=None):
        distance = car.distance_m if distance is None else distance
        if track is not None:
            return _projected_rectangle(track, car, distance)
        return distance, car.lateral_m, 0.0, 1.0

    poses = {c.driver_id: pose(c) for c in active}
    nearby = set()
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            a, b = active[i], active[j]
            if a.retired or b.retired:
                continue
            if a.distance_m < start_zone_m or b.distance_m < start_zone_m:
                continue
            pa, pb = poses[a.driver_id], poses[b.driver_id]
            if track is None and lap_length_m is not None:
                pb = (pa[0] + _signed_gap(a.distance_m, b.distance_m, lap_length_m), *pb[1:])
            clearance = ASSUMED_CONTACT.episode_clearance_m
            if hypot(pa[0] - pb[0], pa[1] - pb[1]) > (
                hypot(a.length_m, a.width_m) + hypot(b.length_m, b.width_m)
            ) / 2 + clearance:
                continue
            pair = (a.driver_id, b.driver_id)
            if _rectangles_overlap(replace(a, length_m=a.length_m + clearance,
                                          width_m=a.width_m + clearance), pa,
                                   replace(b, length_m=b.length_m + clearance,
                                           width_m=b.width_m + clearance), pb):
                nearby.add(pair)
            if not _rectangles_overlap(a, pa, b, pb):
                continue
            episode = tracker.enter(pair)
            if episode is None:
                continue
            # Velocidade normal relativa no eixo de menor penetracao. A
            # velocidade absoluta ao redor da pista nao determina a gravidade.
            axes = ((pa[2], pa[3]), (-pa[3], pa[2]),
                    (pb[2], pb[3]), (-pb[3], pb[2]))
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            def penetration(axis):
                ax, ay = axis
                def radius(car, p):
                    return (abs(ax*p[2] + ay*p[3])*car.width_m
                            + abs(-ax*p[3] + ay*p[2])*car.length_m) / 2
                return radius(a, pa) + radius(b, pb) - abs(dx*ax + dy*ay)
            normal = min(axes, key=penetration)
            def velocity(car, p):
                old = previous.get(car.driver_id) if previous else None
                lateral_speed = ((car.lateral_m-old.lateral_m)/dt_s
                                 if old is not None and dt_s > 0 else 0.0)
                # A velocidade fisica ja vem do integrador. Diferenciar XY
                # novamente converteria as irregularidades da polilinha em
                # energia de impacto, duplicando distorcoes da geometria mockada.
                return (car.speed_ms*p[3] + lateral_speed*p[2],
                        -car.speed_ms*p[2] + lateral_speed*p[3])
            va, vb = velocity(a, pa), velocity(b, pb)
            orientation = 1.0 if dx*normal[0] + dy*normal[1] >= 0 else -1.0
            closing = max(0.0, ((va[0]-vb[0])*normal[0]
                                + (va[1]-vb[1])*normal[1])*orientation)
            if previous and a.driver_id in previous and b.driver_id in previous:
                old_a, old_b = previous[a.driver_id], previous[b.driver_id]
                if _rectangles_overlap(old_a, pose(old_a), old_b, pose(old_b)):
                    # Nao invente um novo impacto a partir de um estado que
                    # ja nasceu sobreposto; registre o toque para diagnostico.
                    closing = 0.0
            agg_a = aggression_by_id.get(a.driver_id, 1.0)
            agg_b = aggression_by_id.get(b.driver_id, 1.0)
            label = f"collision:{a.driver_id}:{b.driver_id}:episode:{episode}"
            consequence = contact_consequence(closing, (agg_a + agg_b)/2, rng, label)
            a.contact_damage = min(1.0, a.contact_damage + consequence.damage_fraction / 2)
            b.contact_damage = min(1.0, b.contact_damage + consequence.damage_fraction / 2)
            retired_ids = []
            if consequence.retires:
                total = agg_a + agg_b
                assert rng is not None
                victim = a if rng.uniform01(f"{label}:culprit") < (agg_a/total if total else 0.5) else b
                victim.retired = True
                victim.retired_time_s = time_s
                retired_ids.append(victim.driver_id)
            if events is not None:
                events.append({"time_ms": round(time_s*1000, 3), "driver_ids": list(pair),
                               "lap": max(1, int(min(a.distance_m,b.distance_m) / lap_length_m)+1)
                               if lap_length_m else 1,
                               "episode": episode, "kind": consequence.kind,
                               "detection": "overlap",
                               "closing_speed_ms": round(closing, 6),
                               "damage_fraction": consequence.damage_fraction,
                               "damage_by_driver": {a.driver_id: a.contact_damage,
                                                    b.driver_id: b.contact_damage},
                               "retired_driver_ids": retired_ids})
    tracker.retain(nearby)


def _lane_decision(
    car: CarSpaceState,
    by_id: dict[str, CarSpaceState],
    by_distance: list[CarSpaceState],
    ceilings: dict[str, tuple[list[float], list[float]]],
    race_distance_m: float,
    usable_m: float,
    aggression: float,
    lap_length_m: float,
) -> float:
    """Faixa lateral que o carro deve buscar neste passo.

    A manobra tem compromisso: uma vez iniciada (``car.overtaking``), o atacante
    mantem a faixa de ataque ate ficar na frente com folga, em vez de reavaliar
    do zero a cada passo -- o que o faria oscilar ao lado do adversario sem nunca
    passar. Sem bloqueio a frente e sem manobra ativa, converge ao centro.
    """

    # Manobra em andamento: segue atacando ate completar a passagem.
    if car.overtaking is not None:
        target = by_id.get(car.overtaking)
        clearance = (
            (car.length_m + target.length_m) / 2.0 if target is not None else 0.0
        )
        done = (
            target is None
            or target.pit_state is not None
            or target.distance_m >= race_distance_m
            or target.retired
            or _signed_gap(car.distance_m, target.distance_m, lap_length_m) <= -clearance
        )
        if done:
            car.overtaking = None
            return _safe_center(car, by_distance, race_distance_m, usable_m, lap_length_m)
        gap = _signed_gap(car.distance_m, target.distance_m, lap_length_m)
        my_free = _ceiling_at(*ceilings[car.driver_id], target.distance_m)*car.speed_scale
        target_free = _ceiling_at(*ceilings[target.driver_id], target.distance_m)*target.speed_scale
        # Uma oportunidade perdida nao e compromisso de perseguir o mesmo
        # carro pela volta inteira. Emparelhado, mantenha o espaco ate poder
        # retornar sem atravessar o outro corpo.
        if (gap > ASSUMED_PASS_ABORT_GAP_M
                or (gap > clearance and my_free <= target_free)):
            car.overtaking = None
            return _safe_center(car, by_distance, race_distance_m, usable_m, lap_length_m)
        side = 1.0 if car.lateral_m >= 0 else -1.0
        reach = car.width_m * (0.8 + 0.4 * aggression)
        candidate = max(-usable_m, min(usable_m, target.lateral_m + side * reach))
        # O compromisso existente nao revalida o corredor a cada passo.
        return candidate

    ahead = _nearest_ahead_same_lane(car, by_distance, race_distance_m, lap_length_m)
    if ahead is None:
        return _safe_center(car, by_distance, race_distance_m, usable_m, lap_length_m)
    gap = _forward_gap(car.distance_m, ahead.distance_m, lap_length_m)
    if gap > ASSUMED_FOLLOW_TRIGGER_M:
        return _safe_center(car, by_distance, race_distance_m, usable_m, lap_length_m)
    # O seguidor pode ter sido freado ate a velocidade do lider pela exclusao.
    # Seu teto efetivo em pista livre ainda revela se existe vantagem para passar.
    # Compare ambos na mesma posicao para nao criar vantagem apenas porque o
    # carro da frente ja chegou ao trecho mais lento de uma curva.
    my_ceiling = _ceiling_at(*ceilings[car.driver_id], ahead.distance_m) * car.speed_scale
    ahead_ceiling = _ceiling_at(*ceilings[ahead.driver_id], ahead.distance_m) * ahead.speed_scale
    if my_ceiling <= ahead_ceiling:
        # Tetos iguais nao revelam uma fila: o lider pode estar limitado por
        # outro carro. So trate isso como oportunidade quando o par da frente
        # estiver na folga minima longitudinal existente. Consultar o teto do
        # atacante na posicao do lider evita confundir aproximacao de curva com
        # diferenca de ritmo entre posicoes distintas. Nao infere outros motivos
        # para reducao de velocidade.
        obstruction = _nearest_ahead_same_lane(ahead, by_distance, race_distance_m, lap_length_m)
        minimum_gap = (ahead.length_m + obstruction.length_m) / 2 if obstruction else 0.0
        queued = (obstruction is not None
                  and _forward_gap(ahead.distance_m, obstruction.distance_m, lap_length_m)
                  <= minimum_gap + 1e-7)
        if not queued or my_ceiling <= ahead.speed_ms:
            return car.lateral_m

    reach = car.width_m * (0.8 + 0.4 * aggression)
    for side in (1.0, -1.0):
        candidate = max(-usable_m, min(usable_m, ahead.lateral_m + side * reach))
        if _side_is_clear(car, candidate, by_distance, race_distance_m, lap_length_m):
            # Compromete-se com a ultrapassagem deste carro.
            car.overtaking = ahead.driver_id
            return candidate
    return car.lateral_m


def _safe_center(
    car: CarSpaceState,
    by_distance: list[CarSpaceState],
    race_distance_m: float,
    usable_m: float,
    lap_length_m: float,
) -> float:
    """Alvo lateral mais proximo do centro sem invadir um carro emparelhado.

    Um carro livre tende ao centro (``0``), mas se outro carro esta emparelhado
    longitudinalmente entre ele e o centro, parar junto a esse carro em vez de
    atravessa-lo evita o contato irreal da largada (dois carros da mesma fileira
    indo ao centro ao mesmo tempo). Mantem o deslocamento atual quando o caminho
    ao centro nao esta livre.
    """

    min_gap = (car.width_m + ASSUMED_CAR_WIDTH_M) / 2.0 + ASSUMED_RUBBING_MARGIN_M
    target = 0.0
    for other in by_distance:
        if other.driver_id == car.driver_id or other.retired:
            continue
        if other.distance_m >= race_distance_m:
            continue
        if not _side_by_side(car, other, lap_length_m):
            continue
        # Outro carro entre a posicao atual e o centro, do lado do movimento.
        if car.lateral_m > 0 and other.lateral_m < car.lateral_m:
            target = max(target, other.lateral_m + min_gap)
        elif car.lateral_m < 0 and other.lateral_m > car.lateral_m:
            target = min(target, other.lateral_m - min_gap)
    # Nao ultrapassa a borda nem volta para longe do centro alem de onde esta.
    if car.lateral_m >= 0:
        target = max(0.0, min(car.lateral_m, min(usable_m, target)))
    else:
        target = min(0.0, max(car.lateral_m, max(-usable_m, target)))
    return target


def _side_is_clear(
    car: CarSpaceState,
    candidate_lateral_m: float,
    by_distance: list[CarSpaceState],
    race_distance_m: float,
    lap_length_m: float,
) -> bool:
    """Verifique a faixa e a chegada de carros traseiros a velocidade constante.

    O horizonte e o tempo necessario para atingir o alvo na velocidade lateral
    maxima ja assumida pelo motor. Durante esse tempo o carro percorre a lateral
    linearmente e os demais mantem lateral e velocidades longitudinais atuais.
    Nao e garantia contra aceleracoes, outras mudancas de faixa ou geometria
    cartesiana divergente do eixo; tambem conserva a janela estatica existente.
    Esta consulta ocorre na escolha inicial da passagem, nao durante a manobra
    comprometida nem no retorno ao centro.
    """

    probe = CarSpaceState(
        driver_id=car.driver_id,
        distance_m=car.distance_m,
        lateral_m=candidate_lateral_m,
        length_m=car.length_m,
        width_m=car.width_m,
    )
    displacement = candidate_lateral_m - car.lateral_m
    duration_s = abs(displacement) / ASSUMED_LANE_CHANGE_MS
    for other in by_distance:
        if other.driver_id == car.driver_id:
            continue
        if other.retired or other.pit_state is not None or other.distance_m >= race_distance_m:
            continue
        longitudinal_gap = _signed_gap(car.distance_m, other.distance_m, lap_length_m)
        if -car.length_m <= longitudinal_gap <= ASSUMED_FOLLOW_TRIGGER_M:
            if _same_lane(probe, other):
                return False
        # A regra adicional trata carros que se aproximam por tras. Os pares
        # ja lado a lado ou a frente continuam sob a regra espacial existente.
        if longitudinal_gap >= -car.length_m or other.speed_ms <= car.speed_ms:
            continue
        if duration_s == 0:
            continue
        # Intervalo em que as faixas laterais se sobrepoem, incluindo a
        # travessia ate o alvo; ele pode ser menor que o tempo total da manobra.
        half_width = (car.width_m + other.width_m) / 2
        t1 = (other.lateral_m - half_width - car.lateral_m) / displacement * duration_s
        t2 = (other.lateral_m + half_width - car.lateral_m) / displacement * duration_s
        start = max(0.0, min(t1, t2))
        end = min(duration_s, max(t1, t2))
        if start >= end:
            continue
        relative_speed = other.speed_ms - car.speed_ms
        gap_start = longitudinal_gap + relative_speed * start
        gap_end = longitudinal_gap + relative_speed * end
        half_length = (car.length_m + other.length_m) / 2
        if min(gap_start, gap_end) < half_length and max(gap_start, gap_end) > -half_length:
            return False
    return True


def _nearest_ahead_same_lane(
    car: CarSpaceState,
    by_distance: list[CarSpaceState],
    race_distance_m: float,
    lap_length_m: float,
) -> CarSpaceState | None:
    """Carro imediatamente a frente, na mesma faixa lateral; ``None`` se livre.

    Um carro que ja cruzou a linha de chegada sai da pista e deixa de bloquear,
    senao prenderia para sempre quem vinha atras e a corrida nao terminaria.
    """

    best: CarSpaceState | None = None
    best_gap = float("inf")
    for other in by_distance:
        if other.driver_id == car.driver_id:
            continue
        if other.retired:
            continue
        if other.distance_m >= race_distance_m:
            continue
        if not _same_lane(car, other):
            continue
        gap = _forward_gap(car.distance_m, other.distance_m, lap_length_m)
        # Quando uma entrada ja veio sobreposta, escolha um lider estavel em
        # vez de imobilizar os dois por se enxergarem a distancia zero.
        if gap == 0.0 and other.driver_id < car.driver_id:
            continue
        if gap < best_gap:
            best = other
            best_gap = gap
    return best


def _frozen(car: CarSpaceState) -> CarSpaceState:
    """Copia imutavel do estado, para o retrato nao mudar nos passos seguintes."""

    return CarSpaceState(
        driver_id=car.driver_id,
        distance_m=car.distance_m,
        lateral_m=car.lateral_m,
        speed_ms=car.speed_ms,
        length_m=car.length_m,
        width_m=car.width_m,
        target_lateral_m=car.target_lateral_m,
        overtaking=car.overtaking,
        retired=car.retired,
        retired_time_s=car.retired_time_s,
        speed_scale=car.speed_scale,
        pit_request=car.pit_request,
        pit_state=car.pit_state,
        fuel_kg=car.fuel_kg,
        tyre_wear_laps=car.tyre_wear_laps,
        contact_damage=car.contact_damage,
    )
