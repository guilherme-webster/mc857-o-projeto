"""Regressão: o grid 2D não deve esperar inteiro pelo último prazo comum."""

from dataclasses import replace
import unittest

from f1_simulator.application.build_grid import GridEntry
from f1_simulator.application.run_grid_simulation import (
    RaceSetup,
    run_grid_simulation,
)
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.strategy import (
    HeuristicPitStrategy,
    SpatialPitPlanningParameters,
    StrategyState,
)
from f1_simulator.domain.tyres import TyreSet
from tests.model_support import parameters, track
from tests.test_pit_lane import pit_geometry
from tests.geometry_support import attribute


class SpatialPitPolicyTest(unittest.TestCase):
    def state(self, lap=5, wear=4.0):
        return StrategyState(
            lap,
            10,
            TyreSet("MEDIUM", lap - 1),
            0,
            compounds_used=("MEDIUM",),
            tyre_wear_laps=wear,
        )

    def test_wear_budget_is_optional_and_leaves_the_detailed_policy_unchanged(self):
        model, circuit = parameters(), track(pit_loss_ms=1_000_000)
        old = HeuristicPitStrategy(model, circuit)
        planned = HeuristicPitStrategy(model, circuit, compulsory_wear_target_laps=4)
        self.assertFalse(old.decide(self.state()).pit)
        self.assertTrue(planned.decide(self.state()).pit)
        self.assertFalse(planned.decide(self.state(wear=3.9)).pit)

    def test_individual_preference_uses_wear_but_does_not_skip_the_deadline(self):
        model, circuit = parameters(), track(pit_loss_ms=1_000_000)
        early = HeuristicPitStrategy(
            model, circuit, offset_laps=-2, compulsory_wear_target_laps=4
        )
        late = HeuristicPitStrategy(
            model, circuit, offset_laps=2, compulsory_wear_target_laps=4
        )
        self.assertTrue(early.decide(self.state(lap=3, wear=2)).pit)
        self.assertFalse(late.decide(self.state(lap=3, wear=2)).pit)
        self.assertTrue(late.decide(self.state(lap=7, wear=0.1)).pit)

    def test_used_second_compound_and_short_races_do_not_force_extra_stops(self):
        policy = HeuristicPitStrategy(
            parameters(), track(pit_loss_ms=1_000_000), compulsory_wear_target_laps=4
        )
        self.assertFalse(
            policy.decide(
                replace(self.state(), compounds_used=("MEDIUM", "SOFT"), stops_made=1)
            ).pit
        )
        short = HeuristicPitStrategy(
            parameters(), track(), compulsory_wear_target_laps=0
        )
        self.assertFalse(
            short.decide(replace(self.state(lap=1, wear=0), total_laps=3)).pit
        )

    def test_planning_parameters_have_explicit_bounds(self):
        self.assertEqual(SpatialPitPlanningParameters().wear_target(10), 4)
        for fraction in (0, 1, float("nan"), True):
            with self.subTest(fraction=fraction), self.assertRaises(ValueError):
                SpatialPitPlanningParameters(compulsory_change_fraction=fraction)


def run_grid(*, reverse=False, seed=42):
    ids = ("driver:283", "driver:684", "driver:27", "driver:612")
    grid = tuple(GridEntry(did, did, "team:solid", "Solid") for did in ids)
    attributes = {did: attribute(did) for did in ids}
    if reverse:
        grid = tuple(reversed(grid))
    geometry = pit_geometry()
    return run_grid_simulation(
        grid,
        attributes,
        RaceSetup(10, geometry.circuit_id),
        parameters=parameters(),
        lap_length_m=geometry.lap_length_m,
        rng=SeededRandomSource(seed).spawn("race"),
        geometry=geometry,
        race_control=None,
    )


class SpatialPitCompositionTest(unittest.TestCase):
    def test_ten_lap_grid_has_individual_stops_before_the_common_deadline(self):
        result = run_grid()
        entry_laps = {}
        for did, series in result["trajectories_2d"].items():
            visits = [p for p in series if p[4] is not None]
            self.assertTrue(visits, did)
            entry_laps[did] = int(visits[0][1] // 400) + 1
        self.assertGreater(len(set(entry_laps.values())), 1, entry_laps)
        self.assertTrue(all(lap <= 7 for lap in entry_laps.values()))
        self.assertTrue(all(c["stops_made"] >= 1 for c in result["classification"]))
        self.assertEqual(result, run_grid())

    def test_preference_stream_is_stable_per_driver_and_changes_with_seed(self):
        def offsets(result):
            return {
                did: value["offset_laps"]
                for did, value in result["pit_planning_2d"]["cars"].items()
            }

        first = offsets(run_grid())
        self.assertEqual(first, offsets(run_grid(reverse=True)))
        self.assertNotEqual(first, offsets(run_grid(seed=43)))
        self.assertTrue(all(-2 <= value <= 2 for value in first.values()))


if __name__ == "__main__":
    unittest.main()
