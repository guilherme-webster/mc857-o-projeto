from __future__ import annotations

import os
import unittest
from unittest.mock import patch

try:
    import arcade

    from frontend.arcade.configuration_state import (
        ConfigurationFormData,
        SimulationPlan,
        TournamentRules,
        WeatherSchedule,
    )
    from frontend.arcade.parameters_view import (
        CONFIGURE_TRACK_BOUNDS,
        CONFIRM_SERIES_BOUNDS,
        NEXT_TRACK_BOUNDS,
        ParametersView,
        TOGGLE_TRACK_BOUNDS,
        TOURNAMENT_WINDOW_SIZE,
    )
    from frontend.arcade.race_configuration_view import (
        RaceConfigurationView,
        SESSION_FIELD_BOUNDS,
        SESSION_STEPPER_BOUNDS,
        SIDEBAR_ITEMS,
        WEATHER_APPLY_BOUNDS,
        WEATHER_END_BOUNDS,
        WEATHER_NEXT_BOUNDS,
        WEATHER_PALETTE_BOUNDS as RACE_WEATHER_PALETTE_BOUNDS,
        WEATHER_START_BOUNDS,
        WEATHER_TIMELINE_BOUNDS,
    )
    from frontend.arcade.weather_view import (
        TIMELINE_BOTTOM,
        TIMELINE_LEFT,
        TIMELINE_WIDTH,
        SUMMARY_NEXT_BOUNDS,
        NAVIGATION_BOUNDS,
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
    CATALOG = {
        "count": 2,
        "tracks": [
            {"circuit_id": "circuit:18", "name": "Interlagos", "lap_length_m": 4232.0},
            {"circuit_id": "circuit:6", "name": "Monaco", "lap_length_m": 3337.0},
        ],
    }

    def ready_view(self) -> ParametersView:
        """Provide a catalog response without an HTTP server or waiting."""

        view = ParametersView(track_catalog_loader=lambda: self.CATALOG)
        view._catalog_results.put(("success", self.CATALOG))
        view.on_update(0)
        return view

    @classmethod
    def setUpClass(cls) -> None:
        cls.window = arcade.Window(1280, 720, visible=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.window.close()

    def test_submits_valid_widget_values_to_the_injected_action(self) -> None:
        received: list[SimulationPlan] = []
        view = self.ready_view()
        view._on_start = received.append
        view.toggle_selected_track()
        view.laps_input.text = "71"
        view.accept_weather_schedule(
            WeatherSchedule.dry(71).apply(20, 30, "Chuva intensa")
        )

        view.submit_configuration()

        self.assertEqual(received[0].races[0].configuration.laps, 71)
        self.assertEqual(
            received[0].races[0].configuration.weather_schedule.by_lap[19:30],
            ("Chuva intensa",) * 11,
        )

    def test_keeps_invalid_values_in_the_form_instead_of_starting(self) -> None:
        received: list[SimulationPlan] = []
        view = ParametersView(on_start=received.append)
        view.laps_input.text = "zero"

        view.submit_configuration()

        self.assertEqual(received, [])
        self.assertIn("número inteiro", view.status_message)

    def test_restores_the_initial_values(self) -> None:
        view = ParametersView()
        view.laps_input.text = "12"
        view.accept_weather_schedule(WeatherSchedule.dry(12).apply(2, 4, "Chuva leve"))

        view.reset_configuration()

        self.assertEqual(view.laps_input.text, "69")
        self.assertEqual(
            view.configuration.weather_schedule,
            WeatherSchedule.dry(69),
        )

    def test_opens_climate_tab_in_the_same_race_view(self) -> None:
        view = self.ready_view()
        self.window.show_view(view)
        view.laps_input.text = "71"

        view.open_weather_configuration()

        race_view = self.window.current_view
        self.assertIsInstance(race_view, RaceConfigurationView)
        race_view.on_mouse_release(100, 500, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertIs(self.window.current_view, race_view)
        self.assertEqual(race_view.active_topic, "Clima")
        self.assertEqual(race_view.schedule.total_laps, 71)

    def test_initial_screen_opens_the_selected_track_configuration(self) -> None:
        view = self.ready_view()
        self.window.show_view(view)
        left, bottom, width, height = CONFIGURE_TRACK_BOUNDS
        x = int(left + width / 2)
        y = int(bottom + height / 2)

        view.on_mouse_press(x, y, arcade.MOUSE_BUTTON_LEFT, 0)
        view.on_mouse_release(x, y, arcade.MOUSE_BUTTON_LEFT, 0)

        self.assertIsInstance(self.window.current_view, RaceConfigurationView)
        self.assertFalse(view.preset_dropdown.visible)
        self.assertFalse(view.laps_input.visible)

    def test_selects_another_backend_track_and_preserves_it_after_return(self) -> None:
        view = self.ready_view()
        self.window.show_view(view)
        left, bottom, width, height = NEXT_TRACK_BOUNDS

        view.on_mouse_release(
            left + width // 2, bottom + height // 2, arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertEqual(view.selected_track["circuit_id"], "circuit:6")

        view.open_track_configuration()
        configured = self.window.current_view
        self.assertEqual(configured.circuit_id, "circuit:6")
        self.assertEqual(configured.track_name, "Monaco")
        configured.cancel()
        self.assertIs(self.window.current_view, view)
        self.assertEqual(view.selected_track["circuit_id"], "circuit:6")

    def test_race_configuration_saves_session_and_inline_weather(
        self,
    ) -> None:
        view = self.ready_view()
        self.window.show_view(view)
        view.toggle_selected_track()
        view.open_track_configuration()
        race_view = self.window.current_view
        left, bottom, width, height = SESSION_STEPPER_BOUNDS["first_lap"][1]
        race_view.on_mouse_release(
            left + width // 2,
            bottom + height // 2,
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        self.assertEqual(race_view.session.first_lap, 2)
        self.assertEqual(race_view.session.start_mode, "Parada")
        race_view.on_mouse_release(100, 500, arcade.MOUSE_BUTTON_LEFT, 0)
        palette = RACE_WEATHER_PALETTE_BOUNDS["Chuva leve"]
        race_view.on_mouse_release(
            palette[0] + 10, palette[1] + 10, arcade.MOUSE_BUTTON_LEFT, 0
        )
        left, bottom, width, height = WEATHER_TIMELINE_BOUNDS
        start_x = int(left + width * 1.5 / 69)
        end_x = int(left + width * 2.5 / 69)
        race_view.on_mouse_press(
            start_x, bottom + height // 2, arcade.MOUSE_BUTTON_LEFT, 0
        )
        race_view.on_mouse_drag(
            end_x, bottom + height // 2, 0, 0, arcade.MOUSE_BUTTON_LEFT, 0
        )
        race_view.on_mouse_release(
            end_x, bottom + height // 2, arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertIs(self.window.current_view, race_view)
        self.assertEqual(race_view.schedule.by_lap[1], "Chuva leve")
        self.assertEqual(race_view.schedule.by_lap[2], "Chuva leve")
        race_view.save_and_return()
        self.assertEqual(view.configuration.weather_schedule.by_lap[1], "Chuva leve")
        self.assertEqual(view._session_configurations["circuit:18"].first_lap, 2)
        self.assertEqual(view.build_simulation_plan().races[0].session.first_lap, 2)

    def test_session_stepper_buttons_stay_inside_fields_and_preserve_start_mode(
        self,
    ) -> None:
        parent = self.ready_view()
        self.window.show_view(parent)
        parent.open_track_configuration()
        race_view = self.window.current_view

        for field, buttons in SESSION_STEPPER_BOUNDS.items():
            field_left, field_bottom, field_width, field_height = SESSION_FIELD_BOUNDS[
                field
            ]
            for left, bottom, width, height in buttons:
                self.assertGreaterEqual(left, field_left)
                self.assertGreaterEqual(bottom, field_bottom)
                self.assertLessEqual(left + width, field_left + field_width)
                self.assertLessEqual(bottom + height, field_bottom + field_height)

        left, bottom, width, height = SESSION_STEPPER_BOUNDS["last_lap"][0]
        race_view.on_mouse_release(
            left + width // 2,
            bottom + height // 2,
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        self.assertEqual(race_view.session.last_lap, 68)
        self.assertEqual(race_view.session.start_mode, "Parada")

        left, bottom, width, height = SESSION_FIELD_BOUNDS["last_lap"]
        race_view.on_mouse_release(
            left + 20, bottom + height // 2, arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertEqual(race_view.session.last_lap, 68)

    def test_race_configuration_hides_source_metadata_on_session_and_climate(
        self,
    ) -> None:
        parent = self.ready_view()
        self.window.show_view(parent)
        parent.open_track_configuration()
        race_view = self.window.current_view
        for topic in ("Sessão", "Clima"):
            race_view.active_topic = topic
            with patch.object(RaceConfigurationView, "_text") as draw_text:
                race_view.on_draw()
            labels = [call.args[0] for call in draw_text.call_args_list]
            self.assertFalse(any("ID canônico" in label for label in labels))
            self.assertFalse(any("Geometria reduzida" in label for label in labels))
            self.assertFalse(any("pontos de pista" in label for label in labels))
            if topic == "Sessão":
                self.assertNotIn("Largada", labels)

    def test_inline_weather_numeric_interval_validates_and_paints(self) -> None:
        parent = self.ready_view()
        self.window.show_view(parent)
        parent.open_track_configuration()
        race_view = self.window.current_view
        race_view.on_mouse_release(100, 500, arcade.MOUSE_BUTTON_LEFT, 0)
        bounds = RACE_WEATHER_PALETTE_BOUNDS["Chuva intensa"]
        race_view.on_mouse_release(
            bounds[0] + 10, bounds[1] + 10, arcade.MOUSE_BUTTON_LEFT, 0
        )
        for field, value in ((WEATHER_START_BOUNDS, "5"), (WEATHER_END_BOUNDS, "7")):
            race_view.on_mouse_release(
                field[0] + 10, field[1] + 10, arcade.MOUSE_BUTTON_LEFT, 0
            )
            race_view.on_text(value)
        bounds = WEATHER_APPLY_BOUNDS
        race_view.on_mouse_release(
            bounds[0] + 10, bounds[1] + 10, arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertEqual(race_view.schedule.by_lap[4:7], ("Chuva intensa",) * 3)
        self.assertEqual(race_view.schedule.by_lap[3], "Seco")
        race_view._weather_start_text = "0"
        race_view.apply_weather_range()
        self.assertIn("entre 1 e 69", race_view._status)

    def test_inline_weather_cancel_discards_unsaved_edits(self) -> None:
        parent = self.ready_view()
        self.window.show_view(parent)
        parent.open_track_configuration()
        race_view = self.window.current_view
        race_view.on_mouse_release(100, 500, arcade.MOUSE_BUTTON_LEFT, 0)
        race_view.selected_weather = "Chuva leve"
        race_view._weather_start_text = "1"
        race_view._weather_end_text = "2"
        race_view.apply_weather_range()
        race_view.cancel()
        self.assertIs(self.window.current_view, parent)
        self.assertEqual(parent.configuration.weather_schedule, WeatherSchedule.dry(69))

    def test_inline_weather_summary_pages_when_more_than_eight_intervals(self) -> None:
        schedule = WeatherSchedule(tuple(("Seco", "Chuva leve") * 10))
        parent = self.ready_view()
        race_view = RaceConfigurationView(
            parent,
            schedule,
            circuit_id="circuit:18",
            track_name="Interlagos",
            track_loader=lambda _id: {},
        )
        self.window.show_view(race_view)
        race_view.on_mouse_release(100, 500, arcade.MOUSE_BUTTON_LEFT, 0)
        bounds = WEATHER_NEXT_BOUNDS
        race_view.on_mouse_release(
            bounds[0] + 10, bounds[1] + 10, arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertEqual(race_view._weather_summary_page, 1)
        self.assertIs(self.window.current_view, race_view)

    def test_assistance_tab_is_absent_from_both_race_and_climate(self) -> None:
        self.assertNotIn("Assistências", NAVIGATION_BOUNDS)
        self.assertNotIn("Assistências", SIDEBAR_ITEMS)

    def test_large_window_draws_full_panels_and_maps_clicks(self) -> None:
        original_size = self.window.get_size()
        try:
            self.window.set_size(*TOURNAMENT_WINDOW_SIZE)
            view = self.ready_view()
            self.window.show_view(view)
            view.on_draw()
            screenshot = arcade.get_image()
            self.assertNotEqual(screenshot.getpixel((100, 350))[:3], (0, 0, 0))
            self.assertEqual(view._screen_camera.viewport.width, 1672)
            left, bottom, width, height = TOGGLE_TRACK_BOUNDS
            x = int((left + width / 2) * TOURNAMENT_WINDOW_SIZE[0] / 1280)
            y = int((bottom + height / 2) * TOURNAMENT_WINDOW_SIZE[1] / 720)
            view.on_mouse_release(x, y, arcade.MOUSE_BUTTON_LEFT, 0)
            self.assertEqual(view.selected_track_ids, ("circuit:18",))
        finally:
            self.window.set_size(*original_size)

    def test_does_not_open_a_track_before_catalog_loads(self) -> None:
        view = ParametersView(track_catalog_loader=lambda: self.CATALOG)
        self.window.show_view(view)
        view.open_track_configuration()

        self.assertIs(self.window.current_view, view)
        self.assertIn("catálogo", view.status_message)

    def test_catalog_failure_keeps_selection_unavailable(self) -> None:
        view = ParametersView(track_catalog_loader=lambda: self.CATALOG)
        view._catalog_results.put(("error", "URLError"))
        view.on_update(0)

        self.assertIsNone(view.selected_track)
        self.assertIn("URLError", view.status_message)
        view.open_track_configuration()
        self.assertIsNone(view.selected_track)

    def test_navigation_wraps_through_all_catalog_entries(self) -> None:
        view = self.ready_view()
        view._selected_track_index = len(view._tracks) - 1

        view._change_track(1)

        self.assertEqual(view.selected_track["circuit_id"], "circuit:18")

    def test_builds_ordered_plan_with_independent_per_track_settings(self) -> None:
        view = self.ready_view()
        view.rules = TournamentRules(total_stages=2)
        view.toggle_selected_track()
        view.accept_weather_schedule(WeatherSchedule.dry(4).apply(2, 3, "Chuva leve"))

        view._change_track(1)
        view.toggle_selected_track()
        view.accept_weather_schedule(WeatherSchedule.dry(2))
        plan = view.build_simulation_plan()

        self.assertEqual(
            [race.circuit_id for race in plan.races], ["circuit:18", "circuit:6"]
        )
        self.assertEqual([race.configuration.laps for race in plan.races], [4, 2])
        self.assertEqual(
            plan.races[0].configuration.weather_schedule.by_lap[1], "Chuva leve"
        )
        self.assertEqual(
            plan.races[1].configuration.weather_schedule.by_lap, ("Seco", "Seco")
        )
        self.assertEqual(plan.races[0].configuration.preset, "Corrida livre")

    def test_remove_and_readd_moves_track_to_end_without_duplicate(self) -> None:
        view = self.ready_view()
        view.rules = TournamentRules(total_stages=2)
        view.toggle_selected_track()
        view._change_track(1)
        view.toggle_selected_track()
        view._change_track(-1)
        view.remove_selected_track()
        view.toggle_selected_track()

        self.assertEqual(view.selected_track_ids, ("circuit:6", "circuit:18"))

    def test_confirmation_requires_at_least_one_track(self) -> None:
        view = self.ready_view()
        view.submit_configuration()
        self.assertIn("Selecione 1 pista(s)", view.status_message)

    def test_automatic_sequence_is_reproducible_and_respects_stage_count(self) -> None:
        view = self.ready_view()
        view.rules = TournamentRules(total_stages=2)
        view.generate_automatic_sequence()
        first = view.selected_track_ids
        view.generate_automatic_sequence()
        self.assertEqual(view.selected_track_ids, first)
        self.assertEqual(len(set(first)), 2)

    def test_repeats_are_only_available_when_enabled(self) -> None:
        view = self.ready_view()
        view.rules = TournamentRules(total_stages=2)
        view.toggle_selected_track()
        view.toggle_selected_track()
        self.assertEqual(view.selected_track_ids, ("circuit:18",))
        view.rules = TournamentRules(total_stages=2, allow_repeats=True)
        view.toggle_selected_track()
        self.assertEqual(view.selected_track_ids, ("circuit:18", "circuit:18"))
        self.assertEqual(len(view.build_simulation_plan().races), 2)

    def test_dragging_a_sequence_row_changes_order(self) -> None:
        view = self.ready_view()
        view.rules = TournamentRules(total_stages=2)
        view.toggle_selected_track()
        view._change_track(1)
        view.toggle_selected_track()
        self.window.show_view(view)
        view.on_mouse_press(965, 455, arcade.MOUSE_BUTTON_LEFT, 0)
        view.on_mouse_release(965, 418, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertEqual(view.selected_track_ids, ("circuit:6", "circuit:18"))

    def test_sequence_scrolls_one_stage_at_a_time_and_clamps_after_removal(
        self,
    ) -> None:
        view = self.ready_view()
        view.rules = TournamentRules(total_stages=6, allow_repeats=True)
        self.window.show_view(view)
        for _ in range(6):
            view.toggle_selected_track()

        self.assertEqual(view._sequence_scroll_index, 3)
        width, height = self.window.get_size()
        scroll_x = int(1000 * width / 1280)
        scroll_y = int(420 * height / 720)
        view.on_mouse_scroll(scroll_x, scroll_y, 0, 1)
        self.assertEqual(view._sequence_scroll_index, 2)
        self.assertEqual(view._sequence_index_at(965, 455), 2)
        view.on_mouse_scroll(scroll_x, scroll_y, 0, 10)
        self.assertEqual(view._sequence_scroll_index, 0)
        view.on_mouse_scroll(scroll_x, scroll_y, 0, -10)
        self.assertEqual(view._sequence_scroll_index, 3)

        view.remove_selected_track()

        self.assertEqual(view._sequence_scroll_index, 2)
        self.assertEqual(view._sequence_index_at(965, 381), 4)

    def test_tournament_screen_omits_source_generation_mode_and_summary(self) -> None:
        view = self.ready_view()
        self.window.show_view(view)
        view.on_draw()

        labels = {label.text for label in view._native_labels}
        self.assertIn("Extensão da pista: 4,232 km", labels)
        self.assertNotIn("Geração da sequência", labels)
        self.assertNotIn("Resumo do torneio", labels)
        self.assertFalse(any("Trotman" in label for label in labels))
        self.assertFalse(any("Geometria reduzida" in label for label in labels))

    def test_visible_controls_add_track_and_confirm_sequence(self) -> None:
        received: list[SimulationPlan] = []
        view = self.ready_view()
        view._on_start = received.append
        self.window.show_view(view)
        for bounds in (TOGGLE_TRACK_BOUNDS, CONFIRM_SERIES_BOUNDS):
            left, bottom, width, height = bounds
            view.on_mouse_release(
                left + width // 2, bottom + height // 2, arcade.MOUSE_BUTTON_LEFT, 0
            )
        self.assertEqual(received[0].races[0].circuit_id, "circuit:18")

    def test_track_configuration_uses_the_sidebar_to_change_topics(self) -> None:
        parent = ParametersView()
        view = WeatherConfigurationView(parent, WeatherSchedule.dry(69))
        left, bottom, width, height = NAVIGATION_BOUNDS["Pista"]

        view.on_mouse_press(
            int(left + width / 2),
            int(bottom + height / 2),
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )

        self.assertEqual(view.active_topic, "Pista")
        self.assertFalse(view.start_lap_input.visible)
        self.assertFalse(view.end_lap_input.visible)

    def test_track_configuration_draws_track_pit_lane_and_service_point(self) -> None:
        parent = ParametersView()
        view = WeatherConfigurationView(parent, WeatherSchedule.dry(69))
        view.active_topic = "Pista"
        view._track_results.put(
            (
                "success",
                {
                    "lap_length_m": 4309.0,
                    "track_points": [
                        {"sequence": 0, "x": 0, "y": 0},
                        {"sequence": 1, "x": 2, "y": 0},
                        {"sequence": 2, "x": 2, "y": 1},
                        {"sequence": 3, "x": 0, "y": 1},
                    ],
                    "pit_lane_points": [
                        {
                            "sequence": 0,
                            "x": 0.5,
                            "y": 0.2,
                            "is_service_point": False,
                        },
                        {
                            "sequence": 1,
                            "x": 1.5,
                            "y": 0.2,
                            "is_service_point": True,
                        },
                    ],
                },
            )
        )

        view.on_update(0)
        self.window.show_view(view)
        self.window.clear()
        view._draw_track_preview()

        self.assertIsNotNone(view._track_preview)
        self.assertEqual(view.status_message, "Geometria da pista carregada.")

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
            tuple("Seco" if lap % 2 else "Chuva leve" for lap in range(1, 11))
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
        palette_left, palette_bottom, _, _ = WEATHER_PALETTE_BOUNDS["Chuva intensa"]
        view.on_mouse_press(
            palette_left + 1,
            palette_bottom + 1,
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        lap_six_x = TIMELINE_LEFT + TIMELINE_WIDTH * 5.5 / 10
        lap_three_x = TIMELINE_LEFT + TIMELINE_WIDTH * 2.5 / 10
        timeline_y = TIMELINE_BOTTOM + 1

        view.on_mouse_press(int(lap_six_x), timeline_y, arcade.MOUSE_BUTTON_LEFT, 0)
        view.on_mouse_drag(
            int(lap_three_x), timeline_y, 0, 0, arcade.MOUSE_BUTTON_LEFT, 0
        )
        view.on_mouse_release(int(lap_three_x), timeline_y, arcade.MOUSE_BUTTON_LEFT, 0)

        self.assertEqual(
            view.schedule.by_lap,
            ("Seco", "Seco") + ("Chuva intensa",) * 4 + ("Seco",) * 4,
        )
        self.assertEqual(view.start_lap_input.text, "3")
        self.assertEqual(view.end_lap_input.text, "6")

    def test_weather_view_clamps_a_drag_released_after_the_timeline(self) -> None:
        parent = ParametersView()
        view = WeatherConfigurationView(parent, WeatherSchedule.dry(10))
        lap_nine_x = TIMELINE_LEFT + TIMELINE_WIDTH * 8.5 / 10
        timeline_y = TIMELINE_BOTTOM + 1

        view.on_mouse_press(int(lap_nine_x), timeline_y, arcade.MOUSE_BUTTON_LEFT, 0)
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
