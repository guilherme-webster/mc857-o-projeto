"""Exercise the model against the real ETL contract without network or UI."""

from dataclasses import replace
from datetime import timedelta
import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

from f1_simulator.adapters.datasets.fastf1_sessions import (
    FastF1SessionAdapter,
    MAPPINGS,
)
from f1_simulator.adapters.persistence.sqlite_history import (
    SQLiteHistoryRepository,
    SQLiteHistoryWriter,
)
from f1_simulator.application.history_etl import run_history_etl
from f1_simulator.application.profile_drivers import profile_drivers
from tests.history_support import make_history, synthetic_session, RACE, DRIVERS
from tests.test_driver_profile import CONFIG


class ProfileDriversIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name) / "history.sqlite"
        self.output = Path(self.directory.name) / "sessions.sqlite"
        make_history(self.base)
        session = synthetic_session()
        session.results.append({"DriverNumber": "31", "DriverId": "ocon"})
        template = session.laps[0]
        session.laps = []
        for driver, times in (("1", (90, 92, 94)), ("31", (100, 102, 104))):
            for number, seconds in enumerate(times, 2):
                session.laps.append(
                    dict(
                        template,
                        DriverNumber=driver,
                        LapNumber=number,
                        LapTime=timedelta(seconds=seconds),
                        LapStartTime=timedelta(seconds=100),
                        Time=timedelta(seconds=210),
                        Deleted=False,
                        TrackStatus="1",
                    )
                )
        session.weather_data[0]["Time"] = timedelta(seconds=90)
        # Include all declared lap fields; None in an existing pit column
        # means no pit event, while an absent column has unknown coverage.
        for row in session.laps:
            for column in MAPPINGS["lap_observations"]:
                row.setdefault(column, None)
        adapter = FastF1SessionAdapter(
            session, race=RACE, driver_refs=DRIVERS, kind="R", telemetry=False
        )
        run_history_etl(adapter, SQLiteHistoryWriter(), self.output, base=self.base)
        self.repository = SQLiteHistoryRepository(self.output)

    def test_roundtrip_port_reproducibility_and_source_preservation(self):
        before = hashlib.sha256(self.output.read_bytes()).hexdigest()
        result = profile_drivers(
            self.repository, session_ids=("session:1141:R",), config=CONFIG
        )
        again = profile_drivers(
            self.repository, session_ids=("session:1141:R",), config=CONFIG
        )
        self.assertEqual(result, again)
        self.assertEqual(hashlib.sha256(self.output.read_bytes()).hexdigest(), before)
        self.assertEqual(len(result.source_reports_json), 2)
        self.assertEqual(result.profiles[0].contexts[0].reference_ms, 97000)
        self.assertEqual(result.profiles[0].contexts[0].team_id, "team:9")
        self.assertEqual(result.profiles[1].contexts[0].team_id, "team:214")
        self.assertIn('"canonical_sha256"', result.source_reports_json[0])

    def test_reject_absent_or_duplicate_selection_and_unenriched_base(self):
        for selection in (
            (),
            ("session:1141:Q",),
            ("session:1141:R", "session:1141:R"),
        ):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                profile_drivers(self.repository, session_ids=selection, config=CONFIG)
        with self.assertRaisesRegex(ValueError, "enrich"):
            profile_drivers(
                SQLiteHistoryRepository(self.base),
                session_ids=("session:1141:R",),
                config=CONFIG,
            )

    def test_qualifying_is_not_a_race_sample(self):
        parent = self.repository

        class QualifyingPort:
            def reports(self):
                return parent.reports()

            def records(self, table, **filters):
                for row in parent.records(table, **filters):
                    if table == "sessions":
                        row = replace(
                            row,
                            fields=tuple(
                                (k, "Q" if k == "kind" else v) for k, v in row.fields
                            ),
                        )
                    yield row

        with self.assertRaisesRegex(ValueError, "race"):
            profile_drivers(
                QualifyingPort(), session_ids=("session:1141:R",), config=CONFIG
            )

    def test_missing_team_and_no_laps_do_not_drop_participants(self):
        parent = self.repository

        class IncompletePort:
            def reports(self):
                return parent.reports()

            def records(self, table, **filters):
                for row in parent.records(table, **filters):
                    if table == "race_results":
                        continue
                    if table == "lap_observations" and row["driver_id"] == "driver:839":
                        continue
                    yield row

        result = profile_drivers(
            IncompletePort(), session_ids=("session:1141:R",), config=CONFIG
        )
        self.assertEqual(len(result.profiles), 2)
        self.assertEqual(
            result.profiles[0].exclusions, (("missing_or_ambiguous_team", 3),)
        )
        self.assertEqual(result.profiles[1].unavailable_reason, "no_lap_observations")

    def test_missing_lap_column_cannot_mean_no_pit_stop(self):
        parent = self.repository

        class IncompleteSchemaPort:
            def reports(self):
                reports = parent.reports()
                for report in reports:
                    if report["source"].get("session_id"):
                        report["source"]["missing_columns"]["lap_observations"] = [
                            "an upstream field"
                        ]
                return reports

            def records(self, table, **filters):
                return parent.records(table, **filters)

        result = profile_drivers(
            IncompleteSchemaPort(), session_ids=("session:1141:R",), config=CONFIG
        )
        self.assertTrue(all(p.pace_delta_pct is None for p in result.profiles))
        self.assertTrue(
            all(
                "lap_schema_incomplete_or_unknown" in lap.exclusions
                for lap in result.laps
            )
        )

    def test_cli_uses_same_case_without_optional_plot_dependency(self):
        from scripts.profile_drivers import main

        stream = io.StringIO()
        with redirect_stdout(stream):
            code = main(
                [
                    "--database",
                    str(self.output),
                    "--sessions",
                    "session:1141:R",
                    "--lap-window",
                    "10",
                    "--tyre-age-window",
                    "10",
                    "--weather-max-age-ms",
                    "120000",
                    "--min-laps-per-context",
                    "3",
                    "--min-drivers-per-context",
                    "2",
                    "--min-events",
                    "1",
                ]
            )
        self.assertEqual(code, 0)
        result = json.loads(stream.getvalue())
        self.assertEqual(result["method_version"], "contextual-pace-v1")
        self.assertEqual(result["profiles"][0]["contexts"][0]["reference_ms"], 97000)
        self.assertIn("not_estimated", result["uncertainty"])

    def test_names_come_from_canonical_catalog_and_keep_ids(self):
        from scripts.profile_drivers import driver_labels

        run = profile_drivers(
            self.repository, session_ids=("session:1141:R",), config=CONFIG
        )
        self.assertEqual(
            driver_labels(run),
            {"driver:830": "Max Verstappen", "driver:839": "Esteban Ocon"},
        )
        self.assertEqual(run.profiles[0].driver_id, "driver:830")
        self.assertEqual(run.profiles[0].contexts[0].reference_ms, 97000)

    def test_homonyms_are_distinct_and_missing_name_has_fallback(self):
        from scripts.profile_drivers import driver_labels

        run = profile_drivers(
            self.repository, session_ids=("session:1141:R",), config=CONFIG
        )
        same = replace(
            run,
            driver_names=(("driver:830", "Alex Smith"), ("driver:839", "Alex Smith")),
        )
        labels = driver_labels(same)
        self.assertEqual(labels["driver:830"], "Alex Smith (driver:830)")
        self.assertNotEqual(labels["driver:830"], labels["driver:839"])
        self.assertEqual(
            driver_labels(replace(run, driver_names=()))["driver:830"], "driver:830"
        )


if __name__ == "__main__":
    unittest.main()
