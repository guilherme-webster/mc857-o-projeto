"""Deterministic checks for the reconstructed offline geometry generator."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from scripts.rebuild_fastf1_geometry import (
    PIT_MANIFEST,
    ROOT,
    TRACK_MANIFEST,
    _csv_bytes,
    main,
    rebuild,
    reduce_pit,
    reduce_track,
)


class RebuildFastF1GeometryTest(unittest.TestCase):
    def test_track_and_pit_share_one_transform_and_one_service_point(self) -> None:
        track, transform = reduce_track(
            [
                {"Distance": 0, "X": 0, "Y": 0},
                {"Distance": 10, "X": 10, "Y": 0},
                {"Distance": 20, "X": 10, "Y": 10},
                {"Distance": 30, "X": 0, "Y": 10},
                {"Distance": float("nan"), "X": 0, "Y": 0},
            ],
            count=5,
        )
        self.assertEqual(track[0][:2], track[-1][:2])
        self.assertEqual(track[-1][2], 30)
        self.assertEqual(max(abs(value) for x, y, _ in track for value in (x, y)), 1)

        pit, service_index = reduce_pit(
            [
                {"SessionTime": 1, "X": 0, "Y": 0},
                {"SessionTime": 2, "X": 0, "Y": 5},
                {"SessionTime": 3, "X": 0, "Y": 10},
            ],
            transform,
            service_time_s=2,
            count=5,
        )
        self.assertEqual(pit[0][:2], transform.apply(0, 0))
        self.assertEqual(pit[-1][:2], transform.apply(0, 10))
        self.assertEqual(pit[service_index][2], 0.5)
        self.assertEqual(sum(point[3] for point in pit), 1)

    def test_output_uses_existing_csv_schema(self) -> None:
        raw = _csv_bytes(
            ("circuitId", "sequence", "x", "y", "pathFraction", "isServicePoint"),
            [("18", "0", "0.0", "0.0", "0.0", "false")],
        )
        self.assertEqual(
            next(csv.DictReader(io.StringIO(raw.decode())))["circuitId"], "18"
        )

    def test_rejects_versioned_fixture_as_destination_without_writing(self) -> None:
        fixture = ROOT / "tests/fixtures/trotman_v128_tracks_2025"
        original = hashlib.sha256(
            (fixture / "track_points.csv").read_bytes()
        ).hexdigest()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["--output-dir", str(fixture)])
        self.assertEqual(
            hashlib.sha256((fixture / "track_points.csv").read_bytes()).hexdigest(),
            original,
        )

    def test_manifest_records_match_rounds_and_circuits(self) -> None:
        track = json.loads(TRACK_MANIFEST.read_text(encoding="utf-8"))
        pit = json.loads(PIT_MANIFEST.read_text(encoding="utf-8"))
        track_events = {
            event["round_number"]: event for event in track["source"]["events"]
        }
        pit_events = {event["round_number"]: event for event in pit["source"]["events"]}
        self.assertEqual(len(track_events), 24)
        self.assertEqual(track_events.keys(), pit_events.keys())
        for round_number in track_events:
            self.assertEqual(
                track_events[round_number]["circuit_id"],
                pit_events[round_number]["circuit_id"],
            )

    def test_existing_directory_is_rejected_without_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["--output-dir", str(Path(directory))])

    def test_rebuild_writes_both_paths_from_recorded_event_without_network(
        self,
    ) -> None:
        track_manifest = {
            "artifact_sha256": "original-track-checksum",
            "source": {
                "year": 2025,
                "events": [
                    {
                        "round_number": 1,
                        "circuit_id": "18",
                        "circuit_name": "Interlagos",
                        "driver": "VER",
                        "lap_number": 4,
                    }
                ],
            },
        }
        pit_manifest = {
            "artifact_sha256": "original-pit-checksum",
            "transform": {"track_artifact_sha256": "original-track-checksum"},
            "source": {
                "year": 2025,
                "events": [
                    {
                        "round_number": 1,
                        "circuit_id": "18",
                        "driver": "VER",
                        "pit_in_lap": 10,
                        "pit_out_lap": 11,
                    }
                ],
            },
        }
        track_samples = [
            {"Distance": distance, "X": x, "Y": y}
            for distance, x, y in ((0, 0, 0), (10, 10, 0), (20, 10, 10), (30, 0, 10))
        ]
        pit_samples = [
            {"SessionTime": time, "X": 0, "Y": y}
            for time, y in ((1, 0), (2, 5), (3, 10))
        ]
        calls = []

        def loader(round_number, cache_dir):
            calls.append((round_number, cache_dir))
            return object()

        with (
            patch(
                "scripts.rebuild_fastf1_geometry._session_rows",
                return_value=(track_samples, pit_samples, 2.0, 0.0),
            ),
            redirect_stderr(io.StringIO()),
        ):
            track_bytes, pit_bytes, report = rebuild(
                track_manifest,
                pit_manifest,
                cache_dir=Path("/tmp/example-cache"),
                loader=loader,
            )
        track_rows = list(csv.DictReader(io.StringIO(track_bytes.decode())))
        pit_rows = list(csv.DictReader(io.StringIO(pit_bytes.decode())))
        self.assertEqual(len(track_rows), 240)
        self.assertEqual(len(pit_rows), 80)
        self.assertEqual(sum(row["isServicePoint"] == "true" for row in pit_rows), 1)
        self.assertEqual(calls, [(1, Path("/tmp/example-cache"))])
        self.assertTrue(report["reconstruction"])
        self.assertEqual(
            report["track_sha256"], hashlib.sha256(track_bytes).hexdigest()
        )
        self.assertFalse(report["matches_historical_checksums"]["track"])


if __name__ == "__main__":
    unittest.main()
