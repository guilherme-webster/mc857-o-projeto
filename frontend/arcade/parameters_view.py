"""Arcade implementation of the MVP's initial ``ParametersView``."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from queue import Empty, SimpleQueue
from random import Random
from threading import Thread

import arcade
from arcade.gui import UIDropdown, UIFlatButton, UIInputText, UIView

from frontend.arcade.configuration_layout import (
    Control,
    build_initial_configuration_layout,
)
from frontend.arcade.configuration_state import (
    PRESET_OPTIONS,
    ConfigurationFormData,
    ConfigurationFormError,
    PlannedRace,
    SCORING_OPTIONS,
    SessionConfiguration,
    SimulationPlan,
    TIEBREAK_OPTIONS,
    TournamentRules,
    WEATHER_MODE_OPTIONS,
    WeatherSchedule,
)
from frontend.arcade.track_client import fetch_track, fetch_tracks
from frontend.arcade.track_preview import TrackPreviewGeometry, fit_track_preview
from frontend.arcade.theme import (
    ACCENT_COLOR,
    BACKGROUND_COLOR,
    ERROR_COLOR,
    PANEL_BORDER_COLOR,
    PANEL_COLOR,
    PRIMARY_TEXT_COLOR,
    SECONDARY_TEXT_COLOR,
    SUCCESS_COLOR,
)

RULES_PANEL_BOUNDS = (28, 230, 544, 346)
TRACK_CARD_BOUNDS = (586, 76, 666, 500)
SCHEDULER_BOUNDS = (600, 91, 638, 418)
TRACK_PREVIEW_BOUNDS = (614, 115, 320, 188)
NAME_INPUT_BOUNDS = (230, 459, 322, 32)
PREVIOUS_TRACK_BOUNDS = (622, 382, 34, 31)
NEXT_TRACK_BOUNDS = (816, 382, 34, 31)
TOGGLE_TRACK_BOUNDS = (956, 286, 268, 38)
REMOVE_TRACK_BOUNDS = (956, 236, 268, 38)
AUTOMATIC_BOUNDS = (956, 186, 268, 38)
CONFIGURE_TRACK_BOUNDS = TRACK_PREVIEW_BOUNDS
CONFIRM_SERIES_BOUNDS = (1070, 13, 182, 36)
SAVE_RULES_BOUNDS = (916, 13, 138, 36)
BACK_BOUNDS = (28, 13, 134, 36)
SCORING_BOUNDS = (232, 420, 320, 34)
STAGES_DECREASE_BOUNDS = (232, 383, 28, 34)
STAGES_INCREASE_BOUNDS = (326, 383, 28, 34)
WEATHER_BOUNDS = (232, 344, 320, 34)
REPEATS_BOUNDS = (232, 306, 44, 25)
TIEBREAK_BOUNDS = (232, 268, 320, 34)
SEQUENCE_ROW_BOUNDS = tuple((956, 440 - 37 * index, 268, 37) for index in range(3))
SEQUENCE_SCROLL_BOUNDS = (1228, 366, 4, 111)
LOGO_PATH = Path(__file__).with_name("assets") / "f1-logo.png"
TOURNAMENT_WINDOW_SIZE = (1672, 900)
CONFIGURATION_WINDOW_SIZE = (1280, 720)


class _NativeText:
    """Defer a physical-resolution label until after logical shapes are drawn."""

    def __init__(self, label: arcade.Text, pending: list[arcade.Text]) -> None:
        self.label = label
        self.pending = pending

    def draw(self) -> None:
        self.pending.append(self.label)


class ParametersView(UIView):
    """Choose and configure an ordered sequence of circuits from the catalog."""

    def __init__(
        self,
        initial: ConfigurationFormData | None = None,
        on_start: Callable[[SimulationPlan], None] | None = None,
        track_catalog_loader: Callable[[], dict] = fetch_tracks,
        track_loader: Callable[[str], dict] = fetch_track,
    ) -> None:
        super().__init__()
        self.layout = build_initial_configuration_layout()
        self.initial = initial or ConfigurationFormData()
        self.configuration = self.initial
        self._on_start = on_start
        self._track_catalog_loader = track_catalog_loader
        self._track_loader = track_loader
        self._catalog_results: SimpleQueue[tuple[str, object]] = SimpleQueue()
        self._preview_results: SimpleQueue[tuple[str, str, object]] = SimpleQueue()
        self._preview: TrackPreviewGeometry | None = None
        self._preview_error: str | None = None
        self._catalog_loading = False
        self._tracks: tuple[dict, ...] = ()
        self._selected_track_index = 0
        self._selected_track_ids: list[str] = []
        self._track_configurations: dict[str, ConfigurationFormData] = {}
        self._session_configurations: dict[str, SessionConfiguration] = {}
        self.rules = TournamentRules()
        self._sequence_scroll_index = 0
        self._catalog_error: str | None = None
        self._status_message = (
            "Adicione as pistas na ordem desejada e configure cada etapa."
        )
        self._status_color = SECONDARY_TEXT_COLOR
        self._controls = {
            control.identifier: control for control in self.layout.controls
        }

        self.preset_dropdown = self._add_dropdown(
            "preset", self.initial.preset, list(PRESET_OPTIONS)
        )
        self.laps_input = self._add_input("laps", str(self.initial.laps))
        self.weather_button = self._add_button(
            "weather_schedule", self.open_weather_configuration
        )
        self.reset_button = self._add_button(
            "reset_configuration", self.reset_configuration
        )
        self.start_button = self._add_button(
            "start_simulation", self.submit_configuration, primary=True
        )
        for widget in (
            self.preset_dropdown,
            self.laps_input,
            self.weather_button,
            self.reset_button,
            self.start_button,
        ):
            widget.visible = False
        self._configure_pressed = False
        self._configure_hovered = False
        self._dragged_sequence_index: int | None = None
        self._editing_name = False
        self._screen_camera: arcade.Camera2D | None = None
        self._native_labels: list[arcade.Text] = []
        name_style = deepcopy(UIInputText.DEFAULT_STYLE)
        name_style["normal"].border = PANEL_BORDER_COLOR
        self.tournament_name_input = self.add_widget(
            UIInputText(
                x=NAME_INPUT_BOUNDS[0],
                y=NAME_INPUT_BOUNDS[1],
                width=NAME_INPUT_BOUNDS[2],
                height=NAME_INPUT_BOUNDS[3],
                text=self.rules.name,
                font_size=12,
                text_color=PRIMARY_TEXT_COLOR,
                caret_color=PRIMARY_TEXT_COLOR,
                style=name_style,
            )
        )
        self.tournament_name_input.visible = False
        self._logo_texture = arcade.load_texture(LOGO_PATH)
        self._status_text = arcade.Text(
            self._status_message,
            956,
            115,
            self._status_color,
            10,
            width=268,
            multiline=True,
        )
        weather_control = self._controls["weather_summary"]
        self._weather_summary_text = arcade.Text(
            self.configuration.weather_schedule.compact_summary(),
            weather_control.bounds.x,
            weather_control.bounds.y - 18,
            PRIMARY_TEXT_COLOR,
            12,
            width=weather_control.bounds.width,
            multiline=True,
        )

    @property
    def status_message(self) -> str:
        """Return the current user-facing validation or submission message."""

        return self._status_message

    @property
    def selected_track(self) -> dict | None:
        """Return the circuit selected from the backend catalog, if loaded."""

        return self._tracks[self._selected_track_index] if self._tracks else None

    @property
    def selected_track_ids(self) -> tuple[str, ...]:
        """IDs das pistas participantes, em ordem de inclusão."""

        return tuple(self._selected_track_ids)

    def _load_track_catalog(self) -> None:
        """Fetch the catalog in a worker so the Arcade window stays responsive."""

        if self._catalog_loading or self._tracks:
            return
        self._catalog_loading = True
        self._catalog_error = None
        self._set_status("Carregando pistas disponíveis...", SECONDARY_TEXT_COLOR)

        def load() -> None:
            try:
                result = self._track_catalog_loader()
            except Exception as error:  # noqa: BLE001 - external HTTP boundary
                self._catalog_results.put(("error", type(error).__name__))
                return
            self._catalog_results.put(("success", result))

        Thread(target=load, name="track-catalog-loader", daemon=True).start()

    def on_update(self, delta_time: float) -> None:
        """Accept completed catalog responses on the Arcade thread."""

        del delta_time
        try:
            outcome, payload = self._catalog_results.get_nowait()
        except Empty:
            self._accept_track_preview()
            return
        self._catalog_loading = False
        if outcome == "error":
            self._catalog_error = str(payload)
        else:
            try:
                entries = payload["tracks"]
                if not isinstance(entries, list) or not entries:
                    raise ValueError("catálogo vazio")
                tracks = tuple(
                    {
                        "circuit_id": str(entry["circuit_id"]),
                        "name": str(entry["name"]),
                        "lap_length_m": float(entry["lap_length_m"]),
                    }
                    for entry in entries
                )
                if any(
                    not track["circuit_id"].startswith("circuit:") or not track["name"]
                    for track in tracks
                ):
                    raise ValueError("pista sem identificação")
            except (KeyError, TypeError, ValueError) as error:
                self._catalog_error = f"resposta inválida: {error}"
            else:
                selected_id = (
                    self.selected_track["circuit_id"]
                    if self.selected_track
                    else "circuit:18"
                )
                self._tracks = tracks
                self._selected_track_index = next(
                    (
                        i
                        for i, track in enumerate(tracks)
                        if track["circuit_id"] == selected_id
                    ),
                    0,
                )
                self._catalog_error = None
                self._set_status(
                    f"{len(tracks)} pistas disponíveis. Monte sua sequência.",
                    SUCCESS_COLOR,
                )
                self._load_track_preview()
                return
        self._set_status(
            f"Não foi possível listar as pistas ({self._catalog_error}). Clique em tentar novamente.",
            ERROR_COLOR,
        )

    def _load_track_preview(self) -> None:
        """Load only the highlighted circuit; stale worker responses are ignored."""

        track = self.selected_track
        self._preview = None
        self._preview_error = None
        if track is None:
            return
        circuit_id = track["circuit_id"]

        def load() -> None:
            try:
                payload = self._track_loader(circuit_id)
            except Exception as error:  # noqa: BLE001 - HTTP boundary
                self._preview_results.put((circuit_id, "error", type(error).__name__))
            else:
                self._preview_results.put((circuit_id, "success", payload))

        Thread(target=load, name="tournament-track-preview", daemon=True).start()

    def _accept_track_preview(self) -> None:
        """Only the current selection may replace the geometry on screen."""

        while True:
            try:
                circuit_id, outcome, payload = self._preview_results.get_nowait()
            except Empty:
                return
            if (
                self.selected_track is None
                or circuit_id != self.selected_track["circuit_id"]
            ):
                continue
            if outcome == "error":
                self._preview_error = str(payload)
                continue
            try:
                left, bottom, width, height = TRACK_PREVIEW_BOUNDS
                self._preview = fit_track_preview(
                    payload, (left, bottom + 30, width, height - 30), padding=20
                )
            except ValueError as error:
                self._preview_error = str(error)

    def _change_track(self, step: int) -> None:
        """Move the selection through the complete catalog, wrapping at ends."""

        if self._tracks:
            self._selected_track_index = (self._selected_track_index + step) % len(
                self._tracks
            )
            self.configuration = self._track_configurations.get(
                self.selected_track["circuit_id"], ConfigurationFormData()
            )
            self.laps_input.text = str(self.configuration.laps)
            self._update_weather_summary()
            self._load_track_preview()

    def toggle_selected_track(self) -> None:
        """Inclua/remova a pista atual sem alterar as demais configurações."""

        track = self.selected_track
        if track is None:
            return
        circuit_id = track["circuit_id"]
        if circuit_id in self._selected_track_ids and not self.rules.allow_repeats:
            self._set_status("Esta pista já está na sequência.", SECONDARY_TEXT_COLOR)
            return
        if len(self._selected_track_ids) >= self.rules.total_stages:
            self._set_status("O total de etapas já foi atingido.", ERROR_COLOR)
            return
        self._selected_track_ids.append(circuit_id)
        self._track_configurations.setdefault(circuit_id, self.configuration)
        self._set_status(
            f"{track['name']} adicionada como etapa {len(self._selected_track_ids)}.",
            SUCCESS_COLOR,
        )
        self._sequence_scroll_index = self._max_sequence_scroll()

    def remove_selected_track(self) -> None:
        """Remove the last occurrence of the highlighted circuit."""

        track = self.selected_track
        if track is None or track["circuit_id"] not in self._selected_track_ids:
            self._set_status("Esta pista não está na sequência.", SECONDARY_TEXT_COLOR)
            return
        index = (
            len(self._selected_track_ids)
            - 1
            - self._selected_track_ids[::-1].index(track["circuit_id"])
        )
        self._selected_track_ids.pop(index)
        self._sequence_scroll_index = min(
            self._sequence_scroll_index, self._max_sequence_scroll()
        )
        self._set_status(
            f"{track['name']} removida da sequência.", SECONDARY_TEXT_COLOR
        )

    def generate_automatic_sequence(self) -> None:
        """Build a reproducible fixture-independent order from the catalog."""

        if not self._tracks:
            self._set_status("Aguarde o catálogo de pistas carregar.", ERROR_COLOR)
            return
        if not self.rules.allow_repeats and self.rules.total_stages > len(self._tracks):
            self._set_status(
                "Não há pistas únicas suficientes para as etapas.", ERROR_COLOR
            )
            return
        ids = sorted(track["circuit_id"] for track in self._tracks)
        chooser = Random(self.rules.name.strip())
        if self.rules.allow_repeats:
            self._selected_track_ids = [
                chooser.choice(ids) for _ in range(self.rules.total_stages)
            ]
        else:
            self._selected_track_ids = chooser.sample(ids, self.rules.total_stages)
        for circuit_id in self._selected_track_ids:
            self._track_configurations.setdefault(circuit_id, ConfigurationFormData())
        self._sequence_scroll_index = 0
        self._set_status("Sequência automática gerada.", SUCCESS_COLOR)

    def _update_rules(self, **changes: object) -> bool:
        """Validate general rules and preserve already selected races."""

        try:
            self.rules = TournamentRules(
                **{
                    "name": self.tournament_name_input.text,
                    "total_stages": self.rules.total_stages,
                    "scoring": self.rules.scoring,
                    "generation_mode": self.rules.generation_mode,
                    "weather_mode": self.rules.weather_mode,
                    "allow_repeats": self.rules.allow_repeats,
                    "tiebreak": self.rules.tiebreak,
                    **changes,
                }
            )
        except ConfigurationFormError as error:
            self._set_status(str(error), ERROR_COLOR)
            return False
        self._set_status("Regras do torneio atualizadas.", SUCCESS_COLOR)
        return True

    def build_simulation_plan(self) -> SimulationPlan:
        """Congele a seleção e as configurações de cada etapa em dados puros."""

        catalog = {track["circuit_id"]: track for track in self._tracks}
        if len(self._selected_track_ids) != self.rules.total_stages:
            raise ConfigurationFormError(
                f"Selecione {self.rules.total_stages} pista(s) para confirmar o torneio."
            )
        return SimulationPlan(
            tuple(
                PlannedRace(
                    circuit_id=circuit_id,
                    name=catalog[circuit_id]["name"],
                    configuration=self._track_configurations[circuit_id],
                    session=self._session_configurations.get(
                        circuit_id,
                        SessionConfiguration(
                            1, self._track_configurations[circuit_id].laps
                        ),
                    ),
                )
                for circuit_id in self._selected_track_ids
            ),
            self.rules,
        )

    def _add_input(self, identifier: str, value: str) -> UIInputText:
        """Create one text input at the position declared by the layout."""

        control = self._controls[identifier]
        style = deepcopy(UIInputText.DEFAULT_STYLE)
        style["normal"].border = PANEL_BORDER_COLOR
        widget = UIInputText(
            x=control.bounds.x,
            y=control.bounds.y,
            width=control.bounds.width,
            height=30,
            text=value,
            font_size=14,
            text_color=PRIMARY_TEXT_COLOR,
            caret_color=PRIMARY_TEXT_COLOR,
            style=style,
        )
        return self.add_widget(widget)

    def _add_dropdown(
        self, identifier: str, value: str, options: list[str]
    ) -> UIDropdown:
        """Create one dropdown at the position declared by the layout."""

        control = self._controls[identifier]
        widget = UIDropdown(
            x=control.bounds.x,
            y=control.bounds.y,
            width=control.bounds.width,
            height=32,
            default=value,
            options=options,
        )
        return self.add_widget(widget)

    def _add_button(
        self,
        identifier: str,
        action: Callable[[], None],
        *,
        primary: bool = False,
    ) -> UIFlatButton:
        """Create one button and connect it to a no-argument presentation action."""

        control = self._controls[identifier]
        style = UIFlatButton.STYLE_RED if primary else UIFlatButton.STYLE_BLUE
        widget = UIFlatButton(
            x=control.bounds.x,
            y=control.bounds.y,
            width=control.bounds.width,
            height=control.bounds.height,
            text=control.value,
            style=style,
        )

        @widget.event("on_click")
        def handle_click(_event: object) -> None:
            action()

        return self.add_widget(widget)

    def submit_configuration(self) -> None:
        """Finalize the ordered plan; execution requires an injected action."""

        if not self._update_rules():
            return
        try:
            configuration = ConfigurationFormData.from_text(
                preset=self.preset_dropdown.value or "",
                laps=self.laps_input.text,
                weather_schedule=self.configuration.weather_schedule,
            )
        except ConfigurationFormError as error:
            self._set_status(str(error), ERROR_COLOR)
            return

        self.configuration = configuration
        track = self.selected_track
        if track is not None:
            self._track_configurations[track["circuit_id"]] = configuration
        try:
            plan = self.build_simulation_plan()
        except ConfigurationFormError as error:
            self._set_status(str(error), ERROR_COLOR)
            return
        if self._on_start is not None:
            self._on_start(plan)
            message = "Sequência enviada para iniciar a simulação."
        else:
            message = "Sequência válida; execução pela interface ainda pendente."
        self._set_status(message, SUCCESS_COLOR)

    def reset_configuration(self) -> None:
        """Restore the values that were supplied when the view was created."""

        self.configuration = self.initial
        self._selected_track_ids.clear()
        self._track_configurations.clear()
        self._session_configurations.clear()
        self.rules = TournamentRules()
        self.tournament_name_input.text = self.rules.name
        self.preset_dropdown.value = self.initial.preset
        self.laps_input.text = str(self.initial.laps)
        self._update_weather_summary()
        self._set_status("Configuração restaurada.", SECONDARY_TEXT_COLOR)

    def open_track_configuration(self, stage_index: int | None = None) -> None:
        """Open the configurator for the highlighted circuit."""

        track = self.selected_track
        if track is None:
            self._set_status("Aguarde o catálogo de pistas carregar.", ERROR_COLOR)
            return
        try:
            self.configuration = ConfigurationFormData.from_text(
                preset=self.preset_dropdown.value or "",
                laps=self.laps_input.text,
                weather_schedule=self.configuration.weather_schedule,
            )
        except ConfigurationFormError as error:
            self._set_status(str(error), ERROR_COLOR)
            return

        self._track_configurations[track["circuit_id"]] = self.configuration

        from frontend.arcade.race_configuration_view import RaceConfigurationView

        if stage_index is None:
            stage_index = (
                self._selected_track_ids.index(track["circuit_id"]) + 1
                if track["circuit_id"] in self._selected_track_ids
                else 1
            )
        self.window.show_view(
            RaceConfigurationView(
                parent=self,
                schedule=self.configuration.weather_schedule,
                circuit_id=track["circuit_id"],
                track_name=track["name"],
                stage_index=stage_index,
                session=self._session_configurations.get(track["circuit_id"]),
            )
        )

    def open_tournament_stage(self, stage_index: int) -> None:
        """Open a particular selected stage without changing its saved settings."""

        circuit_id = self._selected_track_ids[stage_index - 1]
        self._selected_track_index = next(
            index
            for index, track in enumerate(self._tracks)
            if track["circuit_id"] == circuit_id
        )
        self.configuration = self._track_configurations[circuit_id]
        self.laps_input.text = str(self.configuration.laps)
        self.open_track_configuration(stage_index)

    def accept_session_configuration(
        self, circuit_id: str, session: SessionConfiguration
    ) -> None:
        """Preserve session settings when returning from the per-race screen."""

        self._session_configurations[circuit_id] = session

    def open_weather_configuration(self) -> None:
        """Keep the former navigation entry compatible during the UI migration."""

        self.open_track_configuration()

    def accept_weather_schedule(self, schedule: WeatherSchedule) -> None:
        """Receive a weather schedule saved by the secondary Arcade view."""

        self.configuration = ConfigurationFormData(
            preset=self.preset_dropdown.value or "",
            laps=schedule.total_laps,
            weather_schedule=schedule,
        )
        if self.selected_track is not None:
            self._track_configurations[self.selected_track["circuit_id"]] = (
                self.configuration
            )
        self.laps_input.text = str(schedule.total_laps)
        self._update_weather_summary()
        self._set_status("Clima por volta atualizado.", SUCCESS_COLOR)

    def _update_weather_summary(self) -> None:
        """Refresh the cached main-card summary after schedule changes."""

        self._weather_summary_text.text = (
            self.configuration.weather_schedule.compact_summary()
        )

    def _set_status(
        self,
        message: str,
        color: tuple[int, int, int],
    ) -> None:
        """Update both the state and cached Arcade text for the status line."""

        self._status_message = message
        self._status_color = color
        self._status_text.text = message
        self._status_text.color = color

    def on_show_view(self) -> None:
        """Enable Arcade GUI input and apply the screen background color."""

        super().on_show_view()
        if self.window.visible and self.window.get_size() != TOURNAMENT_WINDOW_SIZE:
            self.window.set_size(*TOURNAMENT_WINDOW_SIZE)
        self._screen_camera = arcade.Camera2D(
            projection=arcade.LBWH(-640, -360, *CONFIGURATION_WINDOW_SIZE),
            viewport=arcade.LBWH(0, 0, *self.window.get_size()),
            position=(640, 360),
            window=self.window,
        )
        arcade.set_background_color(BACKGROUND_COLOR)
        self._load_track_catalog()

    def on_draw(self) -> None:
        """Scale shapes while rasterizing text at the window's native resolution."""

        self.clear()
        self._native_labels.clear()
        if self._screen_camera is None:
            self.on_draw_before_ui()
        else:
            with self._screen_camera.activate():
                self.on_draw_before_ui()
        with self.window.default_camera.activate():
            for label in self._native_labels:
                label.draw()

    def _native_text(
        self,
        text: str,
        x: float,
        y: float,
        color: tuple[int, ...] = PRIMARY_TEXT_COLOR,
        font_size: float = 12,
        **kwargs: object,
    ) -> _NativeText:
        """Place a label in logical layout units but render its glyphs natively."""

        scale_x = self.window.width / CONFIGURATION_WINDOW_SIZE[0]
        scale_y = self.window.height / CONFIGURATION_WINDOW_SIZE[1]
        width = kwargs.get("width")
        if width is not None:
            kwargs["width"] = int(width * scale_x)
        label = arcade.Text(
            text,
            x * scale_x,
            y * scale_y,
            color,
            font_size * scale_y,
            **kwargs,
        )
        return _NativeText(label, self._native_labels)

    def _logical_pointer(self, x: int, y: int) -> tuple[int, int]:
        """Map physical pointer pixels back to the 1280×720 design canvas."""

        width, height = self.window.get_size()
        return int(x * 1280 / width), int(y * 720 / height)

    def on_draw_before_ui(self) -> None:
        """Draw the track-selection screen before hidden controller widgets."""

        arcade.draw_lbwh_rectangle_filled(0, 0, 1280, 720, BACKGROUND_COLOR)
        arcade.draw_lbwh_rectangle_filled(0, 674, 1280, 46, (12, 17, 24))
        arcade.draw_line(0, 674, 1280, 674, PANEL_BORDER_COLOR, 1)
        arcade.draw_texture_rect(
            self._logo_texture,
            arcade.LBWH(16, 688, 40, 19),
        )
        self._draw_rounded_panel(
            *RULES_PANEL_BOUNDS, 8, (19, 27, 37), PANEL_BORDER_COLOR
        )
        self._draw_rounded_panel(
            *TRACK_CARD_BOUNDS, 8, (19, 27, 37), PANEL_BORDER_COLOR
        )
        self._draw_rounded_panel(*SCHEDULER_BOUNDS, 8, (20, 28, 38), PANEL_BORDER_COLOR)
        self._draw_rule_controls()
        self._draw_selection_button()
        self._draw_remove_button()
        self._draw_automatic_button()
        self._draw_confirmation_button()
        self._draw_track_navigation()
        self._draw_preview()
        self._draw_track_texts()
        self._native_text(
            self._status_message,
            956,
            115,
            self._status_color,
            10,
            width=268,
            multiline=True,
        ).draw()

    def on_mouse_motion(self, x: int, y: int, dx: int, dy: int) -> None:
        """Provide hover feedback for the selected track action."""

        x, y = self._logical_pointer(x, y)
        self._configure_hovered = self.selected_track is not None and self._contains(
            CONFIGURE_TRACK_BOUNDS, x, y
        )

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        """Begin the custom configure-button interaction."""

        x, y = self._logical_pointer(x, y)
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._editing_name = self._contains(NAME_INPUT_BOUNDS, x, y)
        if button == arcade.MOUSE_BUTTON_LEFT and self.selected_track is not None:
            self._configure_pressed = self._contains(CONFIGURE_TRACK_BOUNDS, x, y)
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._dragged_sequence_index = self._sequence_index_at(x, y)

    def on_mouse_release(self, x: int, y: int, button: int, modifiers: int) -> None:
        """Open the track configurator when the button click completes."""

        x, y = self._logical_pointer(x, y)
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        target_index = self._sequence_index_at(x, y)
        if target_index is not None:
            source_index = self._dragged_sequence_index
            if source_index is not None and source_index != target_index:
                circuit_id = self._selected_track_ids.pop(source_index)
                self._selected_track_ids.insert(target_index, circuit_id)
                self._set_status("Ordem das etapas atualizada.", SUCCESS_COLOR)
            else:
                circuit_id = self._selected_track_ids[target_index]
                self._selected_track_index = next(
                    index
                    for index, track in enumerate(self._tracks)
                    if track["circuit_id"] == circuit_id
                )
                self.configuration = self._track_configurations[circuit_id]
                self.laps_input.text = str(self.configuration.laps)
                self._load_track_preview()
            self._dragged_sequence_index = None
            return
        self._dragged_sequence_index = None
        if self._contains(SCORING_BOUNDS, x, y):
            self._cycle_rule("scoring", SCORING_OPTIONS)
            return
        if self._contains(WEATHER_BOUNDS, x, y):
            self._cycle_rule("weather_mode", WEATHER_MODE_OPTIONS)
            return
        if self._contains(TIEBREAK_BOUNDS, x, y):
            self._cycle_rule("tiebreak", TIEBREAK_OPTIONS)
            return
        if self._contains(STAGES_DECREASE_BOUNDS, x, y):
            self._update_rules(total_stages=max(1, self.rules.total_stages - 1))
            return
        if self._contains(STAGES_INCREASE_BOUNDS, x, y):
            self._update_rules(total_stages=min(24, self.rules.total_stages + 1))
            return
        if self._contains(REPEATS_BOUNDS, x, y):
            self._update_rules(allow_repeats=not self.rules.allow_repeats)
            return
        if self._contains(PREVIOUS_TRACK_BOUNDS, x, y):
            self._change_track(-1)
            return
        if self._contains(NEXT_TRACK_BOUNDS, x, y):
            self._change_track(1)
            return
        if self._contains(TOGGLE_TRACK_BOUNDS, x, y):
            self.toggle_selected_track()
            return
        if self._contains(REMOVE_TRACK_BOUNDS, x, y):
            self.remove_selected_track()
            return
        if self._contains(AUTOMATIC_BOUNDS, x, y):
            self._update_rules(generation_mode="Automática")
            self.generate_automatic_sequence()
            return
        if self._contains(CONFIRM_SERIES_BOUNDS, x, y):
            self.submit_configuration()
            return
        if self._contains(SAVE_RULES_BOUNDS, x, y):
            self._update_rules()
            return
        if self._contains(BACK_BOUNDS, x, y):
            self._set_status(
                "Esta é a primeira tela; não há etapa anterior.", SECONDARY_TEXT_COLOR
            )
            return
        if self._catalog_error and self._contains(CONFIGURE_TRACK_BOUNDS, x, y):
            self._load_track_catalog()
            return
        should_open = self._configure_pressed and self._contains(
            CONFIGURE_TRACK_BOUNDS, x, y
        )
        self._configure_pressed = False
        if should_open:
            self.open_track_configuration()

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int) -> None:
        """Scroll the sequence one stage at a time within its visible area."""

        x, y = self._logical_pointer(x, y)
        if 956 <= x <= 1232 and 346 <= y <= 477:
            self._sequence_scroll_index = min(
                self._max_sequence_scroll(),
                max(0, self._sequence_scroll_index - int(scroll_y)),
            )

    def _max_sequence_scroll(self) -> int:
        """Keep the last stage visible without exposing empty row slots."""

        return max(0, len(self._selected_track_ids) - len(SEQUENCE_ROW_BOUNDS))

    def on_text(self, text: str) -> None:
        """Edit the tournament name with the same data field used by validation."""

        if self._editing_name and text.isprintable():
            self.tournament_name_input.text += text

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if not self._editing_name:
            return
        if symbol == arcade.key.BACKSPACE:
            self.tournament_name_input.text = self.tournament_name_input.text[:-1]
        elif symbol in (arcade.key.ENTER, arcade.key.ESCAPE):
            self._editing_name = False

    def _sequence_index_at(self, x: int, y: int) -> int | None:
        for slot, bounds in enumerate(SEQUENCE_ROW_BOUNDS):
            index = self._sequence_scroll_index + slot
            if index < len(self._selected_track_ids) and self._contains(bounds, x, y):
                return index
        return None

    def _cycle_rule(self, name: str, options: tuple[str, ...]) -> None:
        current = getattr(self.rules, name)
        self._update_rules(
            **{name: options[(options.index(current) + 1) % len(options)]}
        )

    def _draw_selection_button(self) -> None:
        """Show whether the highlighted circuit participates in the sequence."""

        left, bottom, width, height = TOGGLE_TRACK_BOUNDS
        self._draw_rounded_panel(
            left, bottom, width, height, 8, (203, 27, 43), (236, 50, 65)
        )
        self._native_text(
            "Adicionar à sequência",
            left + width / 2,
            bottom + height / 2,
            PRIMARY_TEXT_COLOR,
            11,
            anchor_x="center",
            anchor_y="center",
        ).draw()

    def _draw_remove_button(self) -> None:
        left, bottom, width, height = REMOVE_TRACK_BOUNDS
        self._draw_rounded_panel(
            left, bottom, width, height, 8, (26, 36, 48), PANEL_BORDER_COLOR
        )
        self._native_text(
            "Remover da sequência",
            left + width / 2,
            bottom + height / 2,
            PRIMARY_TEXT_COLOR,
            11,
            anchor_x="center",
            anchor_y="center",
        ).draw()

    def _draw_automatic_button(self) -> None:
        left, bottom, width, height = AUTOMATIC_BOUNDS
        self._draw_rounded_panel(
            left, bottom, width, height, 8, (26, 36, 48), PANEL_BORDER_COLOR
        )
        self._native_text(
            "*  Gerar sequência automática",
            left + width / 2,
            bottom + height / 2,
            PRIMARY_TEXT_COLOR,
            11,
            anchor_x="center",
            anchor_y="center",
        ).draw()

    def _draw_confirmation_button(self) -> None:
        """Offer a visible action to finalize the chosen order."""

        for bounds, label, fill, border in (
            (BACK_BOUNDS, "‹   Voltar", (26, 36, 48), PANEL_BORDER_COLOR),
            (SAVE_RULES_BOUNDS, "Salvar regras", (26, 36, 48), PANEL_BORDER_COLOR),
            (CONFIRM_SERIES_BOUNDS, "Confirmar torneio", (203, 27, 43), (236, 50, 65)),
        ):
            left, bottom, width, height = bounds
            self._draw_rounded_panel(left, bottom, width, height, 8, fill, border)
            self._native_text(
                label,
                left + width / 2,
                bottom + height / 2,
                PRIMARY_TEXT_COLOR,
                11,
                anchor_x="center",
                anchor_y="center",
            ).draw()

    def _draw_track_navigation(self) -> None:
        """Draw previous/next controls for all backend catalog entries."""

        if not self._tracks:
            return
        for bounds, symbol in ((PREVIOUS_TRACK_BOUNDS, "‹"), (NEXT_TRACK_BOUNDS, "›")):
            left, bottom, width, height = bounds
            self._draw_rounded_panel(
                left, bottom, width, height, 6, PANEL_COLOR, PANEL_BORDER_COLOR
            )
            self._native_text(
                symbol,
                left + width / 2,
                bottom + height / 2,
                PRIMARY_TEXT_COLOR,
                24,
                anchor_x="center",
                anchor_y="center",
            ).draw()
        self._native_text(
            f"{self._selected_track_index + 1} / {len(self._tracks)}",
            737,
            397,
            SECONDARY_TEXT_COLOR,
            11,
            anchor_x="center",
            anchor_y="center",
        ).draw()

    def _draw_rule_controls(self) -> None:
        """Draw compact controls matching the tournament rules panel."""

        self._native_text("Regras do torneio", 48, 545, PRIMARY_TEXT_COLOR, 22).draw()
        self._native_text(
            "Defina as configurações gerais da competição.",
            48,
            525,
            SECONDARY_TEXT_COLOR,
            12,
        ).draw()
        left, bottom, width, height = NAME_INPUT_BOUNDS
        self._draw_rounded_panel(
            left,
            bottom,
            width,
            height,
            7,
            (20, 30, 40),
            (111, 127, 148) if self._editing_name else PANEL_BORDER_COLOR,
        )
        self._native_text(
            self.tournament_name_input.text,
            left + 10,
            bottom + height / 2,
            PRIMARY_TEXT_COLOR,
            12,
            anchor_y="center",
            width=width - 20,
        ).draw()
        labels = (
            ("Nome do torneio", 467),
            ("Sistema de pontuação", 429),
            ("Total de etapas", 392),
            ("Clima", 354),
            ("Permitir repetição de pista", 315),
            ("Critério de desempate", 277),
        )
        for label, y in labels:
            self._native_text(
                label,
                48,
                y,
                SECONDARY_TEXT_COLOR,
                10 if label == "Permitir repetição de pista" else 11,
            ).draw()
        for bounds, value in (
            (SCORING_BOUNDS, self.rules.scoring),
            (WEATHER_BOUNDS, self.rules.weather_mode),
            (TIEBREAK_BOUNDS, self.rules.tiebreak),
        ):
            left, bottom, width, height = bounds
            self._draw_rounded_panel(
                left, bottom, width, height, 7, (21, 31, 42), PANEL_BORDER_COLOR
            )
            self._native_text(
                value,
                left + 12,
                bottom + height / 2,
                PRIMARY_TEXT_COLOR,
                11,
                anchor_y="center",
            ).draw()
            self._native_text(
                "v",
                left + width - 18,
                bottom + height / 2,
                PRIMARY_TEXT_COLOR,
                15,
                anchor_x="center",
                anchor_y="center",
            ).draw()
        for bounds, label in (
            (STAGES_DECREASE_BOUNDS, "−"),
            (STAGES_INCREASE_BOUNDS, "+"),
        ):
            left, bottom, width, height = bounds
            self._draw_rounded_panel(
                left, bottom, width, height, 7, (21, 31, 42), PANEL_BORDER_COLOR
            )
            self._native_text(
                label,
                left + width / 2,
                bottom + height / 2,
                PRIMARY_TEXT_COLOR,
                15,
                anchor_x="center",
                anchor_y="center",
            ).draw()
        self._native_text(
            str(self.rules.total_stages),
            293,
            400,
            PRIMARY_TEXT_COLOR,
            12,
            anchor_x="center",
            anchor_y="center",
        ).draw()
        left, bottom, width, height = REPEATS_BOUNDS
        self._draw_rounded_panel(
            left,
            bottom,
            width,
            height,
            12,
            (191, 43, 54) if self.rules.allow_repeats else (57, 67, 81),
            PANEL_BORDER_COLOR,
        )
        arcade.draw_circle_filled(
            left + (width - 12 if self.rules.allow_repeats else 12),
            bottom + height / 2,
            9,
            PRIMARY_TEXT_COLOR,
        )
        self._native_text(
            "Ativado" if self.rules.allow_repeats else "Desativado",
            290,
            315,
            SECONDARY_TEXT_COLOR,
            11,
        ).draw()

    def _draw_preview(self) -> None:
        """Render a schematic of the selected track from backend geometry."""

        left, bottom, width, height = TRACK_PREVIEW_BOUNDS
        self._draw_rounded_panel(
            left, bottom, width, height, 7, (9, 20, 17), PANEL_BORDER_COLOR
        )
        if self._preview is None:
            message = self._preview_error or "Carregando geometria..."
            self._native_text(
                message,
                left + width / 2,
                bottom + height / 2,
                ERROR_COLOR if self._preview_error else SECONDARY_TEXT_COLOR,
                10,
                anchor_x="center",
                anchor_y="center",
                width=width - 30,
                align="center",
                multiline=True,
            ).draw()
            return
        track = self._preview.track_points
        pit = self._preview.pit_lane_points
        arcade.draw_line_strip(track, (29, 33, 39), 12)
        arcade.draw_line_strip(track, (223, 226, 231), 9)
        arcade.draw_line_strip(track, (96, 102, 110), 6)
        arcade.draw_line_strip(pit, (249, 184, 66), 3)
        arcade.draw_circle_filled(*self._preview.service_point, 5, (255, 176, 0))
        arcade.draw_circle_filled(*pit[0], 4, (70, 211, 142))
        arcade.draw_circle_filled(*pit[-1], 4, (75, 142, 214))
        legend_y = bottom + 14
        for x, color, label in (
            (left + 13, (148, 152, 160), "Pista"),
            (left + 72, (249, 184, 66), "Pit lane"),
            (left + 146, (255, 176, 0), "Serviço"),
            (left + 219, (70, 211, 142), "Entrada"),
        ):
            arcade.draw_circle_filled(x, legend_y + 3, 3, color)
            self._native_text(label, x + 7, legend_y, SECONDARY_TEXT_COLOR, 8).draw()

    def _draw_track_texts(self) -> None:
        """Draw the catalog, selected order and top-level tournament headings."""

        track = self.selected_track
        name = (
            track["name"]
            if track
            else (
                "Carregando pistas..."
                if self._catalog_loading
                else "Pistas indisponíveis"
            )
        )
        length = (
            f"{track['lap_length_m'] / 1000:.3f} km".replace(".", ",") if track else ""
        )
        for label, x, y, color, size in (
            ("SIMULADOR DE CORRIDA", 72, 692, SECONDARY_TEXT_COLOR, 11),
            ("Configuração do torneio", 40, 620, PRIMARY_TEXT_COLOR, 31),
            (
                "Defina as regras gerais e monte o scheduler de pistas.",
                40,
                596,
                SECONDARY_TEXT_COLOR,
                14,
            ),
            ("Scheduler de pistas", 608, 545, PRIMARY_TEXT_COLOR, 22),
            (
                "Monte a sequência de pistas do torneio.",
                608,
                525,
                SECONDARY_TEXT_COLOR,
                12,
            ),
            ("CATÁLOGO DE PISTAS", 622, 481, ACCENT_COLOR, 10),
            (name, 622, 448, PRIMARY_TEXT_COLOR, 18),
            (
                f"Extensão da pista: {length}" if track else "",
                622,
                428,
                SECONDARY_TEXT_COLOR,
                11,
            ),
            (
                f"{self.configuration.laps} voltas configuradas",
                622,
                373,
                SECONDARY_TEXT_COLOR,
                10,
            ),
            ("Clique na prévia para configurar", 622, 354, SECONDARY_TEXT_COLOR, 9),
            (
                f"SEQUÊNCIA • {len(self._selected_track_ids)} pista(s)",
                956,
                481,
                ACCENT_COLOR,
                10,
            ),
        ):
            self._native_text(
                label, x, y, color, size, width=310 if x == 622 else None
            ).draw()
        names = {item["circuit_id"]: item["name"] for item in self._tracks}
        for slot, bounds in enumerate(SEQUENCE_ROW_BOUNDS):
            index = self._sequence_scroll_index + slot
            left, bottom, width, height = bounds
            selected = (
                index < len(self._selected_track_ids)
                and self.selected_track is not None
                and self._selected_track_ids[index] == self.selected_track["circuit_id"]
            )
            self._draw_rounded_panel(
                left,
                bottom,
                width,
                height,
                4,
                (65, 38, 46) if selected else (24, 34, 46),
                PANEL_BORDER_COLOR,
            )
            if index >= len(self._selected_track_ids):
                continue
            circuit_id = self._selected_track_ids[index]
            self._native_text(
                f"{index + 1}.  {names[circuit_id]}",
                left + 10,
                bottom + 12,
                PRIMARY_TEXT_COLOR,
                10,
                width=235,
            ).draw()
            self._native_text(
                "||", left + width - 20, bottom + 12, SECONDARY_TEXT_COLOR, 10
            ).draw()
        if len(self._selected_track_ids) > len(SEQUENCE_ROW_BOUNDS):
            visible_start = self._sequence_scroll_index + 1
            visible_end = min(
                len(self._selected_track_ids),
                self._sequence_scroll_index + len(SEQUENCE_ROW_BOUNDS),
            )
            self._native_text(
                f"Role para ver etapas {visible_start}–{visible_end} de {len(self._selected_track_ids)}",
                956,
                345,
                SECONDARY_TEXT_COLOR,
                9,
            ).draw()
            self._draw_sequence_scrollbar()
        self._draw_rounded_panel(1175, 681, 78, 29, 6, (26, 36, 48), PANEL_BORDER_COLOR)
        self._native_text(
            "Ajuda",
            1214,
            696,
            SECONDARY_TEXT_COLOR,
            10,
            anchor_x="center",
            anchor_y="center",
        ).draw()

    def _draw_sequence_scrollbar(self) -> None:
        """Show the visible fraction of the sequence beside its fixed row slots."""

        left, bottom, width, height = SEQUENCE_SCROLL_BOUNDS
        total = len(self._selected_track_ids)
        visible = len(SEQUENCE_ROW_BOUNDS)
        thumb_height = max(18, height * visible / total)
        available_travel = height - thumb_height
        thumb_bottom = bottom + available_travel * (
            1 - self._sequence_scroll_index / self._max_sequence_scroll()
        )
        arcade.draw_lbwh_rectangle_filled(
            left, bottom, width, height, PANEL_BORDER_COLOR
        )
        arcade.draw_lbwh_rectangle_filled(
            left, thumb_bottom, width, thumb_height, ACCENT_COLOR
        )

    @staticmethod
    def _contains(bounds: tuple[int, int, int, int], x: int, y: int) -> bool:
        """Return whether a pointer lies inside one custom control."""

        left, bottom, width, height = bounds
        return left <= x <= left + width and bottom <= y <= bottom + height

    @staticmethod
    def _draw_rounded_rectangle(
        left: float,
        bottom: float,
        width: float,
        height: float,
        radius: float,
        color: tuple[int, ...],
    ) -> None:
        """Fill a rounded rectangle with Arcade's basic primitives."""

        radius = min(radius, width / 2, height / 2)
        arcade.draw_lbwh_rectangle_filled(
            left + radius, bottom, width - 2 * radius, height, color
        )
        arcade.draw_lbwh_rectangle_filled(
            left, bottom + radius, width, height - 2 * radius, color
        )
        for center_x in (left + radius, left + width - radius):
            for center_y in (bottom + radius, bottom + height - radius):
                arcade.draw_circle_filled(center_x, center_y, radius, color)

    @classmethod
    def _draw_rounded_panel(
        cls,
        left: float,
        bottom: float,
        width: float,
        height: float,
        radius: float,
        fill_color: tuple[int, ...],
        border_color: tuple[int, ...],
    ) -> None:
        """Draw a one-pixel rounded border around a filled panel."""

        cls._draw_rounded_rectangle(left, bottom, width, height, radius, border_color)
        cls._draw_rounded_rectangle(
            left + 1,
            bottom + 1,
            width - 2,
            height - 2,
            max(radius - 1, 0),
            fill_color,
        )

    def _draw_panels(self) -> None:
        """Draw the three content cards declared by the shared layout."""

        for panel in self.layout.panels:
            bounds = panel.bounds
            arcade.draw_lbwh_rectangle_filled(
                bounds.x, bounds.y, bounds.width, bounds.height, PANEL_COLOR
            )
            arcade.draw_lbwh_rectangle_outline(
                bounds.x,
                bounds.y,
                bounds.width,
                bounds.height,
                PANEL_BORDER_COLOR,
                2,
            )

    def _create_static_texts(self) -> tuple[arcade.Text, ...]:
        """Create cached text objects for the static screen contents."""

        texts = [
            arcade.Text(
                self.layout.title,
                48,
                676,
                PRIMARY_TEXT_COLOR,
                26,
                bold=True,
            ),
            arcade.Text(
                self.layout.subtitle,
                48,
                652,
                SECONDARY_TEXT_COLOR,
                13,
            ),
        ]
        texts.extend(
            arcade.Text(
                panel.title,
                panel.bounds.x + 24,
                panel.bounds.top - 38,
                PRIMARY_TEXT_COLOR,
                16,
                bold=True,
            )
            for panel in self.layout.panels
        )
        for control in self.layout.controls:
            if control.kind == "button":
                continue
            if control.kind == "dynamic_read_only":
                texts.append(self._read_only_label(control))
                continue
            if control.kind == "read_only":
                texts.extend(self._read_only_texts(control))
            else:
                texts.append(
                    arcade.Text(
                        control.label,
                        control.bounds.x,
                        control.bounds.y + 36,
                        SECONDARY_TEXT_COLOR,
                        11,
                    )
                )
        return tuple(texts)

    @staticmethod
    def _read_only_label(control: Control) -> arcade.Text:
        """Create the label used by a dynamic immutable presentation value."""

        return arcade.Text(
            control.label,
            control.bounds.x,
            control.bounds.y + 27,
            SECONDARY_TEXT_COLOR,
            11,
        )

    @staticmethod
    def _read_only_texts(control: Control) -> tuple[arcade.Text, arcade.Text]:
        """Create cached label and value text for one immutable ETL field."""

        return (
            arcade.Text(
                control.label,
                control.bounds.x,
                control.bounds.y + 27,
                SECONDARY_TEXT_COLOR,
                11,
            ),
            arcade.Text(
                control.value,
                control.bounds.x,
                control.bounds.y + 4,
                PRIMARY_TEXT_COLOR,
                12,
                width=control.bounds.width,
            ),
        )


def create_parameters_window() -> arcade.Window:
    """Create the single desktop window and show its initial ParametersView."""

    layout = build_initial_configuration_layout()
    window = arcade.Window(
        *TOURNAMENT_WINDOW_SIZE,
        layout.title,
        resizable=False,
    )
    window.show_view(ParametersView())
    return window
