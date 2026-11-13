"""Integração do reabastecimento espacial, em kg e segundos."""

import unittest

from f1_simulator.domain.fuel import FuelPlan
from f1_simulator.domain.race_simulation_2d import simulate_2d_race
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.strategy import PitDecision
from tests.fuel_support import fuel_parameters
from tests.model_support import parameters, track
from tests.test_pit_lane import pit_geometry


class FixedRefuelStrategy:
    def decide(self, state):
        return PitDecision(True, "HARD", 100.0) if state.lap_number == 1 else PitDecision(False)


def run_race(allowed=True, rate=0.2):
    geo = pit_geometry()
    model = parameters()
    plan = FuelPlan(
        fuel_parameters(max_fuel_kg=5.0, refuelling_allowed=allowed,
                        refuel_rate_kg_per_s=rate),
        30_000, geo.lap_length_m / 1000, "track_geometry",
    )
    return simulate_2d_race(
        [{"driver_id": "a", "name": "A", "grid_position": 1,
          "start_fuel_kg": 3.0, "strategy": FixedRefuelStrategy()}],
        geo, total_laps=4, rng=SeededRandomSource(1),
        compounds={c.name: c for c in model.compounds}, track_params=track(),
        model_parameters=model, fuel=plan, race_control=None, dt_s=0.1,
    )


class Refuel2DTest(unittest.TestCase):
    def test_service_conserves_mass_respects_capacity_and_flow(self):
        result = run_race()
        self.assertEqual(result, run_race())
        events = result["fuel"]["refuel_stops"]
        self.assertEqual(len(events), 1)
        event = events[0]
        pit = {e["type"]: e for e in result["pit_stop_events"]}
        elapsed_s = (pit["service_completed"]["time_ms"] - pit["service_started"]["time_ms"]) / 1000
        self.assertGreater(elapsed_s, 2.5)
        self.assertAlmostEqual(elapsed_s, event["added_kg"] / 0.2, delta=0.001)
        self.assertEqual(result["classification"][0]["refuels_made"], 1)
        self.assertEqual(result["classification"][0]["stops_made"], 1)
        self.assertEqual(result["classification"][0]["compound"], "HARD")
        samples = result["trajectories_2d"]["a"]
        self.assertLessEqual(max(point[5] for point in samples), 5.000001)
        burned = result["usage_2d"]["cars"]["a"]["fuel_burned_kg"]
        self.assertAlmostEqual(3.0 + event["added_kg"] - burned, samples[-1][5], delta=0.000002)

    def test_disabled_ignores_fuel_request_but_still_changes_tyres(self):
        result = run_race(allowed=False)
        self.assertEqual(result["fuel"]["refuel_stops"], [])
        self.assertEqual(result["classification"][0]["refuels_made"], 0)
        self.assertEqual(result["classification"][0]["stops_made"], 1)
        samples = result["trajectories_2d"]["a"]
        self.assertTrue(all(a[5] >= b[5] for a, b in zip(samples, samples[1:])))


if __name__ == "__main__":
    unittest.main()
