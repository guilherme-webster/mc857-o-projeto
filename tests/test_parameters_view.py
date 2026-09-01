from __future__ import annotations

import os
import unittest

try:
    import arcade

    from frontend.arcade.configuration_state import (
        ConfigurationFormData,
        WeatherSchedule,
    )
    from frontend.arcade.parameters_view import ParametersView
    from frontend.arcade.weather_view import WeatherConfigurationView
except ModuleNotFoundError as error:
    if error.name != "arcade":
        raise
    arcade = None  # type: ignore[assignment]
    ConfigurationFormData = None  # type: ignore[assignment,misc]
    ParametersView = None  # type: ignore[assignment,misc]
    WeatherConfigurationView = None  # type: ignore[assignment,misc]


ARCADE_GUI_TEST = ParametersView is not None and bool(os.environ.get("ARCADE_GUI_TEST"))


@unittest.skipUnless(
    ARCADE_GUI_TEST,
    "requires Arcade with ARCADE_GUI_TEST=True",
)
class ParametersViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.window = arcade.Window(1280, 720, visible=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.window.close()

    def test_submits_valid_widget_values_to_the_injected_action(self) -> None:
        received: list[ConfigurationFormData] = []
        view = ParametersView(on_start=received.append)
        view.laps_input.text = "71"
        view.accept_weather_schedule(
            WeatherSchedule.dry(71).apply(20, 30, "Chuva intensa")
        )

        view.submit_configuration()

        self.assertEqual(received[0].laps, 71)
        self.assertEqual(
            received[0].weather_schedule.by_lap[19:30],
            ("Chuva intensa",) * 11,
        )

    def test_keeps_invalid_values_in_the_form_instead_of_starting(self) -> None:
        received: list[ConfigurationFormData] = []
        view = ParametersView(on_start=received.append)
        view.laps_input.text = "zero"

        view.submit_configuration()

        self.assertEqual(received, [])
        self.assertIn("número inteiro", view.status_message)

    def test_restores_the_initial_values(self) -> None:
        view = ParametersView()
        view.laps_input.text = "12"
        view.accept_weather_schedule(
            WeatherSchedule.dry(12).apply(2, 4, "Chuva leve")
        )

        view.reset_configuration()

        self.assertEqual(view.laps_input.text, "69")
        self.assertEqual(
            view.configuration.weather_schedule,
            WeatherSchedule.dry(69),
        )

    def test_opens_the_weather_view_with_the_current_lap_count(self) -> None:
        view = ParametersView()
        self.window.show_view(view)
        view.laps_input.text = "71"

        view.open_weather_configuration()

        self.assertIsInstance(self.window.current_view, WeatherConfigurationView)
        self.assertEqual(self.window.current_view.schedule.total_laps, 71)

    def test_weather_view_applies_an_interval_and_saves_it_in_parent(self) -> None:
        parent = ParametersView()
        view = WeatherConfigurationView(parent, WeatherSchedule.dry(69))
        self.window.show_view(view)
        view.start_lap_input.text = "10"
        view.end_lap_input.text = "20"
        view.weather_dropdown.value = "Chuva leve"

        view.apply_weather_range()
        view.save_and_return()

        self.assertIs(self.window.current_view, parent)
        self.assertEqual(
            parent.configuration.weather_schedule.by_lap[9:20],
            ("Chuva leve",) * 11,
        )


if __name__ == "__main__":
    unittest.main()
