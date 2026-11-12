"""Diagnóstico reproduzível de carga derivada dos mocks; não é calibração.

Não baixa dados nem grava nas fixtures. Os resultados são estimativas do
envelope de velocidade do simulador, não acelerações medidas em telemetria.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from f1_simulator.adapters.datasets.mock_track_geometry import MockTrackDatasetAdapter
from f1_simulator.adapters.fuel_parameters_json import read_fuel_parameters
from f1_simulator.domain.dynamic_usage import (
    STANDARD_GRAVITY_MS2,
    DynamicUsageParameters,
    curvature_profile,
    usage_delta,
    usage_reference,
)
from f1_simulator.domain.speed_dynamics import CarPhysics, steady_lap
from f1_simulator.factories.track_geometry_factory import TrackGeometryFactory


def analyze(geometry, burn_kg_per_km: float) -> dict:
    """Compare parcelas ao longo da volta neutra, com a mesma unidade por metro."""

    p = DynamicUsageParameters()
    profile = curvature_profile(geometry)
    reference = usage_reference(geometry, profile, CarPhysics(), p)
    samples = steady_lap(geometry)
    rows = []
    fuel = wear = 0.0
    for a, b in zip(samples, samples[1:]):
        ds, dt = b.distance_m - a.distance_m, b.time_s - a.time_s
        if ds <= 0 or dt <= 0:
            continue
        midpoint = (a.distance_m + b.distance_m) / 2
        speed = ds / dt
        k = profile.at(midpoint)
        delta = usage_delta(
            distance_m=ds,
            dt_s=dt,
            speed_ms=speed,
            acceleration_ms2=(b.speed_ms - a.speed_ms) / dt,
            curvature_per_m=k,
            lap_length_m=geometry.lap_length_m,
            burn_kg_per_km=burn_kg_per_km,
            reference=reference,
            parameters=p,
        )
        fuel += delta.fuel_kg
        wear += delta.wear_laps
        rows.append(
            dict(
                distance_m=round(midpoint, 1),
                speed_kmh=round(speed * 3.6, 1),
                curvature_per_m=round(k, 6),
                lateral_g_unbounded=round(speed * speed * k / STANDARD_GRAVITY_MS2, 3),
                lateral_wear_per_km=round(delta.lateral_wear_laps / ds * 1000, 5),
            )
        )
    return dict(
        circuit_id=geometry.circuit_id,
        kind="derived_not_measured",
        nominal_burn_kg_per_km=burn_kg_per_km,
        neutral_wear_laps=round(wear, 6),
        neutral_fuel_kg=round(fuel, 4),
        peak_lateral_g_unbounded=max(row["lateral_g_unbounded"] for row in rows),
        segments_above_model_load_limit=sum(
            row["lateral_g_unbounded"] > p.max_lateral_g for row in rows
        ),
        top_lateral_load_segments=sorted(
            rows, key=lambda row: row["lateral_wear_per_km"], reverse=True
        )[:5],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--circuit", help="ID canônico, por exemplo circuit:9")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    fixture = root / "tests/fixtures/trotman_v128_tracks_2025"
    manifest = root / "data/sources/fastf1-tracks-2025.json"
    adapter = MockTrackDatasetAdapter(
        fixture / "track_points.csv",
        manifest,
        fixture / "pit_lane_points.csv",
        root / "data/sources/fastf1-pit-lanes-2025.json",
    )
    events = json.loads(manifest.read_text(encoding="utf-8"))["source"]["events"]
    ids = ["circuit:" + event["circuit_id"] for event in events]
    if args.circuit and args.circuit not in ids:
        parser.error("circuito não está nas 24 fixtures existentes")
    fuel = read_fuel_parameters(root / "data/parameters/fuel-v1.json")
    report = [
        analyze(
            TrackGeometryFactory.build(adapter.load_geometry(cid)), fuel.burn_kg_per_km
        )
        for cid in ids
        if args.circuit is None or cid == args.circuit
    ]
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
