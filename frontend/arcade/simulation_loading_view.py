"""Tela de carregamento enquanto o backend simula as etapas do plano.

A esquerda mostra o grid de largada, a direita a etapa em foco (voltas, sessao,
motor e clima por volta) com setas para as demais etapas, e embaixo o
status da simulacao com o botao de abortar. A simulacao roda numa thread; a
tela so le a fila de resultados em ``on_update``, na thread do Arcade.

Todo o layout usa o canvas de design de 1280x720 (o mesmo de ``grid_view.py``).
Formas saem pela camera do canvas, que escala e centraliza na janela; textos
saem por ``_draw_label``, que os rasteriza na escala da janela para ficarem
nitidos. Os ponteiros chegam em unidades da janela e sao convertidos antes de
qualquer teste de area.
"""

from __future__ import annotations

from collections.abc import Callable
from queue import Empty, SimpleQueue
from threading import Event, Thread
from typing import Any

import arcade

from frontend.arcade import track_client
from frontend.arcade.canvas_fit import CanvasFit, make_canvas_camera
from frontend.arcade.configuration_state import SimulationPlan
from frontend.arcade.drawing import draw_rounded_panel
from frontend.arcade.race_launcher import LaunchCancelled, LaunchOutcome, LaunchProgress
from frontend.arcade.theme import (
    BACKGROUND_COLOR,
    ERROR_COLOR,
    PANEL_BORDER_COLOR,
    PANEL_COLOR,
    PRIMARY_TEXT_COLOR,
    SECONDARY_TEXT_COLOR,
    WEATHER_TIMELINE_COLORS,
)
from frontend.arcade.track_preview import TrackPreviewGeometry, fit_track_preview

# Canvas de design: todo o layout usa estas medidas fixas, e a janela so recebe
# a escala uniforme de CanvasFit. E a mesma referencia das outras telas.
DESIGN_WIDTH = 1280
DESIGN_HEIGHT = 720
_WEATHER_FALLBACK_COLOR = (90, 90, 90)
_BUTTON_BG = (46, 62, 80)
_BUTTON_HOVER = (70, 90, 115)
_PRIMARY_BG = (190, 30, 45)
_PRIMARY_HOVER = (225, 45, 60)
_HEADER_COLOR = (130, 140, 150)
_ROW_HEIGHT = 22
# Pilotos visiveis de uma vez no grid; o restante aparece rolando a caixa.
_MAX_VISIBLE_ROWS = 20
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
        # a area do canvas de design. A area nunca muda com a janela, entao a
        # previa so e refeita quando o circuito ou a area mudam.
        self._track_payloads: dict[str, dict] = {}
        self._track_errors: dict[str, str] = {}
        self._previews: dict[tuple, TrackPreviewGeometry] = {}
        self._results: SimpleQueue[tuple[str, object]] = SimpleQueue()
        self._cancel = Event()
        self._started = False
        self._grid: list[dict] = []
        self._grid_loaded = False
        self._grid_scroll = 0  # indice do primeiro piloto visivel
        # Arrasto do cursor do grid: (y do ponteiro, piloto visivel) no inicio.
        self._grid_drag: tuple[float, float] | None = None
        self._progress = LaunchProgress("Preparando a simulação…")
        self._error: str | None = None
        self._race_index = 0
        self._hover: str | None = None
        self._texts: dict[str, arcade.Text] = {}
        # Tamanho de design de cada texto (fonte em unidades do canvas). A fonte
        # real do texto e esse valor vezes a escala da janela, aplicada em _draw_label.
        self._label_sizes: dict[arcade.Text, float] = {}
        # Largura de quebra de linha de design dos textos que quebram (multilinha).
        self._label_widths: dict[arcade.Text, float] = {}

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
                self._results.put(("cancelled", None))
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
            elif kind == "cancelled":
                self._return_to_form("Simulação cancelada.", SECONDARY_TEXT_COLOR)
                return
            elif kind == "done":
                self._on_done(payload)  # type: ignore[arg-type]
                return

    # -- acoes -------------------------------------------------------------------

    def abort(self) -> None:
        """Solicite o cancelamento e volte a configuracao."""

        if self._error is not None:
            self._return_to_form(f"Não foi possível simular: {self._error}", ERROR_COLOR)
        else:
            self._cancel.set()
            self._progress = LaunchProgress("Cancelando simulação…")

    def _return_to_form(self, message: str, color) -> None:
        if self._return_view is not None:
            self._return_view.show_message(message, color)
            self.window.show_view(self._return_view)

    # -- canvas de design ----------------------------------------------------------

    def _canvas_fit(self) -> CanvasFit:
        """Mapeamento atual entre o canvas de design e a janela.

        Recalculado a cada chamada, e so aritmetica: assim um redimensionamento
        nunca deixa uma escala antiga para o proximo evento de mouse ou quadro.
        """

        return CanvasFit.fit((DESIGN_WIDTH, DESIGN_HEIGHT), self.window.get_size())

    def _canvas_camera(self) -> arcade.Camera2D:
        """Camera que desenha formas em unidades de design, escaladas e centralizadas."""

        return make_canvas_camera(self._canvas_fit(), self.window)

    def _logical_pointer(self, x: float, y: float) -> tuple[float, float]:
        """Converte o ponteiro (unidades da janela) para unidades de design."""

        return self._canvas_fit().to_logical(x, y)

    # -- geometria ---------------------------------------------------------------

    def _rects(self) -> dict[str, tuple[float, float, float, float]]:
        width, height = DESIGN_WIDTH, DESIGN_HEIGHT
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

        panel_top, panel_bottom = DESIGN_HEIGHT - 110, 130
        first_row_y = panel_top - 60
        fits = int((first_row_y - panel_bottom - 20) // _ROW_HEIGHT) + 1
        return max(1, min(_MAX_VISIBLE_ROWS, fits))

    def _max_grid_scroll(self) -> int:
        return max(0, len(self._grid) - self._visible_rows())

    @staticmethod
    def _grid_top(rect) -> float:
        """Y da primeira linha de pilotos dentro da caixa do grid."""

        left, bottom, _w, h = rect
        return bottom + h - 60

    def _grid_bar_layout(
        self, rect, top: float, visible: int
    ) -> tuple[float, float, float, float, int] | None:
        """Trilho do grid: (topo, base, altura do cursor, curso do cursor, rolagem
        maxima). None quando todos os pilotos cabem. Desenho e arrasto usam esta conta."""

        total = len(self._grid)
        if total <= visible:
            return None
        _left, bottom, _width, _height = rect
        track_top, track_bottom = top + 4, bottom + 20
        track_h = track_top - track_bottom
        thumb_h = max(track_h * visible / total, 24)
        return track_top, track_bottom, thumb_h, track_h - thumb_h, total - visible

    def _start_grid_drag(self, x: float, y: float) -> bool:
        """Inicia o arrasto se o clique cair no trilho do grid (ponteiro em design)."""

        rect = self._rects()["grid"]
        layout = self._grid_bar_layout(rect, self._grid_top(rect), self._visible_rows())
        if layout is None:
            return False
        track_top, track_bottom = layout[0], layout[1]
        left, _bottom, width, _height = rect
        # Trilho de 4 px em left + width - 12; a faixa de clique aceita 4 px de folga.
        track_x = left + width - 12
        if not (track_x - 4 <= x <= track_x + 8 and track_bottom <= y <= track_top):
            return False
        self._grid_drag = (y, self._grid_scroll)
        return True

    # -- eventos -----------------------------------------------------------------

    def on_mouse_motion(self, x: int, y: int, dx: int, dy: int) -> None:
        x, y = self._logical_pointer(x, y)
        self._hover = next(
            (key for key in ("abort", "prev", "next")
             if _inside(x, y, self._rects()[key])),
            None,
        )

    def on_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float) -> None:
        """Roda do mouse sobre a caixa do grid rola uma linha por passo."""

        x, y = self._logical_pointer(x, y)
        if not self._grid or not _inside(x, y, self._rects()["grid"]):
            return
        step = -1 if scroll_y > 0 else 1 if scroll_y < 0 else 0
        self._grid_scroll = min(max(self._grid_scroll + step, 0), self._max_grid_scroll())

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        x, y = self._logical_pointer(x, y)
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        if self._start_grid_drag(x, y):
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

    def on_mouse_drag(self, x: int, y: int, dx: int, dy: int, buttons: int, modifiers: int) -> None:
        if self._grid_drag is None:
            return
        _x, y = self._logical_pointer(x, y)
        rect = self._rects()["grid"]
        layout = self._grid_bar_layout(rect, self._grid_top(rect), self._visible_rows())
        if layout is None or layout[3] <= 0:
            return
        travel, max_scroll = layout[3], layout[4]
        start, start_scroll = self._grid_drag
        # Arrastar o cursor para baixo (y decrescendo) rola o grid para baixo.
        self._grid_scroll = round(start_scroll - (y - start) * max_scroll / travel)
        self._grid_scroll = min(max(0, self._grid_scroll), self._max_grid_scroll())

    def on_mouse_release(self, x: int, y: int, button: int, modifiers: int) -> None:
        self._grid_drag = None

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol == arcade.key.LEFT:
            self._step_race(-1)
        elif symbol == arcade.key.RIGHT:
            self._step_race(1)

    def _step_race(self, step: int) -> None:
        self._race_index = next_index(self._race_index, step, len(self._plan.races))

    # -- textos ------------------------------------------------------------------
    #
    # Formas usam a camera de design. Textos sao rasterizados pela camera padrao
    # da janela (escalar glifos pela camera de design os deixaria borrados). Por
    # isso a posicao e o tamanho dos textos ficam em unidades de design, e
    # _draw_label os converte na hora de desenhar. Mesmo padrao de grid_view.py.

    def _text(
        self,
        key: str,
        value: str,
        color,
        size: float = 12,
        *,
        width: float | None = None,
        **style,
    ) -> arcade.Text:
        """Texto reutilizado entre quadros, sem posicao: ela vem em _draw_label.

        ``size`` e o tamanho de design. ``width`` e a largura de quebra de linha
        em unidades de design; sem ela o texto nao quebra.
        """

        text = self._texts.get(key)
        if text is None:
            # pyglet exige largura para texto multilinha, mesmo na criacao. A largura
            # de design vale aqui; _apply_label_size a converte para a janela depois.
            if width is not None:
                style.setdefault("width", int(width))
            text = arcade.Text(value, 0, 0, color, size, **style)
            self._texts[key] = text
        if text.text != value:
            text.text = value
        if text.color != color:
            text.color = color
        self._label_sizes[text] = size
        if width is not None:
            self._label_widths[text] = width
        return text

    def _draw_text(
        self,
        key: str,
        value: str,
        x: float,
        y: float,
        color,
        size: float = 12,
        *,
        width: float | None = None,
        **style,
    ) -> None:
        """Desenha um texto em (x, y) de design, sem precisar guardar o objeto."""

        text = self._text(key, value, color, size, width=width, **style)
        self._draw_label(text, x, y)

    def _apply_label_size(self, text: arcade.Text) -> None:
        """Aplica ao texto o tamanho de design na escala atual da janela.

        A largura de quebra tambem e convertida, pois pyglet a mede em pixels.
        Fonte e largura so sao trocadas quando mudam, porque cada troca refaz o
        layout do texto.
        """

        fit = self._canvas_fit()
        target = self._label_sizes[text] * fit.scale
        if abs(text.font_size - target) > 1e-6:
            text.font_size = target
        wrap = self._label_widths.get(text)
        if wrap is not None:
            target_width = int(wrap * fit.scale)
            if text.width is None or abs(text.width - target_width) > 1e-6:
                text.width = target_width

    def _draw_label(self, text: arcade.Text, x: float, y: float) -> None:
        """Desenha ``text`` em (x, y) de design, rasterizado na escala da janela.

        Um texto desenhado pela camera escalada sairia borrado, entao a posicao
        e o tamanho viram unidades da janela e o desenho usa a camera padrao. Ao
        sair dela, a camera de design e restaurada. As ancoragens do texto
        (anchor_x/anchor_y) continuam valendo.
        """

        self._apply_label_size(text)
        text.x, text.y = self._canvas_fit().to_window(x, y)
        # Ativar uma camera zera a tesoura (scissor) do Arcade. Por isso a tesoura
        # atual e guardada antes e reaplicada dentro da ativacao, e depois restaurada.
        clip = self.window.ctx.scissor
        with self.window.default_camera.activate():
            self.window.ctx.scissor = clip
            text.draw()
        # Sair do bloco restaura a camera do canvas, que tambem zera a tesoura.
        self.window.ctx.scissor = clip

    # -- desenho -----------------------------------------------------------------

    def on_draw(self) -> None:
        self.clear()
        width, height = DESIGN_WIDTH, DESIGN_HEIGHT
        rects = self._rects()
        title = (
            "Simulando o torneio" if len(self._plan.races) > 1 else "Simulando a corrida"
        )
        # Formas ficam na camera de design; os textos saem por _draw_label, que
        # volta para a camera padrao da janela e depois restaura a de design.
        with self._canvas_camera().activate():
            self._draw_text(
                "title", title, 40, height - 60, PRIMARY_TEXT_COLOR, 26, bold=True
            )
            self._draw_text(
                "subtitle", self._plan.rules.name, 40, height - 90, SECONDARY_TEXT_COLOR, 12
            )
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
            self._draw_text(
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
            )
            return
        arcade.draw_line_strip(geometry.track_points, (29, 33, 39), 12)
        arcade.draw_line_strip(geometry.track_points, (223, 226, 231), 9)
        arcade.draw_line_strip(geometry.track_points, (96, 102, 110), 6)
        arcade.draw_line_strip(geometry.pit_lane_points, (249, 184, 66), 3)
        arcade.draw_circle_filled(*geometry.service_point, 5, (255, 176, 0))
        length = f"{geometry.lap_length_m / 1000:.3f}".replace(".", ",")
        self._draw_text(
            "preview-length",
            f"Comprimento da volta: {length} km",
            x,
            bottom + h + 6,
            PRIMARY_TEXT_COLOR,
            11,
        )

    def _panel(self, rect, title: str, key: str, fill=None) -> None:
        left, bottom, w, h = rect
        _rounded(left, bottom, w, h, PANEL_COLOR if fill is None else fill, PANEL_BORDER_COLOR, radius=8)
        self._draw_text(
            key, title, left + 20, bottom + h - 30, _HEADER_COLOR, 11, bold=True
        )

    def _draw_grid(self, rect) -> None:
        left, _bottom, _w, _h = rect
        # Teste visual: fundo preto na caixa do grid, para ver se o contraste melhora.
        self._panel(rect, "GRID DE LARGADA", "grid-title", fill=(0, 0, 0))
        top = self._grid_top(rect)
        if not self._grid_loaded:
            message = "Carregando o grid…"
        elif not self._grid:
            message = "Sem grid no backend: ele sera montado ao iniciar."
        else:
            message = None
        if message is not None:
            self._draw_text("grid-message", message, left + 20, top, SECONDARY_TEXT_COLOR, 12)
            return
        visible = self._visible_rows()
        self._grid_scroll = min(self._grid_scroll, self._max_grid_scroll())
        start = self._grid_scroll
        for offset, entry in enumerate(self._grid[start : start + visible]):
            index = start + offset
            y = top - offset * _ROW_HEIGHT
            self._draw_text(f"grid-p:{index}", str(index + 1), left + 20, y, PRIMARY_TEXT_COLOR, 10)
            self._draw_text(
                f"grid-n:{index}",
                str(entry.get("driver_name", ""))[:24],
                left + 60,
                y,
                (255, 255, 255),
                12,
            )
            self._draw_text(
                f"grid-t:{index}",
                str(entry.get("team_name", ""))[:22],
                left + 300,
                y,
                (255, 255, 255),
                10,
            )
        self._draw_grid_scrollbar(rect, top, visible)

    def _draw_grid_scrollbar(self, rect, top: float, visible: int) -> None:
        """Trilho e cursor a direita da caixa; so aparece se houver pilotos ocultos."""

        layout = self._grid_bar_layout(rect, top, visible)
        if layout is None:
            return
        track_top, track_bottom, thumb_h, travel, max_scroll = layout
        left, _bottom, width, _height = rect
        track_x = left + width - 12
        arcade.draw_lbwh_rectangle_filled(
            track_x, track_bottom, 4, track_top - track_bottom, _SCROLLBAR_COLOR
        )
        thumb_top = track_top - travel * self._grid_scroll / max_scroll
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
        )
        for index, (text, size, bold) in enumerate(lines):
            self._draw_text(
                f"race-line:{index}",
                text,
                left + 20,
                top - index * 28,
                PRIMARY_TEXT_COLOR,
                size,
                bold=bold,
            )
        # Abaixo do resumo (3 linhas, a ultima na base top-56): prévia da pista a
        # esquerda e clima a direita. Sem a linha "Largada", a prévia sobe.
        body_top = top - 96
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

        self._draw_text("weather-title", "Clima por volta", x, top, SECONDARY_TEXT_COLOR, 11)
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
        self._draw_text(
            "weather-summary",
            schedule.compact_summary(),
            x + bar_w + 14,
            bar_top,
            SECONDARY_TEXT_COLOR,
            10,
            width=column_w - bar_w - 14,
            multiline=True,
        )

    def _draw_stepper(self, rect) -> None:
        rects = self._rects()
        count = len(self._plan.races)
        self._draw_text(
            "stepper-count",
            f"{self._race_index + 1} / {count}",
            rect[0] + rect[2] - 170,
            rect[1] + rect[3] - 29,
            SECONDARY_TEXT_COLOR,
            11,
            anchor_y="center",
        )
        for key, symbol in (("prev", "‹"), ("next", "›")):
            left, bottom, w, h = rects[key]
            hover = self._hover == key
            _rounded(
                left, bottom, w, h, _BUTTON_HOVER if hover else _BUTTON_BG, radius=6
            )
            self._draw_text(
                f"stepper-{key}",
                symbol,
                left + w / 2,
                bottom + h / 2,
                PRIMARY_TEXT_COLOR,
                16,
                anchor_x="center",
                anchor_y="center",
            )

    def _draw_status(self, width: float, rects) -> None:
        status_color = ERROR_COLOR if self._error is not None else PRIMARY_TEXT_COLOR
        self._draw_text(
            "status",
            progress_text(self._progress),
            40,
            90,
            status_color,
            14,
            width=width - 340,
            multiline=True,
        )
        left, bottom, w, h = rects["abort"]
        hover = self._hover == "abort"
        background = (
            _PRIMARY_HOVER if hover else _PRIMARY_BG
        ) if self._error is None else (_BUTTON_HOVER if hover else _BUTTON_BG)
        _rounded(left, bottom, w, h, background, radius=6)
        label = (
            "Abortar simulação" if self._error is None else "Voltar à configuração"
        )
        self._draw_text(
            "abort-label",
            label,
            left + w / 2,
            bottom + h / 2,
            PRIMARY_TEXT_COLOR,
            13,
            bold=True,
            anchor_x="center",
            anchor_y="center",
        )


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

    draw_rounded_panel(left, bottom, width, height, radius, fill, border)


def _inside(x: float, y: float, rect) -> bool:
    left, bottom, width, height = rect
    return left <= x <= left + width and bottom <= y <= bottom + height
