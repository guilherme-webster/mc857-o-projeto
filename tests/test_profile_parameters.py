"""Ranking and profiling-to-core boundary tested without database, GUI or HTTP."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from f1_simulator.adapters.profile_parameters import ProfileParametersAdapter
from f1_simulator.application.profile_drivers import profile_drivers
from f1_simulator.application.rank_drivers import rank_drivers
from f1_simulator.application.simulate_profile_lap import simulate_profile_lap
from f1_simulator.domain.driver_parameters import deterministic_lap_time
from f1_simulator.domain.profile_reliability import BootstrapConfig
from scripts.rank_drivers import publish
from tests.test_driver_profile import CONFIG
from tests.test_profile_evaluation import MemoryHistory


class ProfileParametersTests(unittest.TestCase):
    def setUp(self):
        self.run = profile_drivers(
            MemoryHistory(), session_ids=("session:1:R", "session:2:R"), config=CONFIG
        )
        self.adapter = ProfileParametersAdapter(
            self.run, allowed_sessions=self.run.session_ids
        )
        self.profile = self.run.profiles[0]
        self.estimate = self.profile.contexts[0]
        self.params = self.adapter.parameters(
            self.profile.driver_id, self.estimate.team_id, self.estimate.context
        )

    def test_ranking_pace_names_ties_and_unavailable(self):
        p, q = self.run.profiles
        run = replace(
            self.run,
            profiles=(
                replace(q, pace_delta_pct=-1),
                replace(p, pace_delta_pct=-1),
                replace(
                    p,
                    driver_id="absent",
                    pace_delta_pct=None,
                    unavailable_reason="insufficient_events",
                ),
            ),
        )
        rows = rank_drivers(run, BootstrapConfig(100))
        self.assertEqual([r.position for r in rows], [1, 1, None])
        self.assertEqual(
            [r.driver_id for r in rows[:2]], sorted([p.driver_id, q.driver_id])
        )
        self.assertEqual(rows[0].name, dict(run.driver_names)[rows[0].driver_id])
        self.assertIn("insufficient_events", rows[2].support.warnings)
        different = replace(
            run,
            profiles=run.profiles[:2]
            + (replace(p, driver_id="third", pace_delta_pct=1),),
        )
        self.assertEqual([r.position for r in rank_drivers(different)], [1, 1, 3])
        self.assertEqual(
            rank_drivers(run),
            rank_drivers(replace(run, profiles=tuple(reversed(run.profiles)))),
        )

    def test_invalid_ranking_values_and_duplicates(self):
        for pace in (None, float("nan"), float("inf"), -100):
            with self.assertRaises(ValueError):
                rank_drivers(
                    replace(
                        self.run, profiles=(replace(self.profile, pace_delta_pct=pace),)
                    )
                )
        with self.assertRaises(ValueError):
            rank_drivers(replace(self.run, profiles=self.run.profiles * 2))

    def test_adapter_core_reconstruct_context_not_aggregate(self):
        output = simulate_profile_lap(
            self.adapter,
            driver_id=self.profile.driver_id,
            team_id=self.estimate.team_id,
            context=self.estimate.context,
        )
        self.assertAlmostEqual(
            float(output.modeled_ms), self.estimate.observed_median_ms
        )
        changed = replace(
            self.run,
            profiles=(replace(self.profile, pace_delta_pct=50),)
            + self.run.profiles[1:],
        )
        adapter = ProfileParametersAdapter(
            changed, allowed_sessions=self.run.session_ids
        )
        self.assertEqual(
            adapter.parameters(
                self.profile.driver_id, self.estimate.team_id, self.estimate.context
            ).pace_offset_pct,
            self.params.pace_offset_pct,
        )
        self.assertEqual(
            output,
            simulate_profile_lap(
                self.adapter,
                driver_id=self.profile.driver_id,
                team_id=self.estimate.team_id,
                context=self.estimate.context,
            ),
        )
        self.assertTrue(self.params.source_manifest_hashes)

    def test_missing_wrong_team_context_and_reserve_rejected(self):
        for driver, team, context in (
            ("absent", self.params.team_id, self.params.context),
            (self.params.driver_id, "wrong", self.params.context),
            (
                self.params.driver_id,
                self.params.team_id,
                replace(self.params.context, compound="unknown"),
            ),
        ):
            with self.assertRaises(ValueError):
                self.adapter.parameters(driver, team, context)
        with self.assertRaises(ValueError):
            ProfileParametersAdapter(self.run, allowed_sessions=("session:1:R",))
        for run in (
            replace(self.run, method_version="unknown"),
            replace(self.run, source_reports_json=()),
            replace(self.run, profiles=self.run.profiles * 2),
        ):
            with self.assertRaises(ValueError):
                ProfileParametersAdapter(run, allowed_sessions=self.run.session_ids)
        unavailable = replace(
            self.run,
            profiles=(replace(self.profile, unavailable_reason="insufficient_events"),)
            + self.run.profiles[1:],
        )
        with self.assertRaises(ValueError):
            ProfileParametersAdapter(
                unavailable, allowed_sessions=self.run.session_ids
            ).parameters(
                self.params.driver_id, self.params.team_id, self.params.context
            )

    def test_time_units_sign_and_rounding(self):
        for pace, expected in ((-1, 99000), (0, 100000), (1, 101000)):
            result = deterministic_lap_time(
                replace(self.params, reference_lap_time_ms=100000, pace_offset_pct=pace)
            )
            self.assertEqual(result.clock_ms, expected)
            self.assertEqual(
                result.reference_ms + result.pace_effect_ms, result.modeled_ms
            )
        result = deterministic_lap_time(
            replace(self.params, reference_lap_time_ms=97175.5, pace_offset_pct=0)
        )
        self.assertEqual(result.modeled_ms, Decimal("97175.5"))
        self.assertEqual(result.clock_ms, 97176)
        for fields in (
            dict(reference_lap_time_ms=0),
            dict(pace_offset_pct=-100),
            dict(pace_offset_pct=float("nan")),
            dict(variability_mode="calibrated"),
            dict(context_laps=0),
        ):
            with self.assertRaises(ValueError):
                replace(self.params, **fields)

    def test_consumer_rejects_provider_substitution(self):
        class WrongProvider:
            def parameters(inner, *args):
                return replace(self.params, driver_id="other")

        with self.assertRaises(ValueError):
            simulate_profile_lap(
                WrongProvider(),
                driver_id=self.params.driver_id,
                team_id=self.params.team_id,
                context=self.params.context,
            )

    def test_report_publication_reproducible_and_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = publish(self.run, root, plots=False)
            second = publish(self.run, root, plots=False)
            self.assertEqual(
                (first / "ranking.json").read_bytes(),
                (second / "ranking.json").read_bytes(),
            )
            self.assertIn("Verstappen", (first / "report.md").read_text())
            with patch("scripts.rank_drivers.os.rename", side_effect=OSError("failed")):
                with self.assertRaises(OSError):
                    publish(self.run, root, plots=False)
            self.assertEqual(len(list(root.iterdir())), 2)
