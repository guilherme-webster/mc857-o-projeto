from __future__ import annotations

from dataclasses import dataclass
from math import acos

from f1_simulator.domain.driver_attributes import DriverAttributes
from f1_simulator.domain.track_geometry import TrackGeometry

KMH_TO_MS = 1000.0 / 3600.0


@dataclass(frozen=True, slots=True)
class CarPhysics:

    v_max_straight_kmh: float = 320.0
    v_min_corner_kmh: float = 90.0
    accel_ms2: float = 5.0
    brake_ms2: float = 12.0

    def __post_init__(self) -> None:
        if not 0 < self.v_min_corner_kmh <= self.v_max_straight_kmh:
            raise ValueError("exija 0 < v_min_corner <= v_max_straight")
        if self.accel_ms2 <= 0 or self.brake_ms2 <= 0:
            raise ValueError("accel e brake devem ser positivos")


ASSUMED_CAR_PHYSICS = CarPhysics()

#: Ganhos que traduzem atributos (neutros em 1.0, ou 0% no ritmo) no envelope
#: fisico. Nao calibrados e deliberadamente exagerados em relacao a F1 real,
#: para que os estilos ficticios se separem de forma visivel na tela.
#: Agressividade atua na frenagem, compostura na velocidade de curva, ritmo
#: num fator geral sobre as duas velocidades.
_PACE_GAIN = 7.0
_COMPOSURE_CORNER_GAIN = 0.5
_AGGRESSION_BRAKE_GAIN = 0.5


def physics_for(
    attributes: DriverAttributes | None,
    base: CarPhysics = ASSUMED_CAR_PHYSICS,
) -> CarPhysics:
    """Envelope fisico de um piloto, derivado dos atributos (ADR 0010, caráter).

    Sem atributos, devolve o envelope base inalterado. O ritmo escala as duas
    velocidades, a compostura levanta a velocidade de curva e a agressividade
    aumenta a frenagem; consistencia e gestao de pneu nao entram aqui porque ja
    atuam no ruido e na degradacao.
    """

    if attributes is None:
        return base
    pace = 1.0 - attributes.pace_offset_pct / 100.0 * _PACE_GAIN
    corner = 1.0 + (attributes.composure - 1.0) * _COMPOSURE_CORNER_GAIN
    brake = 1.0 + (attributes.aggression - 1.0) * _AGGRESSION_BRAKE_GAIN
    v_max = base.v_max_straight_kmh * pace
    v_min = min(base.v_min_corner_kmh * pace * corner, v_max)
    return CarPhysics(
        v_max_straight_kmh=v_max,
        v_min_corner_kmh=v_min,
        accel_ms2=base.accel_ms2,
        brake_ms2=base.brake_ms2 * brake,
    )


@dataclass(frozen=True, slots=True)
class SpeedSample:

    distance_m: float
    speed_ms: float
    time_s: float


def _target_speeds(geometry: TrackGeometry, physics: CarPhysics) -> list[float]:

    points = geometry.track_points
    n = len(points)
    unique = n - 1  # ultimo ponto repete o primeiro
    turn = [0.0] * n
    for i in range(unique):
        prev_i = (i - 1) % unique
        ax = points[i].x_normalized - points[prev_i].x_normalized
        ay = points[i].y_normalized - points[prev_i].y_normalized
        bx = points[i + 1].x_normalized - points[i].x_normalized
        by = points[i + 1].y_normalized - points[i].y_normalized
        la = (ax * ax + ay * ay) ** 0.5
        lb = (bx * bx + by * by) ** 0.5
        if la == 0.0 or lb == 0.0:
            continue
        cos_angle = max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))
        turn[i] = acos(cos_angle)
    turn[unique] = turn[0]

    max_turn = max(turn) or 1.0
    v_max = physics.v_max_straight_kmh * KMH_TO_MS
    v_min = physics.v_min_corner_kmh * KMH_TO_MS
    return [v_max - (v_max - v_min) * (t / max_turn) for t in turn]


def _brake_limited(targets: list[float], cum: list[float], brake_ms2: float) -> list[float]:

    n = len(targets)
    capped = list(targets)
    for _ in range(2):  # duas passadas fecham o anel de freada
        for i in range(n - 2, -1, -1):
            ds = cum[i + 1] - cum[i]
            reachable = (capped[i + 1] ** 2 + 2 * brake_ms2 * ds) ** 0.5
            capped[i] = min(capped[i], reachable)
    return capped


def speed_ceiling(
    geometry: TrackGeometry,
    physics: CarPhysics = ASSUMED_CAR_PHYSICS,
) -> tuple[list[float], list[float]]:
    """Distancias e velocidade maxima permitida em cada ponto (alvo + freada).

    E a velocidade-alvo da curvatura ja limitada pela frenagem antecipada, o
    teto que tanto ``simulate_lap_speed`` (integracao por distancia, ADR 0010)
    quanto o integrador 2D por tempo (ADR 0011) consomem, sem duplicar a
    curvatura nem a freada.
    """

    points = geometry.track_points
    if len(points) < 2:
        raise ValueError("geometria precisa de pelo menos dois pontos")
    cum = [p.cumulative_distance_m for p in points]
    targets = _target_speeds(geometry, physics)
    return cum, _brake_limited(targets, cum, physics.brake_ms2)


def simulate_lap_speed(
    geometry: TrackGeometry,
    physics: CarPhysics = ASSUMED_CAR_PHYSICS,
    *,
    initial_speed_ms: float = 0.0,
) -> tuple[SpeedSample, ...]:

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
        reachable = (speed ** 2 + 2 * physics.accel_ms2 * ds) ** 0.5
        next_speed = min(reachable, ceiling[i + 1])
        avg = (speed + next_speed) / 2 or 1e-6
        time_s += ds / avg
        speed = next_speed
        samples.append(SpeedSample(cum[i + 1], speed, time_s))
    return tuple(samples)


def steady_lap(
    geometry: TrackGeometry,
    physics: CarPhysics = ASSUMED_CAR_PHYSICS,
) -> tuple[SpeedSample, ...]:

    speed = physics.v_min_corner_kmh * KMH_TO_MS
    for _ in range(8):
        samples = simulate_lap_speed(geometry, physics, initial_speed_ms=speed)
        final = samples[-1].speed_ms
        if abs(final - speed) < 1e-3:
            speed = final
            break
        speed = final
    return simulate_lap_speed(geometry, physics, initial_speed_ms=speed)


def lap_time_ms(samples: tuple[SpeedSample, ...]) -> float:
    return samples[-1].time_s * 1000.0


def speed_at(samples: tuple[SpeedSample, ...], distance_m: float) -> float:
    lap_length = samples[-1].distance_m
    d = distance_m % lap_length if lap_length else 0.0
    lo, hi = 0, len(samples) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if samples[mid].distance_m < d:
            lo = mid + 1
        else:
            hi = mid
    i = max(1, lo)
    a, b = samples[i - 1], samples[i]
    span = b.distance_m - a.distance_m
    f = (d - a.distance_m) / span if span > 0 else 0.0
    return a.speed_ms + (b.speed_ms - a.speed_ms) * f
