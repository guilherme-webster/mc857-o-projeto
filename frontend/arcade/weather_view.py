"""Arcade view for editing the weather condition of each race lap."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import arcade
from arcade.gui import UIDropdown, UIInputText, UIView

from frontend.arcade.configuration_state import (
    WEATHER_OPTIONS,
    ConfigurationFormError,
    WeatherRange,
    WeatherSchedule,
)
from frontend.arcade.theme import (
    ACCENT_COLOR,
    BACKGROUND_COLOR,
    ERROR_COLOR,
    PRIMARY_TEXT_COLOR,
    SECONDARY_TEXT_COLOR,
    SUCCESS_COLOR,
)

if TYPE_CHECKING:
    from frontend.arcade.parameters_view import ParametersView


# Coordinates are shared by drawing and mouse hit-testing. Arcade uses a
# bottom-left origin, so these values describe the 1280x720 desktop canvas.
SIDEBAR_WIDTH = 174
TIMELINE_LEFT = 214
TIMELINE_BOTTOM = 350
TIMELINE_WIDTH = 1006
TIMELINE_HEIGHT = 24
TIMELINE_RIGHT = TIMELINE_LEFT + TIMELINE_WIDTH
SUMMARY_PAGE_SIZE = 8
SUMMARY_PREVIOUS_BOUNDS = (1100, 238, 28, 24)
SUMMARY_NEXT_BOUNDS = (1192, 238, 28, 24)
MUTED_BORDER_COLOR = (35, 47, 61)
SURFACE_COLOR = (12, 19, 29)
CARD_COLOR = (15, 24, 36)
CARD_COLOR_LIGHT = (18, 28, 41)
WEATHER_TIMELINE_COLORS = {
    "Seco": (244, 183, 64),
    "Chuva leve": (75, 142, 214),
    "Chuva intensa": (40, 82, 174),
}
WEATHER_PALETTE_BOUNDS = {
    "Seco": (522, 492, 92, 42),
    "Chuva leve": (624, 492, 124, 42),
    "Chuva intensa": (758, 492, 136, 42),
}
LOGO_PATH = Path(__file__).with_name("assets") / "f1-logo.png"
WEATHER_ICON_PATHS = {
    "Seco": Path(__file__).with_name("assets") / "icons" / "weather-dry.png",
    "Chuva leve": Path(__file__).with_name("assets")
    / "icons"
    / "weather-light-rain.png",
    "Chuva intensa": Path(__file__).with_name("assets")
    / "icons"
    / "weather-heavy-rain.png",
}


@dataclass(frozen=True, slots=True)
class DashboardButton:
    """Geometry and action for a button drawn by this Arcade view."""

    left: int
    bottom: int
    width: int
    height: int
    text: str
    action: Callable[[], None]
    primary: bool = False

    def contains(self, x: int, y: int) -> bool:
        """Return whether the pointer is inside the clickable rectangle."""

        return (
            self.left <= x <= self.left + self.width
            and self.bottom <= y <= self.bottom + self.height
        )


class WeatherConfigurationView(UIView):
    """Edit a lap weather schedule while keeping rules outside the UI.

    Clicking a palette item selects a condition. A click-drag over the bar
    previews and then applies an inclusive lap range; the numeric fields remain
    available for precise keyboard editing and the existing save flow.
    """

    def __init__(self, parent: ParametersView, schedule: WeatherSchedule) -> None:
        super().__init__()
        self.parent = parent
        self.schedule = schedule
        self.selected_weather = WEATHER_OPTIONS[0]
        self._drag_start_lap: int | None = None
        self._drag_current_lap: int | None = None
        self._hovered_button: DashboardButton | None = None
        self._pressed_button: DashboardButton | None = None
        self._summary_page = 0
        self._status_message = "Escolha uma condição e arraste sobre a timeline."
        self._status_color = SECONDARY_TEXT_COLOR

        self.start_lap_input = self._add_input(214, 492, "1")
        self.end_lap_input = self._add_input(
            358, 492, str(self.schedule.total_laps)
        )
        # This hidden bridge preserves the precise interval API while the
        # visible control is the faster color palette from the new design.
        self.weather_dropdown = UIDropdown(
            x=-400,
            y=-400,
            width=1,
            height=1,
            default=self.selected_weather,
            options=list(WEATHER_OPTIONS),
        )
        self.apply_button = DashboardButton(
            1040, 486, 194, 46, "Aplicar às voltas", self.apply_weather_range, True
        )
        self.cancel_button = DashboardButton(
            790, 28, 138, 40, "Cancelar", self.cancel, False
        )
        self.save_button = DashboardButton(
            1066, 28, 168, 40, "Salvar e voltar", self.save_and_return, True
        )
        self._action_buttons = (
            self.apply_button,
            self.cancel_button,
            self.save_button,
        )
        self._logo = arcade.Sprite(
            LOGO_PATH, scale=(0.095, 0.095), center_x=31, center_y=26
        )
        self._weather_icons = {
            weather: arcade.load_texture(path)
            for weather, path in WEATHER_ICON_PATHS.items()
        }
        self._static_texts = self._create_static_texts()
        self._status_text = arcade.Text(
            self._status_message, 222, 76, self._status_color, 10
        )

    @property
    def status_message(self) -> str:
        """Return the current validation or interaction message."""

        return self._status_message

    def _add_input(self, x: int, y: int, value: str) -> UIInputText:
        """Create one compact input styled for the dark dashboard."""

        style = deepcopy(UIInputText.DEFAULT_STYLE)
        # The widget renders only text/caret. A rounded field is drawn behind it
        # because Arcade's built-in input style supports only square borders.
        for state in ("normal", "hover", "press"):
            style[state].bg = None
            style[state].border = None
            style[state].border_width = 0
        widget = UIInputText(
            x=x,
            y=y,
            width=124,
            height=34,
            text=value,
            font_size=12,
            text_color=PRIMARY_TEXT_COLOR,
            caret_color=PRIMARY_TEXT_COLOR,
            style=style,
        )
        self._center_input_text(widget)
        return self.add_widget(widget)

    @staticmethod
    def _center_input_text(widget: UIInputText) -> None:
        """Center a numeric value in Pyglet's document-backed input layout."""

        if widget.text:
            widget.doc.set_paragraph_style(
                0, len(widget.text), {"align": "center"}
            )
        widget.layout.content_valign = "center"

    def apply_weather_range(self) -> None:
        """Validate the fields and apply their inclusive weather range."""

        weather = self.weather_dropdown.value or self.selected_weather
        try:
            self.schedule = self.schedule.apply_text(
                start_lap=self.start_lap_input.text,
                end_lap=self.end_lap_input.text,
                weather=weather,
            )
        except ConfigurationFormError as error:
            self._set_status(str(error), ERROR_COLOR)
            return
        self.selected_weather = weather
        self._set_status("Intervalo climático atualizado.", SUCCESS_COLOR)

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        """Select a condition or begin painting a timeline interval."""

        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        action_button = self._button_at_position(x, y)
        if action_button is not None:
            self._pressed_button = action_button
            return
        if self._handle_summary_navigation(x, y):
            return
        weather = self._weather_at_palette_position(x, y)
        if weather is not None:
            self.selected_weather = weather
            self.weather_dropdown.value = weather
            self._set_status(
                f"{weather} selecionado; arraste sobre a timeline.",
                WEATHER_TIMELINE_COLORS[weather],
            )
            return
        if not self._is_timeline_position(x, y):
            return
        lap = self._lap_at_timeline_x(x)
        self._drag_start_lap = lap
        self._drag_current_lap = lap
        self._update_interval_inputs(lap, lap)
        self._set_status(
            f"Selecionando {self.selected_weather} a partir da volta {lap}...",
            WEATHER_TIMELINE_COLORS[self.selected_weather],
        )

    def on_mouse_drag(
        self, x: int, y: int, dx: int, dy: int, buttons: int, modifiers: int
    ) -> None:
        """Extend the live preview to the lap below the mouse."""

        if self._drag_start_lap is None:
            return
        self._drag_current_lap = self._lap_at_timeline_x(x)
        self._sync_inputs_with_drag()

    def on_mouse_motion(
        self, x: int, y: int, dx: int, dy: int
    ) -> None:
        """Track the action button under the pointer for hover feedback."""

        self._hovered_button = self._button_at_position(x, y)

    def on_mouse_release(
        self, x: int, y: int, button: int, modifiers: int
    ) -> None:
        """Commit the inclusive preview when the left button is released."""

        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        if self._pressed_button is not None:
            pressed_button = self._pressed_button
            self._pressed_button = None
            if pressed_button.contains(x, y):
                pressed_button.action()
            return
        if self._drag_start_lap is None:
            return
        self._drag_current_lap = self._lap_at_timeline_x(x)
        start_lap, end_lap = sorted(
            (self._drag_start_lap, self._drag_current_lap)
        )
        self.schedule = self.schedule.apply(
            start_lap, end_lap, self.selected_weather
        )
        self._update_interval_inputs(start_lap, end_lap)
        self._drag_start_lap = None
        self._drag_current_lap = None
        self._set_status(
            f"{self.selected_weather} aplicado às voltas {start_lap}–{end_lap}.",
            SUCCESS_COLOR,
        )

    def _sync_inputs_with_drag(self) -> None:
        """Mirror a possibly reversed drag in ordered numeric fields."""

        if self._drag_start_lap is None or self._drag_current_lap is None:
            return
        self._update_interval_inputs(
            *sorted((self._drag_start_lap, self._drag_current_lap))
        )

    def _update_interval_inputs(self, start_lap: int, end_lap: int) -> None:
        """Keep precise interval fields synchronized with mouse painting."""

        self.start_lap_input.text = str(start_lap)
        self.end_lap_input.text = str(end_lap)
        self._center_input_text(self.start_lap_input)
        self._center_input_text(self.end_lap_input)

    @staticmethod
    def _weather_at_palette_position(x: int, y: int) -> str | None:
        """Return the condition represented by the palette area under the mouse."""

        for weather, (left, bottom, width, height) in WEATHER_PALETTE_BOUNDS.items():
            if left <= x <= left + width and bottom <= y <= bottom + height:
                return weather
        return None

    def _button_at_position(self, x: int, y: int) -> DashboardButton | None:
        """Return the custom action button under the pointer, when present."""

        return next(
            (button for button in self._action_buttons if button.contains(x, y)),
            None,
        )

    def _handle_summary_navigation(self, x: int, y: int) -> bool:
        """Change summary pages when one of the compact controls is clicked."""

        if self._summary_page_count() <= 1:
            return False
        if self._position_in_bounds(x, y, SUMMARY_PREVIOUS_BOUNDS):
            self._summary_page = max(self._summary_page - 1, 0)
            return True
        if self._position_in_bounds(x, y, SUMMARY_NEXT_BOUNDS):
            self._summary_page = min(
                self._summary_page + 1, self._summary_page_count() - 1
            )
            return True
        return False

    @staticmethod
    def _position_in_bounds(
        x: int, y: int, bounds: tuple[int, int, int, int]
    ) -> bool:
        """Return whether a point lies in a left-bottom-width-height tuple."""

        left, bottom, width, height = bounds
        return left <= x <= left + width and bottom <= y <= bottom + height

    @staticmethod
    def _is_timeline_position(x: int, y: int) -> bool:
        """Return whether a point lies inside the interactive timeline bar."""

        return (
            TIMELINE_LEFT <= x <= TIMELINE_RIGHT
            and TIMELINE_BOTTOM <= y <= TIMELINE_BOTTOM + TIMELINE_HEIGHT
        )

    def _lap_at_timeline_x(self, x: int) -> int:
        """Map a horizontal pixel to a one-based lap, clamping overflow."""

        clamped_x = min(max(x, TIMELINE_LEFT), TIMELINE_RIGHT)
        fraction = (clamped_x - TIMELINE_LEFT) / TIMELINE_WIDTH
        lap = int(fraction * self.schedule.total_laps) + 1
        return min(lap, self.schedule.total_laps)

    def save_and_return(self) -> None:
        """Persist the local schedule in the parent form and return to it."""

        self.parent.accept_weather_schedule(self.schedule)
        self.window.show_view(self.parent)

    def cancel(self) -> None:
        """Return without changing the schedule saved in the parent form."""

        self.window.show_view(self.parent)

    def _set_status(self, message: str, color: tuple[int, int, int]) -> None:
        """Update the state and cached Arcade text together."""

        self._status_message = message
        self._status_color = color
        self._status_text.text = message
        self._status_text.color = color

    def on_show_view(self) -> None:
        """Enable GUI input and apply the dashboard background color."""

        super().on_show_view()
        arcade.set_background_color(BACKGROUND_COLOR)

    def on_draw_before_ui(self) -> None:
        """Draw the dashboard shell, controls, timeline and summary cards."""

        self._draw_shell()
        self._draw_action_buttons()
        self._draw_weather_palette()
        self._draw_timeline()
        self._draw_weather_legend()
        self._draw_summary_cards()
        for text in self._static_texts:
            text.draw()
        self._status_text.draw()
        arcade.draw_texture_rect(
            self._logo.texture,
            arcade.LBWH(8, 683, 46, 22),
        )

    def _draw_shell(self) -> None:
        """Draw header, navigation rail and the three content cards."""

        arcade.draw_lbwh_rectangle_filled(0, 0, 1280, 720, BACKGROUND_COLOR)
        arcade.draw_lbwh_rectangle_filled(0, 668, 1280, 52, (7, 12, 19))
        arcade.draw_line(0, 668, 1280, 668, MUTED_BORDER_COLOR, 1)
        arcade.draw_lbwh_rectangle_filled(0, 0, SIDEBAR_WIDTH, 668, (8, 15, 24))
        arcade.draw_line(SIDEBAR_WIDTH, 0, SIDEBAR_WIDTH, 668, MUTED_BORDER_COLOR, 1)
        self._draw_rounded_panel(
            174, 72, 1082, 574, 8, SURFACE_COLOR, MUTED_BORDER_COLOR
        )
        for bounds in ((198, 464, 1038, 112), (198, 282, 1038, 170), (198, 110, 1038, 160)):
            self._draw_rounded_panel(
                *bounds, 6, CARD_COLOR, MUTED_BORDER_COLOR
            )
        self._draw_rounded_panel(
            214, 492, 124, 34, 5, CARD_COLOR_LIGHT, MUTED_BORDER_COLOR
        )
        self._draw_rounded_panel(
            358, 492, 124, 34, 5, CARD_COLOR_LIGHT, MUTED_BORDER_COLOR
        )
        arcade.draw_lbwh_rectangle_filled(0, 476, SIDEBAR_WIDTH, 42, (55, 18, 25))
        arcade.draw_lbwh_rectangle_filled(0, 476, 3, 42, ACCENT_COLOR)
        self._draw_rounded_panel(
            1086, 680, 72, 28, 6, CARD_COLOR_LIGHT, MUTED_BORDER_COLOR
        )

    def _draw_action_buttons(self) -> None:
        """Draw custom rounded buttons with hover and pressed feedback."""

        for button in self._action_buttons:
            hovered = button is self._hovered_button
            pressed = button is self._pressed_button
            if button.primary:
                fill = (161, 22, 31) if pressed else (232, 43, 53) if hovered else (204, 31, 42)
                border = (128, 15, 23) if pressed else (255, 103, 109) if hovered else (238, 55, 64)
            else:
                fill = (9, 16, 25) if pressed else (27, 40, 56) if hovered else CARD_COLOR_LIGHT
                border = ACCENT_COLOR if pressed else (88, 106, 128) if hovered else (49, 65, 83)
            self._draw_rounded_panel(
                button.left,
                button.bottom,
                button.width,
                button.height,
                7,
                fill,
                border,
            )
            arcade.Text(
                button.text,
                button.left + button.width / 2,
                button.bottom + button.height / 2,
                PRIMARY_TEXT_COLOR,
                11,
                anchor_x="center",
                anchor_y="center",
            ).draw()

    def _draw_weather_palette(self) -> None:
        """Draw condition buttons; each full button area is clickable."""

        for weather, (left, bottom, width, height) in WEATHER_PALETTE_BOUNDS.items():
            selected = weather == self.selected_weather
            background = (31, 29, 38) if selected else CARD_COLOR_LIGHT
            self._draw_rounded_panel(
                left,
                bottom,
                width,
                height,
                6,
                background,
                ACCENT_COLOR if selected else MUTED_BORDER_COLOR,
                2 if selected else 1,
            )
            arcade.draw_line(
                left + 1,
                bottom + height - 1,
                left + width - 1,
                bottom + height - 1,
                (69, 82, 99) if not selected else (244, 73, 81),
                1,
            )
            arcade.draw_texture_rect(
                self._weather_icons[weather],
                arcade.LBWH(left + 9, bottom + 9, 24, 24),
            )
            arcade.Text(
                weather, left + 39, bottom + 14,
                PRIMARY_TEXT_COLOR if selected else SECONDARY_TEXT_COLOR, 10,
            ).draw()

    def _draw_weather_legend(self) -> None:
        """Draw the same weather icon language below the timeline."""

        positions = ((214, "Seco"), (296, "Chuva leve"), (410, "Chuva intensa"))
        for left, weather in positions:
            arcade.draw_texture_rect(
                self._weather_icons[weather],
                arcade.LBWH(left, 306, 14, 14),
            )
            arcade.Text(
                weather,
                left + 20,
                307,
                WEATHER_TIMELINE_COLORS[weather],
                9,
            ).draw()

    def _draw_timeline(self) -> None:
        """Draw segments proportional to their inclusive lap ranges."""

        self._draw_rounded_panel(
            TIMELINE_LEFT,
            TIMELINE_BOTTOM,
            TIMELINE_WIDTH,
            TIMELINE_HEIGHT,
            TIMELINE_HEIGHT / 2,
            (7, 12, 19),
            (87, 102, 121),
            2,
        )
        for weather_range in self.schedule.ranges():
            self._draw_timeline_range(
                weather_range,
                WEATHER_TIMELINE_COLORS[weather_range.weather],
            )
        self._draw_drag_preview()
        arcade.draw_line(
            TIMELINE_LEFT + TIMELINE_HEIGHT / 2,
            TIMELINE_BOTTOM + TIMELINE_HEIGHT - 3,
            TIMELINE_RIGHT - TIMELINE_HEIGHT / 2,
            TIMELINE_BOTTOM + TIMELINE_HEIGHT - 3,
            (255, 255, 255, 90),
            1,
        )
        for weather_range in self.schedule.ranges()[1:]:
            x = TIMELINE_LEFT + 2 + (TIMELINE_WIDTH - 4) * (
                (weather_range.start_lap - 1) / self.schedule.total_laps
            )
            arcade.draw_lbwh_rectangle_filled(x - 5, 344, 10, 36, (9, 15, 23))
            arcade.draw_lbwh_rectangle_outline(x - 5, 344, 10, 36, (91, 106, 124), 1)
            arcade.draw_lbwh_rectangle_filled(x - 3, 346, 6, 32, (235, 238, 242))
            arcade.draw_line(x, 351, x, 373, (143, 153, 165), 1)
            arcade.Text(
                str(weather_range.start_lap - 1),
                x,
                383,
                SECONDARY_TEXT_COLOR,
                9,
                anchor_x="center",
            ).draw()

    def _draw_timeline_range(
        self, weather_range: WeatherRange, color: tuple[int, ...]
    ) -> None:
        """Draw a segment clipped geometrically to the rounded inner capsule."""

        inner_left = TIMELINE_LEFT + 2
        inner_bottom = TIMELINE_BOTTOM + 2
        inner_width = TIMELINE_WIDTH - 4
        inner_height = TIMELINE_HEIGHT - 4
        start_fraction = (weather_range.start_lap - 1) / self.schedule.total_laps
        end_fraction = weather_range.end_lap / self.schedule.total_laps
        left = inner_left + inner_width * start_fraction
        right = inner_left + inner_width * end_fraction
        body_left = left
        body_right = right

        if weather_range.start_lap == 1:
            radius = min(inner_height / 2, (right - left) / 2)
            arcade.draw_circle_filled(
                left + radius,
                inner_bottom + inner_height / 2,
                radius,
                color,
            )
            body_left += radius
        if weather_range.end_lap == self.schedule.total_laps:
            radius = min(inner_height / 2, (right - left) / 2)
            arcade.draw_circle_filled(
                right - radius,
                inner_bottom + inner_height / 2,
                radius,
                color,
            )
            body_right -= radius
        if body_right > body_left:
            arcade.draw_lbwh_rectangle_filled(
                body_left,
                inner_bottom,
                body_right - body_left,
                inner_height,
                color,
            )

    def _range_geometry(self, weather_range: WeatherRange) -> tuple[float, float]:
        """Return horizontal geometry for one inclusive schedule range."""

        start = (weather_range.start_lap - 1) / self.schedule.total_laps
        end = weather_range.end_lap / self.schedule.total_laps
        return TIMELINE_LEFT + TIMELINE_WIDTH * start, TIMELINE_WIDTH * (end - start)

    def _draw_drag_preview(self) -> None:
        """Overlay the selected range before it is committed on release."""

        if self._drag_start_lap is None or self._drag_current_lap is None:
            return
        start_lap, end_lap = sorted((self._drag_start_lap, self._drag_current_lap))
        self._draw_timeline_range(
            WeatherRange(start_lap, end_lap, self.selected_weather),
            (*WEATHER_TIMELINE_COLORS[self.selected_weather], 210),
        )

    def _draw_summary_cards(self) -> None:
        """Draw every interval through a compact, paginated card grid."""

        all_ranges = self.schedule.ranges()
        page_count = self._summary_page_count()
        self._summary_page = min(self._summary_page, page_count - 1)
        start = self._summary_page * SUMMARY_PAGE_SIZE
        ranges = all_ranges[start : start + SUMMARY_PAGE_SIZE]
        gap = 12
        column_count = min(len(ranges), 4)
        width = (1006 - gap * (column_count - 1)) / column_count
        for index, weather_range in enumerate(ranges):
            column = index % 4
            row = index // 4
            compact = len(ranges) > 4
            bottom = 176 - row * 60 if compact else 136
            height = 54 if compact else 92
            self._draw_summary_card(
                214 + column * (width + gap),
                bottom,
                width,
                height,
                weather_range,
                compact=compact,
            )
        if page_count > 1:
            self._draw_summary_navigation(page_count)

    def _summary_page_count(self) -> int:
        """Return the number of pages needed without hiding any interval."""

        range_count = len(self.schedule.ranges())
        return max(1, (range_count + SUMMARY_PAGE_SIZE - 1) // SUMMARY_PAGE_SIZE)

    def _draw_summary_navigation(self, page_count: int) -> None:
        """Draw previous/next controls and the current summary page number."""

        for bounds, label, enabled in (
            (SUMMARY_PREVIOUS_BOUNDS, "<", self._summary_page > 0),
            (SUMMARY_NEXT_BOUNDS, ">", self._summary_page < page_count - 1),
        ):
            left, bottom, width, height = bounds
            self._draw_rounded_panel(
                left,
                bottom,
                width,
                height,
                5,
                CARD_COLOR_LIGHT,
                MUTED_BORDER_COLOR if enabled else (27, 36, 48),
            )
            arcade.Text(
                label,
                left + width / 2,
                bottom + height / 2,
                PRIMARY_TEXT_COLOR if enabled else (76, 87, 102),
                10,
                anchor_x="center",
                anchor_y="center",
            ).draw()
        arcade.Text(
            f"{self._summary_page + 1}/{page_count}",
            1160,
            246,
            SECONDARY_TEXT_COLOR,
            9,
            anchor_x="center",
        ).draw()

    def _draw_summary_card(
        self,
        x: float,
        bottom: float,
        width: float,
        height: float,
        weather_range: WeatherRange,
        *,
        compact: bool,
    ) -> None:
        """Draw one interval, its condition, and its percentage of the race."""

        color = WEATHER_TIMELINE_COLORS[weather_range.weather]
        laps = weather_range.end_lap - weather_range.start_lap + 1
        percentage = 100 * laps / self.schedule.total_laps
        self._draw_rounded_panel(
            x, bottom, width, height, 6, CARD_COLOR_LIGHT, MUTED_BORDER_COLOR
        )
        arcade.draw_lbwh_rectangle_filled(
            x + 6, bottom + height - 2, width - 12, 2, color
        )
        title_y = bottom + height - 26 if compact else bottom + 66
        weather_y = bottom + 13 if compact else bottom + 40
        details_y = bottom + 5 if compact else bottom + 15
        arcade.Text(f"Voltas {weather_range.start_lap} – {weather_range.end_lap}", x + 10, title_y, color, 9 if compact else 10, bold=True).draw()
        arcade.draw_texture_rect(
            self._weather_icons[weather_range.weather],
            arcade.LBWH(x + 10, weather_y - 2, 16 if compact else 18, 16 if compact else 18),
        )
        arcade.Text(weather_range.weather, x + 32, weather_y + 4, PRIMARY_TEXT_COLOR, 9 if compact else 10).draw()
        details_x = x + width - 10 if compact else x + 10
        arcade.Text(
            f"{laps} voltas ({percentage:.1f}%)".replace(".", ","),
            details_x,
            details_y,
            SECONDARY_TEXT_COLOR,
            8 if compact else 9,
            anchor_x="right" if compact else "left",
        ).draw()

    def _create_static_texts(self) -> tuple[arcade.Text, ...]:
        """Create cached labels for the shell and the current screen."""

        labels = [
            arcade.Text("SIMULADOR DE CORRIDA", 70, 690, SECONDARY_TEXT_COLOR, 10, bold=True),
            arcade.Text("Ajuda", 1101, 689, SECONDARY_TEXT_COLOR, 10),
            arcade.Text("CONFIGURAÇÕES DA CORRIDA", 8, 630, SECONDARY_TEXT_COLOR, 8),
            arcade.Text("Sessão", 38, 590, SECONDARY_TEXT_COLOR, 11),
            arcade.Text("Pista", 38, 548, SECONDARY_TEXT_COLOR, 11),
            arcade.Text("Clima", 38, 492, PRIMARY_TEXT_COLOR, 11),
            arcade.Text("Assistências", 38, 450, SECONDARY_TEXT_COLOR, 11),
            arcade.Text("Regras", 38, 408, SECONDARY_TEXT_COLOR, 11),
            arcade.Text("Carros", 38, 366, SECONDARY_TEXT_COLOR, 11),
            arcade.Text("Clima por volta", 198, 614, PRIMARY_TEXT_COLOR, 26, bold=True),
            arcade.Text(f"Defina as condições climáticas ao longo das {self.schedule.total_laps} voltas da corrida.", 198, 590, SECONDARY_TEXT_COLOR, 11),
            arcade.Text("Intervalo de voltas", 214, 548, PRIMARY_TEXT_COLOR, 12, bold=True),
            arcade.Text("Volta inicial", 276, 530, SECONDARY_TEXT_COLOR, 9, anchor_x="center"),
            arcade.Text("Volta final", 420, 530, SECONDARY_TEXT_COLOR, 9, anchor_x="center"),
            arcade.Text("Condição climática", 522, 548, PRIMARY_TEXT_COLOR, 10, bold=True),
            arcade.Text("Timeline da pista", 214, 424, PRIMARY_TEXT_COLOR, 12, bold=True),
            arcade.Text("Clique e arraste para pintar um período da corrida.", 214, 407, SECONDARY_TEXT_COLOR, 9),
            arcade.Text("1", TIMELINE_LEFT, 383, SECONDARY_TEXT_COLOR, 9),
            arcade.Text(str(self.schedule.total_laps), TIMELINE_RIGHT, 383, SECONDARY_TEXT_COLOR, 9, anchor_x="right"),
            arcade.Text("Arraste sobre a barra para ajustar os intervalos", TIMELINE_LEFT + TIMELINE_WIDTH / 2, 329, SECONDARY_TEXT_COLOR, 8, anchor_x="center"),
            arcade.Text("Resumo por intervalo", 214, 246, PRIMARY_TEXT_COLOR, 12, bold=True),
            arcade.Text("Info: as condições climáticas impactam o desgaste dos pneus e o desempenho do carro.", 214, 91, SECONDARY_TEXT_COLOR, 9),
            arcade.Text("←  Voltar ao menu", 34, 30, SECONDARY_TEXT_COLOR, 10),
        ]
        return tuple(labels)

    @staticmethod
    def _draw_rounded_rectangle(
        left: float,
        bottom: float,
        width: float,
        height: float,
        radius: float,
        color: tuple[int, ...],
    ) -> None:
        """Fill a rounded rectangle using primitives available in Arcade 3.3."""

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
        border_width: int = 1,
    ) -> None:
        """Draw a rounded fill and a consistent border without texture assets."""

        cls._draw_rounded_rectangle(
            left, bottom, width, height, radius, border_color
        )
        inset = border_width
        cls._draw_rounded_rectangle(
            left + inset,
            bottom + inset,
            width - 2 * inset,
            height - 2 * inset,
            max(radius - inset, 0),
            fill_color,
        )
