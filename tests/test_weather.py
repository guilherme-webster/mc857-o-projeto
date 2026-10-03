"""Contratos do modelo climático isolado do backend e do Arcade."""

from dataclasses import replace
import unittest

from f1_simulator.domain.weather import (
    ASSUMED_WEATHER_PARAMETERS,
    RainLevel,
    WeatherState,
    simulate_weather,
)


class WeatherModelTests(unittest.TestCase):
    def test_dry_race_keeps_dry_track_and_default_humidity(self) -> None:
        history = simulate_weather([RainLevel.DRY] * 8)
        self.assertEqual(tuple(item.lap for item in history), tuple(range(1, 9)))
        self.assertTrue(all(item.state == WeatherState(50.0, 0.0) for item in history))

    def test_rain_builds_humidity_and_water_progressively(self) -> None:
        history = simulate_weather([RainLevel.LIGHT] * 3)
        self.assertEqual(history[0].rain, RainLevel.LIGHT)
        self.assertTrue(
            50
            < history[0].state.humidity_pct
            < history[1].state.humidity_pct
            < history[2].state.humidity_pct
            < 75
        )
        self.assertTrue(
            0
            < history[0].state.surface_water
            < history[1].state.surface_water
            < history[2].state.surface_water
        )

    def test_heavy_rain_has_stronger_effect_than_light(self) -> None:
        light = simulate_weather([RainLevel.LIGHT])[0].state
        heavy = simulate_weather([RainLevel.HEAVY])[0].state
        self.assertGreater(heavy.humidity_pct, light.humidity_pct)
        self.assertGreater(heavy.surface_water, light.surface_water)

    def test_water_persists_after_rain_and_then_drains(self) -> None:
        history = simulate_weather(
            [RainLevel.HEAVY, RainLevel.HEAVY] + [RainLevel.DRY] * 30
        )
        wet = history[1].state
        first_dry = history[2].state
        self.assertGreater(first_dry.surface_water, 0)
        self.assertLess(first_dry.surface_water, wet.surface_water)
        self.assertLess(first_dry.humidity_pct, wet.humidity_pct)
        self.assertEqual(history[-1].state.surface_water, 0)
        self.assertGreaterEqual(history[-1].state.humidity_pct, 50)

    def test_saturation_and_initial_state_are_bounded(self) -> None:
        history = simulate_weather([RainLevel.HEAVY] * 50)
        self.assertEqual(history[-1].state.surface_water, 1)
        self.assertTrue(all(0 <= item.state.humidity_pct <= 100 for item in history))
        drying = simulate_weather(
            [RainLevel.DRY], initial_state=WeatherState(90.0, 1.0)
        )
        self.assertGreater(drying[0].state.surface_water, 0)

    def test_same_inputs_produce_same_history(self) -> None:
        conditions = [RainLevel.DRY, RainLevel.LIGHT, RainLevel.HEAVY, RainLevel.DRY]
        self.assertEqual(simulate_weather(conditions), simulate_weather(conditions))

    def test_invalid_inputs_and_parameters_fail_explicitly(self) -> None:
        with self.assertRaisesRegex(ValueError, "pelo menos uma volta"):
            simulate_weather([])
        with self.assertRaisesRegex(ValueError, "volta 2"):
            simulate_weather([RainLevel.DRY, "Seco"])  # type: ignore[list-item]
        for state in ((-1, 0), (101, 0), (50, -0.1), (50, 1.1), (True, 0)):
            with self.subTest(state=state), self.assertRaises(ValueError):
                WeatherState(*state)
        for change in (
            {"humidity_response_fraction": 1.1},
            {"heavy_water_gain_per_lap": -0.1},
            {"light_water_gain_per_lap": 0.9},
            {"dry_humidity_pct": 95},
            {"parameter_version": " "},
            {"source_kind": "unknown"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(ASSUMED_WEATHER_PARAMETERS, **change)


if __name__ == "__main__":
    unittest.main()
