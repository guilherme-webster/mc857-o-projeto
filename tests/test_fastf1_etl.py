"""Offline session enrichment tests: identity, clocks, coverage and rollback."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from f1_simulator.adapters.datasets.fastf1_sessions import (
    FastF1DatasetError,
    FastF1SessionAdapter,
)
from f1_simulator.adapters.persistence.sqlite_history import (
    SQLiteHistoryRepository,
    SQLiteHistoryWriter,
)
from f1_simulator.application.history_etl import run_history_etl
from scripts.ingest_fastf1 import ingest, parse_args
from tests.history_support import DRIVERS, RACE, make_history, synthetic_session


class FastF1EtlTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "base.sqlite"
        self.destination = self.root / "enriched.sqlite"
        make_history(self.base)

    def enrich(self, session=None, kind="R", base=None, **options):
        dataset = FastF1SessionAdapter(
            session or synthetic_session(kind), RACE, DRIVERS, kind, **options
        )
        return run_history_etl(
            dataset,
            SQLiteHistoryWriter(),
            self.destination,
            base=base or self.base,
            overwrite=self.destination.exists(),
        )

    def test_all_families_round_trip_without_overwriting_trotman_or_interpolating(self):
        before = hashlib.sha256(self.base.read_bytes()).hexdigest()
        report = self.enrich()
        self.assertEqual(len(report["row_counts"]), 10)
        self.assertEqual(hashlib.sha256(self.base.read_bytes()).hexdigest(), before)
        repository = SQLiteHistoryRepository(self.destination)
        lap = next(repository.records("lap_observations"))
        self.assertEqual(lap["lap_time_ms"], 90000)
        self.assertEqual(lap["sector1_ms"], 30000)
        self.assertIsNone(lap["deleted"])
        self.assertIs(lap["fresh_tyre"], False)
        self.assertEqual(lap["compound"], "INTERMEDIATE")
        weather = next(repository.records("weather_observations"))
        self.assertIs(weather["rainfall"], False)
        self.assertEqual(weather["wind_speed_ms"], 0)
        car = next(repository.records("car_samples"))
        position = next(repository.records("position_samples"))
        self.assertEqual(car["session_time_ms"], 12000)
        self.assertEqual(position["session_time_ms"], 12050)
        self.assertEqual(position["x_m"], 12.3)
        self.assertEqual(position["y_m"], -4.5)
        self.assertEqual(report["source"]["warnings"]["invalid_throttle_pct"], 1)
        self.assertIsNone(car["throttle_pct"])
        self.assertEqual(car["throttle_raw_pct"], 104)
        self.assertEqual(len(list(repository.records("race_control_messages"))), 2)
        self.assertEqual(len(list(repository.records("laps"))), 6)
        self.assertEqual(
            repository.get_race("race:1141"),
            SQLiteHistoryRepository(self.base).get_race("race:1141"),
        )
        self.assertEqual(report["lap_time_comparison"]["matched"], 1)
        self.assertEqual(report["lap_time_comparison"]["different"], 1)

    def test_missing_identity_and_mismatched_event_fail_before_publication(self):
        session = synthetic_session()
        session.results[0]["DriverId"] = "unknown"
        with self.assertRaisesRegex(FastF1DatasetError, "mapping missing"):
            self.enrich(session)
        self.assertFalse(self.destination.exists())
        session = synthetic_session()
        session.event["RoundNumber"] = 20
        with self.assertRaisesRegex(FastF1DatasetError, "does not match"):
            self.enrich(session)
        with self.assertRaisesRegex(FastF1DatasetError, "requested kind"):
            self.enrich(synthetic_session("Q"), kind="R")

    def test_none_feed_is_reported_as_unavailable(self):
        session = synthetic_session()
        session.weather_data = None
        report = self.enrich(session)
        self.assertEqual(
            report["source"]["coverage"]["weather_observations"]["status"],
            "unavailable",
        )
        with self.assertRaises(FastF1DatasetError):
            self.enrich(session, strict=True)

    def test_season_and_round_selection_are_checked_before_acquisition(self):
        args = parse_args(
            [
                "--base",
                str(self.base),
                "--season",
                "2024",
                "--rounds",
                "21",
                "--output",
                str(self.destination),
            ]
        )
        calls = []

        def loader(year, stage, kind, cache, **options):
            calls.append((year, stage, kind))
            return synthetic_session(kind)

        ingest(args, loader=loader)
        self.assertEqual(calls, [(2024, 21, "R"), (2024, 21, "Q")])
        args.output = self.root / "missing-round.sqlite"
        args.rounds = [20]
        with self.assertRaisesRegex(ValueError, "rounds absent"):
            ingest(args, loader=loader)
        self.assertEqual(len(calls), 2)

    def test_unavailable_feed_is_not_empty_or_dry_and_strict_mode_rejects(self):
        session = synthetic_session()
        del session.weather_data
        report = self.enrich(session)
        self.assertEqual(
            report["source"]["coverage"]["weather_observations"]["status"],
            "unavailable",
        )
        self.assertEqual(report["row_counts"]["weather_observations"], 0)
        with self.assertRaisesRegex(FastF1DatasetError, "weather_data unavailable"):
            self.enrich(session, strict=True)

    def test_replacing_one_session_preserves_others_and_base(self):
        self.enrich()
        self.enrich(kind="Q", base=self.destination)
        first = self.enrich(base=self.destination)
        second = self.enrich(base=self.destination)
        self.assertEqual(first["canonical_sha256"], second["canonical_sha256"])
        repository = SQLiteHistoryRepository(self.destination)
        self.assertEqual(len(list(repository.records("sessions"))), 2)
        self.assertEqual(len(list(repository.records("lap_observations"))), 2)
        self.assertEqual(len(repository.reports()), 3)

    def test_telemetry_opt_out_is_visible(self):
        report = self.enrich(telemetry=False)
        self.assertEqual(report["row_counts"]["car_samples"], 0)
        self.assertEqual(
            report["source"]["coverage"]["car_samples"]["status"], "not_requested"
        )

    def test_invalid_boolean_is_not_coerced_to_true(self):
        session = synthetic_session()
        session.laps[0]["FreshTyre"] = "False"
        with self.assertRaisesRegex(FastF1DatasetError, "invalid boolean"):
            self.enrich(session)
        self.assertFalse(self.destination.exists())

    def test_partial_driver_telemetry_is_reported_and_strict_rejects(self):
        session = synthetic_session()
        session.car_data = {}
        report = self.enrich(session)
        self.assertEqual(
            report["source"]["coverage"]["car_samples"]["missing_driver_numbers"], [1]
        )
        with self.assertRaisesRegex(FastF1DatasetError, "missing telemetry"):
            self.enrich(session, strict=True)

    def test_batch_failure_keeps_previous_output_and_successful_batch_has_both_sessions(
        self,
    ):
        args = parse_args(
            [
                "--base",
                str(self.base),
                "--race-id",
                "1141",
                "--sessions",
                "R",
                "Q",
                "--output",
                str(self.destination),
                "--overwrite",
            ]
        )
        self.destination.write_bytes(b"old output remains intact")

        def failing_loader(season, round_number, kind, cache, **options):
            if kind == "Q":
                raise OSError("network interrupted")
            return synthetic_session(kind)

        with self.assertRaisesRegex(OSError, "interrupted"):
            ingest(args, loader=failing_loader)
        self.assertEqual(self.destination.read_bytes(), b"old output remains intact")
        self.assertFalse(list(self.root.glob(".fastf1-import-*")))
        reports = ingest(
            args,
            loader=lambda year, stage, kind, cache, **options: synthetic_session(kind),
        )
        self.assertEqual(len(reports), 2)
        self.assertEqual(
            len(list(SQLiteHistoryRepository(self.destination).records("sessions"))), 2
        )


if __name__ == "__main__":
    unittest.main()
