"""Matched pairing, reference scope and absence cannot be inferred from rankings."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from f1_simulator.domain.driver_profile import estimate_profiles
from f1_simulator.domain.profile_reliability import BootstrapConfig
from f1_simulator.domain.teammates import compare_teammates, context_reference
from f1_simulator.application.analyze_teammates import analyze_teammates
from scripts.analyze_teammates import publish
from tests.test_driver_profile import CONFIG, assess, sample
from tests.test_profile_evaluation import MemoryHistory, plan, change

BOOT = BootstrapConfig(100, 42)


def paired_profiles():
    profiles, _ = estimate_profiles(
        assess(sample()), ("driver:830", "driver:839"), CONFIG
    )
    return tuple(
        replace(p, contexts=tuple(replace(c, team_id="team:9") for c in p.contexts))
        for p in profiles
    )


def membership(profiles):
    return tuple(
        sorted(
            {
                (c.context.session_id, c.team_id, p.driver_id)
                for p in profiles
                for c in p.contexts
            }
        )
    )


class TeammateTests(unittest.TestCase):
    def test_known_gap_and_order_invariance(self):
        profiles = paired_profiles()
        pairs = compare_teammates(profiles, membership(profiles), CONFIG, BOOT)
        self.assertEqual(len(pairs), 1)
        self.assertAlmostEqual(pairs[0]["gap_pct"], 100 * (92000 - 102000) / 97000)
        self.assertEqual(pairs[0]["shared_contexts"], 1)
        self.assertIsNone(pairs[0]["interval_pct"])
        self.assertEqual(
            pairs,
            compare_teammates(
                tuple(reversed(profiles)),
                tuple(reversed(membership(profiles))),
                CONFIG,
                BOOT,
            ),
        )
        swapped = tuple(
            replace(p, contexts=profiles[1 - i].contexts)
            for i, p in enumerate(profiles)
        )
        self.assertAlmostEqual(
            compare_teammates(swapped, membership(swapped), CONFIG, BOOT)[0]["gap_pct"],
            -pairs[0]["gap_pct"],
        )

    def test_different_contexts_and_insufficient_events_are_not_zero(self):
        profiles = paired_profiles()
        other = replace(
            profiles[1],
            contexts=tuple(
                replace(c, context=replace(c.context, compound="HARD"))
                for c in profiles[1].contexts
            ),
        )
        rows = compare_teammates(
            (profiles[0], other), membership(profiles), CONFIG, BOOT
        )
        self.assertEqual(rows[0]["union_contexts"], 2)
        self.assertEqual(rows[0]["shared_contexts"], 0)
        self.assertEqual(rows[0]["unavailable_reason"], "no_shared_contexts")
        self.assertIsNone(rows[0]["gap_pct"])
        rows = compare_teammates(
            profiles, membership(profiles), replace(CONFIG, min_events=2), BOOT
        )
        self.assertEqual(rows[0]["unavailable_reason"], "insufficient_shared_events")

    def test_different_teams_are_not_compared(self):
        profiles = paired_profiles()
        other = replace(
            profiles[1],
            contexts=tuple(replace(c, team_id="team:6") for c in profiles[1].contexts),
        )
        self.assertEqual(
            compare_teammates(
                (profiles[0], other), membership((profiles[0], other)), CONFIG, BOOT
            ),
            (),
        )

    def test_team_changes_remain_separate_pairs(self):
        profiles = []
        for p in paired_profiles():
            original = p.contexts[0]
            moved = replace(
                original,
                team_id="team:6",
                context=replace(
                    original.context, session_id="session:2:R", race_id="race:2"
                ),
            )
            profiles.append(replace(p, contexts=(original, moved)))
        profiles = tuple(profiles)
        rows = compare_teammates(
            profiles, membership(profiles), replace(CONFIG, min_events=2), BOOT
        )
        self.assertEqual(len(rows), 2)
        self.assertTrue(
            all(r["shared_events"] == 1 and r["gap_pct"] is None for r in rows)
        )

    def test_missing_contexts_keep_roster_pair(self):
        profiles = paired_profiles()
        rows = compare_teammates(
            tuple(replace(p, contexts=()) for p in profiles),
            membership(profiles),
            CONFIG,
            BOOT,
        )
        self.assertEqual(rows[0]["candidate_events"], 1)
        self.assertEqual(rows[0]["shared_events"], 0)
        self.assertIsNone(rows[0]["gap_pct"])

    def test_duplicate_membership_and_context_are_rejected(self):
        profiles = paired_profiles()
        entries = membership(profiles)
        with self.assertRaises(ValueError):
            compare_teammates(profiles, entries + entries[:1], CONFIG, BOOT)
        invalid = (replace(profiles[0], contexts=profiles[0].contexts * 2), profiles[1])
        with self.assertRaises(ValueError):
            compare_teammates(invalid, entries, CONFIG, BOOT)

    def test_reference_is_context_specific_and_equal_driver_weight(self):
        profiles = paired_profiles()
        context = profiles[0].contexts[0].context
        reference = context_reference(profiles, context)
        self.assertEqual(reference["reference_lap_time_ms"], 97000)
        self.assertEqual(reference["drivers"], 2)
        self.assertEqual(reference["laps"], 6)
        weighted = (
            replace(
                profiles[0],
                contexts=tuple(replace(c, laps=100) for c in profiles[0].contexts),
            ),
            profiles[1],
        )
        self.assertEqual(
            context_reference(weighted, context)["reference_lap_time_ms"], 97000
        )
        with self.assertRaises(ValueError):
            context_reference(profiles, replace(context, circuit_id="other"))
        with self.assertRaises(ValueError):
            context_reference(profiles[:1], context)
        for p in profiles:
            c = p.contexts[0]
            self.assertAlmostEqual(
                reference["reference_lap_time_ms"] * (1 + c.pace_delta_pct / 100),
                c.observed_median_ms,
            )

    def test_events_have_equal_weight_not_laps_or_context_count(self):
        original = paired_profiles()
        profiles = []
        for i, p in enumerate(original):
            cs = []
            for event, count, a, b in ((1, 1, 90000, 100000), (2, 3, 100000, 100000)):
                for j in range(count):
                    c = p.contexts[0]
                    cs.append(
                        replace(
                            c,
                            context=replace(
                                c.context,
                                session_id=f"session:{event}:R",
                                race_id=f"race:{event}",
                                lap_window_start=1 + 10 * j,
                            ),
                            observed_median_ms=a if i == 0 else b,
                            reference_ms=(a + b) / 2,
                        )
                    )
            profiles.append(replace(p, contexts=tuple(cs)))
        profiles = tuple(profiles)
        row = compare_teammates(
            profiles, membership(profiles), replace(CONFIG, min_events=2), BOOT
        )[0]
        self.assertAlmostEqual(row["gap_pct"], -10000 / 95000 * 100 / 2)
        self.assertEqual(row["shared_events"], 2)
        self.assertAlmostEqual(row["interval_pct"][0], -10000 / 95000 * 100)
        self.assertEqual(row["interval_pct"][1], 0)

    def test_application_does_not_query_unselected_sessions_and_reproduces(self):
        repository = MemoryHistory()
        repository.tables["race_results"] = [
            change(r, team_id="team:9") for r in repository.tables["race_results"]
        ]
        original = repository.records

        def guarded(table, **filters):
            self.assertNotIn(filters.get("session_id"), plan().validation_sessions)
            return original(table, **filters)

        repository.records = guarded
        result = analyze_teammates(
            repository,
            session_ids=plan().development_sessions,
            config=plan().config,
            bootstrap=BOOT,
        )
        self.assertEqual(len(result["pairs"]), 1)
        self.assertEqual(
            result,
            analyze_teammates(
                repository,
                session_ids=plan().development_sessions,
                config=plan().config,
                bootstrap=BOOT,
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = publish(result, root, plots=False)
            self.assertTrue((target / "references.csv").exists())
            with patch(
                "scripts.analyze_teammates.os.rename", side_effect=OSError("failure")
            ):
                with self.assertRaises(OSError):
                    publish(result, root, plots=False)
            self.assertEqual(list(root.iterdir()), [target])


if __name__ == "__main__":
    unittest.main()
