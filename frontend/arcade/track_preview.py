"""Pure geometry preparation for drawing a track preview with Arcade.

The module deliberately does not import Arcade. It translates the backend's
normalized track contract into screen coordinates, leaving rendering as an
adapter concern and keeping the transformation testable without a window/GPU.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

ScreenPoint = tuple[float, float]
Bounds = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class TrackPreviewGeometry:
    """Screen-space paths plus trustworthy metadata from the backend."""

    track_points: tuple[ScreenPoint, ...]
    pit_lane_points: tuple[ScreenPoint, ...]
    service_point: ScreenPoint
    lap_length_m: float


def fit_track_preview(
    payload: object,
    bounds: Bounds,
    *,
    padding: float = 20,
) -> TrackPreviewGeometry:
    """Fit track and pit lane together inside ``bounds`` preserving aspect.

    The pit lane must use the exact transform calculated from both paths. This
    preserves the shared coordinates guaranteed by the backend and prevents a
    visually plausible but spatially detached pit lane.

    Raises:
        ValueError: if the payload is incomplete, non-finite or has no unique
            representative service point.
    """

    if not isinstance(payload, dict):
        raise ValueError("resposta de geometria deve ser um objeto")
    try:
        lap_length_m = float(payload["lap_length_m"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("comprimento da volta ausente ou inválido") from error
    if not isfinite(lap_length_m) or lap_length_m <= 0:
        raise ValueError("comprimento da volta deve ser positivo e finito")

    left, bottom, width, height = bounds
    if width <= 2 * padding or height <= 2 * padding:
        raise ValueError("área do visualizador é pequena demais")

    track_rows = _ordered_rows(payload.get("track_points"), "pista")
    pit_rows = _ordered_rows(payload.get("pit_lane_points"), "pit lane")
    service_rows = [row for row in pit_rows if row.get("is_service_point") is True]
    if len(service_rows) != 1:
        raise ValueError("a pit lane deve possuir exatamente um ponto de serviço")

    source_points = [_xy(row) for row in (*track_rows, *pit_rows)]
    xs = [point[0] for point in source_points]
    ys = [point[1] for point in source_points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max_x - min_x
    span_y = max_y - min_y
    if span_x <= 0 or span_y <= 0:
        raise ValueError("a geometria precisa ter extensão nos dois eixos")

    scale = min(
        (width - 2 * padding) / span_x,
        (height - 2 * padding) / span_y,
    )
    source_center_x = (min_x + max_x) / 2
    source_center_y = (min_y + max_y) / 2
    target_center_x = left + width / 2
    target_center_y = bottom + height / 2

    def transform(row: dict[str, Any]) -> ScreenPoint:
        x, y = _xy(row)
        return (
            target_center_x + (x - source_center_x) * scale,
            target_center_y + (y - source_center_y) * scale,
        )

    return TrackPreviewGeometry(
        track_points=tuple(transform(row) for row in track_rows),
        pit_lane_points=tuple(transform(row) for row in pit_rows),
        service_point=transform(service_rows[0]),
        lap_length_m=lap_length_m,
    )


def _ordered_rows(value: object, label: str) -> tuple[dict[str, Any], ...]:
    """Validate and order one path from the backend JSON contract."""

    if not isinstance(value, list) or len(value) < 2:
        raise ValueError(f"{label} deve possuir pelo menos dois pontos")
    if not all(isinstance(row, dict) for row in value):
        raise ValueError(f"{label} contém um ponto inválido")
    try:
        rows = tuple(sorted(value, key=lambda row: int(row["sequence"])))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{label} possui sequência inválida") from error
    return rows


def _xy(row: dict[str, Any]) -> tuple[float, float]:
    """Read one finite normalized coordinate from a response row."""

    try:
        x = float(row["x"])
        y = float(row["y"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("ponto da geometria sem coordenadas válidas") from error
    if not isfinite(x) or not isfinite(y):
        raise ValueError("coordenadas da geometria devem ser finitas")
    return x, y
