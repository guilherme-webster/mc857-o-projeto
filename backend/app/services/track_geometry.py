from __future__ import annotations

import json
import sqlite3

from fastapi import HTTPException, status


def geometry_artifacts() -> tuple:
    from app.config import (
        GEOMETRY_PIT_LANE_POINTS,
        GEOMETRY_PIT_MANIFEST,
        GEOMETRY_TRACK_MANIFEST,
        GEOMETRY_TRACK_POINTS,
    )

    return (
        GEOMETRY_TRACK_POINTS,
        GEOMETRY_TRACK_MANIFEST,
        GEOMETRY_PIT_LANE_POINTS,
        GEOMETRY_PIT_MANIFEST,
    )


def geometry_dataset():
    from f1_simulator.adapters.datasets.mock_track_geometry import (
        MockTrackDatasetAdapter,
    )

    artifacts = geometry_artifacts()
    if not all(path.exists() for path in artifacts):
        return None
    return MockTrackDatasetAdapter(*artifacts)


def history_repository():
    """Abra o histórico canônico usado pelas demais rotas, quando publicado."""

    from app.config import HISTORY_DB
    from f1_simulator.adapters.persistence.sqlite_history import (
        SQLiteHistoryRepository,
    )

    if not HISTORY_DB.is_file():
        return None
    return SQLiteHistoryRepository(HISTORY_DB)


def _geometry_payload(geometry) -> dict:
    from f1_simulator.domain.speed_dynamics import steady_lap

    samples = steady_lap(geometry)
    return {
        "circuit_id": geometry.circuit_id,
        "lap_length_m": geometry.lap_length_m,
        "speed_profile_physical": [
            {
                "distance_m": s.distance_m,
                "speed_ms": s.speed_ms,
                "time_s": s.time_s,
            }
            for s in samples
        ],
        "track_points": [
            {
                "sequence": p.sequence,
                "x": p.x_normalized,
                "y": p.y_normalized,
                "cumulative_distance_m": p.cumulative_distance_m,
            }
            for p in geometry.track_points
        ],
        "pit_lane_points": [
            {
                "sequence": p.sequence,
                "x": p.x_normalized,
                "y": p.y_normalized,
                "path_fraction": p.path_fraction,
                "is_service_point": p.is_service_point,
            }
            for p in geometry.pit_lane_points
        ],
    }


def list_available_tracks() -> dict:
    _, track_manifest, _, _ = geometry_artifacts()
    if not track_manifest.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"geometry manifest not found: {track_manifest.name}",
        )
    try:
        manifest = json.loads(track_manifest.read_text(encoding="utf-8"))
        events = manifest["source"]["events"]
    except (OSError, ValueError, KeyError) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"invalid geometry manifest: {error}",
        ) from error

    from f1_simulator.application.default_laps import default_laps_for_circuit
    from f1_simulator.factories.history_factory import HistoryValidationError

    repository = history_repository()
    tracks = []
    for event in events:
        circuit_id = f"circuit:{event['circuit_id']}"
        lap_length_m = event.get("lap_length_m")
        try:
            default = default_laps_for_circuit(circuit_id, lap_length_m, repository)
        except (OSError, sqlite3.Error, HistoryValidationError):
            # O catálogo continua útil antes do ETL ou se o histórico estiver
            # ilegível. Após a primeira falha, não reabrimos o mesmo artefato.
            repository = None
            default = default_laps_for_circuit(circuit_id, lap_length_m)
        track = {
            "circuit_id": circuit_id,
            "name": event.get("circuit_name"),
            "lap_length_m": lap_length_m,
            "default_laps": default.laps,
            "default_laps_source": default.source,
        }
        if default.race is not None:
            track["default_laps_race"] = {
                "race_id": default.race.race_id,
                "season": default.race.season,
                "round_number": default.race.round_number,
            }
        tracks.append(track)
    tracks.sort(key=lambda t: t["circuit_id"])
    return {"count": len(tracks), "tracks": tracks}


def geometry_object(circuit_id: str):
    """Monte a TrackGeometry de dominio para a pista, ou sinalize indisponibilidade."""

    from f1_simulator.adapters.datasets.mock_track_geometry import (
        MockTrackDatasetAdapter,
        MockTrackDatasetError,
    )
    from f1_simulator.factories.track_geometry_factory import (
        TrackGeometryFactory,
        TrackGeometryValidationError,
    )

    canonical = (
        circuit_id if circuit_id.startswith("circuit:") else f"circuit:{circuit_id}"
    )

    artifacts = geometry_artifacts()
    if not all(path.exists() for path in artifacts):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="geometry artifacts not found in /data/geometry volume",
        )

    adapter = MockTrackDatasetAdapter(*artifacts)
    try:
        normalized = adapter.load_geometry(canonical)
        return TrackGeometryFactory.build(normalized)
    except (MockTrackDatasetError, TrackGeometryValidationError) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"geometry unavailable for {canonical}: {error}",
        ) from error


def track_geometry_for(circuit_id: str) -> dict:
    return _geometry_payload(geometry_object(circuit_id))
