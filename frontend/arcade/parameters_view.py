"""Arcade implementation of the MVP's initial ``ParametersView``."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from queue import Empty, SimpleQueue
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
    WeatherSchedule,
)
from frontend.arcade.track_client import fetch_tracks
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


TRACK_CARD_BOUNDS = (104, 230, 1072, 300)
CONFIGURE_TRACK_BOUNDS = (880, 270, 240, 52)
PREVIOUS_TRACK_BOUNDS = (136, 352, 42, 38)
NEXT_TRACK_BOUNDS = (398, 352, 42, 38)
LOGO_PATH = Path(__file__).with_name("assets") / "f1-logo.png"


class ParametersView(UIView):
    """Select the circuit that will be configured for the simulation.

    The catalog includes geometry for multiple circuits. Race execution still
    uses the single scenario supported by the current simulation contract.
    """

    def __init__(
        self,
        initial: ConfigurationFormData | None = None,
        on_start: Callable[[ConfigurationFormData], None] | None = None,
        track_catalog_loader: Callable[[], dict] = fetch_tracks,
    ) -> None:
        super().__init__()
        self.layout = build_initial_configuration_layout()
        self.initial = initial or ConfigurationFormData()
        self.configuration = self.initial
        self._on_start = on_start
        self._track_catalog_loader = track_catalog_loader
        self._catalog_results: SimpleQueue[tuple[str, object]] = SimpleQueue()
        self._catalog_loading = False
        self._tracks: tuple[dict, ...] = ()
        self._selected_track_index = 0
        self._catalog_error: str | None = None
        self._status_message = "Selecione uma pista para abrir suas configurações."
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
        self._logo_texture = arcade.load_texture(LOGO_PATH)
        self._status_text = arcade.Text(
            self._status_message,
            104,
            166,
            self._status_color,
            12,
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
                if any(not track["circuit_id"].startswith("circuit:") or not track["name"] for track in tracks):
                    raise ValueError("pista sem identificação")
            except (KeyError, TypeError, ValueError) as error:
                self._catalog_error = f"resposta inválida: {error}"
            else:
                selected_id = self.selected_track["circuit_id"] if self.selected_track else "circuit:18"
                self._tracks = tracks
                self._selected_track_index = next(
                    (i for i, track in enumerate(tracks) if track["circuit_id"] == selected_id),
                    0,
                )
                self._catalog_error = None
                self._set_status(f"{len(tracks)} pistas disponíveis para visualização.", SUCCESS_COLOR)
                return
        self._set_status(
            f"Não foi possível listar as pistas ({self._catalog_error}). Clique em tentar novamente.",
            ERROR_COLOR,
        )

    def _change_track(self, step: int) -> None:
        """Move the selection through the complete catalog, wrapping at ends."""

        if self._tracks:
            self._selected_track_index = (self._selected_track_index + step) % len(self._tracks)

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
        """Validate widget values and send a configuration to the injected action."""

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
        if self._on_start is not None:
            self._on_start(configuration)
            message = "Configuração enviada para iniciar a corrida."
        else:
            message = (
                "Configuração válida; integração com a simulação ainda pendente."
            )
        self._set_status(message, SUCCESS_COLOR)

    def reset_configuration(self) -> None:
        """Restore the values that were supplied when the view was created."""

        self.configuration = self.initial
        self.preset_dropdown.value = self.initial.preset
        self.laps_input.text = str(self.initial.laps)
        self._update_weather_summary()
        self._set_status("Configuração restaurada.", SECONDARY_TEXT_COLOR)

    def open_track_configuration(self) -> None:
        """Validate the selected scenario and open its track configurator."""

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

        from frontend.arcade.weather_view import TrackConfigurationView

        self.window.show_view(
            TrackConfigurationView(
                parent=self,
                schedule=self.configuration.weather_schedule,
                circuit_id=track["circuit_id"],
                track_name=track["name"],
            )
        )

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
        arcade.set_background_color(BACKGROUND_COLOR)
        self._load_track_catalog()

    def on_draw_before_ui(self) -> None:
        """Draw the track-selection screen before hidden controller widgets."""

        arcade.draw_lbwh_rectangle_filled(0, 0, 1280, 720, BACKGROUND_COLOR)
        arcade.draw_lbwh_rectangle_filled(0, 668, 1280, 52, (7, 12, 19))
        arcade.draw_line(0, 668, 1280, 668, PANEL_BORDER_COLOR, 1)
        arcade.draw_texture_rect(
            self._logo_texture,
            arcade.LBWH(16, 683, 46, 22),
        )
        self._draw_rounded_panel(
            *TRACK_CARD_BOUNDS, 10, PANEL_COLOR, PANEL_BORDER_COLOR
        )
        self._draw_track_button()
        self._draw_track_navigation()
        self._draw_track_texts()
        self._status_text.draw()

    def on_mouse_motion(self, x: int, y: int, dx: int, dy: int) -> None:
        """Provide hover feedback for the selected track action."""

        self._configure_hovered = self.selected_track is not None and self._contains(CONFIGURE_TRACK_BOUNDS, x, y)

    def on_mouse_press(
        self, x: int, y: int, button: int, modifiers: int
    ) -> None:
        """Begin the custom configure-button interaction."""

        if button == arcade.MOUSE_BUTTON_LEFT and self.selected_track is not None:
            self._configure_pressed = self._contains(
                CONFIGURE_TRACK_BOUNDS, x, y
            )

    def on_mouse_release(
        self, x: int, y: int, button: int, modifiers: int
    ) -> None:
        """Open the track configurator when the button click completes."""

        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        if self._contains(PREVIOUS_TRACK_BOUNDS, x, y):
            self._change_track(-1)
            return
        if self._contains(NEXT_TRACK_BOUNDS, x, y):
            self._change_track(1)
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

    def _draw_track_button(self) -> None:
        """Draw the rounded action that enters the selected track."""

        left, bottom, width, height = CONFIGURE_TRACK_BOUNDS
        fill = (32, 43, 56) if self.selected_track is None else (
            (161, 22, 31)
            if self._configure_pressed
            else (232, 43, 53)
            if self._configure_hovered
            else (204, 31, 42)
        )
        self._draw_rounded_panel(
            left, bottom, width, height, 8, fill, (238, 55, 64)
        )
        arcade.Text(
            "Tentar novamente" if self._catalog_error else "Configurar pista",
            left + width / 2,
            bottom + height / 2,
            PRIMARY_TEXT_COLOR,
            12,
            anchor_x="center",
            anchor_y="center",
        ).draw()

    def _draw_track_navigation(self) -> None:
        """Draw previous/next controls for all backend catalog entries."""

        if not self._tracks:
            return
        for bounds, symbol in ((PREVIOUS_TRACK_BOUNDS, "‹"), (NEXT_TRACK_BOUNDS, "›")):
            left, bottom, width, height = bounds
            self._draw_rounded_panel(left, bottom, width, height, 6, PANEL_COLOR, PANEL_BORDER_COLOR)
            arcade.Text(symbol, left + width / 2, bottom + height / 2,
                        PRIMARY_TEXT_COLOR, 24, anchor_x="center", anchor_y="center").draw()
        arcade.Text(f"{self._selected_track_index + 1} / {len(self._tracks)}",
                    287, 371, SECONDARY_TEXT_COLOR, 12, anchor_x="center", anchor_y="center").draw()

    def _draw_track_texts(self) -> None:
        """Draw the selected backend circuit and its available geometry metadata."""

        summary = self.configuration.weather_schedule.compact_summary(2)
        track = self.selected_track
        name = track["name"] if track else "Carregando pistas..." if self._catalog_loading else "Pistas indisponíveis"
        length = f"{track['lap_length_m'] / 1000:.3f} km".replace(".", ",") if track else ""
        texts = (
            arcade.Text("SIMULADOR DE CORRIDA", 76, 690, SECONDARY_TEXT_COLOR, 10, bold=True),
            arcade.Text("Selecione a pista", 104, 602, PRIMARY_TEXT_COLOR, 30, bold=True),
            arcade.Text("Escolha uma pista para visualizar e configurar.", 104, 570, SECONDARY_TEXT_COLOR, 13),
            arcade.Text("CATÁLOGO DE PISTAS", 136, 486, ACCENT_COLOR, 9, bold=True),
            arcade.Text(name, 136, 438, PRIMARY_TEXT_COLOR, 19, bold=True, width=440),
            arcade.Text(f"Geometria disponível • {length}" if track else "", 136, 408, SECONDARY_TEXT_COLOR, 11),
            arcade.Text(f"{self.configuration.laps} voltas configuradas", 136, 323, SECONDARY_TEXT_COLOR, 11),
            arcade.Text("Geometria FastF1 2025 • ID Trotman v128", 136, 283, SECONDARY_TEXT_COLOR, 10),
            arcade.Text("Configuração atual", 620, 442, SECONDARY_TEXT_COLOR, 10),
            arcade.Text(summary, 620, 410, PRIMARY_TEXT_COLOR, 11, width=220, multiline=True),
        )
        for text in texts:
            text.draw()

    @staticmethod
    def _contains(
        bounds: tuple[int, int, int, int], x: int, y: int
    ) -> bool:
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

        cls._draw_rounded_rectangle(
            left, bottom, width, height, radius, border_color
        )
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
        layout.screen.width,
        layout.screen.height,
        layout.title,
        resizable=False,
    )
    window.show_view(ParametersView())
    return window
