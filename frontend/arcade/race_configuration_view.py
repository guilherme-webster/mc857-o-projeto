"""Configure one tournament stage, including in-place weather editing."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Thread
from typing import TYPE_CHECKING

import arcade

from frontend.arcade.configuration_state import (
    ConfigurationFormError,
    SessionConfiguration,
    WeatherSchedule,
)
from frontend.arcade.track_client import fetch_track
from frontend.arcade.track_preview import TrackPreviewGeometry, fit_track_preview
from frontend.arcade.theme import (
    ACCENT_COLOR,
    BACKGROUND_COLOR,
    ERROR_COLOR,
    PRIMARY_TEXT_COLOR,
    SECONDARY_TEXT_COLOR,
)
from frontend.arcade.weather_view import WEATHER_ICON_PATHS, WEATHER_TIMELINE_COLORS

if TYPE_CHECKING:
    from frontend.arcade.parameters_view import ParametersView


WINDOW_SIZE = (1672, 900)
SIDEBAR_ITEMS = {
    "Sessão": (45, 600, 378, 55),
    "Pista": (45, 540, 378, 55),
    "Clima": (45, 480, 378, 55),
    "Regras": (45, 420, 378, 55),
    "Carros": (45, 360, 378, 55),
}
TRACK_MAP_BOUNDS = (784, 264, 673, 173)
SESSION_FIELD_BOUNDS = {
    "first_lap": (805, 498, 385, 38),
    "last_lap": (1220, 498, 398, 38),
}
SESSION_STEPPER_BOUNDS = {
    field: (
        (left + width - 74, bottom + 2, 34, height - 4),
        (left + width - 38, bottom + 2, 34, height - 4),
    )
    for field, (left, bottom, width, height) in SESSION_FIELD_BOUNDS.items()
}
BACK_BOUNDS = (50, 56, 367, 53)
CANCEL_BOUNDS = (1100, 8, 152, 42)
SAVE_BOUNDS = (1270, 8, 169, 42)
ADVANCE_BOUNDS = (1454, 8, 186, 42)
WEATHER_PALETTE_BOUNDS = {
    "Seco": (475, 527, 180, 45),
    "Chuva leve": (669, 527, 180, 45),
    "Chuva intensa": (863, 527, 190, 45),
}
WEATHER_START_BOUNDS = (476, 467, 122, 38)
WEATHER_END_BOUNDS = (616, 467, 122, 38)
WEATHER_APPLY_BOUNDS = (1392, 467, 226, 44)
WEATHER_TIMELINE_BOUNDS = (475, 342, 1142, 24)
WEATHER_PREVIOUS_BOUNDS = (1508, 255, 46, 34)
WEATHER_NEXT_BOUNDS = (1568, 255, 46, 34)
WEATHER_SUMMARY_PAGE_SIZE = 8


class RaceConfigurationView(arcade.View):
    """Edit one stage and summarize its track and existing weather schedule."""

    def __init__(
        self,
        parent: ParametersView,
        schedule: WeatherSchedule,
        *,
        circuit_id: str,
        track_name: str,
        stage_index: int = 1,
        session: SessionConfiguration | None = None,
        track_loader: Callable[[str], dict] = fetch_track,
    ) -> None:
        super().__init__()
        self.parent = parent
        self.schedule = schedule
        self.circuit_id = circuit_id
        self.track_name = track_name
        self.stage_index = stage_index
        self.session = session or SessionConfiguration(1, schedule.total_laps)
        self.active_topic = "Sessão"
        self._track_loader = track_loader
        self._results: SimpleQueue[tuple[str, object]] = SimpleQueue()
        self._loading = False
        self._preview: TrackPreviewGeometry | None = None
        self._track_error: str | None = None
        self._status = "Ajuste os parâmetros desta etapa."
        self.selected_weather = "Seco"
        self._weather_start_text = "1"
        self._weather_end_text = str(schedule.total_laps)
        self._weather_focused_field: str | None = None
        self._weather_replace_on_type = False
        self._weather_drag_start: int | None = None
        self._weather_drag_end: int | None = None
        self._weather_summary_page = 0
        self._logo = arcade.load_texture(
            Path(__file__).with_name("assets") / "f1-logo.png"
        )
        self._weather_icons = {
            weather: arcade.load_texture(path)
            for weather, path in WEATHER_ICON_PATHS.items()
        }

    def on_show_view(self) -> None:
        """Use the tournament window size for every tab of this view."""

        if self.window.visible and self.window.get_size() != WINDOW_SIZE:
            self.window.set_size(*WINDOW_SIZE)
        arcade.set_background_color(BACKGROUND_COLOR)
        self._load_track()

    def _load_track(self) -> None:
        if self._loading or self._preview is not None:
            return
        self._loading = True

        def load() -> None:
            try:
                payload = self._track_loader(self.circuit_id)
            except Exception as error:  # noqa: BLE001 - external HTTP boundary
                self._results.put(("error", type(error).__name__))
            else:
                self._results.put(("success", payload))

        Thread(target=load, name="race-configuration-preview", daemon=True).start()

    def on_update(self, delta_time: float) -> None:
        del delta_time
        try:
            outcome, payload = self._results.get_nowait()
        except Empty:
            return
        self._loading = False
        if outcome == "error":
            self._track_error = str(payload)
            return
        try:
            left, bottom, width, height = TRACK_MAP_BOUNDS
            self._preview = fit_track_preview(
                payload, (left, bottom + 12, width, height - 12), padding=22
            )
        except ValueError as error:
            self._track_error = str(error)

    def on_draw(self) -> None:
        self.clear()
        self._draw_header()
        self._draw_sidebar()
        self._draw_stage_header()
        if self.active_topic == "Sessão":
            self._draw_session()
            self._draw_track_summary()
            self._draw_weather_summary()
        elif self.active_topic == "Clima":
            self._draw_weather_editor()
        else:
            self._panel((450, 80, 1190, 555))
            self._text(self.active_topic, 476, 590, 25)
            self._text(
                "Esta seção será configurada em uma próxima etapa.",
                476,
                550,
                14,
                SECONDARY_TEXT_COLOR,
            )
        self._draw_footer()

    def _draw_header(self) -> None:
        arcade.draw_lbwh_rectangle_filled(0, 844, 1672, 56, (12, 17, 24))
        arcade.draw_line(0, 844, 1672, 844, (49, 62, 78), 1)
        arcade.draw_texture_rect(self._logo, arcade.LBWH(20, 860, 50, 25))
        self._text("SIMULADOR DE CORRIDA", 94, 866, 15, SECONDARY_TEXT_COLOR)
        self._panel((1535, 850, 97, 34))
        self._text(
            "Ajuda",
            1583,
            867,
            12,
            SECONDARY_TEXT_COLOR,
            anchor_x="center",
            anchor_y="center",
        )
        self._text("Configuração da corrida", 50, 795, 38)
        self._text(
            "Ajuste os parâmetros específicos de cada etapa do torneio.",
            50,
            768,
            17,
            SECONDARY_TEXT_COLOR,
        )

    def _draw_sidebar(self) -> None:
        self._panel((34, 40, 400, 710))
        self._text("ETAPA DO TORNEIO", 57, 711, 14, SECONDARY_TEXT_COLOR)
        short_name = (
            self.track_name
            if len(self.track_name) <= 20
            else self.track_name[:18] + "…"
        )
        self._text(f"Etapa {self.stage_index} · {short_name}", 57, 682, 16)
        for topic, bounds in SIDEBAR_ITEMS.items():
            if topic == self.active_topic:
                self._panel(bounds, (56, 25, 36), (166, 35, 51))
            self._text(
                topic,
                119,
                bounds[1] + 27,
                19,
                (
                    PRIMARY_TEXT_COLOR
                    if topic == self.active_topic
                    else SECONDARY_TEXT_COLOR
                ),
                anchor_y="center",
            )
        self._panel((50, 121, 367, 65))
        self._text(
            "Configurações gerais podem herdar", 68, 158, 13, SECONDARY_TEXT_COLOR
        )
        self._text("valores do torneio.", 68, 138, 13, SECONDARY_TEXT_COLOR)
        self._button(BACK_BOUNDS, "‹   Voltar ao torneio")

    def _draw_stage_header(self) -> None:
        self._panel((450, 645, 1190, 103))
        self._text(
            f"Etapa {self.stage_index} · {self.track_name}", 468, 712, 24, width=750
        )
        self._text(
            f"{self.schedule.total_laps} voltas     ·     Clima configurável     ·     Pista única",
            469,
            675,
            14,
            SECONDARY_TEXT_COLOR,
        )
        if self._preview:
            length = f"{self._preview.lap_length_m / 1000:.3f}".replace(".", ",")
            self._text(
                f"Distância da amostra: {length} km",
                1620,
                680,
                12,
                SECONDARY_TEXT_COLOR,
                anchor_x="right",
            )

    def _draw_session(self) -> None:
        self._panel((450, 455, 1190, 180))
        self._text("Sessão", 475, 604, 25)
        self._text(
            "Defina os parâmetros principais desta etapa.",
            475,
            578,
            14,
            SECONDARY_TEXT_COLOR,
        )
        labels = (
            ("Tipo de sessão", 475),
            ("Volta inicial", 805),
            ("Volta final", 1220),
        )
        for label, x in labels:
            self._text(label, x, 544, 14, SECONDARY_TEXT_COLOR)
        self._panel((475, 498, 300, 38))
        self._text("Corrida", 490, 518, 15, anchor_y="center")
        for key, value in (
            ("first_lap", str(self.session.first_lap)),
            ("last_lap", str(self.session.last_lap)),
        ):
            bounds = SESSION_FIELD_BOUNDS[key]
            self._panel(bounds)
            self._text(
                value,
                bounds[0] + (bounds[2] - 74) / 2,
                bounds[1] + 19,
                15,
                anchor_x="center",
                anchor_y="center",
            )
            for button_bounds, symbol in zip(
                SESSION_STEPPER_BOUNDS[key], ("−", "+"), strict=True
            ):
                self._panel(button_bounds, (26, 37, 50))
                self._text(
                    symbol,
                    button_bounds[0] + button_bounds[2] / 2,
                    button_bounds[1] + button_bounds[3] / 2,
                    17,
                    anchor_x="center",
                    anchor_y="center",
                )
        self._text(
            "Estas opções afetam apenas a corrida selecionada.",
            475,
            472,
            13,
            SECONDARY_TEXT_COLOR,
        )

    def _draw_track_summary(self) -> None:
        self._panel((450, 250, 1190, 195))
        self._text("Resumo da pista", 475, 412, 24)
        summary_name = (
            self.track_name
            if len(self.track_name) <= 28
            else self.track_name[:25] + "…"
        )
        self._text(summary_name, 475, 372, 16)
        self._text(
            f"{self.schedule.total_laps} voltas", 475, 338, 15, SECONDARY_TEXT_COLOR
        )
        self._panel(TRACK_MAP_BOUNDS, (8, 19, 16))
        if self._preview is None:
            message = self._track_error or "Carregando geometria..."
            self._text(
                message,
                1120,
                350,
                13,
                ERROR_COLOR if self._track_error else SECONDARY_TEXT_COLOR,
                anchor_x="center",
            )
            return
        track = self._preview.track_points
        pit = self._preview.pit_lane_points
        arcade.draw_line_strip(track, (25, 29, 35), 16)
        arcade.draw_line_strip(track, (223, 228, 235), 12)
        arcade.draw_line_strip(track, (95, 102, 112), 8)
        arcade.draw_line_strip(pit, (246, 184, 64), 4)
        arcade.draw_circle_filled(*self._preview.service_point, 6, (255, 176, 0))
        arcade.draw_circle_filled(*pit[0], 5, (70, 211, 142))
        arcade.draw_circle_filled(*pit[-1], 5, (75, 142, 214))
        for index, (label, color) in enumerate(
            (
                ("Pista", (151, 158, 167)),
                ("Pit lane", (246, 184, 64)),
                ("Serviço", (255, 176, 0)),
                ("Entrada", (70, 211, 142)),
                ("Saída", (75, 142, 214)),
            )
        ):
            y = 399 - 26 * index
            arcade.draw_circle_filled(1490, y + 3, 5, color)
            self._text(label, 1507, y, 13, SECONDARY_TEXT_COLOR)

    def _draw_weather_summary(self) -> None:
        self._panel((450, 40, 1190, 200))
        self._text("Resumo do clima", 475, 207, 24)
        self._text(
            "Condição climática para esta etapa.", 475, 182, 14, SECONDARY_TEXT_COLOR
        )
        ranges = self.schedule.ranges()
        first_weather = ranges[0].weather
        for index, weather in enumerate(WEATHER_TIMELINE_COLORS):
            left = 475 + index * 190
            selected = weather == first_weather
            self._panel(
                (left, 130, 176, 42),
                (53, 27, 36) if selected else (23, 33, 45),
                ACCENT_COLOR if selected else (49, 65, 83),
            )
            arcade.draw_texture_rect(
                self._weather_icons[weather], arcade.LBWH(left + 11, 139, 24, 24)
            )
            self._text(
                weather,
                left + 45,
                150,
                14,
                PRIMARY_TEXT_COLOR if selected else SECONDARY_TEXT_COLOR,
                anchor_y="center",
            )
        self._panel((1307, 129, 311, 84))
        self._text(f"Voltas {ranges[0].start_lap} – {ranges[0].end_lap}", 1320, 188, 14)
        self._text(first_weather, 1320, 161, 14, WEATHER_TIMELINE_COLORS[first_weather])
        self._text(
            f"{len(ranges)} intervalo(s) climático(s)",
            1320,
            141,
            12,
            SECONDARY_TEXT_COLOR,
        )
        arcade.draw_lbwh_rectangle_filled(476, 75, 1140, 15, (33, 42, 53))
        for weather_range in ranges:
            left = 476 + (weather_range.start_lap - 1) / self.schedule.total_laps * 1140
            width = (
                (weather_range.end_lap - weather_range.start_lap + 1)
                / self.schedule.total_laps
                * 1140
            )
            arcade.draw_lbwh_rectangle_filled(
                left, 75, width, 15, WEATHER_TIMELINE_COLORS[weather_range.weather]
            )
        self._text("Timeline da corrida", 475, 100, 13)
        self._text(
            str(self.schedule.total_laps),
            1616,
            100,
            13,
            SECONDARY_TEXT_COLOR,
            anchor_x="right",
        )
        self._text(
            "Edite o clima na aba correspondente.", 475, 53, 12, SECONDARY_TEXT_COLOR
        )

    def _draw_weather_editor(self) -> None:
        """Draw the existing per-lap workflow inside the race configuration."""

        self._panel((450, 455, 1190, 180))
        self._text("Clima por volta", 475, 608, 25)
        self._text(
            f"Escolha uma condição e pinte um intervalo das {self.schedule.total_laps} voltas.",
            475,
            584,
            14,
            SECONDARY_TEXT_COLOR,
        )
        for weather, bounds in WEATHER_PALETTE_BOUNDS.items():
            left, bottom, width, height = bounds
            selected = weather == self.selected_weather
            self._panel(
                bounds,
                (53, 27, 36) if selected else (23, 33, 45),
                ACCENT_COLOR if selected else (49, 65, 83),
            )
            arcade.draw_texture_rect(
                self._weather_icons[weather],
                arcade.LBWH(left + 13, bottom + 10, 25, 25),
            )
            self._text(weather, left + 47, bottom + height / 2, 14, anchor_y="center")
        for label, bounds, value, field in (
            ("Volta inicial", WEATHER_START_BOUNDS, self._weather_start_text, "start"),
            ("Volta final", WEATHER_END_BOUNDS, self._weather_end_text, "end"),
        ):
            self._text(label, bounds[0], 510, 13, SECONDARY_TEXT_COLOR)
            self._panel(
                bounds,
                (23, 33, 45),
                ACCENT_COLOR if self._weather_focused_field == field else (49, 65, 83),
            )
            self._text(
                value,
                bounds[0] + bounds[2] / 2,
                bounds[1] + bounds[3] / 2,
                15,
                anchor_x="center",
                anchor_y="center",
            )
        self._button(WEATHER_APPLY_BOUNDS, "Aplicar às voltas", primary=True)
        self._text(self._status, 760, 478, 12, SECONDARY_TEXT_COLOR, width=610)

        self._panel((450, 298, 1190, 147))
        self._text("Timeline da pista", 475, 411, 22)
        self._text(
            "Clique e arraste para pintar um período da corrida.",
            475,
            388,
            13,
            SECONDARY_TEXT_COLOR,
        )
        left, bottom, width, height = WEATHER_TIMELINE_BOUNDS
        self._text("1", left, 372, 12, SECONDARY_TEXT_COLOR)
        self._text(
            str(self.schedule.total_laps),
            left + width,
            372,
            12,
            SECONDARY_TEXT_COLOR,
            anchor_x="right",
        )
        self._panel(WEATHER_TIMELINE_BOUNDS, (23, 33, 45))
        for weather_range in self.schedule.ranges():
            segment_left = (
                left
                + 3
                + (weather_range.start_lap - 1) / self.schedule.total_laps * (width - 6)
            )
            segment_width = (
                (weather_range.end_lap - weather_range.start_lap + 1)
                / self.schedule.total_laps
                * (width - 6)
            )
            arcade.draw_lbwh_rectangle_filled(
                segment_left,
                bottom + 3,
                segment_width,
                height - 6,
                WEATHER_TIMELINE_COLORS[weather_range.weather],
            )
        if self._weather_drag_start is not None and self._weather_drag_end is not None:
            first, last = sorted((self._weather_drag_start, self._weather_drag_end))
            preview_left = (
                left + 3 + (first - 1) / self.schedule.total_laps * (width - 6)
            )
            preview_width = (last - first + 1) / self.schedule.total_laps * (width - 6)
            arcade.draw_lbwh_rectangle_filled(
                preview_left,
                bottom + 3,
                preview_width,
                height - 6,
                (*WEATHER_TIMELINE_COLORS[self.selected_weather], 190),
            )
        self._text(
            "Arraste sobre a barra para ajustar os intervalos",
            1046,
            321,
            12,
            SECONDARY_TEXT_COLOR,
            anchor_x="center",
        )

        self._panel((450, 62, 1190, 226))
        self._text("Resumo por intervalo", 475, 258, 22)
        ranges = self.schedule.ranges()
        pages = (
            len(ranges) + WEATHER_SUMMARY_PAGE_SIZE - 1
        ) // WEATHER_SUMMARY_PAGE_SIZE
        self._weather_summary_page = min(self._weather_summary_page, pages - 1)
        if pages > 1:
            self._text(
                f"{self._weather_summary_page + 1}/{pages}",
                1478,
                267,
                13,
                SECONDARY_TEXT_COLOR,
            )
            self._button(WEATHER_PREVIOUS_BOUNDS, "‹")
            self._button(WEATHER_NEXT_BOUNDS, "›")
        start = self._weather_summary_page * WEATHER_SUMMARY_PAGE_SIZE
        for slot, weather_range in enumerate(
            ranges[start : start + WEATHER_SUMMARY_PAGE_SIZE]
        ):
            column = slot % 4
            row = slot // 4
            card_x = 475 + column * 286
            card_y = 169 - row * 92
            color = WEATHER_TIMELINE_COLORS[weather_range.weather]
            self._panel((card_x, card_y, 270, 82), (23, 33, 45), color)
            self._text(
                f"Voltas {weather_range.start_lap} – {weather_range.end_lap}",
                card_x + 12,
                card_y + 57,
                13,
                color,
            )
            self._text(weather_range.weather, card_x + 12, card_y + 33, 13)
            count = weather_range.end_lap - weather_range.start_lap + 1
            percentage = count / self.schedule.total_laps * 100
            self._text(
                f"{count} voltas ({percentage:.1f}%)".replace(".", ","),
                card_x + 12,
                card_y + 11,
                11,
                SECONDARY_TEXT_COLOR,
            )

    def _draw_footer(self) -> None:
        self._button(CANCEL_BOUNDS, "Cancelar")
        self._button(SAVE_BOUNDS, "Salvar corrida")
        self._button(ADVANCE_BOUNDS, "Salvar e avançar", primary=True)
        if self._status and self.active_topic not in ("Sessão", "Clima"):
            self._text(self._status, 476, 56, 13, SECONDARY_TEXT_COLOR)

    def on_mouse_release(self, x: int, y: int, button: int, modifiers: int) -> None:
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        if self.active_topic == "Clima" and self._weather_drag_start is not None:
            self._weather_drag_end = self._weather_lap_at(x)
            first, last = sorted((self._weather_drag_start, self._weather_drag_end))
            self.schedule = self.schedule.apply(first, last, self.selected_weather)
            self._weather_start_text = str(first)
            self._weather_end_text = str(last)
            self._weather_drag_start = self._weather_drag_end = None
            self._status = f"{self.selected_weather} aplicado às voltas {first}–{last}."
            return
        for topic, bounds in SIDEBAR_ITEMS.items():
            if self._contains(bounds, x, y):
                self.active_topic = topic
                self._weather_focused_field = None
                if topic == "Clima":
                    self._status = "Escolha uma condição e arraste sobre a timeline."
                return
        if self._contains(BACK_BOUNDS, x, y) or self._contains(SAVE_BOUNDS, x, y):
            self.save_and_return()
            return
        if self._contains(CANCEL_BOUNDS, x, y):
            self.cancel()
            return
        if self._contains(ADVANCE_BOUNDS, x, y):
            self.save_and_advance()
            return
        if self.active_topic == "Clima":
            self._handle_weather_click(x, y)
            return
        if self.active_topic != "Sessão":
            return
        for field, buttons in SESSION_STEPPER_BOUNDS.items():
            for delta, bounds in zip((-1, 1), buttons, strict=True):
                if not self._contains(bounds, x, y):
                    continue
                if field == "first_lap":
                    first_lap = min(
                        self.session.last_lap,
                        max(1, self.session.first_lap + delta),
                    )
                    last_lap = self.session.last_lap
                else:
                    first_lap = self.session.first_lap
                    last_lap = min(
                        self.schedule.total_laps,
                        max(first_lap, self.session.last_lap + delta),
                    )
                self.session = SessionConfiguration(
                    first_lap, last_lap, self.session.start_mode
                )
                return

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        """Start an inclusive weather interval without leaving this view."""

        if (
            button == arcade.MOUSE_BUTTON_LEFT
            and self.active_topic == "Clima"
            and self._contains(WEATHER_TIMELINE_BOUNDS, x, y)
        ):
            self._weather_drag_start = self._weather_lap_at(x)
            self._weather_drag_end = self._weather_drag_start

    def on_mouse_drag(
        self, x: int, y: int, dx: int, dy: int, buttons: int, modifiers: int
    ) -> None:
        """Preview the range while dragging over the timeline."""

        if self._weather_drag_start is not None:
            self._weather_drag_end = self._weather_lap_at(x)

    def _weather_lap_at(self, x: float) -> int:
        """Convert a clamped timeline position to a one-based lap number."""

        left, _, width, _ = WEATHER_TIMELINE_BOUNDS
        fraction = min(1, max(0, (x - left) / width))
        return min(
            self.schedule.total_laps, int(fraction * self.schedule.total_laps) + 1
        )

    def _handle_weather_click(self, x: int, y: int) -> None:
        for weather, bounds in WEATHER_PALETTE_BOUNDS.items():
            if self._contains(bounds, x, y):
                self.selected_weather = weather
                self._weather_focused_field = None
                self._status = f"{weather} selecionado; arraste sobre a timeline."
                return
        for field, bounds in (
            ("start", WEATHER_START_BOUNDS),
            ("end", WEATHER_END_BOUNDS),
        ):
            if self._contains(bounds, x, y):
                self._weather_focused_field = field
                self._weather_replace_on_type = True
                return
        self._weather_focused_field = None
        if self._contains(WEATHER_APPLY_BOUNDS, x, y):
            self.apply_weather_range()
        elif self._contains(WEATHER_PREVIOUS_BOUNDS, x, y):
            self._weather_summary_page = max(0, self._weather_summary_page - 1)
        elif self._contains(WEATHER_NEXT_BOUNDS, x, y):
            pages = (
                len(self.schedule.ranges()) + WEATHER_SUMMARY_PAGE_SIZE - 1
            ) // WEATHER_SUMMARY_PAGE_SIZE
            self._weather_summary_page = min(pages - 1, self._weather_summary_page + 1)

    def apply_weather_range(self) -> None:
        """Apply the selected condition to the inclusive numeric interval."""

        try:
            self.schedule = self.schedule.apply_text(
                start_lap=self._weather_start_text,
                end_lap=self._weather_end_text,
                weather=self.selected_weather,
            )
        except ConfigurationFormError as error:
            self._status = str(error)
            return
        self._status = "Intervalo climático atualizado."

    def on_text(self, text: str) -> None:
        """Edit the focused lap field, keeping invalid text visible for validation."""

        if self.active_topic != "Clima" or self._weather_focused_field is None:
            return
        if text.isdigit():
            attribute = f"_weather_{self._weather_focused_field}_text"
            current = "" if self._weather_replace_on_type else getattr(self, attribute)
            setattr(self, attribute, current + text)
            self._weather_replace_on_type = False

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if self.active_topic != "Clima" or self._weather_focused_field is None:
            return
        attribute = f"_weather_{self._weather_focused_field}_text"
        if symbol == arcade.key.BACKSPACE:
            current = "" if self._weather_replace_on_type else getattr(self, attribute)
            setattr(self, attribute, current[:-1])
            self._weather_replace_on_type = False
        elif symbol in (arcade.key.ENTER, arcade.key.TAB):
            self._weather_focused_field = None
            self.apply_weather_range()

    def accept_weather_schedule(self, schedule: WeatherSchedule) -> None:
        """Accept a replacement schedule while keeping lap fields in sync."""

        self.schedule = schedule
        self._weather_start_text = "1"
        self._weather_end_text = str(schedule.total_laps)
        self.session = SessionConfiguration(
            min(self.session.first_lap, schedule.total_laps),
            min(self.session.last_lap, schedule.total_laps),
            self.session.start_mode,
        )

    def save_and_return(self) -> None:
        self.parent.accept_weather_schedule(self.schedule)
        self.parent.accept_session_configuration(self.circuit_id, self.session)
        self.window.show_view(self.parent)

    def cancel(self) -> None:
        """Leave the stage without copying unsaved settings to the tournament."""

        self.window.show_view(self.parent)

    def save_and_advance(self) -> None:
        self.parent.accept_weather_schedule(self.schedule)
        self.parent.accept_session_configuration(self.circuit_id, self.session)
        if self.stage_index < len(self.parent.selected_track_ids):
            self.parent.open_tournament_stage(self.stage_index + 1)
        else:
            self.window.show_view(self.parent)

    @staticmethod
    def _contains(bounds: tuple[int, int, int, int], x: int, y: int) -> bool:
        left, bottom, width, height = bounds
        return left <= x <= left + width and bottom <= y <= bottom + height

    @staticmethod
    def _text(
        value: str,
        x: float,
        y: float,
        size: float,
        color: tuple[int, ...] = PRIMARY_TEXT_COLOR,
        **kwargs: object,
    ) -> None:
        arcade.Text(value, x, y, color, size, **kwargs).draw()

    @staticmethod
    def _panel(
        bounds: tuple[int, int, int, int],
        fill: tuple[int, ...] = (20, 30, 42),
        border: tuple[int, ...] = (49, 65, 83),
    ) -> None:
        from frontend.arcade.weather_view import TrackConfigurationView

        TrackConfigurationView._draw_rounded_panel(*bounds, 8, fill, border)

    def _button(
        self, bounds: tuple[int, int, int, int], label: str, *, primary: bool = False
    ) -> None:
        self._panel(
            bounds,
            (204, 31, 42) if primary else (26, 37, 50),
            (239, 59, 72) if primary else (49, 65, 83),
        )
        left, bottom, width, height = bounds
        self._text(
            label,
            left + width / 2,
            bottom + height / 2,
            15,
            anchor_x="center",
            anchor_y="center",
        )
