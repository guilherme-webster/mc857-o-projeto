from __future__ import annotations

import unittest

from frontend.arcade.configuration_state import (
    MAX_SEED,
    ConfigurationFormData,
    ConfigurationFormError,
    PlannedRace,
    SimulationPlan,
    WeatherRange,
    WeatherSchedule,
    automatic_track_order,
    parse_optional_seed,
)


class ConfigurationFormDataTest(unittest.TestCase):
    def test_free_race_is_default_without_historical_preset(self) -> None:
        self.assertEqual(ConfigurationFormData().preset, "Corrida livre")

    def test_series_plan_requires_unique_circuits(self) -> None:
        race = PlannedRace("circuit:18", "Interlagos", ConfigurationFormData())
        with self.assertRaisesRegex(ConfigurationFormError, "pelo menos uma pista"):
            SimulationPlan(())
        with self.assertRaisesRegex(ConfigurationFormError, "duplicadas"):
            SimulationPlan((race, race))

    def test_parses_valid_widget_text(self) -> None:
        result = ConfigurationFormData.from_text(
            preset="GP de São Paulo 2024",
            laps="71",
        )

        self.assertEqual(result.laps, 71)
        self.assertEqual(result.weather_schedule.total_laps, 71)
        self.assertEqual(set(result.weather_schedule.by_lap), {"Seco"})

    def test_rejects_non_numeric_and_out_of_range_values(self) -> None:
        invalid_cases = (
            ({"laps": "abc"}, "voltas deve ser um número inteiro"),
            ({"laps": "0"}, "voltas deve estar entre 1 e 200"),
        )

        defaults = {
            "preset": "GP de São Paulo 2024",
            "laps": "69",
        }
        for replacement, message in invalid_cases:
            with self.subTest(replacement=replacement):
                values = defaults | replacement
                with self.assertRaisesRegex(ConfigurationFormError, message):
                    ConfigurationFormData.from_text(**values)

    def test_applies_weather_to_inclusive_lap_ranges(self) -> None:
        schedule = WeatherSchedule.dry(10)

        result = schedule.apply(3, 5, "Chuva leve")

        self.assertEqual(
            result.ranges(),
            (
                WeatherRange(1, 2, "Seco"),
                WeatherRange(3, 5, "Chuva leve"),
                WeatherRange(6, 10, "Seco"),
            ),
        )
        self.assertEqual(schedule.ranges(), (WeatherRange(1, 10, "Seco"),))

    def test_rejects_invalid_weather_intervals(self) -> None:
        schedule = WeatherSchedule.dry(10)
        invalid_cases = (
            ("0", "5", "entre 1 e 10"),
            ("8", "3", "inicial não pode ser maior"),
            ("abc", "3", "devem ser números inteiros"),
        )

        for start_lap, end_lap, message in invalid_cases:
            with self.subTest(start_lap=start_lap, end_lap=end_lap):
                with self.assertRaisesRegex(ConfigurationFormError, message):
                    schedule.apply_text(
                        start_lap=start_lap,
                        end_lap=end_lap,
                        weather="Chuva intensa",
                    )

    def test_resizes_weather_when_the_lap_count_changes(self) -> None:
        schedule = WeatherSchedule.dry(5).apply(4, 5, "Chuva intensa")

        result = ConfigurationFormData.from_text(
            preset="GP de São Paulo 2024",
            laps="7",
            weather_schedule=schedule,
        )

        self.assertEqual(
            result.weather_schedule.by_lap,
            (
                "Seco",
                "Seco",
                "Seco",
                "Chuva intensa",
                "Chuva intensa",
                "Seco",
                "Seco",
            ),
        )

    def test_optional_seed_parser_accepts_blank_and_json_safe_integers(self) -> None:
        self.assertIsNone(parse_optional_seed("  "))
        self.assertEqual(parse_optional_seed("0"), 0)
        self.assertEqual(parse_optional_seed(str(MAX_SEED)), MAX_SEED)

        for value in ("texto", "-1", str(MAX_SEED + 1)):
            with self.subTest(value=value), self.assertRaises(ConfigurationFormError):
                parse_optional_seed(value)

    def test_automatic_track_order_depends_only_on_tournament_seed(self) -> None:
        ids = ("circuit:3", "circuit:1", "circuit:4", "circuit:2")
        first = automatic_track_order(ids, 4, 105, allow_repeats=False)
        repeated = automatic_track_order(
            tuple(reversed(ids)), 4, 105, allow_repeats=False
        )
        different = automatic_track_order(ids, 4, 106, allow_repeats=False)

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, different)


if __name__ == "__main__":
    unittest.main()
