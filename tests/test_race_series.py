"""Corridas livres sequenciais, independentes de banco de corridas históricas."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from f1_simulator.domain.race_series import (
    SeriesCompetitor,
    SeriesTrack,
    simulate_series,
)

BACKEND = str(Path(__file__).resolve().parents[1] / "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.routers.simulation import simular_sequencia  # noqa: E402
from app.schemas.responses import SeriesSimulationRequest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402


class RaceSeriesTest(unittest.TestCase):
    def test_runs_two_distinct_tracks_in_selected_order(self) -> None:
        tracks = (
            SeriesTrack("circuit:18", "Interlagos", 4000, 2),
            SeriesTrack("circuit:6", "Monaco", 3000, 1),
        )
        drivers = (
            SeriesCompetitor("alice", "Alice", 20000),
            SeriesCompetitor("bob", "Bob", 21000),
        )

        result = simulate_series(tracks, drivers)

        self.assertEqual(result["race_count"], 2)
        self.assertEqual(
            [race["circuit_id"] for race in result["races"]],
            ["circuit:18", "circuit:6"],
        )
        self.assertEqual(
            result["races"][0]["history"][0]["cars"][0]["lap_time_ms"], 80000
        )
        self.assertEqual(
            result["races"][1]["history"][0]["cars"][0]["lap_time_ms"], 60000
        )
        self.assertEqual(
            result["races"][0]["classification"][0]["total_time_ms"], 160000
        )
        self.assertEqual(
            result["races"][1]["classification"][0]["total_time_ms"], 60000
        )

    def test_rejects_empty_duplicate_and_invalid_inputs(self) -> None:
        track = SeriesTrack("circuit:18", "Interlagos", 4000, 2)
        driver = SeriesCompetitor("alice", "Alice", 20000)
        invalid = (
            ((), (driver,)),
            ((track,), ()),
            ((track, track), (driver,)),
            ((track,), (driver, driver)),
            ((SeriesTrack("circuit:18", "Interlagos", float("nan"), 2),), (driver,)),
            ((track,), (SeriesCompetitor("alice", "Alice", float("inf")),)),
            ((track,), (SeriesCompetitor("alice", "Alice", 1e308),)),
        )
        for tracks, drivers in invalid:
            with (
                self.subTest(tracks=tracks, drivers=drivers),
                self.assertRaises(ValueError),
            ):
                simulate_series(tracks, drivers)

    def test_route_uses_catalog_and_never_loads_historical_race(self) -> None:
        request = SeriesSimulationRequest.model_validate(
            {
                "tracks": [
                    {"circuit_id": "circuit:6", "total_laps": 1},
                    {"circuit_id": "circuit:18", "total_laps": 2},
                ],
                "competitors": [
                    {"driver_id": "a", "name": "A", "pace_ms_per_km": 20000}
                ],
            }
        )
        catalog = {
            "tracks": [
                {
                    "circuit_id": "circuit:18",
                    "name": "Interlagos",
                    "lap_length_m": 4000,
                },
                {"circuit_id": "circuit:6", "name": "Monaco", "lap_length_m": 3000},
            ]
        }

        with patch(
            "app.routers.simulation.list_available_tracks", return_value=catalog
        ):
            result = simular_sequencia(request)

        self.assertEqual(
            [race["circuit_id"] for race in result["races"]],
            ["circuit:6", "circuit:18"],
        )
        self.assertEqual(
            result["races"][0]["classification"][0]["total_time_ms"], 60000
        )

    def test_route_rejects_unknown_track(self) -> None:
        request = SeriesSimulationRequest.model_validate(
            {
                "tracks": [{"circuit_id": "circuit:999", "total_laps": 1}],
                "competitors": [
                    {"driver_id": "a", "name": "A", "pace_ms_per_km": 20000}
                ],
            }
        )
        with patch(
            "app.routers.simulation.list_available_tracks", return_value={"tracks": []}
        ):
            with self.assertRaises(HTTPException) as context:
                simular_sequencia(request)
        self.assertEqual(context.exception.status_code, 422)

    def test_route_validates_bounds_before_simulating(self) -> None:
        with self.assertRaises(ValidationError):
            SeriesSimulationRequest.model_validate(
                {
                    "tracks": [{"circuit_id": "circuit:18", "total_laps": 0}],
                    "competitors": [
                        {"driver_id": "a", "name": "A", "pace_ms_per_km": 20000}
                    ],
                }
            )


if __name__ == "__main__":
    unittest.main()
