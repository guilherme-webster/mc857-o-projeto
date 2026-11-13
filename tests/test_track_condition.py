"""Estado dinamico da pista: agua, temperatura, borracha e aderencia (ADR 0015)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from f1_simulator.adapters.datasets.mock_track_geometry import MockTrackDatasetAdapter
from f1_simulator.application.build_grid import GridEntry
from f1_simulator.application.run_grid_simulation import (
    RaceSetup,
    _track_states,
    run_grid_simulation,
)
from f1_simulator.domain.race_simulation_2d import GRID_ROW_SPACING_M, simulate_2d_race
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.speed_dynamics import (
    DEFAULT_CAR_PHYSICS,
    GripLapTimes,
    lap_time_ms,
    steady_lap,
)
from f1_simulator.domain.track_condition import (
    ASSUMED_TRACK_CONDITION,
    TrackConditionParameters,
    TrackState,
    approximate_lap_time_ratio,
    circuit_dry_temperature_c,
    rubber_grip_factor,
    simulate_track_conditions,
    step_track_condition,
    water_grip_factor,
)
from f1_simulator.domain.weather import (
    RainLevel,
    WeatherSegment,
    WeatherState,
    simulate_weather,
    step_weather,
)
from f1_simulator.factories.track_geometry_factory import TrackGeometryFactory
from tests.geometry_support import attribute, small_geometry
from tests.model_support import parameters

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "trotman_v128_tracks_2025"
SOURCES = ROOT / "data" / "sources"
DRY, LIGHT, HEAVY = RainLevel.DRY, RainLevel.LIGHT, RainLevel.HEAVY


def _fixture_geometry(circuit_id):
    adapter = MockTrackDatasetAdapter(
        FIXTURE / "track_points.csv",
        SOURCES / "fastf1-tracks-2025.json",
        FIXTURE / "pit_lane_points.csv",
        SOURCES / "fastf1-pit-lanes-2025.json",
    )
    return TrackGeometryFactory.build(adapter.load_geometry(circuit_id))


class GripFactorTest(unittest.TestCase):
    def test_water_envelope_hits_its_anchors_and_never_rises(self):
        p = ASSUMED_TRACK_CONDITION
        self.assertEqual(water_grip_factor(0.0), 1.0)
        self.assertAlmostEqual(water_grip_factor(p.damp_water), p.damp_grip)
        self.assertAlmostEqual(water_grip_factor(1.0), p.saturated_grip)
        values = [water_grip_factor(w / 20) for w in range(21)]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_green_track_has_less_grip_than_rubbered(self):
        self.assertEqual(rubber_grip_factor(1.0), 1.0)
        self.assertLess(rubber_grip_factor(0.0), rubber_grip_factor(0.8))

    def test_anchors_cost_what_the_wet_races_cost(self):
        # Na pista mediana, a umida custa ~13% e a saturada ~25%.
        p = ASSUMED_TRACK_CONDITION
        self.assertAlmostEqual(
            approximate_lap_time_ratio(p.damp_grip), 1.13, delta=0.02
        )
        self.assertAlmostEqual(
            approximate_lap_time_ratio(p.saturated_grip), 1.25, delta=0.02
        )

    def test_rejects_inconsistent_parameters(self):
        with self.assertRaises(ValueError):
            TrackConditionParameters(damp_grip=0.6, saturated_grip=0.7)
        with self.assertRaises(ValueError):
            water_grip_factor(1.5)


class TrackEvolutionTest(unittest.TestCase):
    def test_reference_lap_step_matches_the_original_weather_model(self):
        conditions = [LIGHT, LIGHT, HEAVY, DRY, DRY]
        legacy = simulate_weather(conditions)
        state = WeatherState(50.0, 0.0)
        for item, rain in zip(legacy, conditions):
            state = step_weather(state, rain)
            self.assertEqual(state, item.state)

    def test_dry_race_lays_rubber_and_gains_grip(self):
        states = simulate_track_conditions([DRY] * 30, lap_minutes=1.5)
        rubbers = [s.rubber for s in states]
        grips = [s.grip_factor for s in states]
        self.assertEqual(rubbers, sorted(rubbers))
        self.assertEqual(grips, sorted(grips))
        self.assertGreater(states[0].rubber, ASSUMED_TRACK_CONDITION.initial_rubber)
        self.assertGreater(states[-1].grip_factor, 0.999)
        self.assertTrue(all(s.surface_water == 0.0 for s in states))

    def test_rain_wets_cools_and_washes_then_the_track_dries(self):
        states = simulate_track_conditions([HEAVY] * 6 + [DRY] * 40, lap_minutes=1.5)
        wettest = states[5]
        self.assertGreater(wettest.surface_water, 0.9)
        self.assertLess(
            wettest.track_temp_c, ASSUMED_TRACK_CONDITION.dry_track_temp_c - 5
        )
        self.assertLess(wettest.rubber, ASSUMED_TRACK_CONDITION.initial_rubber)
        self.assertLess(wettest.grip_factor, 0.75)
        self.assertEqual(states[-1].surface_water, 0.0)
        self.assertGreater(states[-1].grip_factor, wettest.grip_factor)

    def test_hot_track_dries_sooner(self):
        pattern = [HEAVY] * 5 + [DRY] * 60

        def laps_to_dry(dry_temp_c):
            states = simulate_track_conditions(
                pattern,
                lap_minutes=1.5,
                parameters=TrackConditionParameters(dry_track_temp_c=dry_temp_c),
            )
            return next(s.lap for s in states[5:] if s.surface_water == 0.0)

        self.assertLess(laps_to_dry(50.0), laps_to_dry(15.0))

    def test_longer_laps_wet_and_dry_more_per_lap(self):
        short = simulate_track_conditions([LIGHT] * 3, lap_minutes=1.0)
        long = simulate_track_conditions([LIGHT] * 3, lap_minutes=2.0)
        self.assertGreater(long[-1].surface_water, short[-1].surface_water)

    def test_traffic_and_elapsed_time_are_independent(self):
        initial = TrackState(1, DRY, 50.0, 0.7, 35.0, 0.8, 0.8)
        no_traffic = step_track_condition(
            initial, DRY, elapsed_s=60, traffic_laps=0, dry_temp_c=35
        )
        traffic = step_track_condition(
            initial, DRY, elapsed_s=60, traffic_laps=20, dry_temp_c=35
        )
        longer = step_track_condition(
            initial, DRY, elapsed_s=120, traffic_laps=0, dry_temp_c=35
        )
        self.assertGreater(traffic.rubber, no_traffic.rubber)
        self.assertEqual(traffic.surface_water, no_traffic.surface_water)
        self.assertLess(longer.surface_water, no_traffic.surface_water)
        self.assertLess(longer.rubber, no_traffic.rubber)

    def test_rubber_uses_equivalent_distance_and_time_units(self):
        initial = TrackState(1, DRY, 50.0, 0.0, 35.0, 0.8, 1.0)
        state = step_track_condition(
            initial, DRY, elapsed_s=90, traffic_laps=20, dry_temp_c=35
        )
        self.assertAlmostEqual(state.rubber, 0.8 + 0.08 * 0.2)
        wet = TrackState(1, DRY, 100.0, 1.0, 35.0, 0.8, 1.0)
        # Sem drenagem/evaporacao a agua permanece saturada por 90 segundos.
        from dataclasses import replace

        from f1_simulator.domain.weather import ASSUMED_WEATHER_PARAMETERS

        params = replace(
            ASSUMED_WEATHER_PARAMETERS, drainage_per_lap=0, evaporation_per_lap=0
        )
        washed = step_track_condition(
            wet,
            DRY,
            elapsed_s=90,
            traffic_laps=0,
            dry_temp_c=35,
            weather_parameters=params,
        )
        self.assertAlmostEqual(washed.rubber, 0.8 * 0.7)

    def test_smaller_time_steps_converge(self):
        initial = TrackState(1, HEAVY, 50.0, 0.0, 35.0, 0.8, 1.0)

        def evolve(dt):
            state = initial
            for _ in range(round(90 / dt)):
                state = step_track_condition(
                    state, HEAVY, elapsed_s=dt, traffic_laps=20 * dt / 90, dry_temp_c=35
                )
            return state

        coarse, fine = evolve(0.5), evolve(0.1)
        self.assertAlmostEqual(coarse.surface_water, fine.surface_water, delta=0.0001)
        self.assertAlmostEqual(coarse.rubber, fine.rubber, delta=0.0002)
        self.assertAlmostEqual(coarse.track_temp_c, fine.track_temp_c, delta=0.01)

    def test_start_prediction_uses_circuit_temperature_as_target(self):
        setup = RaceSetup(total_laps=1, track_id="circuit:69")
        state = _track_states(setup, 90_000)[0]
        self.assertEqual(state.track_temp_c, circuit_dry_temperature_c("circuit:69"))

    def test_circuit_temperatures_have_explicit_fallback(self):
        self.assertNotEqual(
            circuit_dry_temperature_c("circuit:3"),
            circuit_dry_temperature_c("circuit:69"),
        )
        self.assertEqual(
            circuit_dry_temperature_c("unknown"),
            ASSUMED_TRACK_CONDITION.dry_track_temp_c,
        )

    def test_is_deterministic(self):
        pattern = [DRY, LIGHT, HEAVY, DRY]
        self.assertEqual(
            simulate_track_conditions(pattern, lap_minutes=1.4),
            simulate_track_conditions(pattern, lap_minutes=1.4),
        )


class GripLapTimesTest(unittest.TestCase):
    def test_interpolation_tracks_the_direct_physics(self):
        geometry = _fixture_geometry("circuit:6")
        table = GripLapTimes(geometry, DEFAULT_CAR_PHYSICS)
        for factor in (0.97, 0.83, 0.72):
            direct = lap_time_ms(
                steady_lap(geometry, DEFAULT_CAR_PHYSICS.with_grip(factor))
            )
            self.assertAlmostEqual(table.lap_ms(factor), direct, delta=direct * 0.002)
        self.assertEqual(table.delta_ms(1.0), 0.0)
        self.assertGreater(table.delta_ms(0.8), 0.0)

    def test_twisty_tracks_lose_more_in_the_wet(self):
        factor = ASSUMED_TRACK_CONDITION.saturated_grip
        monaco = GripLapTimes(_fixture_geometry("circuit:6"), DEFAULT_CAR_PHYSICS)
        monza = GripLapTimes(_fixture_geometry("circuit:14"), DEFAULT_CAR_PHYSICS)
        self.assertGreater(
            monaco.lap_ms(factor) / monaco.lap_ms(1.0),
            monza.lap_ms(factor) / monza.lap_ms(1.0),
        )


class EngineIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.grid = tuple(
            GridEntry(f"driver:{i}", f"P{i}", "team:1", "Team") for i in range(3)
        )
        self.attributes = {g.driver_id: attribute(g.driver_id) for g in self.grid}

    def _run(self, weather, laps=4):
        geometry = small_geometry()
        return run_grid_simulation(
            self.grid,
            self.attributes,
            RaceSetup(total_laps=laps, track_id=None, weather=weather),
            parameters=parameters(),
            lap_length_m=geometry.lap_length_m,
            rng=SeededRandomSource(7),
            geometry=geometry,
            race_control=None,
        )

    def test_traffic_stops_at_finish_line(self):
        geometry = small_geometry()
        traffic = []

        def record_step(*args, **kwargs):
            traffic.append(kwargs["traffic_laps"])
            return step_track_condition(*args, **kwargs)

        with patch(
            "f1_simulator.domain.race_simulation_2d.step_track_condition",
            side_effect=record_step,
        ):
            simulate_2d_race(
                [{"driver_id": "a", "name": "A", "grid_position": 1}],
                geometry,
                total_laps=1,
                rng=SeededRandomSource(1),
                track_rain=(DRY,),
                race_control=None,
                dt_s=0.5,
            )
        # A pole percorre uma volta mais a distancia do grid ate a linha.
        self.assertAlmostEqual(
            sum(traffic), 1 + GRID_ROW_SPACING_M / geometry.lap_length_m
        )

    def test_pit_service_does_not_deposit_rubber(self):
        from f1_simulator.domain.strategy import PlannedStopStrategy
        from tests.model_support import track
        from tests.test_pit_lane import pit_geometry

        model = parameters()
        traffic = []

        def record_step(*args, **kwargs):
            traffic.append(kwargs["traffic_laps"])
            return step_track_condition(*args, **kwargs)

        with patch(
            "f1_simulator.domain.race_simulation_2d.step_track_condition",
            side_effect=record_step,
        ):
            race = simulate_2d_race(
                [
                    {
                        "driver_id": "a",
                        "name": "A",
                        "grid_position": 1,
                        "strategy": PlannedStopStrategy(1, ("HARD",)),
                    }
                ],
                pit_geometry(),
                total_laps=4,
                rng=SeededRandomSource(1),
                compounds={c.name: c for c in model.compounds},
                track_params=track(),
                model_parameters=model,
                track_rain=(DRY,) * 4,
                race_control=None,
                dt_s=0.5,
            )
        events = {
            event["type"]: event["time_ms"] / 1000 for event in race["pit_stop_events"]
        }
        inside = [
            value
            for index, value in enumerate(traffic)
            if events["service_started"] + 0.5
            < (index + 1) * 0.5
            < events["service_completed"]
        ]
        self.assertTrue(inside)
        self.assertTrue(all(value == 0 for value in inside))

    def test_cancellation_interrupts_dynamic_track_integration(self):
        calls = 0

        def cancel_after_two_steps():
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("cancelada")

        with patch(
            "f1_simulator.domain.race_simulation_2d.step_track_condition",
            wraps=step_track_condition,
        ) as evolve:
            with self.assertRaisesRegex(RuntimeError, "cancelada"):
                simulate_2d_race(
                    [{"driver_id": "a", "name": "A", "grid_position": 1}],
                    small_geometry(), total_laps=1, rng=SeededRandomSource(1),
                    track_rain=(HEAVY,), race_control=None,
                    check_cancelled=cancel_after_two_steps,
                )
        self.assertEqual(evolve.call_count, 2)

    def test_real_elapsed_time_and_seed_reproducibility(self):
        rain = (WeatherSegment(1, 3, HEAVY),)
        first = self._run(rain, 3)
        second = self._run(rain, 3)
        self.assertEqual(first["track_conditions"], second["track_conditions"])
        self.assertEqual(first["classification"], second["classification"])
        # A volta nao tem duracao historica fixa: compare o tempo observado
        # a uma previsao que supoe uma volta de 90 segundos.
        predicted = simulate_track_conditions([HEAVY] * 3, lap_minutes=1.5)
        self.assertLess(
            first["track_conditions"][-1]["surface_water"], predicted[-1].surface_water
        )

    def test_engine_publishes_track_conditions_and_slows_down_in_rain(self):
        # Volta sintetica de ~7 s: a agua evolui por minuto, entao 12 voltas
        # de chuva forte (~1,4 min) deixam a pista apenas umida.
        laps = 12
        rain = (WeatherSegment(1, laps, HEAVY),)
        dry = self._run((), laps)
        wet = self._run(rain, laps)
        self.assertEqual(len(wet["track_conditions"]), laps)
        self.assertGreater(wet["track_conditions"][-1]["surface_water"], 0.15)
        dry_time = min(c["total_time_ms"] for c in dry["classification"])
        wet_time = min(c["total_time_ms"] for c in wet["classification"])
        self.assertGreater(wet_time, dry_time * 1.03)
        kinds = {a["kind"] for a in wet["assumptions"]}
        self.assertIn("track_condition", kinds)


if __name__ == "__main__":
    unittest.main()
