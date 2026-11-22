"""Configure one tournament stage, including in-place weather editing."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Thread
from typing import TYPE_CHECKING

import arcade

from frontend.arcade.button_text import fit_button_text
from frontend.arcade.canvas_fit import CanvasFit
from frontend.arcade.configuration_state import (
    MAX_LAPS,
    WEATHER_OPTIONS,
    ConfigurationFormError,
    SessionConfiguration,
    WeatherSchedule,
)
from frontend.arcade.drawing import caret_visible, draw_rounded_panel
from frontend.arcade.theme import (
    ACCENT_COLOR,
    BACKGROUND_COLOR,
    ERROR_COLOR,
    PRIMARY_TEXT_COLOR,
    SECONDARY_TEXT_COLOR,
    WEATHER_ICON_PATHS,
    WEATHER_TIMELINE_COLORS,
)
from frontend.arcade.track_client import fetch_track
from frontend.arcade.track_preview import TrackPreviewGeometry, fit_track_preview

if TYPE_CHECKING:
    from frontend.arcade.parameters_view import ParametersView


# Design canvas of this screen: 1280x720, o padrao das telas de configuracao.
# Every *_BOUNDS constant and draw call uses absolute x and these units. O canvas
# visivel vai de x=CANVAS_ORIGIN_X ate CANVAS_ORIGIN_X + DESIGN_SIZE[0]. O
# conteudo (x de 450 a 1640) fica centrado nele, com 45 unidades de margem em
# cada lado. Os y cabem em 0..720: cabecalho 672..720, faixa da etapa 542..612,
# colunas 16..532.
CANVAS_ORIGIN_X = 405
DESIGN_SIZE = (1280, 720)
TRACK_MAP_BOUNDS = (474, 66, 492, 374)
SESSION_FIELD_BOUNDS = {
    "first_lap": (1030, 444, 290, 38),
    "last_lap": (1340, 444, 290, 38),
}
SESSION_STEPPER_BOUNDS = {
    field: (
        (left + width - 74, bottom + 2, 34, height - 4),
        (left + width - 38, bottom + 2, 34, height - 4),
    )
    for field, (left, bottom, width, height) in SESSION_FIELD_BOUNDS.items()
}
# Botoes de acao ficam no canto inferior direito da caixa de clima.
RESET_BOUNDS = (1160, 32, 150, 40)
CANCEL_BOUNDS = (1320, 32, 150, 40)
SAVE_BOUNDS = (1480, 32, 150, 40)
# Caixa de clima: x 1010..1640 (centro 1325). Paleta (150+10+150+10+160 = 480 px)
# e campos de volta (120+10+120 = 250 px) sao centralizados nesse eixo.
WEATHER_PALETTE_BOUNDS = {
    "Seco": (1085, 314, 150, 40),
    "Chuva leve": (1245, 314, 150, 40),
    "Chuva intensa": (1405, 314, 160, 40),
}
WEATHER_START_BOUNDS = (1200, 244, 120, 40)
WEATHER_END_BOUNDS = (1330, 244, 120, 40)
WEATHER_TIMELINE_BOUNDS = (1030, 172, 580, 24)


def weather_breakdown(schedule: WeatherSchedule) -> list[str]:
    """Uma linha por condicao climatica, listando as voltas em que ela ocorre.

    Exemplo: ``"Seco: voltas 1-3, 6"``. As voltas de cada condicao sao agrupadas
    em faixas consecutivas (``a-b``), na ordem de ``WEATHER_OPTIONS``. Condicoes
    sem nenhuma volta nao aparecem.
    """

    laps_by_weather: dict[str, list[int]] = {weather: [] for weather in WEATHER_OPTIONS}
    for lap, weather in enumerate(schedule.by_lap, start=1):
        laps_by_weather[weather].append(lap)

    lines: list[str] = []
    for weather in WEATHER_OPTIONS:
        laps = laps_by_weather[weather]
        if not laps:
            continue
        runs: list[str] = []
        start = previous = laps[0]
        for lap in laps[1:] + [None]:
            if lap is not None and lap == previous + 1:
                previous = lap
                continue
            runs.append(f"{start}-{previous}" if previous != start else f"{start}")
            if lap is not None:
                start = previous = lap
        lines.append(f"{weather}: voltas {', '.join(runs)}")
    return lines


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
        # Tamanho e largura de design de cada rotulo desenhado neste quadro. Criados
        # antes de qualquer chamada que os use, e reiniciados em on_draw.
        self._label_sizes: dict[arcade.Text, float] = {}
        self._label_widths: dict[arcade.Text, float] = {}
        self.parent = parent
        self.schedule = schedule
        self.circuit_id = circuit_id
        self.track_name = track_name
        self.stage_index = stage_index
        self.session = session or SessionConfiguration(1, schedule.total_laps)
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
        # Campos "Volta inicial"/"Volta final" digitaveis: o texto so existe
        # enquanto o campo tem foco; fora dele o campo mostra a sessao.
        self._session_focused_field: str | None = None
        # Setas de etapa anterior/proxima, recalculadas a cada quadro.
        self._stage_arrows: dict[str, tuple[float, float, float, float]] = {}
        self._session_replace_on_type = False
        self._session_text: dict[str, str] = {"first_lap": "", "last_lap": ""}
        self._weather_drag_start: int | None = None
        self._weather_drag_end: int | None = None
        self._logo = arcade.load_texture(
            Path(__file__).with_name("assets") / "f1-logo.png"
        )
        self._weather_icons = {
            weather: arcade.load_texture(path)
            for weather, path in WEATHER_ICON_PATHS.items()
        }

    def on_show_view(self) -> None:
        """Apply the background and start loading the track preview.

        The window keeps whatever size the user chose; drawing and pointer
        input go through :meth:`_canvas_fit` instead of resizing the window.
        """

        arcade.set_background_color(BACKGROUND_COLOR)
        self._load_track()

    def _canvas_fit(self) -> CanvasFit:
        """Current uniform mapping between the design canvas and the window."""

        return CanvasFit.fit(DESIGN_SIZE, self.window.get_size())

    def _canvas_camera(self) -> arcade.Camera2D:
        """Camera que mostra o canvas a partir de x=CANVAS_ORIGIN_X."""

        fit = self._canvas_fit()
        width, height = fit.logical_width, fit.logical_height
        return arcade.Camera2D(
            projection=arcade.LBWH(-width / 2, -height / 2, width, height),
            viewport=arcade.LBWH(*fit.viewport),
            position=(width / 2 + CANVAS_ORIGIN_X, height / 2),
            window=self.window,
        )

    def _logical_pointer(self, x: float, y: float) -> tuple[float, float]:
        """Convert window pointer coordinates to design-canvas units."""

        design_x, design_y = self._canvas_fit().to_logical(x, y)
        return design_x + CANVAS_ORIGIN_X, design_y

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
        """Draw the design canvas scaled to the window.

        Shapes go through the canvas camera. Labels go through :meth:`_draw_label`,
        which rasterizes them at window resolution so they stay sharp at any scale.
        The label registries hold only this frame's labels, so they are rebuilt
        here and never grow.
        """

        self.clear()
        self._label_sizes = {}
        self._label_widths = {}
        # Built per frame: it is cheap and always matches the current size,
        # including resizes that happened while another view was shown.
        with self._canvas_camera().activate():
            self._draw_canvas()

    def _draw_canvas(self) -> None:
        self._draw_header()
        self._draw_stage_header()
        self._draw_session()
        self._draw_track_summary()
        self._draw_weather_editor()
        self._draw_weather_actions()

    def _draw_header(self) -> None:
        # Faixa do canvas inteiro: comeca na origem e tem a largura do design.
        arcade.draw_lbwh_rectangle_filled(
            CANVAS_ORIGIN_X, 672, DESIGN_SIZE[0], 48, (12, 17, 24)
        )
        arcade.draw_line(
            CANVAS_ORIGIN_X,
            672,
            CANVAS_ORIGIN_X + DESIGN_SIZE[0],
            672,
            (49, 62, 78),
            1,
        )
        arcade.draw_texture_rect(self._logo, arcade.LBWH(450, 683, 50, 25))
        self._text("SIMULADOR DE CORRIDA", 524, 690, 15, SECONDARY_TEXT_COLOR)
        self._text("Configuração da corrida", 450, 630, 32)

    def _draw_stage_header(self) -> None:
        """Faixa da etapa: so as setas de navegacao e o nome do circuito, centralizados."""

        self._panel((450, 542, 1190, 70))
        center_x = 450 + 1190 / 2
        name_y = 586
        self._text(
            self.track_name,
            center_x,
            name_y,
            24,
            anchor_x="center",
            anchor_y="center",
        )
        total = len(self.parent.selected_track_ids)
        stage_text = (
            "Etapa Única" if total <= 1 else f"Etapa {self.stage_index} de {total}"
        )
        self._text(stage_text, center_x, 556, 12, SECONDARY_TEXT_COLOR, anchor_x="center", anchor_y="center")
        # Setas em posicao fixa, nas bordas de uma faixa central: o tamanho do nome
        # nao as desloca. Nomes longos ficam entre elas.
        arrow_size = 34
        arrow_bottom = name_y - arrow_size / 2
        # Distancia do centro da faixa ao centro de cada seta, em unidades de design.
        arrow_offset = 360
        self._stage_arrows = {}
        # Carrossel ciclico: com mais de uma etapa, as setas sempre aparecem.
        if total > 1:
            left = center_x - arrow_offset - arrow_size / 2
            self._stage_arrows["previous"] = (left, arrow_bottom, arrow_size, arrow_size)
            left = center_x + arrow_offset - arrow_size / 2
            self._stage_arrows["next"] = (left, arrow_bottom, arrow_size, arrow_size)
        for key, bounds in self._stage_arrows.items():
            self._button(bounds, "‹" if key == "previous" else "›")

    def _draw_session(self) -> None:
        self._panel((1010, 430, 630, 102))
        self._text(
            "Altere o número de voltas do circuito.",
            1030,
            512,
            13,
            SECONDARY_TEXT_COLOR,
        )
        labels = (
            ("Volta inicial", 1030),
            ("Volta final", 1340),
        )
        for label, x in labels:
            self._text(label, x, 488, 13, SECONDARY_TEXT_COLOR)
        for key, value in (
            ("first_lap", str(self.session.first_lap)),
            ("last_lap", str(self.session.last_lap)),
        ):
            bounds = SESSION_FIELD_BOUNDS[key]
            focused = self._session_focused_field == key
            if focused:
                value = self._session_text[key]
            self._panel(bounds)
            if focused:
                arcade.draw_lbwh_rectangle_outline(*bounds, ACCENT_COLOR, 2)
            value_x = bounds[0] + (bounds[2] - 74) / 2
            value_y = bounds[1] + 19
            label = self._text(
                value,
                value_x,
                value_y,
                15,
                anchor_x="center",
                anchor_y="center",
            )
            # Cursor como linha logo apos o numero: o texto nao muda de largura, entao
            # ele nao treme quando o cursor aparece e some.
            if focused and caret_visible():
                self._draw_caret_after(label, value_x, value_y)
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

    def _draw_caret_after(self, label: arcade.Text, x: float, y: float) -> None:
        """Linha de cursor logo depois do texto ``label``, centralizado em (x, y) de design.

        Desenhada dentro da camera do canvas, em unidades de design: forma nunca
        passa pela camera padrao, so o texto passa.
        """

        caret_x = x + self._label_width(label) / 2 + 2
        half = self._label_height(label) * 0.4
        arcade.draw_line(caret_x, y - half, caret_x, y + half, PRIMARY_TEXT_COLOR, 2)

    def _draw_track_summary(self) -> None:
        self._panel((450, 16, 540, 516))
        # Centro horizontal da caixa da pista (x de 450 a 990).
        # Sem o titulo "Resumo da pista", o nome ocupa o topo da caixa. O nome
        # encolhe ate caber em 500 unidades de design (a caixa tem 540).
        self._text(
            self.track_name, 720, 484, 22, anchor_x="center", fit_width=500
        )
        laps_text = f"{self.schedule.total_laps} voltas"
        if self._preview is not None:
            length = f"{self._preview.lap_length_m / 1000:.3f}".replace(".", ",")
            laps_text += f"   ·   {length} km"
        self._text(laps_text, 720, 452, 15, SECONDARY_TEXT_COLOR, anchor_x="center")
        self._panel(TRACK_MAP_BOUNDS, (8, 19, 16))
        if self._preview is None:
            message = self._track_error or "Carregando geometria..."
            self._text(
                message,
                720,
                253,
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
            # Legenda numa linha so, abaixo do mapa.
            x = 474 + 110 * index
            arcade.draw_circle_filled(x + 5, 45, 5, color)
            self._text(label, x + 17, 42, 13, SECONDARY_TEXT_COLOR)

    def _draw_weather_editor(self) -> None:
        """Clima por volta no painel de baixo, na mesma tela da sessao.

        Paleta, intervalo, aplicar e a linha do tempo ocupam o lugar do resumo
        antigo; a linha do tempo mostra os intervalos ja definidos.
        """

        self._panel((1010, 16, 630, 404))
        self._text("Clima por volta", 1030, 388, 20)
        self._text(
            "Escolha uma condição e arraste sobre a barra para pintar as voltas.",
            1030,
            364,
            13,
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
                arcade.LBWH(left + 13, bottom + 7, 25, 25),
            )
            self._text(weather, left + 47, bottom + height / 2, 14, anchor_y="center")
        for label, bounds, value, field in (
            ("Volta inicial", WEATHER_START_BOUNDS, self._weather_start_text, "start"),
            ("Volta final", WEATHER_END_BOUNDS, self._weather_end_text, "end"),
        ):
            left, bottom, width, height = bounds
            self._text(
                label,
                left + width / 2,
                bottom + height + 6,
                12,
                SECONDARY_TEXT_COLOR,
                anchor_x="center",
            )
            self._panel(
                bounds,
                (23, 33, 45),
                ACCENT_COLOR if self._weather_focused_field == field else (49, 65, 83),
            )
            self._text(
                value,
                left + width / 2,
                bottom + height / 2,
                15,
                anchor_x="center",
                anchor_y="center",
            )
        self._text(self._status, 1030, 220, 12, SECONDARY_TEXT_COLOR, width=580)
        # Resumo por condicao, abaixo da barra de pintura e a esquerda dos botoes
        # Cancelar/Salvar (que comecam em x=1320). As linhas descem de 20 em 20.
        for index, line in enumerate(weather_breakdown(self.schedule)):
            self._text(line, 1030, 130 - 20 * index, 13, SECONDARY_TEXT_COLOR, width=280)
        left, bottom, width, height = WEATHER_TIMELINE_BOUNDS
        self._text("1", left, bottom - 20, 12, SECONDARY_TEXT_COLOR)
        self._text(
            str(self.schedule.total_laps),
            left + width,
            bottom - 20,
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

    def _draw_weather_actions(self) -> None:
        """Cancelar e Salvar corrida, no canto inferior da caixa de clima."""

        self._button(RESET_BOUNDS, "Redefinir")
        self._button(CANCEL_BOUNDS, "Cancelar")
        self._button(SAVE_BOUNDS, "Salvar", primary=True)

    def on_mouse_release(self, x: int, y: int, button: int, modifiers: int) -> None:
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        x, y = self._logical_pointer(x, y)
        # O arrasto pendente vem antes das setas: soltar o botao sobre uma seta
        # nao pode descartar a pintura do clima antes de salvar a etapa.
        if self._weather_drag_start is not None:
            self._weather_drag_end = self._weather_lap_at(x)
            first, last = sorted((self._weather_drag_start, self._weather_drag_end))
            self.schedule = self.schedule.apply(first, last, self.selected_weather)
            self._weather_start_text = str(first)
            self._weather_end_text = str(last)
            self._weather_drag_start = self._weather_drag_end = None
            self._status = f"{self.selected_weather} aplicado às voltas {first}–{last}."
            return
        if self._contains(self._stage_arrows.get("previous", (0, 0, 0, 0)), x, y):
            self._go_to_stage(self._neighbor_stage(-1))
            return
        if self._contains(self._stage_arrows.get("next", (0, 0, 0, 0)), x, y):
            self._go_to_stage(self._neighbor_stage(1))
            return
        if self._contains(SAVE_BOUNDS, x, y):
            self.save_and_return()
            return
        if self._contains(RESET_BOUNDS, x, y):
            self.reset_tournament_defaults()
            return
        if self._contains(CANCEL_BOUNDS, x, y):
            self.cancel()
            return
        self._handle_weather_click(x, y)
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
                    # A ultima volta e o tamanho da corrida: ao muda-la, o clima
                    # por volta acompanha, e ao salvar a etapa a quantidade de
                    # voltas enviada ao motor e esta.
                    last_lap = min(
                        MAX_LAPS, max(first_lap, self.session.last_lap + delta)
                    )
                    self._resize_race(last_lap)
                self.session = SessionConfiguration(
                    first_lap, last_lap, self.session.start_mode
                )
                return

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        """Start an inclusive weather interval without leaving this view."""

        x, y = self._logical_pointer(x, y)
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._handle_session_press(x, y)
        if button == arcade.MOUSE_BUTTON_LEFT and self._contains(
            WEATHER_TIMELINE_BOUNDS, x, y
        ):
            self._weather_drag_start = self._weather_lap_at(x)
            self._weather_drag_end = self._weather_drag_start

    def on_mouse_drag(
        self, x: int, y: int, dx: int, dy: int, buttons: int, modifiers: int
    ) -> None:
        """Preview the range while dragging over the timeline."""

        x, _ = self._logical_pointer(x, y)
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

    def _handle_session_press(self, x: int, y: int) -> None:
        """Foca um campo de voltas da sessao ou aplica o que estava digitado.

        Os botoes − e + ficam dentro do campo, mas nao o focam: o clique neles
        segue para o passo de soltar, como antes.
        """

        for key in ("first_lap", "last_lap"):
            bounds = SESSION_FIELD_BOUNDS[key]
            on_stepper = any(
                self._contains(button, x, y) for button in SESSION_STEPPER_BOUNDS[key]
            )
            if self._contains(bounds, x, y) and not on_stepper:
                if self._session_focused_field == key:
                    return
                self._commit_session_text()
                self._session_focused_field = key
                self._session_text[key] = str(getattr(self.session, key))
                self._session_replace_on_type = True
                return
        self._commit_session_text()

    def _commit_session_text(self) -> None:
        """Valide o texto digitado e aplique-o; texto invalido e descartado."""

        field = self._session_focused_field
        if field is None:
            return
        self._session_focused_field = None
        self._session_replace_on_type = False
        text = self._session_text[field].strip()
        if not text.isdigit():
            self._status = "Digite um número inteiro de voltas."
            return
        value = int(text)
        first, last = self.session.first_lap, self.session.last_lap
        if field == "first_lap":
            first = value
        else:
            last = value
        if not 1 <= first <= last <= MAX_LAPS:
            self._status = (
                f"Volta inicial deve ser no mínimo 1 e não passar da volta final, "
                f"que vai de 1 a {MAX_LAPS}."
            )
            return
        self._resize_race(last)
        self.session = SessionConfiguration(first, last, self.session.start_mode)
        self._status = "Voltas da etapa atualizadas."

    def on_text(self, text: str) -> None:
        """Edit the focused lap field, keeping invalid text visible for validation."""

        if self._session_focused_field is not None:
            if text.isdigit():
                field = self._session_focused_field
                current = (
                    "" if self._session_replace_on_type else self._session_text[field]
                )
                self._session_text[field] = (current + text)[:3]
                self._session_replace_on_type = False
            return
        if self._weather_focused_field is None:
            return
        if text.isdigit():
            attribute = f"_weather_{self._weather_focused_field}_text"
            current = "" if self._weather_replace_on_type else getattr(self, attribute)
            setattr(self, attribute, current + text)
            self._weather_replace_on_type = False
            self.apply_weather_range()

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if self._session_focused_field is not None:
            field = self._session_focused_field
            if symbol == arcade.key.BACKSPACE:
                current = (
                    "" if self._session_replace_on_type else self._session_text[field]
                )
                self._session_text[field] = current[:-1]
                self._session_replace_on_type = False
            elif symbol in (arcade.key.ENTER, arcade.key.TAB):
                self._commit_session_text()
            elif symbol == arcade.key.ESCAPE:
                self._session_focused_field = None
                self._session_replace_on_type = False
            return
        if self._weather_focused_field is None:
            return
        attribute = f"_weather_{self._weather_focused_field}_text"
        if symbol == arcade.key.BACKSPACE:
            current = "" if self._weather_replace_on_type else getattr(self, attribute)
            setattr(self, attribute, current[:-1])
            self._weather_replace_on_type = False
            self.apply_weather_range()
        elif symbol in (arcade.key.ENTER, arcade.key.TAB):
            self._weather_focused_field = None
            self.apply_weather_range()

    def _resize_race(self, laps: int) -> None:
        """Mantem o numero de voltas da corrida e o clima por volta sincronizados."""

        if laps != self.schedule.total_laps:
            self.schedule = self.schedule.resize(laps)
            self._weather_end_text = str(laps)

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
        self._commit_session_text()
        self.parent.accept_weather_schedule(self.schedule)
        self.parent.accept_session_configuration(self.circuit_id, self.session)
        self.window.show_view(self.parent)

    def reset_tournament_defaults(self) -> None:
        """Restaura clima e voltas padrão de todas as pistas do torneio.

        Edições não salvas desta etapa também são descartadas: a tela é reaberta
        a partir do estado restaurado no torneio.
        """

        self.parent.restore_tournament_defaults()
        self.parent.open_tournament_stage(self.stage_index)

    def cancel(self) -> None:
        """Leave the stage without copying unsaved settings to the tournament."""

        self.window.show_view(self.parent)

    def _save_stage(self) -> None:
        """Copia as configuracoes desta etapa para o torneio."""

        self._commit_session_text()
        self.parent.accept_weather_schedule(self.schedule)
        self.parent.accept_session_configuration(self.circuit_id, self.session)

    def _neighbor_stage(self, step: int) -> int:
        """Etapa anterior (step -1) ou seguinte (step +1) no ciclo de 1 ate o total."""

        total = len(self.parent.selected_track_ids)
        return (self.stage_index - 1 + step) % total + 1

    def _go_to_stage(self, stage_index: int) -> None:
        """Salva esta etapa e abre outra do torneio (setas de navegacao)."""

        self._save_stage()
        self.parent.open_tournament_stage(stage_index)

    @staticmethod
    def _contains(bounds: tuple[int, int, int, int], x: int, y: int) -> bool:
        left, bottom, width, height = bounds
        return left <= x <= left + width and bottom <= y <= bottom + height

    # Formas usam a camera de design. Textos sao rasterizados pela camera padrao
    # da janela (escalar glifos pela camera de design os deixaria borrados). Por
    # isso a posicao e o tamanho dos textos ficam em unidades de design, e
    # _draw_label os converte na hora de desenhar. Mesmo padrao de grid_view.py.

    def _text(
        self,
        value: str,
        x: float,
        y: float,
        size: float,
        color: tuple[int, ...] = PRIMARY_TEXT_COLOR,
        *,
        width: float | None = None,
        fit_width: float | None = None,
        **style: object,
    ) -> arcade.Text:
        """Cria e desenha um rotulo em (x, y) de design; devolve o objeto.

        ``size`` e o tamanho de design. ``width`` e a largura de quebra de linha em
        unidades de design; sem ela o texto nao quebra. ``fit_width`` reduz a fonte
        ate o texto caber nessa largura de design.
        """

        if width is not None:
            # pyglet exige largura nao nula para texto multilinha, mesmo na criacao.
            # Usa-se a largura de design; _apply_label_size a converte em cada quadro.
            style["width"] = int(width)
        label = arcade.Text(value, 0, 0, color, size, **style)
        self._label_sizes[label] = size
        if width is not None:
            self._label_widths[label] = width
        if fit_width is not None:
            self._fit_label(label, fit_width, size)
        self._draw_label(label, x, y)
        return label

    def _apply_label_size(self, text: arcade.Text, size: float | None = None) -> None:
        """Aplica ao texto o tamanho de design na escala atual da janela.

        ``size`` redefine o tamanho de design (ajustes de fonte). Sem ele, vale o
        registrado. A largura de quebra, guardada em design, tambem e convertida,
        pois pyglet a mede em pixels. Fonte e largura so sao trocadas quando mudam,
        porque cada troca refaz o layout.
        """

        fit = self._canvas_fit()
        if size is not None:
            self._label_sizes[text] = size
        design = self._label_sizes.setdefault(text, text.font_size)
        target = design * fit.scale
        if abs(text.font_size - target) > 1e-6:
            text.font_size = target
        wrap = self._label_widths.get(text)
        if wrap is not None:
            target_width = int(wrap * fit.scale)
            if text.width is None or abs(text.width - target_width) > 1e-6:
                text.width = target_width

    def _label_width(self, text: arcade.Text) -> float:
        """Largura do texto em unidades de design, medida na escala da janela."""

        self._apply_label_size(text)
        return text.content_width / self._canvas_fit().scale

    def _label_height(self, text: arcade.Text) -> float:
        """Altura do texto em unidades de design, medida na escala da janela."""

        self._apply_label_size(text)
        return text.content_height / self._canvas_fit().scale

    def _fit_label(self, text: arcade.Text, max_width: float, base_size: float) -> None:
        """Reduz a fonte de ``text`` para caber em ``max_width`` (design).

        A medida e feita com a fonte em tamanho de design, entao o resultado ja esta
        em unidades de design. O tamanho final vira o tamanho registrado do texto.
        """

        fit_button_text(text, max_width, base_size)
        self._apply_label_size(text, text.font_size)

    def _draw_label(self, text: arcade.Text, x: float, y: float) -> None:
        """Desenha ``text`` em (x, y) de design, rasterizado na escala da janela.

        Um texto desenhado pela camera escalada sairia borrado, entao a posicao
        e o tamanho viram unidades da janela e o desenho usa a camera padrao. As
        ancoragens do texto (anchor_x/anchor_y) continuam valendo.
        """

        self._apply_label_size(text)
        text.x, text.y = self._canvas_fit().to_window(x - CANVAS_ORIGIN_X, y)
        # Ativar uma camera zera a tesoura (scissor) do Arcade. O recorte de quem
        # chama e salvo antes e reaplicado dentro da camera; depois do bloco, a
        # tesoura volta ao valor original, para o proximo texto recortado nao
        # perder o seu recorte.
        clip = self.window.ctx.scissor
        with self.window.default_camera.activate():
            self.window.ctx.scissor = clip
            text.draw()
        self.window.ctx.scissor = clip

    @staticmethod
    def _panel(
        bounds: tuple[int, int, int, int],
        fill: tuple[int, ...] = (20, 30, 42),
        border: tuple[int, ...] = (49, 65, 83),
    ) -> None:
        draw_rounded_panel(*bounds, 8, fill, border)

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
