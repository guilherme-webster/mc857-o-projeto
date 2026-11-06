"""Tendências físicas, conservação de recursos e integração 2D, sem GPU."""

from dataclasses import replace
import json
import unittest

from frontend.arcade.race_playback import RacePlayback
from f1_simulator.domain.dynamic_usage import (
    DynamicUsageParameters,
    UsageReference,
    curvature_profile,
    usage_delta,
    usage_reference,
)
from f1_simulator.domain.fuel import FuelPlan
from f1_simulator.domain.race_simulation_2d import simulate_2d_race
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.speed_dynamics import CarPhysics, steady_lap
from f1_simulator.domain.strategy import (
    PlannedStopStrategy,
    StrategyState,
    TyreLifeStrategy,
)
from f1_simulator.domain.tyres import TyreSet, tyre_penalty_ms
from tests.model_support import parameters, track
from tests.test_fuel import fuel_parameters
from tests.test_track_space import _circle
from tests.test_pit_lane import pit_geometry


def delta(**overrides):
    values = dict(
        distance_m=100.0,
        dt_s=2.0,
        speed_ms=50.0,
        acceleration_ms2=0.0,
        curvature_per_m=0.0,
        lap_length_m=4000.0,
        burn_kg_per_km=0.3443,
        reference=UsageReference(1.0, 1.0),
    )
    values.update(overrides)
    return usage_delta(**values)


class DynamicUsageTest(unittest.TestCase):
    def test_same_corner_at_double_speed_has_four_times_lateral_load(self):
        slow = delta(speed_ms=40, curvature_per_m=1 / 150)
        fast = delta(speed_ms=80, curvature_per_m=1 / 150)
        self.assertAlmostEqual(fast.lateral_wear_laps / slow.lateral_wear_laps, 4.0)
        self.assertGreater(fast.wear_laps, slow.wear_laps)
        self.assertEqual(delta(speed_ms=80).lateral_wear_laps, 0)

    def test_braking_and_acceleration_add_wear_but_coasting_uses_less_fuel(self):
        cruise = delta()
        accelerating = delta(acceleration_ms2=4.0)
        braking = delta(acceleration_ms2=-4.0)
        self.assertGreater(accelerating.wear_laps, cruise.wear_laps)
        self.assertGreater(braking.wear_laps, cruise.wear_laps)
        self.assertGreater(accelerating.fuel_kg, cruise.fuel_kg)
        self.assertLess(braking.fuel_kg, cruise.fuel_kg)
        self.assertGreater(delta(speed_ms=80).fuel_kg, cruise.fuel_kg)

    def test_stationary_service_has_no_wear_but_small_idle_consumption(self):
        stopped = delta(distance_m=0, speed_ms=0, in_pit=True)
        self.assertEqual(stopped.wear_laps, 0)
        self.assertGreater(stopped.fuel_kg, 0)
        self.assertLess(stopped.fuel_kg, delta().fuel_kg)

    def test_fuel_flow_is_bounded_by_2025_reference(self):
        high = delta(distance_m=1000, dt_s=1, speed_ms=1000, acceleration_ms2=100)
        self.assertAlmostEqual(high.fuel_kg, 100 / 3600)

    def test_partition_of_same_movement_is_invariant(self):
        whole = delta(curvature_per_m=0.01, acceleration_ms2=3)
        parts = [
            delta(distance_m=1, dt_s=0.02, curvature_per_m=0.01, acceleration_ms2=3)
            for _ in range(100)
        ]
        self.assertAlmostEqual(whole.wear_laps, sum(p.wear_laps for p in parts))
        self.assertAlmostEqual(whole.fuel_kg, sum(p.fuel_kg for p in parts))

    def test_management_changes_only_wear_once(self):
        normal = delta(curvature_per_m=0.01)
        managed = delta(curvature_per_m=0.01, management_factor=0.8)
        self.assertAlmostEqual(managed.wear_laps, normal.wear_laps * 0.8)
        self.assertEqual(managed.fuel_kg, normal.fuel_kg)

    def test_lower_neutralized_speed_reduces_load_without_a_second_sc_multiplier(self):
        green = delta(curvature_per_m=0.01)
        slow = delta(speed_ms=25, dt_s=4, curvature_per_m=0.01)
        self.assertLess(slow.wear_laps, green.wear_laps)
        self.assertLess(slow.fuel_kg, green.fuel_kg)

    def test_circle_curvature_and_reference_mean(self):
        geometry = _circle(radius=150)
        profile = curvature_profile(geometry)
        self.assertAlmostEqual(profile.at(0), 1 / 150, delta=0.00001)
        self.assertAlmostEqual(profile.at(0), profile.at(geometry.lap_length_m))
        p = DynamicUsageParameters()
        reference = usage_reference(geometry, profile, CarPhysics(), p)
        samples = steady_lap(geometry)
        total = 0.0
        for a, b in zip(samples, samples[1:]):
            ds, dt = b.distance_m - a.distance_m, b.time_s - a.time_s
            total += usage_delta(
                distance_m=ds,
                dt_s=dt,
                speed_ms=ds / dt,
                acceleration_ms2=(b.speed_ms - a.speed_ms) / dt,
                curvature_per_m=profile.at((a.distance_m + b.distance_m) / 2),
                lap_length_m=geometry.lap_length_m,
                burn_kg_per_km=0,
                reference=reference,
            ).wear_laps
        self.assertAlmostEqual(total, 1.0)

    def test_invalid_inputs_are_not_silently_repaired(self):
        for kwargs in (
            {"dt_s": 0},
            {"curvature_per_m": -1},
            {"distance_m": float("nan")},
            {"management_factor": -1},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                delta(**kwargs)
        with self.assertRaises(ValueError):
            DynamicUsageParameters(max_lateral_g=0)

    def test_penalty_and_strategy_use_effective_wear_separately_from_lap_count(self):
        model = parameters()
        tyre = TyreSet("MEDIUM", 2)
        old = tyre_penalty_ms(tyre, model.compound("MEDIUM"), track())
        worn = tyre_penalty_ms(tyre, model.compound("MEDIUM"), track(), wear_laps=25.0)
        self.assertGreater(worn, old)
        state = StrategyState(3, 50, tyre, 0, tyre_wear_laps=25)
        strategy = TyreLifeStrategy(model, "HARD")
        self.assertTrue(strategy.decide(state).pit)
        self.assertFalse(strategy.decide(replace(state, tyre_wear_laps=2)).pit)


def dynamic_race(*, dt=0.05, load=5.0):
    geometry = _circle(radius=150)
    model = parameters()
    plan = FuelPlan(
        fuel_parameters(), 60_000, geometry.lap_length_m / 1000, "track_geometry"
    )
    return simulate_2d_race(
        [{"driver_id": "a", "name": "A", "grid_position": 1, "start_fuel_kg": load}],
        geometry,
        total_laps=3,
        rng=SeededRandomSource(1),
        dt_s=dt,
        compounds={c.name: c for c in model.compounds},
        track_params=track(),
        fuel=plan,
        race_control=None,
    )


class DynamicUsageIntegrationTest(unittest.TestCase):
    def test_continuous_fuel_is_conserved_and_not_charged_again_each_lap(self):
        race = dynamic_race()
        self.assertEqual(race, dynamic_race())
        json.dumps(race, allow_nan=False)
        data = race["usage_2d"]["cars"]["a"]
        series = race["trajectories_2d"]["a"]
        self.assertAlmostEqual(
            data["fuel_burned_kg"], 5 - series[-1][5], delta=0.000002
        )
        self.assertEqual(race["classification"][0]["laps_completed"], 3)
        self.assertGreater(data["current_tyre_wear_laps"], 0)
        self.assertTrue(all(a[5] >= b[5] for a, b in zip(series, series[1:])))
        playback = RacePlayback(race)
        t = series[4][0]
        self.assertAlmostEqual(playback.car("a").fuel_at(t), series[4][5])

    def test_smaller_time_step_converges(self):
        coarse = dynamic_race(dt=0.05)["usage_2d"]["cars"]["a"]
        fine = dynamic_race(dt=0.025)["usage_2d"]["cars"]["a"]
        self.assertAlmostEqual(
            coarse["fuel_burned_kg"], fine["fuel_burned_kg"], delta=0.01
        )
        self.assertAlmostEqual(
            coarse["current_tyre_wear_laps"], fine["current_tyre_wear_laps"], delta=0.03
        )

    def test_fuel_starvation_between_lines_does_not_credit_a_fictitious_lap(self):
        race = dynamic_race(load=0.005)
        final = race["classification"][0]
        self.assertEqual(final["status"], "RETIRED")
        self.assertEqual(final["retirement_cause"], "FUEL")
        self.assertEqual(final["fuel_kg"], 0)
        self.assertEqual(final["laps_completed"], 0)
        playback = RacePlayback(race)
        self.assertGreater(playback.duration_ms, 0)
        self.assertFalse(playback.car("a").is_retired_at(0))
        self.assertTrue(playback.car("a").is_retired_at(playback.duration_ms))

    def test_partial_lap_after_one_completed_lap_is_played_until_actual_retirement(
        self,
    ):
        race = dynamic_race(load=0.7)
        playback = RacePlayback(race)
        car = playback.car("a")
        self.assertEqual(car.laps_completed, 1)
        last_crossing = car.lap_end_times_ms[-1]
        self.assertGreater(car.finish_time_ms, last_crossing)
        self.assertGreater(car.laps_at((last_crossing + car.finish_time_ms) / 2), 1)
        self.assertFalse(car.is_retired_at(last_crossing))

    def test_pit_service_keeps_wear_constant_and_fuel_burns_only_at_idle(self):
        geo = pit_geometry()
        model = parameters()
        plan = FuelPlan(
            fuel_parameters(), 30_000, geo.lap_length_m / 1000, "track_geometry"
        )
        race = simulate_2d_race(
            [
                {
                    "driver_id": "a",
                    "name": "A",
                    "grid_position": 1,
                    "start_fuel_kg": 5.0,
                    "strategy": PlannedStopStrategy(1, ("HARD",)),
                }
            ],
            geo,
            total_laps=4,
            rng=SeededRandomSource(1),
            compounds={c.name: c for c in model.compounds},
            track_params=track(),
            model_parameters=model,
            fuel=plan,
            race_control=None,
        )
        events = {event["type"]: event for event in race["pit_stop_events"]}
        playback = RacePlayback(race)
        car = playback.car("a")
        a = car.spatial_at(events["service_started"]["time_ms"] + 200)
        b = car.spatial_at(events["service_completed"]["time_ms"] - 200)
        self.assertAlmostEqual(a.tyre_wear_laps, b.tyre_wear_laps, places=5)
        self.assertGreater(a.fuel_kg, b.fuel_kg)
        self.assertLess(a.fuel_kg - b.fuel_kg, 0.01)
        after = car.spatial_at(events["service_completed"]["time_ms"] + 100)
        self.assertLess(after.tyre_wear_laps, b.tyre_wear_laps)


if __name__ == "__main__":
    unittest.main()
