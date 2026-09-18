"""Guard the reserved sample and verify descriptive event influence."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from f1_simulator.application.analyze_development import analyze_development
from f1_simulator.domain.profile_reliability import BootstrapConfig
from scripts.analyze_profile_development import publish
from tests.test_profile_evaluation import MemoryHistory, plan

BOOT = BootstrapConfig(100, 42)


class DevelopmentAnalysisTests(unittest.TestCase):
    def test_reserved_records_are_never_requested(self):
        repository = MemoryHistory()
        original = repository.records

        def guarded(table, **filters):
            self.assertNotIn(filters.get("session_id"), plan().validation_sessions)
            return original(table, **filters)

        repository.records = guarded
        first = analyze_development(repository, plan(), bootstrap=BOOT)
        self.assertFalse(first["reserved_metrics_computed"])
        for result in first["results"]:
            self.assertEqual(result["run"]["session_ids"], plan().development_sessions)
        # Entire held-out feeds can disappear without changing the analysis.
        other = MemoryHistory()
        for table, rows in other.tables.items():
            other.tables[table] = [
                r
                for r in rows
                if r.as_dict().get("session_id") not in plan().validation_sessions
            ]
        self.assertEqual(first, analyze_development(other, plan(), bootstrap=BOOT))

    def test_leaving_one_of_two_events_respects_minimum(self):
        result = analyze_development(MemoryHistory(), plan(), bootstrap=BOOT)
        self.assertTrue(
            all(
                r["pace_pct"] is None and r["remaining_events"] == 1
                for r in result["results"][0]["event_influence"]
            )
        )

    def test_known_identical_events_have_zero_influence(self):
        p = plan(
            development_sessions=("session:1:R", "session:2:R", "session:3:R"),
            validation_sessions=("session:4:R",),
        )
        result = analyze_development(MemoryHistory(), p, bootstrap=BOOT)
        self.assertTrue(
            all(
                r["pace_shift_pp"] == 0 and r["mad_shift_pp"] == 0
                for r in result["results"][0]["event_influence"]
            )
        )
        self.assertEqual(
            result, analyze_development(MemoryHistory(), p, bootstrap=BOOT)
        )
        changed = analyze_development(
            MemoryHistory(), p, bootstrap=replace(BOOT, seed=4)
        )
        self.assertNotEqual(result["analysis_sha256"], changed["analysis_sha256"])

    def test_known_nonzero_event_influence(self):
        from f1_simulator.application.profile_drivers import profile_drivers

        p = plan(
            development_sessions=("session:1:R", "session:2:R", "session:3:R"),
            validation_sessions=("session:4:R",),
        )
        run = profile_drivers(
            MemoryHistory(), session_ids=p.development_sessions, config=p.config
        )
        profile = run.profiles[0]
        values = {"race:1": 0.0, "race:2": 2.0, "race:3": 10.0}
        profile = replace(
            profile,
            pace_delta_pct=2.0,
            contexts=tuple(
                replace(c, pace_delta_pct=values[c.context.race_id])
                for c in profile.contexts
            ),
        )
        run = replace(run, profiles=(profile,) + run.profiles[1:])
        with patch(
            "f1_simulator.application.analyze_development.profile_drivers",
            return_value=run,
        ):
            result = analyze_development(MemoryHistory(), p, bootstrap=BOOT)
        rows = {
            r["omitted_race_id"]: r
            for r in result["results"][0]["event_influence"]
            if r["driver_id"] == profile.driver_id
        }
        self.assertEqual(rows["race:1"]["pace_shift_pp"], 4.0)
        self.assertEqual(rows["race:2"]["pace_shift_pp"], 3.0)
        self.assertEqual(rows["race:3"]["pace_shift_pp"], -1.0)

    def test_publication_failure_does_not_replace_previous_result(self):
        result = analyze_development(MemoryHistory(), plan(), bootstrap=BOOT)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = publish(result, root, plots=False)
            self.assertFalse(
                json.loads((folder / "analysis.json").read_text())[
                    "reserved_metrics_computed"
                ]
            )
            with patch(
                "scripts.analyze_profile_development.os.rename",
                side_effect=OSError("failure"),
            ):
                with self.assertRaises(OSError):
                    publish(deepcopy(result), root, plots=False)
            self.assertEqual(list(root.iterdir()), [folder])


if __name__ == "__main__":
    unittest.main()
