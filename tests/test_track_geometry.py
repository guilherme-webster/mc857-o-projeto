from __future__ import annotations

import csv
import hashlib
import json
import unittest
from pathlib import Path

class TrackGeometryDataTest(unittest.TestCase):
    def test_versioned_interlagos_fixture_matches_its_manifest(self) -> None:
        root = Path(__file__).resolve().parents[1]
        fixture = (
            root
            / "tests"
            / "fixtures"
            / "trotman_v128_sample"
            / "track_points.csv"
        )
        manifest_path = (
            root / "data" / "sources" / "fastf1-track-interlagos-2024.json"
        )
        with fixture.open(encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source))
        with manifest_path.open(encoding="utf-8") as source:
            manifest = json.load(source)

        self.assertEqual(len(rows), manifest["transform"]["point_count"])
        self.assertEqual({row["circuitId"] for row in rows}, {"18"})
        self.assertEqual(
            [int(row["sequence"]) for row in rows], list(range(len(rows)))
        )
        distances = [float(row["cumulativeDistanceMeters"]) for row in rows]
        self.assertEqual(distances, sorted(distances))
        self.assertAlmostEqual(distances[-1], manifest["transform"]["lap_length_m"])
        self.assertEqual(
            (rows[0]["x"], rows[0]["y"]),
            (rows[-1]["x"], rows[-1]["y"]),
        )
        self.assertEqual(
            hashlib.sha256(fixture.read_bytes()).hexdigest(),
            manifest["artifact_sha256"],
        )

    def test_2025_fixture_contains_every_calendar_track(self) -> None:
        root = Path(__file__).resolve().parents[1]
        fixture = (
            root
            / "tests"
            / "fixtures"
            / "trotman_v128_tracks_2025"
            / "track_points.csv"
        )
        manifest_path = root / "data" / "sources" / "fastf1-tracks-2025.json"
        with fixture.open(encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source))
        with manifest_path.open(encoding="utf-8") as source:
            manifest = json.load(source)

        expected_ids = {
            "1", "3", "4", "6", "7", "9", "11", "13", "14", "15",
            "17", "18", "21", "22", "24", "32", "39", "69", "70",
            "73", "77", "78", "79", "80",
        }
        self.assertEqual({row["circuitId"] for row in rows}, expected_ids)
        self.assertEqual(len(rows), 24 * 240)
        self.assertEqual(manifest["transform"]["track_count"], 24)
        self.assertEqual(len(manifest["source"]["events"]), 24)
        self.assertEqual(
            hashlib.sha256(fixture.read_bytes()).hexdigest(),
            manifest["artifact_sha256"],
        )
        for circuit_id in expected_ids:
            track_rows = [row for row in rows if row["circuitId"] == circuit_id]
            self.assertEqual(
                [int(row["sequence"]) for row in track_rows], list(range(240))
            )
            self.assertEqual(
                (track_rows[0]["x"], track_rows[0]["y"]),
                (track_rows[-1]["x"], track_rows[-1]["y"]),
            )

    def test_2025_pit_lanes_match_tracks_and_manifest(self) -> None:
        root = Path(__file__).resolve().parents[1]
        fixture_dir = root / "tests" / "fixtures" / "trotman_v128_tracks_2025"
        pit_fixture = fixture_dir / "pit_lane_points.csv"
        track_fixture = fixture_dir / "track_points.csv"
        manifest_path = root / "data" / "sources" / "fastf1-pit-lanes-2025.json"
        with pit_fixture.open(encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source))
        with manifest_path.open(encoding="utf-8") as source:
            manifest = json.load(source)

        circuit_ids = {row["circuitId"] for row in rows}
        self.assertEqual(len(circuit_ids), 24)
        self.assertEqual(len(rows), 24 * 80)
        self.assertEqual(manifest["transform"]["track_count"], 24)
        self.assertEqual(len(manifest["source"]["events"]), 24)
        self.assertEqual(
            hashlib.sha256(pit_fixture.read_bytes()).hexdigest(),
            manifest["artifact_sha256"],
        )
        self.assertEqual(
            hashlib.sha256(track_fixture.read_bytes()).hexdigest(),
            manifest["transform"]["track_artifact_sha256"],
        )
        for circuit_id in circuit_ids:
            pit_rows = [row for row in rows if row["circuitId"] == circuit_id]
            self.assertEqual(
                [int(row["sequence"]) for row in pit_rows], list(range(80))
            )
            self.assertEqual(float(pit_rows[0]["pathFraction"]), 0)
            self.assertEqual(float(pit_rows[-1]["pathFraction"]), 1)
            self.assertEqual(
                sum(row["isServicePoint"] == "true" for row in pit_rows), 1
            )


if __name__ == "__main__":
    unittest.main()
