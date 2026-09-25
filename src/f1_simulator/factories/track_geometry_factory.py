"""Validate normalized paths before constructing canonical geometry."""

import math
import re
from datetime import date

from f1_simulator.application.track_geometry_dto import NormalizedTrackGeometry
from f1_simulator.domain.track_geometry import (
    GeometryProvenance,
    PitLanePoint,
    TrackGeometry,
    TrackPoint,
)


class TrackGeometryValidationError(ValueError):
    """A path, circuit association or provenance violates the geometry contract."""


class TrackGeometryFactory:
    """Enforce path invariants without files, rendering or source-specific rules."""

    @classmethod
    def build(cls, data: NormalizedTrackGeometry) -> TrackGeometry:
        """Reject gaps, duplicates, nonfinite values and incomplete paths.

        No samples are dropped, reordered, closed or imputed here: silently
        repairing a path could change its direction, service point or scale.
        The adapter must supply sequence order, starting at zero.
        """

        if not isinstance(data.circuit_id, str) or not data.circuit_id.strip():
            raise TrackGeometryValidationError("circuit_id must be non-empty text")
        track = cls._points(data.track_points, TrackPoint, "cumulative_distance_m")
        pit = cls._points(data.pit_lane_points, PitLanePoint, "path_fraction")
        if len(track) < 4 or len(pit) < 2:
            raise TrackGeometryValidationError("track needs >=4 points; pit lane >=2")
        if (track[0].x_normalized, track[0].y_normalized) != (
            track[-1].x_normalized,
            track[-1].y_normalized,
        ):
            raise TrackGeometryValidationError("track must be explicitly closed")
        if len({(p.x_normalized, p.y_normalized) for p in track}) < 3:
            raise TrackGeometryValidationError("track needs >=3 distinct positions")
        if len({(p.x_normalized, p.y_normalized) for p in pit}) < 2:
            raise TrackGeometryValidationError("pit lane must have spatial extent")
        if pit[-1].path_fraction != 1:
            raise TrackGeometryValidationError("pit path_fraction must end at 1")
        if sum(p.is_service_point for p in pit) != 1:
            raise TrackGeometryValidationError(
                "pit lane needs exactly one service point"
            )
        track_source = cls._provenance(data.track_source)
        pit_source = cls._provenance(data.pit_lane_source)
        if track_source.source_year != pit_source.source_year:
            raise TrackGeometryValidationError("track and pit lane source years differ")
        return TrackGeometry(data.circuit_id, track, pit, track_source, pit_source)

    @staticmethod
    def _points(rows, point_type, progress_field):
        points = []
        previous = -1.0
        for index, row in enumerate(rows):
            if type(row.get("sequence")) is not int or row["sequence"] != index:
                raise TrackGeometryValidationError("sequence must be contiguous from 0")
            for field in ("x_normalized", "y_normalized", progress_field):
                value = row.get(field)
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise TrackGeometryValidationError(
                        f"{field} must be finite numeric data"
                    )
            progress = row[progress_field]
            if (index == 0 and progress != 0) or progress <= previous:
                raise TrackGeometryValidationError(
                    f"{progress_field} must start at 0 and increase"
                )
            if (
                point_type is PitLanePoint
                and type(row.get("is_service_point")) is not bool
            ):
                raise TrackGeometryValidationError("is_service_point must be boolean")
            try:
                points.append(point_type(**row))
            except TypeError as error:
                raise TrackGeometryValidationError("invalid point fields") from error
            previous = progress
        return tuple(points)

    @staticmethod
    def _provenance(row: dict[str, object]) -> GeometryProvenance:
        for field in (
            "source_name",
            "source_version",
            "upstream_data_license",
            "transformation",
        ):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise TrackGeometryValidationError(f"{field} must be non-empty text")
        upstream = row.get("upstream")
        if upstream is not None and (
            not isinstance(upstream, str) or not upstream.strip()
        ):
            raise TrackGeometryValidationError("upstream must be text or None")
        for field in ("artifact_sha256", "manifest_sha256"):
            if not isinstance(row.get(field), str) or not re.fullmatch(
                r"[0-9a-f]{64}", row[field]
            ):
                raise TrackGeometryValidationError(f"{field} must be a SHA-256")
        if type(row.get("generated_on")) is not date:
            raise TrackGeometryValidationError("generated_on must be a date")
        if type(row.get("source_year")) is not int or row["source_year"] <= 0:
            raise TrackGeometryValidationError("source_year must be positive")
        try:
            return GeometryProvenance(**row)
        except TypeError as error:
            raise TrackGeometryValidationError("invalid provenance fields") from error
