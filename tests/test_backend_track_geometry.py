"""Verify the HTTP-facing track contract includes its associated pit lane."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = str(ROOT / "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.services import track_geometry  # noqa: E402
from f1_simulator.domain.history import HistoricalRecord  # noqa: E402

GEOMETRY = ROOT / "tests" / "fixtures" / "trotman_v128_tracks_2025"
SOURCES = ROOT / "data" / "sources"
ARTIFACTS = (
    GEOMETRY / "track_points.csv",
    SOURCES / "fastf1-tracks-2025.json",
    GEOMETRY / "pit_lane_points.csv",
    SOURCES / "fastf1-pit-lanes-2025.json",
)


class BackendTrackGeometryTest(unittest.TestCase):
    def test_track_payload_contains_aligned_pit_lane_and_service_point(self) -> None:
        with patch.object(track_geometry, "geometry_artifacts", return_value=ARTIFACTS):
            payload = track_geometry.track_geometry_for("18")

        self.assertEqual(payload["circuit_id"], "circuit:18")
        self.assertEqual(len(payload["track_points"]), 240)
        self.assertEqual(len(payload["pit_lane_points"]), 80)
        self.assertEqual(
            sum(point["is_service_point"] for point in payload["pit_lane_points"]),
            1,
        )
        self.assertEqual(payload["pit_lane_points"][0]["path_fraction"], 0.0)
        self.assertEqual(payload["pit_lane_points"][-1]["path_fraction"], 1.0)

    def test_track_catalog_exposes_observed_default_with_provenance(self) -> None:
        class History:
            def records(self, table, **filters):
                rows = {
                    "races": (
                        HistoricalRecord(
                            "races",
                            (
                                ("race_id", "race:1141"),
                                ("circuit_id", "circuit:18"),
                                ("season", 2024),
                                ("round_number", 21),
                            ),
                        ),
                    ),
                    "race_results": (
                        HistoricalRecord(
                            "race_results",
                            (("race_id", "race:1141"), ("laps_completed", 69)),
                        ),
                    ),
                }
                return iter(
                    row
                    for row in rows[table]
                    if all(row[key] == value for key, value in filters.items())
                )

        with (
            patch.object(track_geometry, "geometry_artifacts", return_value=ARTIFACTS),
            patch.object(track_geometry, "history_repository", return_value=History()),
        ):
            payload = track_geometry.list_available_tracks()

        interlagos = next(
            track for track in payload["tracks"] if track["circuit_id"] == "circuit:18"
        )
        self.assertEqual(interlagos["default_laps"], 69)
        self.assertEqual(interlagos["default_laps_source"], "latest_observed_race")
        self.assertEqual(
            interlagos["default_laps_race"],
            {"race_id": "race:1141", "season": 2024, "round_number": 21},
        )

    def test_unavailable_history_falls_back_without_breaking_catalog(self) -> None:
        class BrokenHistory:
            def records(self, table, **filters):
                raise sqlite3.OperationalError("database is unavailable")

        with (
            patch.object(track_geometry, "geometry_artifacts", return_value=ARTIFACTS),
            patch.object(
                track_geometry, "history_repository", return_value=BrokenHistory()
            ),
        ):
            payload = track_geometry.list_available_tracks()

        monaco = next(
            track for track in payload["tracks"] if track["circuit_id"] == "circuit:6"
        )
        self.assertEqual(monaco["default_laps"], 80)
        self.assertEqual(monaco["default_laps_source"], "assumed_distance_rule")
        self.assertNotIn("default_laps_race", monaco)


if __name__ == "__main__":
    unittest.main()
