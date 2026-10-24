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
from dataclasses import dataclass

from f1_simulator.domain.random_source import RandomSource
from f1_simulator.domain.speed_dynamics import (
    ASSUMED_CAR_PHYSICS,
    CarPhysics,
    speed_ceiling,
)
from f1_simulator.domain.track_geometry import TrackGeometry

#: Passo de tempo da integracao sub-volta (s). Hipotese assumida (ADR 0011):
#: menor passo aproxima melhor o continuo e custa mais. 50 ms equilibra as duas
#: coisas para o uso educacional.
ASSUMED_TIME_STEP_S = 0.05

#: Velocidade lateral maxima de troca de faixa (m/s). Hipotese assumida: um
#: carro leva cerca de um segundo para cruzar a pista inteira. Governa quao
#: rapido a manobra de ultrapassagem se desloca para o lado.
ASSUMED_LANE_CHANGE_MS = 6.0

#: Folga longitudinal (m) a partir da qual um carro mais rapido "sente" o da
#: frente e considera tentar passar. Ordem de grandeza de alguns comprimentos
#: de carro; nao calibrada.
ASSUMED_FOLLOW_TRIGGER_M = 20.0

#: Taxa de contato por SEGUNDO de corpos rocando lado a lado, com perfis
#: neutros. Expressa por segundo (nao por passo) para a frequencia de colisao
#: nao depender de ``dt``: a chance de um passo e ``taxa * dt``. Hipotese nao
#: calibrada; escalada pela agressividade dos envolvidos.
ASSUMED_SIDE_CONTACT_PER_SECOND = 0.6

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
    #: Fator (<=1 tipico) aplicado ao teto de velocidade neste trecho. E o gancho
    #: por onde pneu, combustivel e clima reduzem o ritmo do carro no motor 2D,
    #: atualizado volta a volta por quem orquestra a corrida. 1.0 e neutro.
    speed_scale: float = 1.0

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
    physics: CarPhysics = ASSUMED_CAR_PHYSICS,
    *,
    dt_s: float = ASSUMED_TIME_STEP_S,
    initial_speed_ms: float | None = None,
    max_steps: int = 1_000_000,
) -> tuple[MotionSample, ...]:
    """Integre uma volta de um carro por passos de tempo (fatia 2 do ADR 0011).

    A cada passo o carro ajusta a velocidade em direcao ao teto da curvatura,
    limitado por ``accel``/``brake``, e avanca ``speed * dt`` metros. Para quando
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
            speed = min(target, speed + physics.accel_ms2 * dt_s)
        elif speed > target:
            speed = max(target, speed - physics.brake_ms2 * dt_s)
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


def _same_lane(a: CarSpaceState, b: CarSpaceState) -> bool:
    """Duas faixas se sobrepoem se os corpos se cruzam lateralmente."""

    return abs(a.lateral_m - b.lateral_m) < (a.width_m + b.width_m) / 2.0


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
    max_steps: int = 10_000_000,
) -> tuple[FieldSample, ...]:
    """Avance varios carros por passos de tempo, com ultrapassagem e colisao (fatia 5).

    A cada passo, um carro preso atras de outro mais lento na sua faixa tenta se
    deslocar para um lado livre e passar; a passagem acontece pela posicao, nao
    por sorteio. ``aggression_by_id`` (1.0 neutro) antecipa e alarga a tentativa:
    um carro mais agressivo busca o espaco mais cedo. Carro livre retorna suave
    ao centro.

    Dois carros lado a lado com os corpos quase encostados podem se tocar: com
    ``rng``, cada passo sorteia um contato cuja chance cresce com a agressividade
    dos envolvidos; havendo contato, um dos dois abandona, com o mais agressivo
    mais provavel de ser o culpado que sai. Sem ``rng``, nao ha colisao (fatias
    anteriores). A ordem de sorteio e fixa (pares por ``driver_id``), para o
    resultado reproduzir por semente.

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
        if not standing_start and car.speed_ms == 0.0:
            car.speed_ms = ceilings[car.driver_id][1][0]

    race_distance = total_laps * track.lap_length_m
    lap_length = track.lap_length_m
    usable = track.bounds.usable_m
    by_id = {c.driver_id: c for c in cars}
    laps_done = {c.driver_id: 0 for c in cars}
    order = sorted(cars, key=lambda c: c.driver_id)
    samples = [FieldSample(0.0, tuple(_frozen(c) for c in order))]
    time_s = 0.0
    steps = 0
    while steps < max_steps and any(
        c.distance_m < race_distance and not c.retired for c in cars
    ):
        time_s += dt_s
        by_distance = sorted(cars, key=lambda c: c.distance_m)
        for car in sorted(cars, key=lambda c: c.driver_id):
            if car.retired or car.distance_m >= race_distance:
                continue
            cum, ceiling = ceilings[car.driver_id]
            physics = physics_by_id[car.driver_id]
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
                )
            # (2) move a lateral em direcao ao alvo, limitada pela velocidade lateral.
            max_step_lat = ASSUMED_LANE_CHANGE_MS * dt_s
            delta = car.target_lateral_m - car.lateral_m
            car.lateral_m += max(-max_step_lat, min(max_step_lat, delta))
            car.clamp_lateral(track.bounds)

            # (3) velocidade longitudinal: acelera/freia em direcao ao teto.
            # O teto e reduzido por ``speed_scale`` (pneu, combustivel, clima).
            target = _ceiling_at(cum, ceiling, car.distance_m) * car.speed_scale
            if car.speed_ms < target:
                car.speed_ms = min(target, car.speed_ms + physics.accel_ms2 * dt_s)
            elif car.speed_ms > target:
                car.speed_ms = max(target, car.speed_ms - physics.brake_ms2 * dt_s)

            # (4) avanco com exclusao: usa a faixa lateral JA atualizada, entao
            # um carro que saiu da esteira do da frente deixa de ser bloqueado.
            # Limitacao conhecida: a folga e imposta no avanco, nao por frenagem
            # antecipada. Quando o carro da frente freia forte (entrada de curva),
            # a folga instantanea pode encolher por um ou dois passos antes de
            # estabilizar; um modelo de car-following preciso e trabalho futuro.
            proposed = car.distance_m + car.speed_ms * dt_s
            ahead = _nearest_ahead_same_lane(car, by_distance, race_distance)
            if ahead is not None:
                limit = ahead.distance_m - (ahead.length_m + car.length_m) / 2.0
                if proposed > limit:
                    proposed = max(car.distance_m, limit)
                    car.speed_ms = min(car.speed_ms, ahead.speed_ms)
            car.distance_m = proposed

            # Volta concluida: avisa o orquestrador (pneu, combustivel, clima
            # atualizam ``speed_scale`` do carro para a proxima volta).
            completed = int(car.distance_m // lap_length)
            if on_lap_complete is not None and completed > laps_done[car.driver_id]:
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
        if rng is not None and not field_neutralized:
            _resolve_collisions(
                cars, race_distance, aggression_by_id, rng, dt_s, start_zone_m
            )

        order = sorted(cars, key=lambda c: c.driver_id)
        samples.append(FieldSample(time_s, tuple(_frozen(c) for c in order)))
        steps += 1
    return tuple(samples)


def _side_by_side(a: CarSpaceState, b: CarSpaceState) -> bool:
    """Se os dois carros se sobrepoem longitudinalmente (andam emparelhados)."""

    return abs(a.distance_m - b.distance_m) < (a.length_m + b.length_m) / 2.0


def _rubbing(a: CarSpaceState, b: CarSpaceState) -> bool:
    """Se os corpos quase se encostam lateralmente estando emparelhados."""

    lateral_clearance = abs(a.lateral_m - b.lateral_m) - (a.width_m + b.width_m) / 2.0
    return _side_by_side(a, b) and lateral_clearance < ASSUMED_RUBBING_MARGIN_M


def _resolve_collisions(
    cars: list[CarSpaceState],
    race_distance_m: float,
    aggression_by_id: dict[str, float],
    rng: RandomSource,
    dt_s: float,
    start_zone_m: float = 0.0,
) -> None:
    """Sorteie contato entre pares que rocam; um dos dois abandona.

    Percorre pares em ordem de ``driver_id`` para a sequencia aleatoria ser
    estavel. A chance por passo e ``taxa_por_segundo * dt`` escalada pela media
    das agressividades, de modo que a frequencia de colisao nao dependa de
    ``dt``. No contato, o culpado que abandona e sorteado com peso na
    agressividade: atacar demais custa. Um carro ja retirado nao participa.

    ``start_zone_m`` suprime o contato de um par enquanto qualquer dos dois ainda
    esta nos primeiros metros da largada parada: o grid se desenrola emparelhado
    e lento, e o contato ali seria artefato da partida, nao disputa.
    """

    active = sorted(
        (c for c in cars if not c.retired and c.distance_m < race_distance_m),
        key=lambda c: c.driver_id,
    )
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            a, b = active[i], active[j]
            if a.retired or b.retired:
                continue
            if a.distance_m < start_zone_m or b.distance_m < start_zone_m:
                continue
            if not _rubbing(a, b):
                continue
            agg_a = aggression_by_id.get(a.driver_id, 1.0)
            agg_b = aggression_by_id.get(b.driver_id, 1.0)
            chance = ASSUMED_SIDE_CONTACT_PER_SECOND * dt_s * (agg_a + agg_b) / 2.0
            label = f"collision:{a.driver_id}:{b.driver_id}"
            if rng.uniform01(f"{label}:contact") >= chance:
                continue
            # Houve contato: o mais agressivo e o mais provavel culpado a sair.
            total = agg_a + agg_b
            a_retires = rng.uniform01(f"{label}:culprit") < (agg_a / total)
            (a if a_retires else b).retired = True


def _lane_decision(
    car: CarSpaceState,
    by_id: dict[str, CarSpaceState],
    by_distance: list[CarSpaceState],
    ceilings: dict[str, tuple[list[float], list[float]]],
    race_distance_m: float,
    usable_m: float,
    aggression: float,
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
            or target.distance_m >= race_distance_m
            or car.distance_m >= target.distance_m + clearance
        )
        if done:
            car.overtaking = None
            return _safe_center(car, by_distance, race_distance_m, usable_m)
        side = 1.0 if car.lateral_m >= 0 else -1.0
        reach = car.width_m * (0.8 + 0.4 * aggression)
        return max(-usable_m, min(usable_m, target.lateral_m + side * reach))

    ahead = _nearest_ahead_same_lane(car, by_distance, race_distance_m)
    if ahead is None:
        return _safe_center(car, by_distance, race_distance_m, usable_m)
    gap = ahead.distance_m - car.distance_m
    if gap > ASSUMED_FOLLOW_TRIGGER_M:
        return _safe_center(car, by_distance, race_distance_m, usable_m)
    if car.speed_ms <= ahead.speed_ms:
        return car.lateral_m
    my_ceiling = _ceiling_at(*ceilings[car.driver_id], car.distance_m)
    ahead_ceiling = _ceiling_at(*ceilings[ahead.driver_id], ahead.distance_m)
    if my_ceiling <= ahead_ceiling:
        return car.lateral_m

    reach = car.width_m * (0.8 + 0.4 * aggression)
    for side in (1.0, -1.0):
        candidate = max(-usable_m, min(usable_m, ahead.lateral_m + side * reach))
        if _side_is_clear(car, candidate, by_distance, race_distance_m):
            # Compromete-se com a ultrapassagem deste carro.
            car.overtaking = ahead.driver_id
            return candidate
    return car.lateral_m


def _safe_center(
    car: CarSpaceState,
    by_distance: list[CarSpaceState],
    race_distance_m: float,
    usable_m: float,
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
        if not _side_by_side(car, other):
            continue
        # Outro carro entre a posicao atual e o centro, do lado do movimento.
        if car.lateral_m > 0 and other.lateral_m < car.lateral_m:
            target = max(target, other.lateral_m + min_gap)
        elif car.lateral_m < 0 and other.lateral_m > car.lateral_m:
            target = min(target, other.lateral_m - min_gap)
    # Nao ultrapassa a borda nem volta para longe do centro alem de onde esta.
    if car.lateral_m >= 0:
        return max(0.0, min(car.lateral_m, min(usable_m, target)))
    return min(0.0, max(car.lateral_m, max(-usable_m, target)))


def _side_is_clear(
    car: CarSpaceState,
    candidate_lateral_m: float,
    by_distance: list[CarSpaceState],
    race_distance_m: float,
) -> bool:
    """Se a faixa candidata esta livre na janela longitudinal da manobra."""

    probe = CarSpaceState(
        driver_id=car.driver_id,
        distance_m=car.distance_m,
        lateral_m=candidate_lateral_m,
        length_m=car.length_m,
        width_m=car.width_m,
    )
    for other in by_distance:
        if other.driver_id == car.driver_id:
            continue
        if other.retired or other.distance_m >= race_distance_m:
            continue
        longitudinal_gap = other.distance_m - car.distance_m
        if -car.length_m <= longitudinal_gap <= ASSUMED_FOLLOW_TRIGGER_M:
            if _same_lane(probe, other):
                return False
    return True


def _nearest_ahead_same_lane(
    car: CarSpaceState,
    by_distance: list[CarSpaceState],
    race_distance_m: float,
) -> CarSpaceState | None:
    """Carro imediatamente a frente, na mesma faixa lateral; ``None`` se livre.

    Um carro que ja cruzou a linha de chegada sai da pista e deixa de bloquear,
    senao prenderia para sempre quem vinha atras e a corrida nao terminaria.
    """

    best: CarSpaceState | None = None
    for other in by_distance:
        if other.driver_id == car.driver_id:
            continue
        if other.retired:
            continue
        if other.distance_m <= car.distance_m:
            continue
        if other.distance_m >= race_distance_m:
            continue
        if not _same_lane(car, other):
            continue
        if best is None or other.distance_m < best.distance_m:
            best = other
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
        speed_scale=car.speed_scale,
    )
