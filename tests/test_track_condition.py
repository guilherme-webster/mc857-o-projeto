"""Estado dinamico da pista: agua, temperatura, borracha e aderencia (ADR 0015)."""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from f1_simulator.adapters.datasets.mock_track_geometry import MockTrackDatasetAdapter
from f1_simulator.application.build_grid import GridEntry
from f1_simulator.application.run_grid_simulation import (
    RaceSetup,
    run_grid_simulation,
)
from f1_simulator.domain.fuel import FuelPlan
from f1_simulator.domain.race_simulation_2d import GRID_ROW_SPACING_M, simulate_2d_race
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.speed_dynamics import (
    DEFAULT_CAR_PHYSICS,
    GripLapTimes,
    lap_time_ms,
    steady_lap,
)
from f1_simulator.domain.strategy import NoStopStrategy, PlannedStopStrategy
from f1_simulator.domain.track_condition import (
    ASSUMED_CIRCUIT_TEMPERATURES_C,
    ASSUMED_TRACK_CONDITION,
    LiveTrackCondition,
    TrackConditionParameters,
    approximate_lap_time_ratio,
    circuit_dry_temperature_c,
    circuit_track_condition,
    rubber_grip_factor,
    simulate_track_conditions,
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
from tests.fuel_support import fuel_parameters
from tests.geometry_support import attribute, small_geometry
from tests.model_support import parameters, track
from tests.test_pit_lane import pit_geometry

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
        self.assertAlmostEqual(approximate_lap_time_ratio(p.damp_grip), 1.13, delta=0.02)
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
        self.assertLess(wettest.track_temp_c, ASSUMED_TRACK_CONDITION.dry_track_temp_c - 5)
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


class _RecordingTrack(LiveTrackCondition):
    """Pista que registra o que o motor 2D passa a cada avanco."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.traffic: list[float | None] = []
        self.laps: list[int] = []

    def advance(self, dt_s, lap, *, traffic_laps=None):
        self.traffic.append(traffic_laps)
        self.laps.append(lap)
        super().advance(dt_s, lap, traffic_laps=traffic_laps)


class TrafficRubberTest(unittest.TestCase):
    """Borracha depositada pela distancia percorrida na pista (issue #119)."""

    def test_a_full_field_lap_lays_one_peloton_lap_of_rubber(self):
        p = ASSUMED_TRACK_CONDITION
        live = LiveTrackCondition([DRY] * 3)
        live.advance(0.2, 1, traffic_laps=float(p.traffic_reference_cars))
        expected = p.initial_rubber + p.rubber_gain_per_lap * (1 - p.initial_rubber)
        self.assertAlmostEqual(live.rubber, expected, places=12)

    def test_slicing_the_same_traffic_into_ticks_lays_the_same_rubber(self):
        one, many = LiveTrackCondition([DRY] * 3), LiveTrackCondition([DRY] * 3)
        one.advance(60.0, 1, traffic_laps=10.0)
        for _ in range(300):
            many.advance(0.2, 1, traffic_laps=10.0 / 300)
        self.assertAlmostEqual(one.rubber, many.rubber, places=12)

    def test_no_traffic_lays_no_rubber_and_negative_is_rejected(self):
        live = LiveTrackCondition([DRY] * 3)
        live.advance(30.0, 1, traffic_laps=0.0)
        self.assertEqual(live.rubber, ASSUMED_TRACK_CONDITION.initial_rubber)
        with self.assertRaises(ValueError):
            live.advance(0.2, 1, traffic_laps=-0.1)

    def test_engine_counts_track_distance_until_the_flag(self):
        # Um carro, largando ``GRID_ROW_SPACING_M`` atras da linha: o trafego
        # somado e a corrida inteira mais o trecho do grid. O ultimo tick nao
        # chega a ser depositado (o clima avanca no tick seguinte), dai a folga.
        geometry = small_geometry()
        laps = 3
        live = _RecordingTrack([DRY] * laps)
        simulate_2d_race(
            [{"driver_id": "a", "name": "A", "grid_position": 1}],
            geometry,
            total_laps=laps,
            rng=SeededRandomSource(1),
            live_track=live,
            race_control=None,
        )
        expected = laps + GRID_ROW_SPACING_M / geometry.lap_length_m
        self.assertAlmostEqual(sum(live.traffic), expected, delta=0.05)
        self.assertEqual(live.laps, sorted(live.laps))
        self.assertEqual((min(live.laps), max(live.laps)), (1, laps))

    def test_pit_lane_lays_no_rubber(self):
        # Boxes de 360 m a 440 m numa volta de 400 m: com uma parada, a pista
        # recebe 80 m (0,2 volta) a menos que na mesma corrida sem parada.
        geometry = pit_geometry()
        model = parameters()

        def traffic(strategy):
            live = _RecordingTrack([DRY] * 4)
            simulate_2d_race(
                [
                    {
                        "driver_id": "a",
                        "name": "A",
                        "grid_position": 1,
                        "start_fuel_kg": 5.0,
                        "strategy": strategy,
                    }
                ],
                geometry,
                total_laps=4,
                rng=SeededRandomSource(1),
                compounds={c.name: c for c in model.compounds},
                track_params=track(),
                model_parameters=model,
                fuel=FuelPlan(
                    fuel_parameters(),
                    30_000,
                    geometry.lap_length_m / 1000,
                    "track_geometry",
                ),
                live_track=live,
                race_control=None,
            )
            return sum(live.traffic)

        missing = traffic(NoStopStrategy()) - traffic(PlannedStopStrategy(1, ("HARD",)))
        self.assertAlmostEqual(missing, 80.0 / geometry.lap_length_m, delta=0.05)


class CircuitTemperatureTest(unittest.TestCase):
    """Temperatura do asfalto seco por circuito, trazida do PR #185."""

    def test_known_circuits_use_the_table_and_others_the_default(self):
        self.assertEqual(circuit_dry_temperature_c("circuit:3"), 28.0)
        self.assertEqual(circuit_dry_temperature_c("circuit:69"), 42.0)
        default = ASSUMED_TRACK_CONDITION.dry_track_temp_c
        self.assertEqual(circuit_dry_temperature_c("circuit:999"), default)
        self.assertEqual(circuit_dry_temperature_c(None), default)

    def test_only_the_dry_temperature_changes(self):
        condition = circuit_track_condition("circuit:69")
        self.assertEqual(condition.dry_track_temp_c, 42.0)
        self.assertEqual(
            replace(condition, dry_track_temp_c=ASSUMED_TRACK_CONDITION.dry_track_temp_c),
            ASSUMED_TRACK_CONDITION,
        )

    def test_engine_uses_and_reports_the_circuit_temperature(self):
        grid = tuple(GridEntry(f"driver:{i}", f"P{i}", "team:1", "Team") for i in range(2))
        attributes = {g.driver_id: attribute(g.driver_id) for g in grid}
        geometry = small_geometry()

        def run(track_id):
            return run_grid_simulation(
                grid,
                attributes,
                RaceSetup(total_laps=3, track_id=track_id),
                parameters=parameters(),
                lap_length_m=geometry.lap_length_m,
                rng=SeededRandomSource(7),
                geometry=geometry,
                race_control=None,
            )

        for track_id, fallback in (("circuit:69", False), ("circuit:999", True)):
            with self.subTest(track_id=track_id):
                result = run(track_id)
                expected = circuit_dry_temperature_c(track_id)
                self.assertEqual(result["track_conditions"][0]["track_temp_c"], expected)
                grip = next(
                    a["grip"] for a in result["assumptions"] if a["kind"] == "track_condition"
                )
                self.assertEqual(grip["dry_track_temp_c"], expected)
                self.assertEqual(grip["temperature_fallback"], fallback)
                self.assertEqual(grip["temperature_source_kind"], "assumed")
        self.assertIn("circuit:69", ASSUMED_CIRCUIT_TEMPERATURES_C)


if __name__ == "__main__":
    unittest.main()
