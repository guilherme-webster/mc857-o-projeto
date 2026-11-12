"""Tela de carregamento enquanto o backend simula as etapas do plano.

A esquerda mostra o grid de largada, a direita a etapa em foco (voltas, sessao,
largada, motor e clima por volta) com setas para as demais etapas, e embaixo o
status da simulacao com o botao de abortar. A simulacao roda numa thread; a
tela so le a fila de resultados em ``on_update``, na thread do Arcade.
"""

from __future__ import annotations

from collections.abc import Callable
from queue import Empty, SimpleQueue
from threading import Event, Thread
from typing import Any

import arcade

from frontend.arcade import track_client
from frontend.arcade.configuration_state import SimulationPlan
from frontend.arcade.track_preview import TrackPreviewGeometry, fit_track_preview
from frontend.arcade.race_launcher import LaunchCancelled, LaunchOutcome, LaunchProgress
from frontend.arcade.theme import (
    BACKGROUND_COLOR,
    ERROR_COLOR,
    PANEL_BORDER_COLOR,
    PANEL_COLOR,
    PRIMARY_TEXT_COLOR,
    SECONDARY_TEXT_COLOR,
)
from frontend.arcade.weather_view import TrackConfigurationView, WEATHER_TIMELINE_COLORS

_WEATHER_FALLBACK_COLOR = (90, 90, 90)
_BUTTON_BG = (46, 62, 80)
_BUTTON_HOVER = (70, 90, 115)
_PRIMARY_BG = (190, 30, 45)
_PRIMARY_HOVER = (225, 45, 60)
_HEADER_COLOR = (130, 140, 150)
_ROW_HEIGHT = 22
_SCROLLBAR_COLOR = (33, 42, 53)


def progress_text(progress: LaunchProgress) -> str:
    """Frase de status: a da etapa com a volta em curso, ou a do passo."""

    if progress.stage_index and progress.lap:
        return (
            f"Simulando etapa {progress.stage_index} de {progress.total_stages} - "
            f"{progress.stage_name}. Volta {progress.lap} de {progress.laps}."
        )
    if progress.stage_index:
        return (
            f"Simulando etapa {progress.stage_index} de {progress.total_stages} - "
            f"{progress.stage_name}. Iniciando a corrida…"
        )
    return progress.message


def progress_fraction(progress: LaunchProgress) -> float:
    """Fracao 0-1 do plano todo: etapas concluidas mais a volta em curso.

    Sem etapa informada (passo de preparo), vale 0. A volta conta so como
    fracao da etapa; a barra nunca passa de 1.
    """

    if progress.total_stages <= 0:
        return 0.0
    finished = max(progress.stage_index - 1, 0)
    lap_part = 0.0
    if progress.stage_index and progress.laps > 0:
        lap_part = min(progress.lap / progress.laps, 1.0)
    return min((finished + lap_part) / progress.total_stages, 1.0)


def next_index(current: int, step: int, count: int) -> int:
    """Etapa vizinha no carrossel, voltando ao inicio ou ao fim."""

    return (current + step) % count


class SimulationLoadingView(arcade.View):
    """Acompanha ``runner(plan, progress, cancelled)`` e leva ao resultado."""

    def __init__(
        self,
        plan: SimulationPlan,
        runner: Callable[..., LaunchOutcome],
        return_view: arcade.View | None,
        on_done: Callable[[LaunchOutcome], None],
        grid_loader: Callable[[], Any] = track_client.fetch_current_grid,
        track_loader: Callable[[str], dict] = track_client.fetch_track,
    ) -> None:
        """``return_view`` precisa aceitar ``show_message(texto, cor)``; e a
        tela da configuracao, para onde o botao de abortar volta."""

        super().__init__()
        self._plan = plan
        self._runner = runner
        self._return_view = return_view
        self._on_done = on_done
        self._grid_loader = grid_loader
        self._track_loader = track_loader
        # Geometria bruta por circuito (buscada uma vez) e prévias ajustadas
        # a area atual, refeitas quando a janela muda de tamanho.
        self._track_payloads: dict[str, dict] = {}
        self._track_errors: dict[str, str] = {}
        self._previews: dict[tuple, TrackPreviewGeometry] = {}
        self._results: SimpleQueue[tuple[str, object]] = SimpleQueue()
        self._cancel = Event()
        self._started = False
        self._grid: list[dict] = []
        self._grid_loaded = False
        self._grid_scroll = 0  # indice do primeiro piloto visivel
        self._progress = LaunchProgress("Preparando a simulação…")
        self._error: str | None = None
        self._race_index = 0
        self._hover: str | None = None
        self._texts: dict[str, arcade.Text] = {}

    # -- trabalho em segundo plano ---------------------------------------------

    def on_show_view(self) -> None:
        arcade.set_background_color(BACKGROUND_COLOR)
        if not self._started:
            self._started = True
            self._start_workers()

    def _start_workers(self) -> None:
        def load_grid() -> None:
            try:
                payload = self._grid_loader()
            except (RuntimeError, OSError, ValueError):
                payload = None
            self._results.put(("grid", payload))

        def run() -> None:
            def progress(item: object) -> None:
                if not isinstance(item, LaunchProgress):
                    item = LaunchProgress(str(item))
                self._results.put(("progress", item))

            try:
                outcome = self._runner(self._plan, progress, self._cancel.is_set)
            except LaunchCancelled:
                return
            except (RuntimeError, OSError, ValueError, KeyError) as error:
                # BackendError e RuntimeError; URLError e OSError.
                self._results.put(("error", str(error)))
                return
            self._results.put(("done", outcome))

        def load_tracks() -> None:
            for circuit_id in dict.fromkeys(race.circuit_id for race in self._plan.races):
                try:
                    payload = self._track_loader(circuit_id)
                except (RuntimeError, OSError, ValueError, KeyError) as error:
                    self._results.put(("track", (circuit_id, False, str(error))))
                else:
                    self._results.put(("track", (circuit_id, True, payload)))

        Thread(target=load_grid, name="loading-grid", daemon=True).start()
        Thread(target=load_tracks, name="loading-tracks", daemon=True).start()
        Thread(target=run, name="simulation-launcher", daemon=True).start()

    def on_update(self, delta_time: float) -> None:
        del delta_time
        while True:
            try:
                kind, payload = self._results.get_nowait()
            except Empty:
                return
            if kind == "grid":
                self._grid_loaded = True
                entries = payload.get("grid", []) if isinstance(payload, dict) else []
                self._grid = list(entries)
            elif kind == "track":
                circuit_id, ok, value = payload  # type: ignore[misc]
                if ok:
                    self._track_payloads[circuit_id] = value  # type: ignore[assignment]
                else:
                    self._track_errors[circuit_id] = str(value)
            elif kind == "progress":
                self._progress = payload  # type: ignore[assignment]
            elif kind == "error":
                self._error = str(payload)
                self._progress = LaunchProgress(
                    f"Não foi possível simular: {payload}"
                )
            elif kind == "done":
                self._on_done(payload)  # type: ignore[arg-type]
                return

    # -- acoes -------------------------------------------------------------------

    def abort(self) -> None:
        """Pare de simular e volte a configuracao; o que ja foi pedido ao
        backend termina, mas nenhuma etapa nova e iniciada."""

        if self._error is not None:
            message, color = f"Não foi possível simular: {self._error}", ERROR_COLOR
        else:
            self._cancel.set()
            message, color = "Simulação cancelada.", SECONDARY_TEXT_COLOR
        if self._return_view is not None:
            self._return_view.show_message(message, color)
            self.window.show_view(self._return_view)

    # -- geometria ---------------------------------------------------------------

    def _rects(self) -> dict[str, tuple[float, float, float, float]]:
        width, height = self.window.width, self.window.height
        top, bottom = height - 110, 130
        middle = width / 2
        right_x = middle + 20
        right_w = width - middle - 60
        return {
            "grid": (40, bottom, middle - 60, top - bottom),
            "race": (right_x, bottom, right_w, top - bottom),
            "prev": (right_x + right_w - 120, top - 44, 34, 30),
            "next": (right_x + right_w - 70, top - 44, 34, 30),
            "abort": (width - 260, 40, 220, 42),
        }

    def _visible_rows(self) -> int:
        """Linhas de piloto que cabem da primeira linha ate a margem inferior da caixa."""

        panel_top, panel_bottom = self.window.height - 110, 130
        first_row_y = panel_top - 60
        return max(1, int((first_row_y - panel_bottom - 20) // _ROW_HEIGHT) + 1)

    def _max_grid_scroll(self) -> int:
        return max(0, len(self._grid) - self._visible_rows())

    # -- eventos -----------------------------------------------------------------

    def on_mouse_motion(self, x: int, y: int, dx: int, dy: int) -> None:
        self._hover = next(
            (key for key in ("abort", "prev", "next")
             if _inside(x, y, self._rects()[key])),
            None,
        )

    def on_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float) -> None:
        """Roda do mouse sobre a caixa do grid rola uma linha por passo."""

        if not self._grid or not _inside(x, y, self._rects()["grid"]):
            return
        step = -1 if scroll_y > 0 else 1 if scroll_y < 0 else 0
        self._grid_scroll = min(max(self._grid_scroll + step, 0), self._max_grid_scroll())

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        rects = self._rects()
        if _inside(x, y, rects["abort"]):
            self.abort()
            return
        if len(self._plan.races) > 1:
            if _inside(x, y, rects["prev"]):
                self._step_race(-1)
            elif _inside(x, y, rects["next"]):
                self._step_race(1)

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol == arcade.key.LEFT:
            self._step_race(-1)
        elif symbol == arcade.key.RIGHT:
            self._step_race(1)

    def _step_race(self, step: int) -> None:
        self._race_index = next_index(self._race_index, step, len(self._plan.races))

    # -- desenho -----------------------------------------------------------------

    def _text(self, key: str, value: str, x, y, color, size=12, **style) -> arcade.Text:
        text = self._texts.get(key)
        if text is None:
            text = arcade.Text(value, x, y, color, size, **style)
            self._texts[key] = text
        if text.text != value:
            text.text = value
        text.x, text.y = x, y
        if text.color != color:
            text.color = color
        return text

    def on_draw(self) -> None:
        self.clear()
        width, height = self.window.width, self.window.height
        rects = self._rects()
        title = (
            "Simulando o torneio" if len(self._plan.races) > 1 else "Simulando a corrida"
        )
        self._text("title", title, 40, height - 60, PRIMARY_TEXT_COLOR, 26, bold=True).draw()
        self._text(
            "subtitle", self._plan.rules.name, 40, height - 90, SECONDARY_TEXT_COLOR, 12
        ).draw()
        self._draw_grid(rects["grid"])
        self._draw_race(rects["race"])
        self._draw_status(width, rects)
        self._draw_loading_bar(width)

    def _draw_loading_bar(self, width: float) -> None:
        """Barra fina logo abaixo do status, com o progresso do plano."""

        left, bottom, height = 40, 60, 8
        bar_w = width - 340  # mesma largura do texto de status
        arcade.draw_lbwh_rectangle_filled(left, bottom, bar_w, height, (33, 42, 53))
        fill = ERROR_COLOR if self._error is not None else PRIMARY_TEXT_COLOR
        fraction = progress_fraction(self._progress)
        if fraction > 0:
            arcade.draw_lbwh_rectangle_filled(left, bottom, bar_w * fraction, height, fill)

    def _preview_for(self, circuit_id: str, bounds: tuple) -> tuple[
        TrackPreviewGeometry | None, str | None
    ]:
        """Prévia da pista dentro de ``bounds``, ou o motivo de nao existir."""

        if circuit_id in self._track_errors:
            return None, self._track_errors[circuit_id]
        payload = self._track_payloads.get(circuit_id)
        if payload is None:
            return None, None
        key = (circuit_id, bounds)
        geometry = self._previews.get(key)
        if geometry is None:
            try:
                geometry = fit_track_preview(payload, bounds, padding=16)
            except ValueError as error:
                return None, str(error)
            self._previews.clear()
            self._previews[key] = geometry
        return geometry, None

    def _draw_track_preview(self, race, x: float, bottom: float, w: float, h: float) -> None:
        """Mesmo desenho da tela de configuracao, com o comprimento da volta."""

        geometry, error = self._preview_for(race.circuit_id, (x, bottom, w, h))
        _rounded(x, bottom, w, h, (9, 20, 17), PANEL_BORDER_COLOR, radius=7)
        if geometry is None:
            message = error or "Carregando geometria…"
            self._text(
                "preview-message",
                message,
                x + w / 2,
                bottom + h / 2,
                ERROR_COLOR if error else SECONDARY_TEXT_COLOR,
                10,
                anchor_x="center",
                anchor_y="center",
                width=w - 20,
                multiline=True,
            ).draw()
            return
        arcade.draw_line_strip(geometry.track_points, (29, 33, 39), 12)
        arcade.draw_line_strip(geometry.track_points, (223, 226, 231), 9)
        arcade.draw_line_strip(geometry.track_points, (96, 102, 110), 6)
        arcade.draw_line_strip(geometry.pit_lane_points, (249, 184, 66), 3)
        arcade.draw_circle_filled(*geometry.service_point, 5, (255, 176, 0))
        length = f"{geometry.lap_length_m / 1000:.3f}".replace(".", ",")
        self._text(
            "preview-length",
            f"Comprimento da volta: {length} km",
            x,
            bottom + h + 6,
            PRIMARY_TEXT_COLOR,
            11,
        ).draw()

    def _panel(self, rect, title: str, key: str) -> None:
        left, bottom, w, h = rect
        _rounded(left, bottom, w, h, PANEL_COLOR, PANEL_BORDER_COLOR, radius=8)
        self._text(
            key, title, left + 20, bottom + h - 30, _HEADER_COLOR, 11, bold=True
        ).draw()

    def _draw_grid(self, rect) -> None:
        left, bottom, _w, _h = rect
        self._panel(rect, "GRID DE LARGADA", "grid-title")
        top = bottom + rect[3] - 60
        if not self._grid_loaded:
            message = "Carregando o grid…"
        elif not self._grid:
            message = "Sem grid no backend: ele sera montado ao iniciar."
        else:
            message = None
        if message is not None:
            self._text("grid-message", message, left + 20, top, SECONDARY_TEXT_COLOR, 12).draw()
            return
        visible = self._visible_rows()
        self._grid_scroll = min(self._grid_scroll, self._max_grid_scroll())
        start = self._grid_scroll
        for offset, entry in enumerate(self._grid[start : start + visible]):
            index = start + offset
            y = top - offset * _ROW_HEIGHT
            self._text(f"grid-p:{index}", str(index + 1), left + 20, y, PRIMARY_TEXT_COLOR, 10).draw()
            self._text(
                f"grid-n:{index}",
                str(entry.get("driver_name", ""))[:24],
                left + 60,
                y,
                PRIMARY_TEXT_COLOR,
                10,
            ).draw()
            self._text(
                f"grid-t:{index}",
                str(entry.get("team_name", ""))[:22],
                left + 300,
                y,
                SECONDARY_TEXT_COLOR,
                9,
            ).draw()
        self._draw_grid_scrollbar(rect, top, visible)

    def _draw_grid_scrollbar(self, rect, top: float, visible: int) -> None:
        """Trilho e cursor a direita da caixa; so aparece se houver pilotos ocultos."""

        total = len(self._grid)
        if total <= visible:
            return
        left, bottom, width, _height = rect
        track_x = left + width - 12
        track_top, track_bottom = top + 4, bottom + 20
        track_h = track_top - track_bottom
        arcade.draw_lbwh_rectangle_filled(track_x, track_bottom, 4, track_h, _SCROLLBAR_COLOR)
        thumb_h = max(track_h * visible / total, 24)
        thumb_top = track_top - (track_h - thumb_h) * self._grid_scroll / (total - visible)
        arcade.draw_lbwh_rectangle_filled(
            track_x, thumb_top - thumb_h, 4, thumb_h, SECONDARY_TEXT_COLOR
        )

    def _draw_race(self, rect) -> None:
        left, bottom, w, h = rect
        self._panel(rect, "ETAPA EM FOCO", "race-title")
        race = self._plan.races[self._race_index]
        config = race.configuration
        session = race.session
        laps = config.laps
        first = session.first_lap if session else 1
        last = session.last_lap if session else laps
        top = bottom + h - 60
        lines = (
            (race.name, 18, True),
            (f"{laps} voltas", 13, False),
            (f"Voltas {first}–{last}", 12, False),
            (f"Largada: {session.start_mode if session else 'Parada'}", 12, False),
        )
        for index, (text, size, bold) in enumerate(lines):
            self._text(
                f"race-line:{index}",
                text,
                left + 20,
                top - index * 28,
                PRIMARY_TEXT_COLOR,
                size,
                bold=bold,
            ).draw()
        # Abaixo do resumo: prévia da pista a esquerda e clima a direita.
        body_top = top - 140
        body_bottom = bottom + 20
        column_w = min(220, (w - 40) // 2)
        column_left = left + w - 20 - column_w
        self._draw_weather(column_left, body_top, column_w, body_top - body_bottom, config)
        preview_w = column_left - 20 - (left + 20)
        # 24 px acima da prévia ficam para o rótulo do comprimento.
        preview_height = body_top - 24 - body_bottom
        if preview_height >= 120 and preview_w >= 120:
            self._draw_track_preview(race, left + 20, body_bottom, preview_w, preview_height)
        if len(self._plan.races) > 1:
            self._draw_stepper(rect)

    def _draw_weather(self, x: float, top: float, column_w: float, height: float, config) -> None:
        """Barra vertical do clima (volta 1 no topo) com o resumo ao lado."""

        self._text("weather-title", "Clima por volta", x, top, SECONDARY_TEXT_COLOR, 11).draw()
        schedule = config.weather_schedule
        total = schedule.total_laps
        bar_w = 26
        bar_top = top - 26
        bar_h = height - 26
        arcade.draw_lbwh_rectangle_filled(x, bar_top - bar_h, bar_w, bar_h, (33, 42, 53))
        for weather_range in schedule.ranges():
            span = (weather_range.end_lap - weather_range.start_lap + 1) / total * bar_h
            segment_top = bar_top - (weather_range.start_lap - 1) / total * bar_h
            color = WEATHER_TIMELINE_COLORS.get(weather_range.weather, _WEATHER_FALLBACK_COLOR)
            arcade.draw_lbwh_rectangle_filled(x, segment_top - span, bar_w, span, color)
        self._text(
            "weather-summary",
            schedule.compact_summary(),
            x + bar_w + 14,
            bar_top,
            SECONDARY_TEXT_COLOR,
            10,
            width=column_w - bar_w - 14,
            multiline=True,
        ).draw()

    def _draw_stepper(self, rect) -> None:
        rects = self._rects()
        count = len(self._plan.races)
        self._text(
            "stepper-count",
            f"{self._race_index + 1} / {count}",
            rect[0] + rect[2] - 170,
            rect[1] + rect[3] - 29,
            SECONDARY_TEXT_COLOR,
            11,
            anchor_y="center",
        ).draw()
        for key, symbol in (("prev", "‹"), ("next", "›")):
            left, bottom, w, h = rects[key]
            hover = self._hover == key
            _rounded(
                left, bottom, w, h, _BUTTON_HOVER if hover else _BUTTON_BG, radius=6
            )
            self._text(
                f"stepper-{key}",
                symbol,
                left + w / 2,
                bottom + h / 2,
                PRIMARY_TEXT_COLOR,
                16,
                anchor_x="center",
                anchor_y="center",
            ).draw()

    def _draw_status(self, width: float, rects) -> None:
        status_color = ERROR_COLOR if self._error is not None else PRIMARY_TEXT_COLOR
        self._text(
            "status",
            progress_text(self._progress),
            40,
            90,
            status_color,
            14,
            width=width - 340,
            multiline=True,
        ).draw()
        left, bottom, w, h = rects["abort"]
        hover = self._hover == "abort"
        background = (
            _PRIMARY_HOVER if hover else _PRIMARY_BG
        ) if self._error is None else (_BUTTON_HOVER if hover else _BUTTON_BG)
        _rounded(left, bottom, w, h, background, radius=6)
        label = (
            "Abortar simulação" if self._error is None else "Voltar à configuração"
        )
        self._text(
            "abort-label",
            label,
            left + w / 2,
            bottom + h / 2,
            PRIMARY_TEXT_COLOR,
            13,
            bold=True,
            anchor_x="center",
            anchor_y="center",
        ).draw()


def _rounded(
    left: float,
    bottom: float,
    width: float,
    height: float,
    fill: tuple[int, ...],
    border: tuple[int, ...] = PANEL_BORDER_COLOR,
    *,
    radius: float,
) -> None:
    """Painel de cantos arredondados, o mesmo desenho das outras telas."""

    TrackConfigurationView._draw_rounded_panel(
        left, bottom, width, height, radius, fill, border
    )


def _inside(x: float, y: float, rect) -> bool:
    left, bottom, width, height = rect
    return left <= x <= left + width and bottom <= y <= bottom + height
