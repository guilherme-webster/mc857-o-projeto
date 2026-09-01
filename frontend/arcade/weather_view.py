"""Arcade view used to assign weather conditions to ranges of race laps."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import TYPE_CHECKING

import arcade
from arcade.gui import UIDropdown, UIFlatButton, UIInputText, UITextArea, UIView

from frontend.arcade.configuration_state import (
    WEATHER_OPTIONS,
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

if TYPE_CHECKING:
    from frontend.arcade.parameters_view import ParametersView


class WeatherConfigurationView(UIView):
    """Assign a weather condition to inclusive ranges of configured laps."""

    def __init__(self, parent: ParametersView, schedule: WeatherSchedule) -> None:
        super().__init__()
        self.parent = parent
        self.schedule = schedule
        self._status_message = (
            "Escolha um intervalo, aplique o clima e salve para voltar."
        )
        self._status_color = SECONDARY_TEXT_COLOR

        self.start_lap_input = self._add_input(72, 486, "1")
        self.end_lap_input = self._add_input(
            288, 486, str(self.schedule.total_laps)
        )
        self.weather_dropdown = self.add_widget(
            UIDropdown(
                x=504,
                y=486,
                width=280,
                height=32,
                default=WEATHER_OPTIONS[0],
                options=list(WEATHER_OPTIONS),
            )
        )
        self.apply_button = self._add_button(
            816,
            474,
            392,
            "Aplicar às voltas",
            self.apply_weather_range,
            primary=True,
        )
        self.summary_area = self.add_widget(
            UITextArea(
                x=72,
                y=224,
                width=1136,
                height=190,
                text=self.schedule.summary(),
                font_size=13,
                text_color=PRIMARY_TEXT_COLOR,
            )
        )
        self.cancel_button = self._add_button(
            776,
            112,
            216,
            "Cancelar",
            self.cancel,
        )
        self.save_button = self._add_button(
            1016,
            112,
            216,
            "Salvar e voltar",
            self.save_and_return,
            primary=True,
        )
        self._static_texts = self._create_static_texts()
        self._status_text = arcade.Text(
            self._status_message,
            48,
            70,
            self._status_color,
            14,
        )

    @property
    def status_message(self) -> str:
        """Return the current user-facing interval validation message."""

        return self._status_message

    def _add_input(self, x: int, y: int, value: str) -> UIInputText:
        """Create a consistently styled lap-number input."""

        style = deepcopy(UIInputText.DEFAULT_STYLE)
        style["normal"].border = PANEL_BORDER_COLOR
        return self.add_widget(
            UIInputText(
                x=x,
                y=y,
                width=184,
                height=32,
                text=value,
                font_size=14,
                text_color=PRIMARY_TEXT_COLOR,
                caret_color=PRIMARY_TEXT_COLOR,
                style=style,
            )
        )

    def _add_button(
        self,
        x: int,
        y: int,
        width: int,
        text: str,
        action: Callable[[], None],
        *,
        primary: bool = False,
    ) -> UIFlatButton:
        """Create one navigation or interval action button."""

        style = UIFlatButton.STYLE_RED if primary else UIFlatButton.STYLE_BLUE
        widget = UIFlatButton(
            x=x,
            y=y,
            width=width,
            height=56,
            text=text,
            style=style,
        )

        @widget.event("on_click")
        def handle_click(_event: object) -> None:
            action()

        return self.add_widget(widget)

    def apply_weather_range(self) -> None:
        """Validate the interval and update exactly the selected laps."""

        try:
            self.schedule = self.schedule.apply_text(
                start_lap=self.start_lap_input.text,
                end_lap=self.end_lap_input.text,
                weather=self.weather_dropdown.value or "",
            )
        except ConfigurationFormError as error:
            self._set_status(str(error), ERROR_COLOR)
            return
        self.summary_area.text = self.schedule.summary()
        self._set_status("Intervalo climático atualizado.", SUCCESS_COLOR)

    def save_and_return(self) -> None:
        """Persist the local schedule in the parent form and return to it."""

        self.parent.accept_weather_schedule(self.schedule)
        self.window.show_view(self.parent)

    def cancel(self) -> None:
        """Return to the parent form without changing its saved schedule."""

        self.window.show_view(self.parent)

    def _set_status(self, message: str, color: tuple[int, int, int]) -> None:
        """Update the state and cached status text together."""

        self._status_message = message
        self._status_color = color
        self._status_text.text = message
        self._status_text.color = color

    def on_show_view(self) -> None:
        """Enable GUI input and restore the desktop background color."""

        super().on_show_view()
        arcade.set_background_color(BACKGROUND_COLOR)

    def on_draw_before_ui(self) -> None:
        """Draw the weather editor card and its cached text labels."""

        arcade.draw_lbwh_rectangle_filled(48, 184, 1184, 384, PANEL_COLOR)
        arcade.draw_lbwh_rectangle_outline(
            48, 184, 1184, 384, PANEL_BORDER_COLOR, 2
        )
        arcade.draw_lbwh_rectangle_filled(48, 638, 72, 4, ACCENT_COLOR)
        for text in self._static_texts:
            text.draw()
        self._status_text.draw()

    def _create_static_texts(self) -> tuple[arcade.Text, ...]:
        """Create cached title and field labels for the weather editor."""

        return (
            arcade.Text(
                "Clima por volta",
                48,
                676,
                PRIMARY_TEXT_COLOR,
                26,
                bold=True,
            ),
            arcade.Text(
                f"Defina as condições das {self.schedule.total_laps} voltas da corrida",
                48,
                652,
                SECONDARY_TEXT_COLOR,
                13,
            ),
            arcade.Text(
                "Intervalo de voltas",
                72,
                530,
                PRIMARY_TEXT_COLOR,
                16,
                bold=True,
            ),
            arcade.Text(
                "Volta inicial",
                72,
                522,
                SECONDARY_TEXT_COLOR,
                11,
            ),
            arcade.Text(
                "Volta final",
                288,
                522,
                SECONDARY_TEXT_COLOR,
                11,
            ),
            arcade.Text(
                "Condição climática",
                504,
                522,
                SECONDARY_TEXT_COLOR,
                11,
            ),
            arcade.Text(
                "Resumo por intervalo",
                72,
                430,
                PRIMARY_TEXT_COLOR,
                16,
                bold=True,
            ),
        )
