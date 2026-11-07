"""Consumo e desgaste por movimento, com coeficientes assumidos (ADR 0014).

A carga lateral usa v² * curvatura, não velocidade sozinha. Os pesos abaixo
são proxies de esforço, não um modelo térmico de borracha nem um mapa de
injeção medido. A referência neutraliza a carga média do traçado, preservando
a severidade já existente sem contar o circuito duas vezes.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, fields
from math import atan2, isfinite

from f1_simulator.domain.speed_dynamics import CarPhysics, steady_lap
from f1_simulator.domain.track_geometry import TrackGeometry

STANDARD_GRAVITY_MS2 = 9.80665


@dataclass(frozen=True, slots=True)
class DynamicUsageParameters:
    """Pesos e limites versionados. Velocidades em m/s, acelerações em m/s².

    O teto de 100 kg/h é referência do regulamento de 2025, art. 5.2.3,
    compatível com o recorte de dados do projeto; não é a regra de 2026.
    Os outros valores são escolhas de cenário, sem calibração empírica.
    """

    reference_speed_ms: float = 200 / 3.6
    reference_lateral_g: float = 3.0
    reference_acceleration_ms2: float = 5.0
    max_lateral_g: float = 6.0
    max_longitudinal_ms2: float = 20.0
    tyre_distance_weight: float = 0.30
    tyre_lateral_weight: float = 0.55
    tyre_longitudinal_weight: float = 0.15
    fuel_cruise_weight: float = 0.20
    fuel_speed_weight: float = 0.50
    fuel_acceleration_weight: float = 0.30
    fuel_coasting_fraction: float = 0.10
    coasting_deceleration_ms2: float = 0.10
    idle_equivalent_speed_ms: float = 1.0
    max_fuel_flow_kg_h: float = 100.0
    origin: str = "assumed"
    parameter_version: str = "dynamic-usage-v1"

    def __post_init__(self) -> None:
        for field in fields(self):
            if field.name in ("origin", "parameter_version"):
                continue
            value = getattr(self, field.name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{field.name} deve ser positivo e finito")
        if self.fuel_coasting_fraction > 1:
            raise ValueError("fuel_coasting_fraction deve ser <= 1")
        if (
            self.origin != "assumed"
            or not isinstance(self.parameter_version, str)
            or not self.parameter_version.strip()
        ):
            raise ValueError("uso dinâmico exige origem assumida e versão")


@dataclass(frozen=True, slots=True)
class CurvatureProfile:
    """Curvatura absoluta (1/m) estimada da polilinha fechada, não telemetria."""

    distances_m: tuple[float, ...]
    curvature_per_m: tuple[float, ...]

    def at(self, distance_m: float) -> float:
        d = distance_m % self.distances_m[-1]
        index = max(
            1, min(bisect_right(self.distances_m, d), len(self.distances_m) - 1)
        )
        a, b = self.distances_m[index - 1 : index + 1]
        f = (d - a) / (b - a)
        return (
            self.curvature_per_m[index - 1] * (1 - f) + self.curvature_per_m[index] * f
        )


def curvature_profile(geometry: TrackGeometry) -> CurvatureProfile:
    """Ângulo entre tangentes dividido pelo arco médio em metros.

    Usa o fechamento da pista, sem tratar a primeira amostra como uma reta.
    A densidade do mock limita a resolução; não se inventam raios oficiais.
    """

    pts = geometry.track_points
    n = len(pts) - 1
    if n < 3 or geometry.lap_length_m <= 0:
        raise ValueError("curvatura exige uma pista fechada com três vértices")
    result = []
    for i in range(n):
        a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        ux, uy = b.x_normalized - a.x_normalized, b.y_normalized - a.y_normalized
        vx, vy = c.x_normalized - b.x_normalized, c.y_normalized - b.y_normalized
        previous = (
            b.cumulative_distance_m - a.cumulative_distance_m
        ) % geometry.lap_length_m
        following = (
            c.cumulative_distance_m - b.cumulative_distance_m
        ) % geometry.lap_length_m
        arc = (previous + following) / 2
        if arc <= 0:
            raise ValueError("distâncias da pista devem crescer")
        result.append(abs(atan2(ux * vy - uy * vx, ux * vx + uy * vy)) / arc)
    return CurvatureProfile(
        tuple(p.cumulative_distance_m for p in pts), tuple([*result, result[0]])
    )


@dataclass(frozen=True, slots=True)
class UsageReference:
    """Média por metro do perfil neutro; normalização, não calibração."""

    tyre_index_per_m: float
    fuel_index_per_m: float


@dataclass(frozen=True, slots=True)
class UsageDelta:
    """Incrementos de um movimento; desgaste em voltas equivalentes, combustível em kg."""

    distance_wear_laps: float
    lateral_wear_laps: float
    longitudinal_wear_laps: float
    fuel_kg: float
    lateral_acceleration_ms2: float

    @property
    def wear_laps(self) -> float:
        return (
            self.distance_wear_laps
            + self.lateral_wear_laps
            + self.longitudinal_wear_laps
        )


def _indices(
    distance_m: float,
    dt_s: float,
    speed_ms: float,
    acceleration_ms2: float,
    curvature_per_m: float,
    in_pit: bool,
    p: DynamicUsageParameters,
) -> tuple[float, float, float, float, float]:
    lateral = (
        0.0
        if in_pit
        else min(speed_ms**2 * curvature_per_m, p.max_lateral_g * STANDARD_GRAVITY_MS2)
    )
    longitudinal = min(abs(acceleration_ms2), p.max_longitudinal_ms2)
    base = distance_m * p.tyre_distance_weight
    side = (
        distance_m
        * p.tyre_lateral_weight
        * lateral
        / (p.reference_lateral_g * STANDARD_GRAVITY_MS2)
    )
    long = (
        0.0
        if in_pit
        else distance_m
        * p.tyre_longitudinal_weight
        * longitudinal
        / p.reference_acceleration_ms2
    )
    driving = (
        p.fuel_cruise_weight
        + p.fuel_speed_weight * (speed_ms / p.reference_speed_ms) ** 2
    )
    if acceleration_ms2 < -p.coasting_deceleration_ms2:
        driving *= p.fuel_coasting_fraction
    else:
        driving += (
            p.fuel_acceleration_weight
            * min(max(0.0, acceleration_ms2), p.max_longitudinal_ms2)
            / p.reference_acceleration_ms2
        )
    fuel = distance_m * driving + p.idle_equivalent_speed_ms * dt_s
    return base, side, long, fuel, lateral


def usage_reference(
    geometry: TrackGeometry,
    curvature: CurvatureProfile,
    physics: CarPhysics,
    p: DynamicUsageParameters,
) -> UsageReference:
    """Normalize por uma volta limpa do mesmo envelope BASE para todos os pilotos.

    Não normalize pelo envelope de cada piloto: isso cancelaria precisamente
    a diferença de esforço causada pelo estilo/velocidade que queremos medir.
    O limite de vazão é aplicado depois; ao atingi-lo o consumo pode ficar
    abaixo da referência nominal, nunca acima do limite por compensação.
    """

    samples = steady_lap(geometry, physics)
    tyre_total = fuel_total = 0.0
    for a, b in zip(samples, samples[1:]):
        distance, dt = b.distance_m - a.distance_m, b.time_s - a.time_s
        if distance <= 0 or dt <= 0:
            continue
        speed = distance / dt
        indices = _indices(
            distance,
            dt,
            speed,
            (b.speed_ms - a.speed_ms) / dt,
            curvature.at((a.distance_m + b.distance_m) / 2),
            False,
            p,
        )
        tyre_total += sum(indices[:3])
        fuel_total += indices[3]
    return UsageReference(
        tyre_total / geometry.lap_length_m, fuel_total / geometry.lap_length_m
    )


def usage_delta(
    *,
    distance_m: float,
    dt_s: float,
    speed_ms: float,
    acceleration_ms2: float,
    curvature_per_m: float,
    lap_length_m: float,
    burn_kg_per_km: float,
    reference: UsageReference,
    parameters: DynamicUsageParameters = DynamicUsageParameters(),
    management_factor: float = 1.0,
    in_pit: bool = False,
) -> UsageDelta:
    """Acumule apenas o movimento realmente realizado, não o desejado.

    Sem distância não há desgaste; o motor em marcha lenta ainda consome.
    Agressividade não ganha um segundo multiplicador: ela já muda o movimento.
    Gestão de pneus escala o desgaste uma única vez, antes da penalidade.
    SC/VSC reduzem esforço pela velocidade, sem multiplicar pelos antigos
    fatores de consumo por volta. Teto de vazão aplica-se a kg por segundo.
    """

    values = (distance_m, speed_ms, curvature_per_m, burn_kg_per_km)
    if (
        any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not isfinite(v)
            or v < 0
            for v in values
        )
        or isinstance(acceleration_ms2, bool)
        or not isinstance(acceleration_ms2, (int, float))
        or not isfinite(acceleration_ms2)
    ):
        raise ValueError("movimento e consumo devem ser finitos e não negativos")
    if not all(
        not isinstance(v, bool)
        and isinstance(v, (int, float))
        and isfinite(v)
        and v > 0
        for v in (
            dt_s,
            lap_length_m,
            management_factor,
            reference.tyre_index_per_m,
            reference.fuel_index_per_m,
        )
    ):
        raise ValueError("tempo, extensão, gestão e referência devem ser positivos")
    base, side, long, fuel, lateral = _indices(
        distance_m,
        dt_s,
        speed_ms,
        acceleration_ms2,
        curvature_per_m,
        in_pit,
        parameters,
    )
    wear_scale = management_factor / (lap_length_m * reference.tyre_index_per_m)
    demand = burn_kg_per_km / 1000 * fuel / reference.fuel_index_per_m
    return UsageDelta(
        base * wear_scale,
        side * wear_scale,
        long * wear_scale,
        min(demand, parameters.max_fuel_flow_kg_h / 3600 * dt_s),
        lateral,
    )
