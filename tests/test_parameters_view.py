from __future__ import annotations

import os
import unittest
from unittest.mock import patch

try:
    import arcade

    from frontend.arcade.configuration_state import (
        ConfigurationFormData,
        WeatherSchedule,
    )
    from frontend.arcade.parameters_view import ParametersView
    from frontend.arcade.weather_view import (
        TIMELINE_BOTTOM,
        TIMELINE_LEFT,
        TIMELINE_WIDTH,
        SUMMARY_NEXT_BOUNDS,
        WEATHER_ICON_PATHS,
        WEATHER_PALETTE_BOUNDS,
        WEATHER_TIMELINE_COLORS,
        WeatherConfigurationView,
    )
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

    def test_weather_view_selects_a_color_from_the_palette(self) -> None:
        parent = ParametersView()
        view = WeatherConfigurationView(parent, WeatherSchedule.dry(10))
        left, bottom, width, height = WEATHER_PALETTE_BOUNDS["Chuva leve"]

        view.on_mouse_press(
            int(left + width / 2),
            int(bottom + height / 2),
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )

        self.assertEqual(view.selected_weather, "Chuva leve")
        self.assertEqual(view.weather_dropdown.value, "Chuva leve")

    def test_weather_icons_cover_every_supported_condition(self) -> None:
        self.assertEqual(
            set(WEATHER_ICON_PATHS),
            {"Seco", "Chuva leve", "Chuva intensa"},
        )
        self.assertTrue(all(path.is_file() for path in WEATHER_ICON_PATHS.values()))

    def test_weather_summary_pages_keep_every_interval_accessible(self) -> None:
        parent = ParametersView()
        schedule = WeatherSchedule(
            tuple(
                "Seco" if lap % 2 else "Chuva leve"
                for lap in range(1, 11)
            )
        )
        view = WeatherConfigurationView(parent, schedule)
        left, bottom, width, height = SUMMARY_NEXT_BOUNDS

        self.assertEqual(len(schedule.ranges()), 10)
        self.assertEqual(view._summary_page_count(), 2)

        handled = view._handle_summary_navigation(
            int(left + width / 2), int(bottom + height / 2)
        )

        self.assertTrue(handled)
        self.assertEqual(view._summary_page, 1)

    def test_weather_view_paints_the_dragged_lap_range(self) -> None:
        parent = ParametersView()
        view = WeatherConfigurationView(parent, WeatherSchedule.dry(10))
        palette_left, palette_bottom, _, _ = WEATHER_PALETTE_BOUNDS[
            "Chuva intensa"
        ]
        view.on_mouse_press(
            palette_left + 1,
            palette_bottom + 1,
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        lap_six_x = TIMELINE_LEFT + TIMELINE_WIDTH * 5.5 / 10
        lap_three_x = TIMELINE_LEFT + TIMELINE_WIDTH * 2.5 / 10
        timeline_y = TIMELINE_BOTTOM + 1

        view.on_mouse_press(
            int(lap_six_x), timeline_y, arcade.MOUSE_BUTTON_LEFT, 0
        )
        view.on_mouse_drag(
            int(lap_three_x), timeline_y, 0, 0, arcade.MOUSE_BUTTON_LEFT, 0
        )
        view.on_mouse_release(
            int(lap_three_x), timeline_y, arcade.MOUSE_BUTTON_LEFT, 0
        )

        self.assertEqual(
            view.schedule.by_lap,
            ("Seco", "Seco")
            + ("Chuva intensa",) * 4
            + ("Seco",) * 4,
        )
        self.assertEqual(view.start_lap_input.text, "3")
        self.assertEqual(view.end_lap_input.text, "6")

    def test_weather_view_clamps_a_drag_released_after_the_timeline(self) -> None:
        parent = ParametersView()
        view = WeatherConfigurationView(parent, WeatherSchedule.dry(10))
        lap_nine_x = TIMELINE_LEFT + TIMELINE_WIDTH * 8.5 / 10
        timeline_y = TIMELINE_BOTTOM + 1

        view.on_mouse_press(
            int(lap_nine_x), timeline_y, arcade.MOUSE_BUTTON_LEFT, 0
        )
        view.on_mouse_release(
            TIMELINE_LEFT + TIMELINE_WIDTH + 200,
            timeline_y,
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )

        self.assertEqual(view.schedule.by_lap[8:], ("Seco", "Seco"))
        self.assertEqual(view.start_lap_input.text, "9")
        self.assertEqual(view.end_lap_input.text, "10")

    @patch("frontend.arcade.weather_view.arcade.draw_lbwh_rectangle_outline")
    @patch("frontend.arcade.weather_view.arcade.draw_lbwh_rectangle_filled")
    def test_weather_timeline_uses_proportional_colored_segments(
        self,
        draw_filled,
        _draw_outline,
    ) -> None:
        parent = ParametersView()
        schedule = (
            WeatherSchedule.dry(10)
            .apply(3, 5, "Chuva leve")
            .apply(6, 10, "Chuva intensa")
        )
        view = WeatherConfigurationView(parent, schedule)

        view._draw_timeline()

        weather_calls = [
            call
            for call in draw_filled.call_args_list
            if call.args[4] in WEATHER_TIMELINE_COLORS.values()
        ]
        self.assertEqual(len(weather_calls), 3)
        colors = [call.args[4] for call in weather_calls]
        geometry_widths = [
            view._range_geometry(weather_range)[1]
            for weather_range in schedule.ranges()
        ]
        self.assertAlmostEqual(sum(geometry_widths), TIMELINE_WIDTH)
        self.assertEqual(
            colors,
            [
                WEATHER_TIMELINE_COLORS["Seco"],
                WEATHER_TIMELINE_COLORS["Chuva leve"],
                WEATHER_TIMELINE_COLORS["Chuva intensa"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
