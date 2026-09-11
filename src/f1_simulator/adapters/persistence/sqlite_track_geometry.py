"""Persist and retrieve canonical geometry inside the curated race database."""

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from f1_simulator.application.ports.track_geometry import (
    TrackGeometryNotFoundError,
    TrackGeometryRepositoryError,
)
from f1_simulator.application.track_geometry_dto import NormalizedTrackGeometry
from f1_simulator.domain.track_geometry import TrackGeometry
from f1_simulator.factories.track_geometry_factory import TrackGeometryFactory


GEOMETRY_SCHEMA = """
CREATE TABLE geometry_sources (
    circuit_id TEXT NOT NULL REFERENCES circuits(circuit_id),
    path_kind TEXT NOT NULL CHECK (path_kind IN ('track', 'pit_lane')),
    source_name TEXT NOT NULL,
    source_version TEXT NOT NULL,
    source_year INTEGER NOT NULL,
    generated_on TEXT NOT NULL,
    upstream TEXT,
    upstream_data_license TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    transformation TEXT NOT NULL,
    PRIMARY KEY (circuit_id, path_kind)
);
CREATE TABLE track_points (
    circuit_id TEXT NOT NULL REFERENCES circuits(circuit_id),
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    x_normalized REAL NOT NULL,
    y_normalized REAL NOT NULL,
    cumulative_distance_m REAL NOT NULL CHECK (cumulative_distance_m >= 0),
    PRIMARY KEY (circuit_id, sequence)
);
CREATE TABLE pit_lane_points (
    circuit_id TEXT NOT NULL REFERENCES circuits(circuit_id),
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    x_normalized REAL NOT NULL,
    y_normalized REAL NOT NULL,
    path_fraction REAL NOT NULL CHECK (path_fraction BETWEEN 0 AND 1),
    is_service_point INTEGER NOT NULL CHECK (is_service_point IN (0, 1)),
    PRIMARY KEY (circuit_id, sequence)
);
"""


def insert_geometry(connection: sqlite3.Connection, geometry: TrackGeometry) -> None:
    """Insert into the writer's existing transaction; do not publish separately.

    The caller creates GEOMETRY_SCHEMA before inserting the race. Foreign keys
    prevent attaching paths to a circuit absent from that database.
    """

    for kind, source in (
        ("track", geometry.track_source),
        ("pit_lane", geometry.pit_lane_source),
    ):
        connection.execute(
            "INSERT INTO geometry_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                geometry.circuit_id,
                kind,
                source.source_name,
                source.source_version,
                source.source_year,
                source.generated_on.isoformat(),
                source.upstream,
                source.upstream_data_license,
                source.artifact_sha256,
                source.manifest_sha256,
                source.transformation,
            ),
        )
    connection.executemany(
        "INSERT INTO track_points VALUES (?, ?, ?, ?, ?)",
        (
            (
                geometry.circuit_id,
                p.sequence,
                p.x_normalized,
                p.y_normalized,
                p.cumulative_distance_m,
            )
            for p in geometry.track_points
        ),
    )
    connection.executemany(
        "INSERT INTO pit_lane_points VALUES (?, ?, ?, ?, ?, ?)",
        (
            (
                geometry.circuit_id,
                p.sequence,
                p.x_normalized,
                p.y_normalized,
                p.path_fraction,
                int(p.is_service_point),
            )
            for p in geometry.pit_lane_points
        ),
    )


class SQLiteTrackGeometryRepository:
    """Return validated geometry in sequence order using read-only connections.

    Historical databases without geometry are supported as a missing-geometry
    result. A partial schema or corrupt paths are errors, never an empty mock.
    """

    def __init__(self, source: Path) -> None:
        """Configure the curated race database, without creating or modifying it."""
        self._source = source.resolve()

    def get_geometry(self, circuit_id: str) -> TrackGeometry:
        """Load both paths and provenance or raise an application-level error."""

        if not isinstance(circuit_id, str) or not circuit_id.strip():
            raise ValueError("circuit_id must be non-empty text")
        try:
            with closing(
                sqlite3.connect(f"{self._source.as_uri()}?mode=ro", uri=True)
            ) as connection:
                connection.row_factory = sqlite3.Row
                # One read transaction gives all queries a consistent snapshot.
                with connection:
                    connection.execute("BEGIN")
                    return self._load(connection, circuit_id)
        except TrackGeometryRepositoryError:
            raise
        except (sqlite3.Error, ValueError, TypeError, KeyError) as error:
            raise TrackGeometryRepositoryError(
                f"cannot read geometry: {error}"
            ) from error

    @staticmethod
    def _load(connection: sqlite3.Connection, circuit_id: str) -> TrackGeometry:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required = {"geometry_sources", "track_points", "pit_lane_points"}
        if not required & tables:
            # Verify that this is at least a race database, not any empty SQLite.
            connection.execute("SELECT circuit_id FROM circuits LIMIT 1")
            raise TrackGeometryNotFoundError(f"database has no geometry: {circuit_id}")
        if not required.issubset(tables):
            raise TrackGeometryRepositoryError("incomplete geometry schema")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise TrackGeometryRepositoryError("database has foreign-key violations")
        sources = {}
        for row in connection.execute(
            "SELECT * FROM geometry_sources WHERE circuit_id = ?", (circuit_id,)
        ):
            source = dict(row)
            kind = source.pop("path_kind")
            source.pop("circuit_id")
            source["generated_on"] = date.fromisoformat(source["generated_on"])
            sources[kind] = source
        paths = []
        for table in ("track_points", "pit_lane_points"):
            # Table names are internal constants; circuit IDs always use binding.
            points = []
            for row in connection.execute(
                f"SELECT * FROM {table} WHERE circuit_id = ? ORDER BY sequence",
                (circuit_id,),
            ):
                point = dict(row)
                point.pop("circuit_id")
                if table == "pit_lane_points":
                    value = point["is_service_point"]
                    if type(value) is not int or value not in (0, 1):
                        raise TrackGeometryRepositoryError("invalid service flag")
                    point["is_service_point"] = bool(value)
                points.append(point)
            paths.append(tuple(points))
        if not sources and not any(paths):
            raise TrackGeometryNotFoundError(f"geometry not found: {circuit_id}")
        if set(sources) != {"track", "pit_lane"}:
            raise TrackGeometryRepositoryError("missing geometry provenance")
        if (
            connection.execute(
                "SELECT 1 FROM circuits WHERE circuit_id = ?", (circuit_id,)
            ).fetchone()
            is None
        ):
            raise TrackGeometryRepositoryError("geometry has no canonical circuit")
        return TrackGeometryFactory.build(
            NormalizedTrackGeometry(
                circuit_id,
                paths[0],
                paths[1],
                sources["track"],
                sources["pit_lane"],
            )
        )
