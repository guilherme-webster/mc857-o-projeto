"""Known event samples test separation, stability and publication without network."""

from collections import defaultdict
from contextlib import redirect_stdout
from dataclasses import asdict, replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from f1_simulator.application.evaluate_profiles import evaluate_profiles
from f1_simulator.domain.history import HistoricalRecord
from f1_simulator.domain.profile_evaluation import EvaluationPlan, compare_profiles
from scripts.evaluate_profiles import load_plan, main, publish_report
from tests.test_driver_profile import CONFIG, assess, record, sample, status, weather
from f1_simulator.domain.driver_profile import estimate_profiles


def change(row, **values):
    data = row.as_dict() | values
    return HistoricalRecord(row.table, tuple(data.items()))


class MemoryHistory:
    """Canonical in-memory observations with explicit synthetic provenance."""

    def __init__(self):
        self.tables = defaultdict(list)
        self.calls = []
        self.sources = []
        self.tables["drivers"] = [
            HistoricalRecord("drivers", tuple(data.items()))
            for data in (
                dict(
                    driver_id="driver:830", given_name="Max", family_name="Verstappen"
                ),
                dict(driver_id="driver:839", given_name="Esteban", family_name="Ocon"),
            )
        ]
        for i in range(1, 5):
            session, race = f"session:{i}:R", f"race:{i}"
            self.sources.append(
                {
                    "source": {
                        "session_id": session,
                        "source_name": "synthetic-test",
                        "missing_columns": {"lap_observations": []},
                    }
                }
            )
            self.tables["sessions"].append(
                record(
                    "sessions", session_id=session, race_id=race, kind="R", name="Race"
                )
            )
            self.tables["races"].append(
                HistoricalRecord(
                    "races",
                    tuple(
                        dict(
                            race_id=race,
                            race_date=f"2024-0{i}-01",
                            season=2024,
                            name=f"Event {i}",
                            circuit_id=f"circuit:{i}",
                        ).items()
                    ),
                )
            )
            self.tables["weather_observations"].append(
                change(weather(), session_id=session)
            )
            self.tables["session_status_events"].append(
                change(status(), session_id=session)
            )
            for n, driver in enumerate(("driver:830", "driver:839"), 1):
                self.tables["session_drivers"].append(
                    record(
                        "session_drivers",
                        session_id=session,
                        driver_id=driver,
                        driver_number=n,
                    )
                )
                self.tables["race_results"].append(
                    HistoricalRecord(
                        "race_results",
                        tuple(
                            dict(
                                race_id=race, driver_id=driver, team_id=f"team:{n}"
                            ).items()
                        ),
                    )
                )
            for row in sample():
                self.tables["lap_observations"].append(change(row, session_id=session))

    def records(self, table, **filters):
        self.calls.append((table, filters))
        return iter(
            row
            for row in self.tables[table]
            if all(row[k] == v for k, v in filters.items())
        )

    def reports(self):
        # Return a detached manifest, matching the repository contract.
        return json.loads(json.dumps(self.sources))


def plan(**changes):
    return replace(
        EvaluationPlan(
            "test",
            ("session:1:R", "session:2:R"),
            ("session:3:R", "session:4:R"),
            replace(CONFIG, min_events=2),
        ),
        **changes,
    )


class ProfileEvaluationTests(unittest.TestCase):
    def test_known_pp_shifts_are_not_relative_percent_changes(self):
        profiles, _ = estimate_profiles(
            assess(sample()), ("driver:830", "driver:839"), CONFIG
        )
        a = replace(profiles[0], pace_delta_pct=2.0, consistency_mad_pct=0.5)
        b = replace(profiles[0], pace_delta_pct=3.0, consistency_mad_pct=0.2)
        rows, summary = compare_profiles((a,), (b,))
        self.assertEqual(rows[0].pace_shift_pp, 1.0)
        self.assertAlmostEqual(rows[0].consistency_shift_pp, -0.3)
        self.assertEqual(summary.median_absolute_pace_shift_pp, 1.0)
        self.assertEqual(summary.paired_drivers, 1)

    def test_invalid_plan_is_rejected(self):
        for changes in (
            {"development_sessions": ()},
            {"validation_sessions": ("session:1:R",)},
            {"validation_sessions": ("session:3:R", "session:3:R")},
            {"validation_sessions": ("",)},
            {"evaluation_version": "future"},
            {"profile_method_version": "future"},
            {"config": {}},
            {"development_sessions": "session:1:R"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                plan(**changes)

    def test_reproduction_and_reordered_selection(self):
        repository = MemoryHistory()
        first = evaluate_profiles(repository, plan())
        second = evaluate_profiles(
            repository, plan(development_sessions=("session:2:R", "session:1:R"))
        )
        self.assertEqual(first, second)
        self.assertEqual(first.summary.paired_drivers, 2)
        self.assertAlmostEqual(first.summary.median_absolute_pace_shift_pp, 0)
        self.assertEqual(len(first.coverage), 4)
        self.assertEqual(first.coverage[0].coverage_pct, 100)
        self.assertTrue(first.validation_after_development)

    def test_validation_changes_never_change_development(self):
        repository = MemoryHistory()
        original = evaluate_profiles(repository, plan())
        repository.tables["lap_observations"] = [
            change(row, lap_time_ms=row["lap_time_ms"] + 9000)
            if row["session_id"] in plan().validation_sessions
            and row["driver_id"] == "driver:830"
            else row
            for row in repository.tables["lap_observations"]
        ]
        changed = evaluate_profiles(repository, plan())
        self.assertEqual(original.development, changed.development)
        self.assertNotEqual(original.validation.profiles, changed.validation.profiles)
        self.assertEqual(original.plan_sha256, changed.plan_sha256)
        self.assertNotEqual(
            original.plan_sha256,
            evaluate_profiles(
                repository, plan(config=replace(CONFIG, min_events=1))
            ).plan_sha256,
        )

    def test_race_alias_is_rejected_before_lap_reads(self):
        repository = MemoryHistory()
        repository.tables["sessions"][2] = change(
            repository.tables["sessions"][2], race_id="race:1"
        )
        with self.assertRaisesRegex(ValueError, "race must occur exactly once"):
            evaluate_profiles(repository, plan())
        self.assertFalse(
            any(table == "lap_observations" for table, _ in repository.calls)
        )

    def test_nonrace_or_missing_session_fails_clearly(self):
        repository = MemoryHistory()
        repository.tables["sessions"][2] = change(
            repository.tables["sessions"][2], kind="Q"
        )
        with self.assertRaisesRegex(ValueError, "race session"):
            evaluate_profiles(repository, plan())
        with self.assertRaisesRegex(ValueError, "provenance"):
            evaluate_profiles(repository, plan(validation_sessions=("missing",)))

    def test_chronology_is_reported_without_changing_the_split(self):
        result = evaluate_profiles(
            MemoryHistory(),
            plan(
                development_sessions=("session:4:R",),
                validation_sessions=("session:1:R",),
            ),
        )
        self.assertFalse(result.validation_after_development)
        self.assertIn("validation_not_strictly_after_development", result.warnings)
        self.assertEqual(result.plan.development_sessions, ("session:4:R",))

    def test_empty_validation_retains_entrants_and_nulls(self):
        repository = MemoryHistory()
        repository.tables["lap_observations"] = [
            r
            for r in repository.tables["lap_observations"]
            if r["session_id"] in plan().development_sessions
        ]
        result = evaluate_profiles(repository, plan())
        self.assertEqual(result.summary.paired_drivers, 0)
        self.assertIsNone(result.summary.median_absolute_pace_shift_pp)
        self.assertEqual(result.coverage[2].participants, 2)
        self.assertIsNone(result.coverage[2].coverage_pct)
        self.assertIsNone(result.comparisons[0].pace_shift_pp)
        self.assertIn(
            "validation:no_lap_observations", result.comparisons[0].unavailable_reasons
        )

    def test_driver_absence_and_min_events_are_not_zero_effect(self):
        profiles, _ = estimate_profiles(
            assess(sample()), ("driver:830", "driver:839"), CONFIG
        )
        missing = replace(
            profiles[1],
            pace_delta_pct=None,
            consistency_mad_pct=None,
            unavailable_reason="insufficient_events",
        )
        rows, summary = compare_profiles(profiles, (missing,))
        self.assertEqual(rows[0].unavailable_reasons, ("validation:driver_absent",))
        self.assertIn("validation:insufficient_events", rows[1].unavailable_reasons)
        self.assertEqual(summary.paired_drivers, 0)

    def test_coverage_exclusions_and_event_descriptions(self):
        repository = MemoryHistory()
        repository.tables["lap_observations"][0] = change(
            repository.tables["lap_observations"][0], accurate=None
        )
        result = evaluate_profiles(repository, plan())
        self.assertEqual(result.coverage[0].input_laps, 6)
        self.assertEqual(result.coverage[0].compared_laps, 0)
        self.assertIn(("accurate_unknown", 1), result.coverage[0].exclusions)
        self.assertEqual(result.coverage[0].race_name, "Event 1")
        self.assertEqual(len(result.event_estimates), 8)

    def test_protocol_loading_requires_explicit_keys_and_versions(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_text(json.dumps(asdict(plan())))
            self.assertEqual(load_plan(path), plan())
            data = asdict(plan())
            data.pop("config")
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                load_plan(path)

    def test_reports_are_unique_complete_and_failure_preserves_prior_output(self):
        result = evaluate_profiles(MemoryHistory(), plan())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = publish_report(result, root, plots=False)
            before = (first / "evaluation.json").read_bytes()
            second = publish_report(result, root, plots=False)
            self.assertNotEqual(first, second)
            self.assertEqual(before, (second / "evaluation.json").read_bytes())
            self.assertIn("Max Verstappen", (first / "stability.csv").read_text())
            with patch(
                "scripts.evaluate_profiles.plot_evaluation",
                side_effect=RuntimeError("plot failure"),
            ):
                with self.assertRaises(RuntimeError):
                    publish_report(result, root)
            self.assertEqual(set(root.iterdir()), {first, second})
            self.assertEqual(before, (first / "evaluation.json").read_bytes())

    def test_cli_uses_plan_and_creates_its_output_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "plan.json"
            path.write_text(json.dumps(asdict(plan())))
            stream = io.StringIO()
            with (
                patch(
                    "f1_simulator.adapters.persistence.sqlite_history.SQLiteHistoryRepository",
                    return_value=MemoryHistory(),
                ),
                redirect_stdout(stream),
            ):
                code = main(
                    [
                        "--database",
                        "injected.sqlite",
                        "--plan",
                        str(path),
                        "--output-root",
                        str(root / "outputs"),
                        "--without-plots",
                    ]
                )
            self.assertEqual(code, 0)
            report = Path(stream.getvalue().strip())
            self.assertTrue((report / "evaluation.json").exists())
            self.assertTrue((report / "coverage.csv").exists())

    def test_minimum_events_is_not_relaxed_for_validation(self):
        result = evaluate_profiles(
            MemoryHistory(), plan(config=replace(CONFIG, min_events=3))
        )
        self.assertEqual(result.summary.paired_drivers, 0)
        self.assertIn(
            "validation:insufficient_events", result.comparisons[0].unavailable_reasons
        )
        self.assertTrue(
            all(row.pace_delta_pct is not None for row in result.event_estimates)
        )

    def test_empty_participants_keep_csv_schema(self):
        repository = MemoryHistory()
        repository.tables["session_drivers"] = []
        repository.tables["lap_observations"] = []
        result = evaluate_profiles(repository, plan())
        with tempfile.TemporaryDirectory() as temporary:
            directory = publish_report(result, Path(temporary), plots=False)
            header = (directory / "stability.csv").read_text().splitlines()[0]
            self.assertIn("pace_shift_pp", header)
            self.assertEqual(result.summary.total_drivers, 0)


if __name__ == "__main__":
    unittest.main()
