"""Exercise the reduced geometry boundary with versioned inputs and corruptions."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from f1_simulator.adapters.datasets.mock_track_geometry import (
    MockTrackDatasetAdapter,
    MockTrackDatasetError,
)
from f1_simulator.adapters.datasets.trotman import TrotmanDatasetAdapter
from f1_simulator.adapters.persistence.sqlite_race_data import SQLiteRaceDataWriter
from f1_simulator.adapters.persistence.sqlite_track_geometry import (
    SQLiteTrackGeometryRepository,
)
from f1_simulator.application.etl import run_race_etl
from f1_simulator.application.ports.track_geometry import (
    TrackGeometryNotFoundError,
    TrackGeometryRepositoryError,
)
from f1_simulator.factories.track_geometry_factory import (
    TrackGeometryFactory,
    TrackGeometryValidationError,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "trotman_v128_sample"
GEOMETRY = ROOT / "tests" / "fixtures" / "trotman_v128_tracks_2025"
MANIFESTS = ROOT / "data" / "sources"


def adapter(geometry=GEOMETRY, manifests=MANIFESTS):
    return MockTrackDatasetAdapter(
        geometry / "track_points.csv",
        manifests / "fastf1-tracks-2025.json",
        geometry / "pit_lane_points.csv",
        manifests / "fastf1-pit-lanes-2025.json",
    )


class TrackGeometryFactoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.normalized = adapter().load_geometry("circuit:18")

    def test_all_24_circuits_build_with_complete_paths(self):
        manifest = json.loads((MANIFESTS / "fastf1-tracks-2025.json").read_text())
        for event in manifest["source"]["events"]:
            with self.subTest(circuit=event["circuit_id"]):
                data = TrackGeometryFactory.build(
                    adapter().load_geometry(f"circuit:{event['circuit_id']}")
                )
                self.assertEqual(len(data.track_points), 240)
                self.assertEqual(len(data.pit_lane_points), 80)
                self.assertEqual(
                    sum(p.is_service_point for p in data.pit_lane_points), 1
                )
                self.assertAlmostEqual(
                    data.lap_length_m, event["lap_length_m"], places=3
                )
                self.assertEqual(data.track_source.source_year, 2025)
                self.assertIn("upstream", data.track_source.upstream_data_license)

    def test_rejects_invalid_track_samples_without_repairing(self):
        cases = [
            ("sequence", -1),
            ("sequence", True),
            ("sequence", 2),
            ("x_normalized", float("nan")),
            ("y_normalized", float("inf")),
            ("x_normalized", None),
            ("x_normalized", True),
            ("cumulative_distance_m", -1),
            ("cumulative_distance_m", 0),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                rows = [dict(row) for row in self.normalized.track_points]
                rows[1][key] = value
                with self.assertRaises(TrackGeometryValidationError):
                    TrackGeometryFactory.build(
                        replace(self.normalized, track_points=tuple(rows))
                    )

    def test_rejects_open_short_and_collapsed_track(self):
        rows = [dict(row) for row in self.normalized.track_points]
        rows[-1]["x_normalized"] += 0.01
        collapsed = tuple(
            dict(row, x_normalized=0, y_normalized=0)
            for row in self.normalized.track_points
        )
        for points in ((), self.normalized.track_points[:3], tuple(rows), collapsed):
            with (
                self.subTest(count=len(points)),
                self.assertRaises(TrackGeometryValidationError),
            ):
                TrackGeometryFactory.build(
                    replace(self.normalized, track_points=points)
                )

    def test_rejects_invalid_pit_progress_and_service_flags(self):
        cases = []
        for key, value in (
            ("path_fraction", 0.9),
            ("path_fraction", 2),
            ("is_service_point", "false"),
        ):
            rows = [dict(row) for row in self.normalized.pit_lane_points]
            rows[-1][key] = value
            cases.append(tuple(rows))
        for flag in (False, True):
            cases.append(
                tuple(
                    dict(row, is_service_point=flag)
                    for row in self.normalized.pit_lane_points
                )
            )
        for points in cases:
            with (
                self.subTest(points=points[-1]),
                self.assertRaises(TrackGeometryValidationError),
            ):
                TrackGeometryFactory.build(
                    replace(self.normalized, pit_lane_points=points)
                )

    def test_rejects_missing_provenance_and_mixed_source_years(self):
        for key, value in (
            ("upstream_data_license", ""),
            ("manifest_sha256", "invalid"),
            ("generated_on", "2025-01-01"),
            ("source_year", 2024),
        ):
            with self.subTest(key=key), self.assertRaises(TrackGeometryValidationError):
                source = dict(self.normalized.pit_lane_source, **{key: value})
                TrackGeometryFactory.build(
                    replace(self.normalized, pit_lane_source=source)
                )


class MockTrackAdapterTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        for source in (
            GEOMETRY / "track_points.csv",
            GEOMETRY / "pit_lane_points.csv",
            MANIFESTS / "fastf1-tracks-2025.json",
            MANIFESTS / "fastf1-pit-lanes-2025.json",
        ):
            shutil.copyfile(source, self.path / source.name)

    def test_missing_circuit_fails_instead_of_using_another_layout(self):
        with self.assertRaisesRegex(MockTrackDatasetError, "no track"):
            adapter().load_geometry("circuit:999")

    def test_rejects_changed_bytes_before_normalization(self):
        with (self.path / "track_points.csv").open("ab") as output:
            output.write(b"\n")
        with self.assertRaisesRegex(MockTrackDatasetError, "checksum mismatch"):
            adapter(self.path, self.path).load_geometry("circuit:18")

    def test_rejects_mismatched_pit_coordinate_reference(self):
        manifest_path = self.path / "fastf1-pit-lanes-2025.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["transform"]["track_artifact_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(MockTrackDatasetError, "different track artifact"):
            adapter(self.path, self.path).load_geometry("circuit:18")

    def test_rejects_missing_columns_even_with_matching_checksum(self):
        csv_path = self.path / "track_points.csv"
        csv_path.write_text(
            csv_path.read_text().replace("cumulativeDistanceMeters", "distance")
        )
        manifest_path = self.path / "fastf1-tracks-2025.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["artifact_sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        pit_path = self.path / "fastf1-pit-lanes-2025.json"
        pit = json.loads(pit_path.read_text())
        pit["transform"]["track_artifact_sha256"] = manifest["artifact_sha256"]
        pit_path.write_text(json.dumps(pit))
        with self.assertRaisesRegex(MockTrackDatasetError, "missing geometry columns"):
            adapter(self.path, self.path).load_geometry("circuit:18")

    def test_rejects_manifest_point_count_and_lap_distance_mismatch(self):
        path = self.path / "fastf1-tracks-2025.json"
        original = path.read_text()
        for key, value in (("point_count", 239), ("lap_length_m", 1)):
            manifest = json.loads(original)
            event = next(
                e for e in manifest["source"]["events"] if e["circuit_id"] == "18"
            )
            event[key] = value
            path.write_text(json.dumps(manifest))
            with self.subTest(key=key), self.assertRaises(MockTrackDatasetError):
                adapter(self.path, self.path).load_geometry("circuit:18")


class TrackGeometryEtlTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.database = self.path / "race.sqlite"
        self.report_path = self.path / "quality.json"

    def ingest(self, geometry=None):
        return run_race_etl(
            TrotmanDatasetAdapter(FIXTURE),
            SQLiteRaceDataWriter(),
            1141,
            self.database,
            self.report_path,
            geometry_dataset=geometry,
        )

    def test_roundtrip_preserves_points_units_provenance_and_circuit_link(self):
        report = self.ingest(adapter())
        expected = TrackGeometryFactory.build(adapter().load_geometry("circuit:18"))
        actual = SQLiteTrackGeometryRepository(self.database).get_geometry("circuit:18")
        self.assertEqual(actual, expected)
        self.assertEqual(report["row_counts"]["track_points"], 240)
        self.assertEqual(report["row_counts"]["pit_lane_points"], 80)
        self.assertTrue(report["warnings"]["geometry_source_year_differs_from_race"])
        self.assertEqual(json.loads(self.report_path.read_text()), report)
        with closing(sqlite3.connect(self.database)) as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(
                conn.execute(
                    "SELECT latitude_deg, longitude_deg FROM circuits"
                ).fetchone(),
                (-23.7036, -46.6997),
            )

    def test_geometry_remains_optional_and_legacy_database_is_readable(self):
        report = self.ingest()
        self.assertNotIn("geometry", report)
        with self.assertRaises(TrackGeometryNotFoundError):
            SQLiteTrackGeometryRepository(self.database).get_geometry("circuit:18")

    def test_adapter_substitution_rejects_wrong_circuit_before_publication(self):
        class WrongCircuitAdapter:
            def load_geometry(self, circuit_id):
                return adapter().load_geometry("circuit:1")

        with self.assertRaisesRegex(TrackGeometryValidationError, "different circuit"):
            self.ingest(WrongCircuitAdapter())
        self.assertFalse(self.database.exists())
        self.assertFalse(self.report_path.exists())

    def test_missing_inputs_publish_nothing(self):
        with self.assertRaises(MockTrackDatasetError):
            self.ingest(adapter(self.path))
        self.assertFalse(self.database.exists())
        self.assertFalse(self.report_path.exists())

    def test_existing_outputs_are_preserved(self):
        self.ingest(adapter())
        original = self.database.read_bytes(), self.report_path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.ingest(adapter())
        self.assertEqual(
            (self.database.read_bytes(), self.report_path.read_bytes()), original
        )

    def test_repository_does_not_create_missing_database(self):
        with self.assertRaises(TrackGeometryRepositoryError):
            SQLiteTrackGeometryRepository(self.database).get_geometry("circuit:18")
        self.assertFalse(self.database.exists())

    def test_repository_distinguishes_missing_circuit_from_corrupt_path(self):
        self.ingest(adapter())
        repository = SQLiteTrackGeometryRepository(self.database)
        with self.assertRaises(TrackGeometryNotFoundError):
            repository.get_geometry("circuit:999")
        with closing(sqlite3.connect(self.database)) as conn, conn:
            conn.execute("DELETE FROM track_points WHERE sequence=3")
        with self.assertRaises(TrackGeometryRepositoryError):
            repository.get_geometry("circuit:18")

    def test_repository_rejects_incomplete_schema(self):
        self.ingest(adapter())
        with closing(sqlite3.connect(self.database)) as conn, conn:
            conn.execute("DROP TABLE pit_lane_points")
        with self.assertRaises(TrackGeometryRepositoryError):
            SQLiteTrackGeometryRepository(self.database).get_geometry("circuit:18")

    def test_cli_ingests_geometry_from_explicit_directory(self):
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "scripts" / "ingest_trotman.py"),
                "--source",
                str(FIXTURE),
                "--race-id",
                "1141",
                "--output",
                str(self.database),
                "--report",
                str(self.report_path),
                "--geometry-dir",
                str(GEOMETRY),
            ],
            cwd=self.path,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            len(
                SQLiteTrackGeometryRepository(self.database)
                .get_geometry("circuit:18")
                .track_points
            ),
            240,
        )
