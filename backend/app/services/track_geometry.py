from __future__ import annotations

import json

from fastapi import HTTPException, status


def geometry_artifacts() -> tuple:
    """Retorne (track_csv, track_manifest, pit_csv, pit_manifest) da config."""

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
    """Monte o adaptador de geometria, ou None se os artefatos nao existirem."""

    from f1_simulator.adapters.datasets.mock_track_geometry import (
        MockTrackDatasetAdapter,
    )

    artifacts = geometry_artifacts()
    if not all(path.exists() for path in artifacts):
        return None
    return MockTrackDatasetAdapter(*artifacts)


def _geometry_payload(geometry) -> dict:
    """Serialize uma TrackGeometry no formato JSON consumido pelo frontend."""

    return {
        "circuit_id": geometry.circuit_id,
        "lap_length_m": geometry.lap_length_m,
        "track_points": [
            {
                "sequence": p.sequence,
                "x": p.x_normalized,
                "y": p.y_normalized,
                "cumulative_distance_m": p.cumulative_distance_m,
            }
            for p in geometry.track_points
        ],
    }


def list_available_tracks() -> dict:
    """Liste os circuitos com geometria disponivel, direto do manifesto.

    Independente do ETL: le apenas o manifesto de pistas para oferecer ao
    usuario as pistas que ele pode visualizar (id canonico, nome e comprimento).
    """

    _, track_manifest, _, _ = geometry_artifacts()
    if not track_manifest.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Manifesto de geometria nao encontrado: {track_manifest.name}.",
        )
    try:
        manifest = json.loads(track_manifest.read_text(encoding="utf-8"))
        events = manifest["source"]["events"]
    except (OSError, ValueError, KeyError) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Manifesto de geometria invalido: {error}",
        ) from error

    tracks = [
        {
            "circuit_id": f"circuit:{event['circuit_id']}",
            "name": event.get("circuit_name"),
            "lap_length_m": event.get("lap_length_m"),
        }
        for event in events
    ]
    tracks.sort(key=lambda t: t["circuit_id"])
    return {"count": len(tracks), "tracks": tracks}


def track_geometry_for(circuit_id: str) -> dict:
    """Retorne a geometria de qualquer circuito, sem depender do ETL carregado.

    Le a geometria direto da fonte reduzida (ADR 0003) via adaptador + factory,
    entao o usuario pode visualizar qualquer pista mapeada mesmo sem ter curado
    a corrida correspondente. Aceita ``circuit:<id>`` ou apenas ``<id>``.
    """

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
            detail="Artefatos de geometria nao encontrados no volume /data/geometry.",
        )

    adapter = MockTrackDatasetAdapter(*artifacts)
    try:
        normalized = adapter.load_geometry(canonical)
        geometry = TrackGeometryFactory.build(normalized)
    except (MockTrackDatasetError, TrackGeometryValidationError) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Geometria indisponivel para {canonical}: {error}",
        ) from error

    return _geometry_payload(geometry)
