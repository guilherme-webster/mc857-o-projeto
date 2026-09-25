"""Verify the HTTP-facing track contract includes its associated pit lane."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = str(ROOT / "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.services import track_geometry  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
