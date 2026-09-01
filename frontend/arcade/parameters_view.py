"""Arcade implementation of the MVP's initial ``ParametersView``."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

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


class ParametersView(UIView):
    """Render and collect the initial race configuration with Arcade widgets.

    The view owns only presentation state. A future HTTP client or application
    controller can be injected through ``on_start``; no simulation rule or
    frame-dependent clock is implemented here.
    """

    def __init__(
        self,
        initial: ConfigurationFormData | None = None,
        on_start: Callable[[ConfigurationFormData], None] | None = None,
    ) -> None:
        super().__init__()
        self.layout = build_initial_configuration_layout()
        self.initial = initial or ConfigurationFormData()
        self.configuration = self.initial
        self._on_start = on_start
        self._status_message = "Ajuste os parâmetros editáveis para continuar."
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
        self._static_texts = self._create_static_texts()
        self._status_text = arcade.Text(
            self._status_message,
            48,
            72,
            self._status_color,
            14,
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

    def open_weather_configuration(self) -> None:
        """Validate the lap count and navigate to weather-by-lap editing."""

        try:
            self.configuration = ConfigurationFormData.from_text(
                preset=self.preset_dropdown.value or "",
                laps=self.laps_input.text,
                weather_schedule=self.configuration.weather_schedule,
            )
        except ConfigurationFormError as error:
            self._set_status(str(error), ERROR_COLOR)
            return

        from frontend.arcade.weather_view import WeatherConfigurationView

        self.window.show_view(
            WeatherConfigurationView(
                parent=self,
                schedule=self.configuration.weather_schedule,
            )
        )

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

    def on_draw_before_ui(self) -> None:
        """Draw the static panels and labels behind the interactive widgets."""

        self._draw_panels()
        arcade.draw_lbwh_rectangle_filled(48, 638, 72, 4, ACCENT_COLOR)
        for text in self._static_texts:
            text.draw()
        self._weather_summary_text.draw()
        self._status_text.draw()

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
