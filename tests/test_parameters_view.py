from __future__ import annotations

import os
import threading
import time
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
        PREVIOUS_TRACK_BOUNDS,
        TOGGLE_TRACK_BOUNDS,
        TOURNAMENT_WINDOW_SIZE,
        ParametersView,
    )
    from frontend.arcade.race_configuration_view import (
        SESSION_FIELD_BOUNDS,
        SESSION_STEPPER_BOUNDS,
        SIDEBAR_ITEMS,
        WEATHER_APPLY_BOUNDS,
        WEATHER_END_BOUNDS,
        WEATHER_NEXT_BOUNDS,
        WEATHER_START_BOUNDS,
        WEATHER_TIMELINE_BOUNDS,
        RaceConfigurationView,
    )
    from frontend.arcade.race_configuration_view import (
        WEATHER_PALETTE_BOUNDS as RACE_WEATHER_PALETTE_BOUNDS,
    )
    from frontend.arcade.theme import WEATHER_ICON_PATHS
except ModuleNotFoundError as error:
    if error.name != "arcade":
        raise
    arcade = None  # type: ignore[assignment]
    ConfigurationFormData = None  # type: ignore[assignment,misc]
    ParametersView = None  # type: ignore[assignment,misc]


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

    @staticmethod
    def to_window(view: object, x: float, y: float) -> tuple[float, float]:
        """Convert design-canvas units into the window units mouse events carry.

        Fixed-layout views scale their design canvas to the window, so tests
        state targets in design units and send them as the real pointer would.
        """

        return view._canvas_fit().to_window(x, y)

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

    RUN_RACE = {
        "total_laps": 1,
        "history": [
            {
                "lap": 1,
                "cars": [
                    {
                        "driver_id": "driver:1",
                        "name": "Piloto",
                        "laps_completed": 1,
                        "total_time_ms": 90_000.0,
                        "status": "RUNNING",
                    }
                ],
            }
        ],
    }
    RUN_TRACK = {
        "circuit_id": "circuit:18",
        "lap_length_m": 1_000.0,
        "track_points": [
            {"sequence": 0, "x": 0, "y": 0, "cumulative_distance_m": 0.0},
            {"sequence": 1, "x": 1, "y": 0, "cumulative_distance_m": 500.0},
            {"sequence": 2, "x": 1, "y": 1, "cumulative_distance_m": 1_000.0},
        ],
    }

    def runner_view(self, runner) -> ParametersView:
        view = ParametersView(
            track_catalog_loader=lambda: self.CATALOG, simulation_runner=runner
        )
        view._catalog_results.put(("success", self.CATALOG))
        view.on_update(0)
        view.toggle_selected_track()
        return view

    def pump_until(self, view: ParametersView, done) -> None:
        """Entrega os resultados a tela atual (a configuracao ou o carregamento)."""

        deadline = time.monotonic() + 5
        while not done() and time.monotonic() < deadline:
            self.window.current_view.on_update(0)
            time.sleep(0.01)

    def test_runner_simulates_in_background_and_opens_the_race(self) -> None:
        from frontend.arcade.race_launcher import LaunchedRace, LaunchOutcome
        from frontend.arcade.track_view import TrackView

        received: list[SimulationPlan] = []

        def runner(plan, progress, cancelled=None):
            received.append(plan)
            progress("Simulando etapa 1/1: Interlagos…")
            return LaunchOutcome(
                (LaunchedRace(plan.races[0], self.RUN_RACE, self.RUN_TRACK),),
                "grid atual do backend (1 pilotos, semente 1)",
                (),
            )

        view = self.runner_view(runner)
        view.submit_configuration()
        self.pump_until(view, lambda: isinstance(self.window.current_view, TrackView))

        self.assertIsInstance(self.window.current_view, TrackView)
        self.assertEqual(received[0].races[0].circuit_id, "circuit:18")
        self.assertEqual(view.status_message, "Simulação concluída.")

    def test_runner_failure_shows_the_reason_and_back_returns_to_the_form(self) -> None:
        from frontend.arcade.simulation_loading_view import SimulationLoadingView
        from frontend.arcade.track_client import BackendError

        def runner(plan, progress, cancelled=None):
            raise BackendError(422, "track_id desconhecido no catalogo")

        view = self.runner_view(runner)
        view.submit_configuration()
        loading = self.window.current_view
        self.assertIsInstance(loading, SimulationLoadingView)
        self.pump_until(view, lambda: "Não foi possível" in loading._progress.message)

        self.assertIn("track_id desconhecido", loading._progress.message)
        loading.abort()
        self.assertIs(self.window.current_view, view)
        self.assertIn("track_id desconhecido", view.status_message)

    def test_abort_sets_the_cancel_flag_and_returns_to_the_form(self) -> None:
        from frontend.arcade.race_launcher import LaunchCancelled
        from frontend.arcade.simulation_loading_view import SimulationLoadingView

        flags = []
        release = threading.Event()

        def runner(plan, progress, cancelled=lambda: False):
            flags.append(cancelled)
            release.wait(5)
            raise LaunchCancelled()

        view = self.runner_view(runner)
        view.submit_configuration()
        loading = self.window.current_view
        self.assertIsInstance(loading, SimulationLoadingView)
        self.pump_until(view, lambda: flags)

        loading.abort()
        release.set()
        self.pump_until(loading, lambda: self.window.current_view is view)
        self.assertIs(self.window.current_view, view)
        self.assertEqual(view.status_message, "Simulação cancelada.")
        self.assertTrue(flags[0]())

    def test_seed_fields_copy_and_paste_through_the_clipboard(self) -> None:
        """Ctrl+V replaces a focused seed and Ctrl+C sends it back (#105)."""

        from frontend.arcade.grid_view import GridView
        from frontend.arcade.parameters_view import SEED_INPUT_BOUNDS

        accel = arcade.key.MOD_ACCEL
        view = self.ready_view()
        self.window.show_view(view)
        left, bottom, width, height = SEED_INPUT_BOUNDS
        x, y = self.to_window(view, left + width / 2, bottom + height / 2)
        view.on_mouse_press(x, y, arcade.MOUSE_BUTTON_LEFT, 0)
        with patch.object(self.window, "get_clipboard_text", return_value=" 424242\n"):
            view.on_key_press(arcade.key.V, accel)
        self.assertEqual(view.tournament_seed_input.text, "424242")
        self.assertEqual(view._tournament_seed(), 424242)
        with patch.object(self.window, "set_clipboard_text") as copy:
            view.on_key_press(arcade.key.C, accel)
        copy.assert_called_once_with("424242")

        class IdleGridClient:
            def fetch_current_grid(self):
                return None

            def fetch_history_races(self, season):
                return {"races": []}

        grid_view = GridView(client=IdleGridClient())
        self.window.show_view(grid_view)
        left, bottom, width, height = grid_view._seed_bounds()
        grid_view.on_mouse_press(
            left + width / 2, bottom + height / 2, arcade.MOUSE_BUTTON_LEFT, 0
        )
        with patch.object(self.window, "get_clipboard_text", return_value="77"):
            grid_view.on_key_press(arcade.key.V, accel)
        self.assertEqual(grid_view._grid_seed_text, "77")
        with patch.object(self.window, "set_clipboard_text") as copy:
            grid_view.on_key_press(arcade.key.C, accel)
        copy.assert_called_once_with("77")

    def test_grid_view_builds_edits_and_saves_through_the_client(self) -> None:
        from frontend.arcade.grid_view import GridView
        from tests.test_grid_editor import grid_payload

        class FakeGridClient:
            def __init__(self) -> None:
                self.calls: list[tuple] = []

            def fetch_current_grid(self):
                return None

            def fetch_history_races(self, season):
                return {
                    "races": [
                        {
                            "race_id": "race:1141",
                            "name": "São Paulo Grand Prix",
                            "season": season,
                            "round_number": 21,
                        }
                    ]
                }

            def build_grid(self, **request):
                self.calls.append(("build", request))
                return grid_payload()

            def edit_grid(self, **payload):
                self.calls.append(("edit", payload))
                return grid_payload()

        client = FakeGridClient()
        view = GridView(client=client)
        deadline = time.monotonic() + 5
        while len(view._sources) < 2 and time.monotonic() < deadline:
            view.on_update(0)
            time.sleep(0.01)
        view._source_index = 1
        view.build_grid()
        while view._draft is None and time.monotonic() < deadline:
            view.on_update(0)
            time.sleep(0.01)
        view.step_attribute("aggression", 1)
        view.move_selected(1)
        view.save_changes()
        while view._busy and time.monotonic() < deadline:
            view.on_update(0)
            time.sleep(0.01)
        view.on_draw()

        self.assertEqual(
            client.calls,
            [
                ("build", {"mode": "race", "race_id": "race:1141"}),
                (
                    "edit",
                    {
                        "overrides": [
                            {"driver_id": "driver:830", "aggression": 1.53}
                        ],
                        "order": ["driver:844", "driver:830"],
                    },
                ),
            ],
        )
        self.assertIn("salvas", view._status)

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

    def test_applies_track_default_and_preserves_edited_laps_after_navigation(self) -> None:
        catalog = {
            "count": 2,
            "tracks": [
                {
                    "circuit_id": "circuit:18",
                    "name": "Interlagos",
                    "lap_length_m": 4232.0,
                    "default_laps": 71,
                    "default_laps_source": "latest_observed_race",
                },
                {
                    "circuit_id": "circuit:6",
                    "name": "Monaco",
                    "lap_length_m": 3337.0,
                    "default_laps": 78,
                    "default_laps_source": "latest_observed_race",
                },
            ],
        }
        view = ParametersView(track_catalog_loader=lambda: catalog)
        view._catalog_results.put(("success", catalog))
        view.on_update(0)

        self.assertEqual(view.laps_input.text, "71")
        self.assertEqual(view.configuration.weather_schedule.total_laps, 71)
        view.laps_input.text = "72"
        view._change_track(1)
        self.assertEqual(view.laps_input.text, "78")
        self.assertEqual(view.configuration.weather_schedule.total_laps, 78)
        view._change_track(-1)
        self.assertEqual(view.laps_input.text, "72")
        self.assertEqual(view.configuration.weather_schedule.total_laps, 72)

    def test_opens_climate_tab_in_the_same_race_view(self) -> None:
        view = self.ready_view()
        self.window.show_view(view)
        view.laps_input.text = "71"

        view.open_weather_configuration()

        race_view = self.window.current_view
        self.assertIsInstance(race_view, RaceConfigurationView)
        race_view.on_mouse_release(
            *self.to_window(race_view, 100, 500),
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
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

    def _rects_overlap(self, a, b) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)

    def test_hidden_data_widgets_do_not_cover_custom_click_areas(self) -> None:
        """Regressao do bug real: um ``UIFlatButton``/``UIInputText`` escondido
        ainda intercepta o clique na sua area (o Arcade nao olha ``visible`` em
        ``UIInteractiveWidget.on_event``). O ``weather_button`` cobria a seta
        'anterior' e abria a configuracao. Os widgets so guardam dados, entao
        suas areas devem ficar fora de qualquer regiao clicavel da tela."""

        view = self.ready_view()
        hidden = (
            view.preset_dropdown,
            view.laps_input,
            view.weather_button,
            view.reset_button,
            view.start_button,
            view.tournament_name_input,
            view.tournament_seed_input,
        )
        custom_areas = (
            PREVIOUS_TRACK_BOUNDS,
            NEXT_TRACK_BOUNDS,
            TOGGLE_TRACK_BOUNDS,
            CONFIGURE_TRACK_BOUNDS,
            CONFIRM_SERIES_BOUNDS,
        )
        for widget in hidden:
            rect = widget.rect
            widget_bounds = (rect.left, rect.bottom, rect.width, rect.height)
            for area in custom_areas:
                self.assertFalse(
                    self._rects_overlap(widget_bounds, area),
                    msg=f"widget {type(widget).__name__} cobre area clicavel {area}",
                )

    def test_previous_arrow_selects_the_previous_track(self) -> None:
        """A seta 'anterior' apenas retrocede a selecao, sem abrir a tela de
        configuracao da pista."""

        view = self.ready_view()
        self.window.show_view(view)
        view._selected_track_index = 1  # Monaco

        left, bottom, width, height = PREVIOUS_TRACK_BOUNDS
        px, py = self.to_window(view, left + width / 2, bottom + height / 2)
        view.on_mouse_press(px, py, arcade.MOUSE_BUTTON_LEFT, 0)
        view.on_mouse_release(px, py, arcade.MOUSE_BUTTON_LEFT, 0)

        self.assertIs(self.window.current_view, view)
        self.assertEqual(view.selected_track["circuit_id"], "circuit:18")

    def test_preview_click_still_opens_the_configurator(self) -> None:
        """A correcao nao pode quebrar o clique legitimo na previa."""

        view = self.ready_view()
        self.window.show_view(view)
        left, bottom, width, height = CONFIGURE_TRACK_BOUNDS
        cx, cy = left + width // 2, bottom + height // 2
        view.on_mouse_press(cx, cy, arcade.MOUSE_BUTTON_LEFT, 0)
        view.on_mouse_release(cx, cy, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertIsInstance(self.window.current_view, RaceConfigurationView)

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
            *self.to_window(race_view, left + width // 2, bottom + height // 2),
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        self.assertEqual(race_view.session.first_lap, 2)
        self.assertEqual(race_view.session.start_mode, "Parada")
        race_view.on_mouse_release(
            *self.to_window(race_view, 100, 500),
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        palette = RACE_WEATHER_PALETTE_BOUNDS["Chuva leve"]
        race_view.on_mouse_release(
            *self.to_window(race_view, palette[0] + 10, palette[1] + 10),
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        left, bottom, width, height = WEATHER_TIMELINE_BOUNDS
        start_x = int(left + width * 1.5 / 69)
        end_x = int(left + width * 2.5 / 69)
        race_view.on_mouse_press(
            *self.to_window(race_view, start_x, bottom + height // 2),
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        race_view.on_mouse_drag(
            *self.to_window(race_view, end_x, bottom + height // 2),
            0,
            0,
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        race_view.on_mouse_release(
            *self.to_window(race_view, end_x, bottom + height // 2),
            arcade.MOUSE_BUTTON_LEFT,
            0,
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
            *self.to_window(race_view, left + width // 2, bottom + height // 2),
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        self.assertEqual(race_view.session.last_lap, 68)
        self.assertEqual(race_view.session.start_mode, "Parada")

        left, bottom, width, height = SESSION_FIELD_BOUNDS["last_lap"]
        race_view.on_mouse_release(
            *self.to_window(race_view, left + 20, bottom + height // 2),
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        self.assertEqual(race_view.session.last_lap, 68)

    def test_typing_lap_fields_applies_valid_values_and_rejects_invalid_ones(
        self,
    ) -> None:
        parent = self.ready_view()
        self.window.show_view(parent)
        parent.toggle_selected_track()
        parent.open_track_configuration()
        race_view = self.window.current_view

        def focus(field: str) -> None:
            left, bottom, _width, height = SESSION_FIELD_BOUNDS[field]
            race_view.on_mouse_press(
                *self.to_window(race_view, left + 80, bottom + height // 2),
                arcade.MOUSE_BUTTON_LEFT,
                0,
            )

        focus("first_lap")
        race_view.on_text("5")
        race_view.on_key_press(arcade.key.ENTER, 0)
        self.assertEqual(race_view.session.first_lap, 5)
        self.assertEqual(race_view.session.last_lap, 69)

        # Volta inicial acima da final e recusada; a sessao nao muda.
        focus("first_lap")
        race_view.on_text("90")
        race_view.on_key_press(arcade.key.ENTER, 0)
        self.assertEqual(race_view.session.first_lap, 5)

        # Volta final digitada reduz a corrida, e o clima acompanha.
        focus("last_lap")
        race_view.on_text("40")
        race_view.on_key_press(arcade.key.ENTER, 0)
        self.assertEqual(race_view.schedule.total_laps, 40)

        race_view.save_and_return()
        plan = parent.build_simulation_plan()
        self.assertEqual(plan.races[0].configuration.laps, 40)
        self.assertEqual(plan.races[0].session.first_lap, 5)
        self.assertEqual(plan.races[0].session.last_lap, 40)

    def test_reducing_last_lap_sets_the_race_length_sent_to_the_engine(self) -> None:
        """Regressao: a ultima volta escolhida na etapa precisa virar o numero de
        voltas da corrida (pedido ao motor e exibicao), e nao so o campo da sessao."""

        parent = self.ready_view()
        self.window.show_view(parent)
        parent.toggle_selected_track()
        parent.open_track_configuration()
        race_view = self.window.current_view

        left, bottom, width, height = SESSION_STEPPER_BOUNDS["last_lap"][0]
        for _ in range(9):  # 69 -> 60 voltas
            race_view.on_mouse_release(
                *self.to_window(race_view, left + width // 2, bottom + height // 2),
                arcade.MOUSE_BUTTON_LEFT,
                0,
            )
        self.assertEqual(race_view.schedule.total_laps, 60)

        race_view.save_and_return()
        plan = parent.build_simulation_plan()
        self.assertEqual(plan.races[0].configuration.laps, 60)
        self.assertEqual(plan.races[0].configuration.weather_schedule.total_laps, 60)
        self.assertEqual(plan.races[0].session.last_lap, 60)

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
        race_view.on_mouse_release(
            *self.to_window(race_view, 100, 500),
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        bounds = RACE_WEATHER_PALETTE_BOUNDS["Chuva intensa"]
        race_view.on_mouse_release(
            *self.to_window(race_view, bounds[0] + 10, bounds[1] + 10),
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        for field, value in ((WEATHER_START_BOUNDS, "5"), (WEATHER_END_BOUNDS, "7")):
            race_view.on_mouse_release(
                *self.to_window(race_view, field[0] + 10, field[1] + 10),
                arcade.MOUSE_BUTTON_LEFT,
                0,
            )
            race_view.on_text(value)
        bounds = WEATHER_APPLY_BOUNDS
        race_view.on_mouse_release(
            *self.to_window(race_view, bounds[0] + 10, bounds[1] + 10),
            arcade.MOUSE_BUTTON_LEFT,
            0,
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
        race_view.on_mouse_release(
            *self.to_window(race_view, 100, 500),
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
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
        race_view.on_mouse_release(
            *self.to_window(race_view, 100, 500),
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        bounds = WEATHER_NEXT_BOUNDS
        race_view.on_mouse_release(
            *self.to_window(race_view, bounds[0] + 10, bounds[1] + 10),
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        self.assertEqual(race_view._weather_summary_page, 1)
        self.assertIs(self.window.current_view, race_view)

    def test_assistance_tab_is_absent_from_both_race_and_climate(self) -> None:
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
            # 1672×900 is wider than 16:9: the 1280×720 canvas scales by
            # 900/720 and is centered between two background strips.
            self.assertEqual(view._screen_camera.viewport.width, 1600)
            self.assertEqual(view._screen_camera.viewport.left, 36)
            left, bottom, width, height = TOGGLE_TRACK_BOUNDS
            x, y = self.to_window(view, left + width / 2, bottom + height / 2)
            view.on_mouse_release(x, y, arcade.MOUSE_BUTTON_LEFT, 0)
            self.assertEqual(view.selected_track_ids, ("circuit:18",))
        finally:
            self.window.set_size(*original_size)

    def test_resizing_keeps_size_and_refits_both_configuration_screens(self) -> None:
        """A small laptop window must not be enlarged and clicks must still land."""

        original_size = self.window.get_size()
        try:
            self.window.set_size(1100, 700)
            view = self.ready_view()
            self.window.show_view(view)
            self.assertEqual(self.window.get_size(), (1100, 700))
            self.assertEqual(view._screen_camera.viewport.width, 1100)

            self.window.set_size(1000, 600)
            view.on_resize(1000, 600)
            self.assertAlmostEqual(view._screen_camera.viewport.height, 562.5)
            left, bottom, width, height = TOGGLE_TRACK_BOUNDS
            x, y = self.to_window(view, left + width / 2, bottom + height / 2)
            view.on_mouse_release(x, y, arcade.MOUSE_BUTTON_LEFT, 0)
            self.assertEqual(view.selected_track_ids, ("circuit:18",))

            view.open_track_configuration()
            race_view = self.window.current_view
            self.assertIsInstance(race_view, RaceConfigurationView)
            self.assertEqual(self.window.get_size(), (1000, 600))
            race_view.on_draw()
            race_view.on_mouse_release(
                *self.to_window(race_view, 100, 500), arcade.MOUSE_BUTTON_LEFT, 0
            )
            self.assertEqual(race_view.active_topic, "Clima")
            # The letterbox strip below the canvas must not reach any control.
            race_view.on_mouse_release(100, 1, arcade.MOUSE_BUTTON_LEFT, 0)
            self.assertIs(self.window.current_view, race_view)
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
        scroll_x, scroll_y = self.to_window(view, 1000, 420)
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

    def test_weather_icons_cover_every_supported_condition(self) -> None:
        self.assertEqual(
            set(WEATHER_ICON_PATHS),
            {"Seco", "Chuva leve", "Chuva intensa"},
        )
        self.assertTrue(all(path.is_file() for path in WEATHER_ICON_PATHS.values()))


if __name__ == "__main__":
    unittest.main()
