"""Percurso hipotético dos boxes, no mesmo plano normalizado da pista.

A escala XY/metre é a da linha de centro. A extensão resultante não é uma
medida oficial de pit lane; usá-la para duração é uma hipótese do motor 2D.
Distância física no caminho e progresso classificatório são separados: o
atalho pelos boxes não acrescenta nem remove uma volta.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from math import hypot, isfinite

from f1_simulator.domain.track_geometry import TrackGeometry


@dataclass(frozen=True, slots=True)
class PitLaneParameters:
    """Limite de velocidade e serviço escolhidos para o cenário, não calibrados."""

    speed_limit_kmh: float = 80.0
    service_time_s: float = 2.5
    merge_gap_m: float = 2.0
    origin: str = "assumed"
    parameter_version: str = "spatial-pit-lane-v1"

    def __post_init__(self) -> None:
        for name in ("speed_limit_kmh", "service_time_s", "merge_gap_m"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name} deve ser positivo e finito")
        if (
            self.origin != "assumed"
            or not isinstance(self.parameter_version, str)
            or not self.parameter_version.strip()
        ):
            raise ValueError("parâmetros de pit lane precisam de origem e versão")


@dataclass(frozen=True, slots=True)
class PitStopRequest:
    """Entrada absoluta em metros de corrida e tempo parado, em segundos."""

    entry_distance_m: float
    service_time_s: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.entry_distance_m, bool)
            or not isinstance(self.entry_distance_m, (int, float))
            or not isfinite(self.entry_distance_m)
            or self.entry_distance_m < 0
        ):
            raise ValueError("entrada dos boxes deve ser não negativa e finita")
        if (
            isinstance(self.service_time_s, bool)
            or not isinstance(self.service_time_s, (int, float))
            or not isfinite(self.service_time_s)
            or self.service_time_s <= 0
        ):
            raise ValueError("serviço deve ter duração positiva e finita")


@dataclass(frozen=True, slots=True)
class PitLaneState:
    """Progresso físico da visita; imutável para preservar os snapshots."""

    path_distance_m: float = 0.0
    service_remaining_s: float = 0.0
    serviced: bool = False


@dataclass(frozen=True, slots=True)
class PitLanePath:
    """Caminho aberto: pontos ``(distância_m, x, y)`` e projeções de entrada/saída.

    ``exit_distance_m`` é desenrolada: pode exceder uma volta quando os boxes
    cruzam a linha. Durante a visita, o progresso de corrida interpola entre
    essas projeções pela fração física percorrida. Parado, ele não avança.
    """

    points: tuple[tuple[float, float, float], ...]
    entry_distance_m: float
    exit_distance_m: float
    service_distance_m: float
    lap_length_m: float

    @property
    def length_m(self) -> float:
        return self.points[-1][0]

    def next_entry(self, distance_m: float) -> float:
        """Próxima entrada à frente do carro, inclusive se estiver na linha."""

        entry = (
            distance_m // self.lap_length_m
        ) * self.lap_length_m + self.entry_distance_m
        return entry if entry > distance_m + 1e-9 else entry + self.lap_length_m

    def race_distance(self, entry: float, path_distance: float) -> float:
        """Mapeie o caminho para progresso monotônico, sem creditar o atalho."""

        fraction = max(0.0, min(1.0, path_distance / self.length_m))
        return entry + fraction * (self.exit_distance_m - self.entry_distance_m)

    def position(self, distance_m: float) -> tuple[float, float]:
        """XY interpolado ao longo do caminho aberto, sem wrap na saída."""

        distances = [p[0] for p in self.points]
        d = max(0.0, min(self.length_m, distance_m))
        index = max(1, min(bisect_right(distances, d), len(distances) - 1))
        a, b = self.points[index - 1], self.points[index]
        f = (d - a[0]) / (b[0] - a[0])
        return a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2])


def build_pit_lane(geometry: TrackGeometry) -> PitLanePath:
    """Conecte a polilinha à pista e estime metros pela escala compartilhada.

    As conexões usam projeção em segmentos (não o vértice mais próximo), para
    evitar saltos de progresso. O ponto de serviço deve ser único e interno.
    As fixtures permanecem imutáveis; as conexões existem só nesta projeção.
    """

    rows = sorted(geometry.pit_lane_points, key=lambda p: p.sequence)
    services = [i for i, p in enumerate(rows) if p.is_service_point]
    if len(rows) < 3 or len(services) != 1 or services[0] in (0, len(rows) - 1):
        raise ValueError(
            "pit lane precisa de entrada, saída e um serviço interno único"
        )
    tp = geometry.track_points
    lap_length = geometry.lap_length_m
    perimeter = sum(
        hypot(b.x_normalized - a.x_normalized, b.y_normalized - a.y_normalized)
        for a, b in zip(tp, tp[1:])
    )
    if lap_length <= 0 or perimeter <= 0:
        raise ValueError("pista sem escala espacial válida")

    def project(x: float, y: float) -> tuple[float, float, float]:
        candidates = []
        for a, b in zip(tp, tp[1:]):
            dx, dy = b.x_normalized - a.x_normalized, b.y_normalized - a.y_normalized
            norm = dx * dx + dy * dy
            if norm == 0:
                continue
            f = max(
                0.0,
                min(
                    1.0, ((x - a.x_normalized) * dx + (y - a.y_normalized) * dy) / norm
                ),
            )
            px, py = a.x_normalized + f * dx, a.y_normalized + f * dy
            d = a.cumulative_distance_m + f * (
                b.cumulative_distance_m - a.cumulative_distance_m
            )
            candidates.append(((x - px) ** 2 + (y - py) ** 2, d, px, py))
        _, d, px, py = min(candidates)
        return d % lap_length, px, py

    entry, ex, ey = project(rows[0].x_normalized, rows[0].y_normalized)
    exit_d, xx, xy = project(rows[-1].x_normalized, rows[-1].y_normalized)
    if exit_d <= entry:
        exit_d += lap_length
    if not 0 < exit_d - entry < lap_length:
        raise ValueError("entrada e saída precisam delimitar um trecho da volta")
    coordinates = [
        (ex, ey),
        *((p.x_normalized, p.y_normalized) for p in rows),
        (xx, xy),
    ]
    points = [(0.0, ex, ey)]
    service_m = 0.0
    for i, (x, y) in enumerate(coordinates[1:], start=1):
        last = points[-1]
        distance = hypot(x - last[1], y - last[2]) * lap_length / perimeter
        if distance > 1e-9:
            points.append((last[0] + distance, x, y))
        if i == services[0] + 1:
            service_m = points[-1][0]
    if not 0 < service_m < points[-1][0]:
        raise ValueError("serviço precisa estar dentro do percurso dos boxes")
    return PitLanePath(tuple(points), entry, exit_d, service_m, lap_length)
