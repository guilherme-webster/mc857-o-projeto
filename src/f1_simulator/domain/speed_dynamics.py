"""Velocidade de um carro ao longo da volta, limitada pela aderencia (ADR 0015).

O carro e um ponto de massa que percorre a linha de centro da geometria. Em cada
ponto, a velocidade maxima e a de curva: a aceleracao lateral ``v**2 / R`` nao
pode passar do que o pneu transmite, ``mu * (g + k_a * v**2)``, em que ``k_a``
e o downforce por unidade de massa e de velocidade ao quadrado. Isolando ``v``:

    v**2 = mu * g / (1/R - mu * k_a)

Quando ``1/R <= mu * k_a`` o downforce sozinho segura a curva e o limite passa a
ser a velocidade maxima de reta. Antes das curvas o carro freia, e depois delas
acelera, com limites que tambem dependem da velocidade:

- freada: ``uso_freio * mu * (g + k_a * v**2) + k_d * v**2`` (o arrasto ajuda);
- tracao: ``min(parcela_tracao * mu * (g + k_a * v**2), P / (m * v)) - k_d * v**2``.

Por que esse modelo (ADR 0015 revisa o ADR 0010): a versao anterior interpolava
entre 320 e 90 km/h pelo angulo entre pontos, normalizado pela curva mais
fechada da propria pista. Ela nao conhecia o raio nem a aderencia, entao toda
pista tinha a curva mais lenta a 90 km/h e Monaco saia 37% rapido demais. Com
``mu`` explicito, a condicao da pista (agua, borracha) e o composto agem num
unico ponto fisico: :meth:`CarPhysics.with_grip`.

Unidades: metros, segundos, m/s e m/s**2; km/h so nos campos que dizem ``kmh``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from math import isfinite, sqrt

from f1_simulator.domain.driver_attributes import DriverAttributes
from f1_simulator.domain.track_geometry import TrackGeometry

KMH_TO_MS = 1000.0 / 3600.0
GRAVITY_MS2 = 9.81
AIR_DENSITY_KG_M3 = 1.2

#: Raio minimo aceito (m). A curvatura vem de tres pontos vizinhos da
#: polilinha de 240 pontos; um desvio de digitalizacao numa reta poderia gerar
#: um raio minusculo e uma "curva" fantasma. O grampo de Monaco, a curva mais
#: fechada do calendario, tem raio da ordem de 10-15 m.
MIN_CORNER_RADIUS_M = 8.0

#: Raio (m) acima do qual o trecho e tratado como reta (curvatura zero). O
#: calculo de curvatura por 3 pontos gera "curvas fantasma" de raio grande na
#: reta por arredondamento das coordenadas; acima deste raio a curva nao
#: limitaria a velocidade de qualquer forma. Curvas reais ficam bem abaixo.
MAX_STRAIGHT_RADIUS_M = 1000.0

#: Meia-janela da media movel da curvatura (pontos). Com 1, cada ponto usa a
#: media de tres curvaturas vizinhas. Escolhida na calibracao: 0 e 2 erraram
#: mais contra as voltas de referencia (ver ``calibrate_car_physics``).
CURVATURE_SMOOTHING_POINTS = 1


@dataclass(frozen=True, slots=True)
class CarPhysics:
    """Envelope fisico de um carro: aderencia, aerodinamica, potencia e massa.

    ``grip_mu`` e ``downforce_cla_m2`` foram estimados contra as voltas de
    referencia historicas (``data/parameters/car-physics-v1.json``); os demais
    campos sao hipoteses de ordem de grandeza de um F1 recente, nao medidas.

    ``corner_grip_use`` e ``brake_grip_use`` dizem quanto da aderencia o piloto
    aproveita na curva e na freada; 1,0 e o carro de referencia. Sao o ponto em
    que os atributos do piloto entram (:func:`physics_for`).
    """

    v_max_straight_kmh: float = 330.0
    grip_mu: float = 1.3
    downforce_cla_m2: float = 4.5
    drag_cda_m2: float = 1.1
    mass_kg: float = 800.0
    power_kw: float = 750.0
    traction_share: float = 0.55
    corner_grip_use: float = 1.0
    brake_grip_use: float = 1.0

    def __post_init__(self) -> None:
        for name in (
            "v_max_straight_kmh",
            "grip_mu",
            "mass_kg",
            "power_kw",
            "corner_grip_use",
            "brake_grip_use",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isfinite(value) or value <= 0:
                raise ValueError(f"{name} deve ser positivo e finito")
        for name in ("downforce_cla_m2", "drag_cda_m2"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} nao pode ser negativo")
        if not 0 < self.traction_share <= 1:
            raise ValueError("traction_share deve estar em (0, 1]")

    @property
    def v_max_ms(self) -> float:
        return self.v_max_straight_kmh * KMH_TO_MS

    @property
    def aero_k_per_m(self) -> float:
        """Downforce por massa e por velocidade ao quadrado (1/m)."""

        return 0.5 * AIR_DENSITY_KG_M3 * self.downforce_cla_m2 / self.mass_kg

    @property
    def drag_k_per_m(self) -> float:
        """Arrasto por massa e por velocidade ao quadrado (1/m)."""

        return 0.5 * AIR_DENSITY_KG_M3 * self.drag_cda_m2 / self.mass_kg

    def with_grip(self, factor: float) -> CarPhysics:
        """O mesmo carro numa pista ou pneu com ``factor`` vezes a aderencia.

        E o ponto unico por onde agua, borracha e composto chegam a fisica: o
        fator multiplica ``mu`` na curva, na freada e na tracao. Potencia,
        arrasto e downforce nao mudam.
        """

        if isinstance(factor, bool) or not isfinite(factor) or factor <= 0:
            raise ValueError("factor deve ser positivo e finito")
        return replace(self, grip_mu=self.grip_mu * factor)

    def corner_speed_ms(self, curvature_per_m: float) -> float:
        """Maior velocidade com que a curvatura dada pode ser feita (m/s)."""

        mu = self.grip_mu * self.corner_grip_use
        denominator = curvature_per_m - mu * self.aero_k_per_m
        if denominator <= 0:
            return self.v_max_ms
        return min(self.v_max_ms, sqrt(mu * GRAVITY_MS2 / denominator))

    def brake_limit_ms2(self, speed_ms: float) -> float:
        """Desaceleracao maxima a ``speed_ms`` (m/s**2, positiva)."""

        v2 = speed_ms * speed_ms
        normal = GRAVITY_MS2 + self.aero_k_per_m * v2
        return self.brake_grip_use * self.grip_mu * normal + self.drag_k_per_m * v2

    def accel_limit_ms2(self, speed_ms: float) -> float:
        """Aceleracao maxima a ``speed_ms`` (m/s**2), zero acima do limite.

        O menor entre a tracao das rodas traseiras e a potencia, menos o
        arrasto. Abaixo de 1 m/s a potencia e avaliada a 1 m/s, para nao
        dividir por zero numa largada parada.
        """

        v2 = speed_ms * speed_ms
        traction = (
            self.traction_share
            * self.grip_mu
            * (GRAVITY_MS2 + self.aero_k_per_m * v2)
        )
        power = self.power_kw * 1000.0 / (self.mass_kg * max(speed_ms, 1.0))
        return max(0.0, min(traction, power) - self.drag_k_per_m * v2)


#: Carro de referencia: o piloto neutro com ele reproduz a volta de referencia
#: historica de cada circuito (erro quadratico medio de ~4,7% em 24 pistas,
#: mediana 0,993). Espelha ``data/parameters/car-physics-v1.json``, gerado por
#: ``scripts/calibrate_car_physics.py``; um teste impede que os dois divirjam.
DEFAULT_CAR_PHYSICS = CarPhysics()

#: Ganhos que traduzem atributos (neutros em 1.0, ou 0% no ritmo) no envelope
#: fisico. O ritmo do piloto tem ganho moderado (2x, nao mais 7x): antes do
#: carro por equipe (``car_pace_to_physics``), o atributo de piloto era o
#: unico medidor de ritmo e precisava ser exagerado para separar estilos na
#: tela. Agora o carro carrega o spread entre equipes de forma literal, e o
#: ganho alto duplicaria essa vantagem (o ``pace_offset_pct`` dos pilotos ja
#: embute parte do desempenho do carro) e espalharia o pelotao alem do
#: realista. Com 2x o piloto continua visivelmente distinto, mas menor que o
#: carro, como na F1. Agressividade atua na frenagem, compostura na velocidade
#: de curva, ritmo num fator geral sobre as duas velocidades.
#:
#: Balanceamento (issue #139). Os tres ganhos sao heuristicos, escolhidos e nao
#: medidos, e foram dimensionados para que a faixa inteira de cada atributo nos
#: arquetipos (``ASSUMED_ARCHETYPES``) mova o tempo de volta na mesma ordem de
#: grandeza, cerca de 1% para cada lado em Monaco:
#:
#: - ritmo, -0,60% a +0,40%: -1,0% a +0,7% de volta;
#: - compostura, 0,85 a 1,30: +0,5% a -1,0%;
#: - agressividade, 0,60 a 1,50: +0,6% a -0,6%.
#:
#: Com os ganhos anteriores (0,5 e 0,5) a compostura 1,30 valia +15% de
#: velocidade de curva e -10,9% de volta, dez vezes o efeito do ritmo: o
#: arquetipo conservador vencia todas as corridas por mais de um minuto e o
#: atributo chamado "ritmo" quase nao decidia nada. Reduzir so a compostura
#: invertia o problema (o agressivo vencia sempre), por isso a frenagem da
#: agressividade caiu junto.
#:
#: A v2 usava compostura 0,08, escolhida quando quase metade do pelotao
#: abandonava por contato. Com isso corrigido (issue #174) e o ritmo sorteado
#: na mesma faixa para os tres arquetipos (``ARCHETYPE_PACE_OFFSET_PCT``), 0,08
#: dava ao conservador 14 vitorias em 18 corridas de distancia completa
#: (Bahrein, Monaco e Zandvoort, 4 pilotos por arquetipo). Com 0,04 a posicao
#: media ficou em 6,9 / 6,5 / 6,1 (agressivo / equilibrado / conservador) e as
#: vitorias em 5 / 5 / 8. Um teste impede que um atributo volte a dominar.
_PACE_GAIN = 2.0
_COMPOSURE_CORNER_GAIN = 0.04
_AGGRESSION_BRAKE_GAIN = 0.25

#: Versao dos tres ganhos acima, exposta em ``assumptions`` para que uma
#: corrida salva diga com qual balanceamento de atributos foi simulada.
DRIVER_PHYSICS_GAINS_VERSION = "driver-physics-gains-v3"


def physics_for(
    attributes: DriverAttributes | None,
    base: CarPhysics = DEFAULT_CAR_PHYSICS,
) -> CarPhysics:
    """Envelope fisico de um piloto, derivado dos atributos.

    Sem atributos, devolve o envelope base inalterado. O significado de cada
    atributo e o mesmo do modelo anterior (ADR 0010), agora expresso como uso
    da aderencia:

    - o ritmo escala a velocidade de reta e a de curva pelo mesmo fator ``p``;
      como a velocidade de curva cresce com a raiz de ``mu``, o uso de
      aderencia em curva escala com ``p**2``;
    - a compostura levanta a velocidade de curva por ``c``, isto e, o uso de
      aderencia em curva por ``c**2``;
    - a agressividade aumenta o uso de aderencia na freada.

    Consistencia e gestao de pneu nao entram aqui porque ja atuam no ruido e na
    degradacao.
    """

    if attributes is None:
        return base
    pace = 1.0 - attributes.pace_offset_pct / 100.0 * _PACE_GAIN
    corner = 1.0 + (attributes.composure - 1.0) * _COMPOSURE_CORNER_GAIN
    brake = 1.0 + (attributes.aggression - 1.0) * _AGGRESSION_BRAKE_GAIN
    return replace(
        base,
        v_max_straight_kmh=base.v_max_straight_kmh * pace,
        corner_grip_use=base.corner_grip_use * (pace * corner) ** 2,
        brake_grip_use=base.brake_grip_use * brake,
    )


#: Ganho que traduz o ritmo de carro de equipe (negativo = mais rapido) no
#: envelope fisico. Diferente do ganho exagerado dos atributos de piloto
#: (``_PACE_GAIN = 7``), o ritmo do carro e aplicado de forma literal (1:1):
#: 1% de ritmo vira ~1% de velocidade de reta e de aderencia. O spread real
#: entre equipes numa temporada fica na casa de 1-3%, entao o mapeamento 1:1
#: mantem o pelotao plausivel. Parametro heuristico, nao calibrado (ADR 0008).
_CAR_PACE_GAIN = 1.0


def car_pace_to_physics(
    pace_offset_pct: float,
    base: CarPhysics = DEFAULT_CAR_PHYSICS,
) -> CarPhysics:
    """Envelope fisico de um carro de equipe a partir do ritmo heuristico.

    ``pace_offset_pct`` segue a mesma convencao dos atributos de piloto:
    negativo e mais rapido, zero e o carro de referencia (o mesmo que o piloto
    neutro reproduz). O fator ``1 - pace_offset_pct/100`` escala a velocidade
    de reta (``v_max_straight_kmh``), a aderencia (``grip_mu``) e a potencia
    (``power_kw``) pelo mesmo valor, de modo que um carro mais rapido o e em
    todos os trechos -- curva, freada e reta -- e nao so na reta. Downforce,
    arrasto, massa e tracao permanecem do carro de referencia; a aderencia do
    proprio carro e o ponto por onde agua, borracha e composto continuam
    atuando (:meth:`CarPhysics.with_grip`).

    O ganho e literal, nao o ganho exagerado dos pilotos, porque o ritmo do
    carro e uma alavanca de realismo, nao de estilo ficticio. Parametros
    heuristicos/assumidos, nao calibrados: ver ADR 0008 e
    ``configs/cars/perfis-ficticios.json``.
    """

    if (
        isinstance(pace_offset_pct, bool)
        or not isinstance(pace_offset_pct, (int, float))
        or not isfinite(pace_offset_pct)
    ):
        raise ValueError("pace_offset_pct deve ser finito")
    factor = 1.0 - pace_offset_pct / 100.0 * _CAR_PACE_GAIN
    if not isfinite(factor) or factor <= 0:
        raise ValueError("pace_offset_pct produz fator de carro nao positivo")
    return replace(
        base,
        v_max_straight_kmh=base.v_max_straight_kmh * factor,
        grip_mu=base.grip_mu * factor,
        power_kw=base.power_kw * factor,
    )


@dataclass(frozen=True, slots=True)
class SpeedSample:

    distance_m: float
    speed_ms: float
    time_s: float


@lru_cache(maxsize=64)
def track_curvature_per_m(geometry: TrackGeometry) -> tuple[float, ...]:
    """Curvatura (1/m) em cada ponto da linha de centro, inclusive o de fechamento.

    As coordenadas normalizadas tem escala uniforme, entao um unico fator as
    converte em metros: a extensao oficial da volta dividida pelo perimetro da
    polilinha. Em cada ponto, a curvatura e a do circulo que passa por ele e
    pelos dois vizinhos (``4 * area / produto dos lados``), suavizada por media
    movel e limitada por :data:`MIN_CORNER_RADIUS_M`. O ultimo ponto repete o
    primeiro, como na geometria.
    """

    points = geometry.track_points
    unique = len(points) - 1
    if unique < 3:
        raise ValueError("geometria precisa de pelo menos tres pontos distintos")
    perimeter = 0.0
    for i in range(unique):
        dx = points[i + 1].x_normalized - points[i].x_normalized
        dy = points[i + 1].y_normalized - points[i].y_normalized
        perimeter += sqrt(dx * dx + dy * dy)
    if perimeter <= 0:
        raise ValueError("geometria degenerada: perimetro nulo")
    scale = geometry.lap_length_m / perimeter
    xy = [(p.x_normalized * scale, p.y_normalized * scale) for p in points[:unique]]

    raw = []
    for i in range(unique):
        ax, ay = xy[(i - 1) % unique]
        bx, by = xy[i]
        cx, cy = xy[(i + 1) % unique]
        ab = sqrt((bx - ax) ** 2 + (by - ay) ** 2)
        bc = sqrt((cx - bx) ** 2 + (cy - by) ** 2)
        ca = sqrt((ax - cx) ** 2 + (ay - cy) ** 2)
        twice_area = abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax))
        product = ab * bc * ca
        raw.append(2.0 * twice_area / product if product > 0 else 0.0)

    # Dead-band: raio acima de ``MAX_STRAIGHT_RADIUS_M`` e reta. O calculo de
    # curvatura por 3 pontos e sensivel ao arredondamento das coordenadas, e
    # numa reta isso gera "curvas fantasma" de raio grande (ex.: 1700 m) que
    # fazem o teto serrilhar e o carro frear sem motivo. Zerar essas curvaturas
    # espurias limpa a reta sem afetar as curvas reais (raio bem menor).
    straight = 1.0 / MAX_STRAIGHT_RADIUS_M
    raw = [0.0 if k < straight else k for k in raw]

    half = CURVATURE_SMOOTHING_POINTS
    width = 2 * half + 1
    cap = 1.0 / MIN_CORNER_RADIUS_M
    smoothed = [
        min(cap, sum(raw[(i + j) % unique] for j in range(-half, half + 1)) / width)
        for i in range(unique)
    ]
    smoothed.append(smoothed[0])
    return tuple(smoothed)


def _reachable(speed_ms: float, ds_m: float, limit) -> float:
    """Velocidade apos ``ds_m`` metros sob a aceleracao ``limit(v)``.

    Preditor-corretor: avalia o limite na velocidade media estimada do trecho,
    porque com downforce a freada e a tracao mudam muito ao longo de 20-30 m.
    """

    first = sqrt(max(0.0, speed_ms * speed_ms + 2.0 * limit(speed_ms) * ds_m))
    middle = 0.5 * (speed_ms + first)
    return sqrt(max(0.0, speed_ms * speed_ms + 2.0 * limit(middle) * ds_m))


def _brake_limited(
    targets: list[float], cum: list[float], physics: CarPhysics
) -> list[float]:
    """Antecipe as freadas: cada ponto nao pode ser mais rapido do que o
    proximo permite frear. Duas passadas fecham o anel (o fechamento repete a
    largada)."""

    n = len(targets)
    capped = list(targets)
    for _ in range(2):
        for i in range(n - 2, -1, -1):
            ds = cum[i + 1] - cum[i]
            if ds <= 0:
                continue
            capped[i] = min(
                capped[i], _reachable(capped[i + 1], ds, physics.brake_limit_ms2)
            )
        capped[n - 1] = min(capped[n - 1], capped[0])
    return capped


def speed_ceiling(
    geometry: TrackGeometry,
    physics: CarPhysics = DEFAULT_CAR_PHYSICS,
) -> tuple[list[float], list[float]]:
    """Distancias e velocidade maxima permitida em cada ponto (curva + freada).

    E o teto que tanto ``simulate_lap_speed`` (integracao por distancia) quanto
    o integrador 2D por tempo (ADR 0011) consomem, sem duplicar a curvatura nem
    a freada.
    """

    points = geometry.track_points
    if len(points) < 2:
        raise ValueError("geometria precisa de pelo menos dois pontos")
    cum = [p.cumulative_distance_m for p in points]
    targets = [physics.corner_speed_ms(k) for k in track_curvature_per_m(geometry)]
    return cum, _brake_limited(targets, cum, physics)


def simulate_lap_speed(
    geometry: TrackGeometry,
    physics: CarPhysics = DEFAULT_CAR_PHYSICS,
    *,
    initial_speed_ms: float = 0.0,
) -> tuple[SpeedSample, ...]:
    """Integre uma volta por distancia, acelerando ate o teto de cada ponto."""

    points = geometry.track_points
    if len(points) < 2:
        raise ValueError("geometria precisa de pelo menos dois pontos")
    cum, ceiling = speed_ceiling(geometry, physics)

    speed = min(max(initial_speed_ms, 0.0), ceiling[0])
    time_s = 0.0
    samples = [SpeedSample(cum[0], speed, time_s)]
    for i in range(len(points) - 1):
        ds = cum[i + 1] - cum[i]
        if ds <= 0:
            samples.append(SpeedSample(cum[i + 1], speed, time_s))
            continue
        next_speed = min(
            _reachable(speed, ds, physics.accel_limit_ms2), ceiling[i + 1]
        )
        avg = (speed + next_speed) / 2 or 1e-6
        time_s += ds / avg
        speed = next_speed
        samples.append(SpeedSample(cum[i + 1], speed, time_s))
    return tuple(samples)


def steady_lap(
    geometry: TrackGeometry,
    physics: CarPhysics = DEFAULT_CAR_PHYSICS,
) -> tuple[SpeedSample, ...]:
    """Volta lancada: a velocidade de chegada vira a de partida, ate convergir."""

    _, ceiling = speed_ceiling(geometry, physics)
    speed = ceiling[0]
    for _ in range(8):
        samples = simulate_lap_speed(geometry, physics, initial_speed_ms=speed)
        final = samples[-1].speed_ms
        if abs(final - speed) < 1e-3:
            return samples
        speed = final
    return simulate_lap_speed(geometry, physics, initial_speed_ms=speed)


def lap_time_ms(samples: tuple[SpeedSample, ...]) -> float:
    return samples[-1].time_s * 1000.0


class GripLapTimes:
    """Volta lancada de um carro em funcao do fator de aderencia da pista.

    A condicao da pista muda a cada volta, mas recalcular a fisica por carro e
    por volta custaria segundos por corrida. Aqui a volta e calculada sob
    demanda apenas nos pontos de :attr:`GRID` que cercam o fator pedido e
    interpolada linearmente entre eles; o tempo de volta e suave no fator, e
    com a grade abaixo o erro de interpolacao fica abaixo de 0,1%. Uma corrida
    seca so toca os pontos 0,95 e 1,0.
    """

    GRID = (0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1)

    __slots__ = ("_geometry", "_physics", "_cache")

    def __init__(self, geometry: TrackGeometry, physics: CarPhysics) -> None:
        self._geometry = geometry
        self._physics = physics
        self._cache: dict[float, float] = {}

    def _at(self, factor: float) -> float:
        if factor not in self._cache:
            physics = self._physics if factor == 1.0 else self._physics.with_grip(factor)
            self._cache[factor] = lap_time_ms(steady_lap(self._geometry, physics))
        return self._cache[factor]

    def lap_ms(self, factor: float) -> float:
        """Tempo de volta (ms) com ``factor`` vezes a aderencia de referencia."""

        if isinstance(factor, bool) or not isfinite(factor) or factor <= 0:
            raise ValueError("factor deve ser positivo e finito")
        grid = self.GRID
        factor = min(max(factor, grid[0]), grid[-1])
        if factor in grid:
            return self._at(factor)
        upper = next(i for i, value in enumerate(grid) if value > factor)
        low, high = grid[upper - 1], grid[upper]
        share = (factor - low) / (high - low)
        return self._at(low) + share * (self._at(high) - self._at(low))

    def delta_ms(self, factor: float) -> float:
        """Tempo a mais (ms) que a volta leva com ``factor`` em vez de 1,0."""

        return self.lap_ms(factor) - self._at(1.0)
