"""Geometria e atributos de teste para o motor 2D (ADR 0011).

O motor 2D exige geometria da pista; estes helpers entregam a geometria real do
fixture ``tests/fixtures/trotman_v128_tracks_2025`` (recorte pequeno de dados
CC0 versionado) para que os testes nao dependam de ``data/`` gerado nem de
rede. ``attribute`` cria atributos neutros de piloto.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from f1_simulator.adapters.datasets.mock_track_geometry import MockTrackDatasetAdapter
from f1_simulator.domain.driver_attributes import ATTRIBUTE_FIELDS, DriverAttributes
from f1_simulator.domain.track_geometry import (
    GeometryProvenance,
    PitLanePoint,
    TrackGeometry,
    TrackPoint,
)
from f1_simulator.factories.track_geometry_factory import TrackGeometryFactory

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "trotman_v128_tracks_2025"
SOURCES = ROOT / "data" / "sources"
#: Monaco: a volta mais curta do fixture (~3,3 km), a mais barata de simular.
MONACO = "circuit:6"


def fixture_geometry(circuit_id: str = MONACO) -> TrackGeometry:
    adapter = MockTrackDatasetAdapter(
        FIXTURE / "track_points.csv",
        SOURCES / "fastf1-tracks-2025.json",
        FIXTURE / "pit_lane_points.csv",
        SOURCES / "fastf1-pit-lanes-2025.json",
    )
    return TrackGeometryFactory.build(adapter.load_geometry(circuit_id))


def attribute(driver_id: str, **overrides: float) -> DriverAttributes:
    values = {
        "pace_offset_pct": 0.0,
        "consistency_factor": 1.0,
        "tyre_management_factor": 1.0,
        "aggression": 1.0,
        "composure": 1.0,
    }
    values.update(overrides)
    return DriverAttributes(
        driver_id=driver_id,
        archetype="balanced",
        sources={name: "generated" for name in ATTRIBUTE_FIELDS},
        **values,
    )


def small_geometry() -> TrackGeometry:
    """Quadrado sintetico curto para exercitar o motor 2D sem fixture externa."""

    provenance = GeometryProvenance(
        source_name="test",
        source_version="1",
        source_year=2026,
        generated_on=date(2026, 1, 1),
        upstream=None,
        upstream_data_license="CC0",
        artifact_sha256="a" * 64,
        manifest_sha256="b" * 64,
        transformation="synthetic square",
    )
    points = tuple(
        TrackPoint(index, x, y, distance)
        for index, (x, y, distance) in enumerate(
            (
                (0.0, 0.0, 0.0),
                (100.0, 0.0, 100.0),
                (100.0, 100.0, 200.0),
                (0.0, 100.0, 300.0),
                (0.0, 0.0, 400.0),
            )
        )
    )
    pit_lane = (
        PitLanePoint(0, 0.0, 90.0, 0.0, False),
        PitLanePoint(1, -5.0, 50.0, 0.5, True),
        PitLanePoint(2, 0.0, 10.0, 1.0, False),
    )
    return TrackGeometry("circuit:1", points, pit_lane, provenance, provenance)
