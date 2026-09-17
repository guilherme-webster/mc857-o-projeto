"""Regression tests for grouping sensitivity and event-level uncertainty."""

from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from f1_simulator.application.analyze_contexts import analyze_contexts
from f1_simulator.application.evaluate_profiles import evaluate_profiles
from f1_simulator.domain.context_sensitivity import ContextVariant, separate_stints
from f1_simulator.domain.driver_profile import estimate_profiles
from f1_simulator.domain.profile_reliability import BootstrapConfig, profile_support
from scripts.analyze_profile_contexts import publish_study
from tests.test_driver_profile import CONFIG, assess, sample
from tests.test_profile_evaluation import MemoryHistory, plan


BOOTSTRAP = BootstrapConfig(200, 7)


class ReliabilityTests(unittest.TestCase):
    def profile(self):
        profiles, _ = estimate_profiles(
            assess(sample()), ("driver:830", "driver:839"), CONFIG
        )
        p = profiles[0]
        c = p.contexts[0]
        contexts = tuple(
            replace(
                c,
                context=replace(c.context, race_id=f"race:{i}"),
                pace_delta_pct=value,
                consistency_mad_pct=value / 2,
            )
            for i, value in enumerate((0.0, 10.0))
        )
        return replace(
            p, contexts=contexts, events=2, pace_delta_pct=5.0, consistency_mad_pct=2.5
        )

    def test_known_two_event_interval_and_reproducibility(self):
        p = self.profile()
        a = profile_support(p, "development", BOOTSTRAP)
        self.assertEqual(a, profile_support(p, "development", BOOTSTRAP))
        self.assertEqual(a.pace_interval_pct, (0.0, 10.0))
        self.assertEqual(a.consistency_interval_pct, (0.0, 5.0))
        self.assertIn("few_events_exploratory_interval", a.warnings)

    def test_many_laps_in_one_event_do_not_increase_independent_sample_size(self):
        p = self.profile()
        expanded = replace(
            p,
            compared_laps=10000,
            contexts=(replace(p.contexts[0], laps=9997), p.contexts[1]),
        )
        a, b = [profile_support(x, "development", BOOTSTRAP) for x in (p, expanded)]
        self.assertEqual(a.pace_interval_pct, b.pace_interval_pct)
        self.assertEqual(b.events, 2)
        reordered = replace(p, contexts=tuple(reversed(p.contexts)))
        self.assertEqual(a, profile_support(reordered, "development", BOOTSTRAP))

    def test_one_event_and_unavailable_profiles_never_receive_interval(self):
        p = self.profile()
        for other in (
            replace(p, contexts=p.contexts[:1], events=1),
            replace(p, unavailable_reason="insufficient_events", pace_delta_pct=None),
        ):
            result = profile_support(other, "development", BOOTSTRAP)
            self.assertIsNone(result.pace_interval_pct)
            self.assertTrue(result.warnings)

    def test_degenerate_interval_is_not_certainty(self):
        p = self.profile()
        p = replace(
            p, contexts=tuple(replace(c, pace_delta_pct=0.0) for c in p.contexts)
        )
        result = profile_support(p, "development", BOOTSTRAP)
        self.assertEqual(result.pace_interval_pct, (0.0, 0.0))
        self.assertIn("degenerate_interval_not_certainty", result.warnings)

    def test_invalid_parameters(self):
        for kwargs in (
            {"replicates": 0},
            {"seed": True},
            {"confidence": 1},
            {"confidence": float("nan")},
            {"warn_below_events": 1},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                BootstrapConfig(**kwargs)
        for kwargs in ({"name": ""}, {"lap_window": True}, {"split_stints": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ContextVariant(**kwargs)

    def test_splitting_stints_enforces_support_and_preserves_quality(self):
        rows = assess(sample())
        # Each driver's old three-lap context becomes groups of two and one.
        rows = tuple(
            replace(lap, stint=2 if lap.lap_number == 4 else 1) for lap in rows
        )
        base, audit = estimate_profiles(rows, ("driver:830", "driver:839"), CONFIG)
        self.assertEqual(base[0].contexts[0].stints, 2)
        split, audit2 = estimate_profiles(
            separate_stints(audit), ("driver:830", "driver:839"), CONFIG
        )
        self.assertTrue(all(p.compared_laps == 0 for p in split))
        self.assertTrue(
            all("insufficient_context_laps" in lap.exclusions for lap in audit2)
        )
        bad = replace(rows[0], exclusions=("pit_lap",))
        self.assertEqual(separate_stints((bad,))[0].exclusions, ("pit_lap",))
        self.assertIsNone(separate_stints(audit)[0].residual_pct)

    def test_baseline_plan_hash_is_preserved_analysis_options_have_own_digest(self):
        a = evaluate_profiles(MemoryHistory(), plan(), bootstrap=BOOTSTRAP)
        b = evaluate_profiles(
            MemoryHistory(), plan(), bootstrap=replace(BOOTSTRAP, seed=8)
        )
        self.assertEqual(a.plan_sha256, b.plan_sha256)
        self.assertNotEqual(a.analysis_sha256, b.analysis_sha256)
        self.assertEqual(a.development, b.development)
        self.assertEqual(a.comparisons, b.comparisons)

    def test_study_same_input_counts_and_baseline_zero_changes(self):
        results, changes = analyze_contexts(
            MemoryHistory(), plan(), bootstrap=BOOTSTRAP
        )
        self.assertEqual(len(results), 4)
        self.assertTrue(
            all(r.pace_shift_pp == 0 for r in changes if r.variant == "baseline")
        )
        counts = [sum(e.input_laps for e in r.event_estimates) for r in results]
        self.assertEqual(len(set(counts)), 1)
        self.assertTrue(
            all(r.common_laps <= min(r.baseline_laps, r.compared_laps) for r in changes)
        )
        self.assertTrue(
            all(
                c.stints == 1
                for r in results
                if r.variant.split_stints
                for run in (r.development, r.validation)
                for p in run.profiles
                for c in p.contexts
            )
        )
        self.assertEqual(results[0].plan, plan())
        with self.assertRaises(ValueError):
            analyze_contexts(MemoryHistory(), plan(), narrow_window=10)

    def test_missing_comparison_is_not_zero(self):
        results, rows = analyze_contexts(
            MemoryHistory(), plan(), narrow_window=1, bootstrap=BOOTSTRAP
        )
        missing = [r for r in rows if r.variant == "narrow"]
        self.assertTrue(
            all(r.compared_laps == 0 and r.pace_shift_pp is None for r in missing)
        )
        self.assertTrue(all(s.pace_interval_pct is None for s in results[2].support))

    def test_publication_and_failure_preserve_existing_reports(self):
        results, changes = analyze_contexts(
            MemoryHistory(), plan(), bootstrap=BOOTSTRAP
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = publish_study(results, changes, root, plots=False)
            report = json.loads((output / "baseline/evaluation.json").read_text())
            self.assertEqual(report["bootstrap"], asdict(BOOTSTRAP))
            self.assertTrue((output / "baseline/support.csv").exists())
            self.assertTrue((output / "context-audit.csv").exists())
            self.assertEqual(len(json.loads((output / "summary.json").read_text())), 4)
            with patch(
                "scripts.evaluate_profiles.publish_report",
                side_effect=RuntimeError("plot failed"),
            ):
                with self.assertRaises(RuntimeError):
                    publish_study(results, changes, root)
            self.assertEqual(list(root.iterdir()), [output])


if __name__ == "__main__":
    unittest.main()
