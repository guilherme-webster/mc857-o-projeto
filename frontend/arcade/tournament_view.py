"""Tela Arcade com os resultados de um torneio simulado.

Uma barra no topo percorre o carrossel: o resultado geral do torneio e, depois,
cada etapa (setas ‹ e ›). A tabela mostra o resultado da selecao atual, com
rolagem para 20 pilotos por vez.

A classificacao geral vem do backend (``POST /championship/standings``) numa
thread. Os pontos de cada etapa usam a mesma tabela F1 do backend
(``F1_POINTS`` em ``src/f1_simulator/domain/championship.py``), aplicada a
posicao da etapa; abandonos pontuam zero. As posicoes ganhas comparam a
largada (``starting_grid`` da corrida) com a chegada da etapa.
"""

from __future__ import annotations

from collections.abc import Callable
from queue import Empty, SimpleQueue
from threading import Thread

import arcade

from frontend.arcade.button_text import fit_button_text
from frontend.arcade.saved_tournaments import save_request
from frontend.arcade.theme import (
    BACKGROUND_COLOR,
    ERROR_COLOR,
    PRIMARY_TEXT_COLOR,
    SECONDARY_TEXT_COLOR,
    SUCCESS_COLOR,
)
from frontend.arcade.tournament_session import (
    StandingLine,
    TournamentSession,
    parse_standings,
)
from frontend.arcade.track_client import fetch_championship_standings, save_tournament

_HEADER_COLOR = (130, 140, 150)
_GOLD = (245, 197, 66)
_SILVER = (200, 205, 215)
_BRONZE = (205, 127, 50)
_RETIRED_COLOR = (255, 112, 112)
_GAINED_COLOR = (70, 211, 142)
_LOST_COLOR = (255, 112, 112)
_BUTTON_BG = (46, 62, 80)
_BUTTON_HOVER = (70, 90, 115)
_PRIMARY_BG = (190, 30, 45)
_PRIMARY_HOVER = (225, 45, 60)
_NAV_BG = (30, 42, 56)
_SCROLL_TRACK = (33, 42, 53)
# Mesma tabela de pontos do campeonato no backend.
F1_POINTS = (25, 18, 15, 12, 10, 8, 6, 4, 2, 1)
ROW_HEIGHT = 24
# Pilotos visiveis de uma vez; o restante aparece rolando a tabela.
MAX_VISIBLE_ROWS = 20
# Distancia do topo da janela ao cabecalho da tabela, e a margem inferior em que
# as linhas param (acima dos botoes e da dica de rolagem).
_HEADER_FROM_TOP = 118
_TABLE_BOTTOM = 110
# Largura da tabela, centralizada na janela.
_TABLE_W = 560

# Colunas: (cabecalho, x a partir da esquerda da tabela, ancora).
_STAGE_COLUMNS = (
    ("P", 40, "right"),
    ("PILOTO", 56, "left"),
    ("EQUIPE", 210, "left"),
    ("PTS", 380, "right"),
    ("GANHO", 440, "right"),
    ("PARADAS", 520, "right"),
)
_OVERALL_COLUMNS = (
    ("P", 40, "right"),
    ("PILOTO", 56, "left"),
    ("EQUIPE", 210, "left"),
    ("PTS", 380, "right"),
    ("V", 440, "right"),
    ("PÓD", 480, "right"),
    ("MÉD", 540, "right"),
)

_ACTION_LABELS = {
    "back": "Voltar",
    "save": "Salvar Torneio",
    "saved": "Simulações Salvas",
    "home": "Tela inicial",
}
_ACTION_W = 200
_ACTION_MARGIN = 40


class TournamentResultView(arcade.View):
    """Resultado de um torneio: o geral e cada etapa, num carrossel."""

    def __init__(
        self,
        tournament: TournamentSession,
        return_view: arcade.View | None = None,
        standings_loader: Callable[[dict], dict] = fetch_championship_standings,
        tournament_saver: Callable[[dict], dict] = save_tournament,
        saveable: bool = True,
    ) -> None:
        """``saveable=False`` tira o botao "Salvar Torneio": torneio aberto ou
        reexecutado a partir das simulacoes salvas ja esta salvo."""

        super().__init__()
        self._tournament = tournament
        self._tournament_saver = tournament_saver
        self._saveable = saveable
        self._saving = False
        self._return_view = return_view
        self._names = tournament.driver_names()
        self._teams = tournament.driver_teams()
        self._rows: list[StandingLine] = []
        # (texto, linha, deslocamento em x); linha -1 e o cabecalho.
        self._cells: list[tuple[arcade.Text, int, float]] = []
        # Carrossel: 0 e o resultado geral; s (1..N) e a etapa s.
        self._selection = 0
        self._scroll = 0
        self._hover: str | None = None
        self._results: SimpleQueue[tuple[str, object]] = SimpleQueue()
        self._save_status = arcade.Text("", 40, 88, SECONDARY_TEXT_COLOR, 12)
        self._scroll_hint = arcade.Text("", 40, 64, SECONDARY_TEXT_COLOR, 10)
        self._message = arcade.Text(
            "Calculando a classificação do campeonato…",
            40,
            0,
            SECONDARY_TEXT_COLOR,
            14,
        )
        self._nav_text = arcade.Text(
            "", 0, 0, PRIMARY_TEXT_COLOR, 14, bold=True, anchor_x="center", anchor_y="center"
        )
        self._button_texts = {
            key: arcade.Text(
                label,
                0,
                0,
                PRIMARY_TEXT_COLOR,
                13,
                bold=key == "home",
                anchor_x="center",
                anchor_y="center",
            )
            for key, label in _ACTION_LABELS.items()
        }
        # Textos da barra de navegacao, reaproveitados entre quadros.
        self._texts: dict[str, arcade.Text] = {}
        request = tournament.standings_request()

        def load() -> None:
            try:
                payload = standings_loader(request)
                rows = parse_standings(payload, tournament.total_stages)
            except (RuntimeError, OSError, ValueError) as error:
                # BackendError e RuntimeError; URLError e OSError.
                self._results.put(("error", str(error)))
            else:
                self._results.put(("success", rows))

        Thread(target=load, name="championship-standings", daemon=True).start()

    # -- dados ----------------------------------------------------------------

    def _is_overall(self) -> bool:
        return self._selection == 0

    def _points_for(self, position: int | None, retired: bool) -> int:
        if retired or position is None or not self._tournament.scored:
            return 0
        if position > len(F1_POINTS):
            return 0
        return F1_POINTS[position - 1]

    def _stage_entries(self, selection: int) -> list[dict]:
        """Classificacao da etapa ``selection`` (1-based): chegada, depois abandonos."""

        race = self._tournament.stage(selection).race
        starts = {
            str(row["driver_id"]): int(row["position"])
            for row in race.get("starting_grid", [])
            if row.get("position") is not None
        }
        # Paradas da corrida: cada carro da classificacao traz ``stops_made``.
        stops = {
            str(car["driver_id"]): int(car.get("stops_made") or 0)
            for car in race.get("classification", [])
        }
        index = selection - 1
        entries = []
        for line in self._rows:
            position = line.stage_positions[index]
            if position is None:
                continue
            retired = line.stage_retired[index]
            start = starts.get(line.driver_id)
            entries.append(
                {
                    "driver_id": line.driver_id,
                    "position": position,
                    "retired": retired,
                    "points": self._points_for(position, retired),
                    "gain": _gain_text(start, position, retired),
                    "stops": stops.get(line.driver_id, 0),
                }
            )
        entries.sort(key=lambda entry: (entry["retired"], entry["position"]))
        return entries

    def _overall_entries(self) -> list[dict]:
        return [
            {
                "driver_id": line.driver_id,
                "position": line.position,
                "retired": False,
                "points": line.points,
                "wins": line.wins,
                "podiums": line.podiums,
                "average": line.average_position,
            }
            for line in self._rows
        ]

    def _entries(self) -> list[dict]:
        if self._is_overall():
            return self._overall_entries()
        return self._stage_entries(self._selection)

    def _build_cells(self) -> list[tuple[arcade.Text, int, float]]:
        """Textos da tabela para a selecao atual; ``row`` -1 e o cabecalho."""

        overall = self._is_overall()
        columns = list(_OVERALL_COLUMNS if overall else _STAGE_COLUMNS)
        if not self._tournament.scored:
            columns = [column for column in columns if column[0] != "PTS"]
        entries = self._entries()
        cells = [
            (
                arcade.Text(label, 0, 0, _HEADER_COLOR, 10, bold=True, anchor_x=anchor),
                -1,
                x,
            )
            for label, x, anchor in columns
        ]
        for index, entry in enumerate(entries):
            position = entry["position"]
            color = (
                {1: _GOLD, 2: _SILVER, 3: _BRONZE}.get(position, PRIMARY_TEXT_COLOR)
                if not entry["retired"]
                else _RETIRED_COLOR
            )
            gain = entry.get("gain", "")
            values = {
                "P": "Ab" if entry["retired"] else str(position),
                "PILOTO": self._names.get(entry["driver_id"], entry["driver_id"])[:20],
                "EQUIPE": self._teams.get(entry["driver_id"], "—")[:20],
                "PTS": str(entry["points"]),
                "V": str(entry.get("wins", 0)),
                "PÓD": str(entry.get("podiums", 0)),
                "GANHO": gain,
                # Media das posicoes nas etapas disputadas (criterio de desempate).
                "MÉD": f"{entry['average']:.1f}" if "average" in entry else "",
                "PARADAS": str(entry.get("stops", 0)),
            }
            for label, x, anchor in columns:
                value = values[label]
                if label == "EQUIPE":
                    cell_color, bold = SECONDARY_TEXT_COLOR, False
                elif label == "GANHO":
                    cell_color = _GAINED_COLOR if gain.startswith("+") else (
                        _LOST_COLOR if gain.startswith("-") and gain != "-" else PRIMARY_TEXT_COLOR
                    )
                    bold = False
                elif label in ("P", "PTS"):
                    cell_color, bold = color, label == "PTS"
                else:
                    cell_color, bold = PRIMARY_TEXT_COLOR, False
                text = arcade.Text(
                    value, 0, 0, cell_color, 13, bold=bold, anchor_x=anchor
                )
                cells.append((text, index, x))
        return cells

    def _rebuild(self) -> None:
        self._cells = self._build_cells()

    # -- selecao e navegacao ------------------------------------------------

    def _select(self, selection: int) -> None:
        if selection == self._selection:
            return
        self._selection = selection
        self._scroll = 0
        self._rebuild()

    def _previous(self) -> None:
        """Carrossel ciclico: a partir do resultado geral, vai para a ultima etapa."""

        total = self._tournament.total_stages
        self._select(total if self._selection == 0 else self._selection - 1)

    def _next(self) -> None:
        """Carrossel ciclico: depois da ultima etapa, volta ao resultado geral."""

        total = self._tournament.total_stages
        self._select(0 if self._selection == total else self._selection + 1)

    def _can_move(self, key: str) -> bool:
        # Ciclico: as setas estao sempre habilitadas.
        return True

    def _selection_label(self) -> str:
        if self._is_overall():
            return f"Resultado do torneio - {self._tournament.rules.name}"
        return self._tournament.stage_title(self._selection)

    # -- eventos do carregamento ---------------------------------------------

    def on_show_view(self) -> None:
        arcade.set_background_color(BACKGROUND_COLOR)

    def on_update(self, delta_time: float) -> None:
        """Receba a tabela do backend e o resultado do salvamento na thread do Arcade."""

        try:
            outcome, payload = self._results.get_nowait()
        except Empty:
            return
        if outcome in ("saved", "save_error"):
            self._saving = False
            if outcome == "saved":
                self._save_status.text = (
                    f"Torneio salvo como “{payload['name']}” ({payload['id']}). "
                    "Abra em “Simulações Salvas” para rever ou reexecutar."
                )
                self._save_status.color = SUCCESS_COLOR
            else:
                self._save_status.text = f"Não foi possível salvar: {payload}"
                self._save_status.color = ERROR_COLOR
            return
        if outcome == "error":
            self._message.text = f"Não foi possível calcular o campeonato: {payload}"
            self._message.color = _RETIRED_COLOR
            return
        self._rows = payload
        self._rebuild()

    def save(self) -> None:
        """Salve o torneio no backend numa thread; o aviso aparece na tela.

        O backend congela o grid atual junto das corridas; se ele mudou depois
        da simulacao, o pedido volta com 409 e a mensagem explica o motivo.
        """

        if self._saving:
            return
        self._saving = True
        self._save_status.text = "Salvando o torneio…"
        self._save_status.color = SECONDARY_TEXT_COLOR
        request = save_request(self._tournament)
        results = self._results

        def run() -> None:
            try:
                meta = self._tournament_saver(request)
            except (RuntimeError, OSError, ValueError) as error:
                results.put(("save_error", str(error)))
            else:
                results.put(("saved", meta))

        Thread(target=run, name="save-tournament", daemon=True).start()

    # -- geometria --------------------------------------------------------------

    def _table_left(self) -> float:
        return (self.window.width - _TABLE_W) / 2

    def _visible_rows(self, height: float) -> int:
        """Linhas de piloto entre o cabecalho e a margem inferior, ate 20."""

        first_row_y = height - _HEADER_FROM_TOP - 30
        fits = int((first_row_y - _TABLE_BOTTOM) // ROW_HEIGHT) + 1
        return max(1, min(MAX_VISIBLE_ROWS, fits))

    def _max_scroll(self, visible: int) -> int:
        return max(0, len(self._entries()) - visible)

    def _nav_rects(self) -> dict[str, tuple[float, float, float, float]]:
        width, height = self.window.width, self.window.height
        bar_y, bar_h = height - 76, 36
        return {
            "prev": (40, bar_y, 40, bar_h),
            "next": (width - 40 - 40, bar_y, 40, bar_h),
        }

    def _name_area(self) -> tuple[float, float]:
        """(esquerda, largura) do texto central da barra de navegacao."""

        rects = self._nav_rects()
        left = rects["prev"][0] + rects["prev"][2] + 8
        right = rects["next"][0] - 8
        return left, right - left

    def _action_keys(self) -> list[str]:
        keys = []
        if self._return_view is not None:
            keys.append("back")
        if self._saveable:
            keys.append("save")
        keys += ["saved", "home"]
        return keys

    def _action_rects(self) -> dict[str, tuple[float, float, float, float]]:
        """Voltar na borda esquerda, Tela inicial na borda direita; o meio espaçado."""

        keys = self._action_keys()
        width = self.window.width
        first = _ACTION_MARGIN
        last = width - _ACTION_MARGIN - _ACTION_W
        if len(keys) == 1:
            positions = [(width - _ACTION_W) / 2]
        else:
            step = (last - first) / (len(keys) - 1)
            positions = [first + i * step for i in range(len(keys))]
        return {
            key: (left, 24, _ACTION_W, 36)
            for key, left in zip(keys, positions, strict=True)
        }

    def _button_rects(self) -> dict[str, tuple[float, float, float, float]]:
        """Botoes de acao da base da tela (nome mantido para os testes de GUI)."""

        return self._action_rects()

    # -- mouse e teclado ----------------------------------------------------------

    def on_mouse_motion(self, x, y, dx, dy) -> None:
        rects = {**self._nav_rects(), **self._action_rects()}
        self._hover = next(
            (key for key, rect in rects.items() if _inside(x, y, rect)), None
        )

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y) -> None:
        """A roda do mouse rola a tabela uma linha por passo."""

        height = self.window.height
        if not (_TABLE_BOTTOM <= y <= height - _HEADER_FROM_TOP):
            return
        visible = self._visible_rows(height)
        self._scroll = min(max(self._scroll - int(scroll_y), 0), self._max_scroll(visible))

    def on_mouse_press(self, x, y, button, modifiers) -> None:
        for key, rect in self._nav_rects().items():
            if not _inside(x, y, rect):
                continue
            if key == "prev":
                self._previous()
            else:
                self._next()
            return
        for key, rect in self._action_rects().items():
            if not _inside(x, y, rect):
                continue
            if key == "back":
                self.window.show_view(self._return_view)
            elif key == "save":
                self.save()
            elif key == "saved":
                from frontend.arcade.saved_tournaments_view import (
                    SavedTournamentsView,
                )

                self.window.show_view(SavedTournamentsView(return_view=self))
            else:
                from frontend.arcade.parameters_view import (
                    ParametersView,
                    backend_simulation_runner,
                )

                self.window.show_view(
                    ParametersView(simulation_runner=backend_simulation_runner)
                )
            return

    # -- desenho ------------------------------------------------------------------

    def on_draw(self) -> None:
        self.clear()
        width, height = self.window.width, self.window.height
        self._draw_navigation(width, height)

        header_y = height - _HEADER_FROM_TOP
        if not self._rows:
            self._message.x = self._table_left()
            self._message.y = header_y - 30
            self._message.draw()
        visible = self._visible_rows(height)
        self._scroll = min(self._scroll, self._max_scroll(visible))
        table_left = self._table_left()
        for text, row, dx in self._cells:
            if row < 0:
                y = header_y
            elif self._scroll <= row < self._scroll + visible:
                y = header_y - (30 + (row - self._scroll) * ROW_HEIGHT)
            else:
                continue
            text.x = table_left + dx
            text.y = y
            text.draw()
        total = len(self._entries())
        if total > visible:
            first = self._scroll + 1
            last = min(total, self._scroll + visible)
            self._scroll_hint.text = (
                f"Pilotos {first}–{last} de {total} · role a tabela para ver os demais"
            )
            self._scroll_hint.draw()
            self._draw_scrollbar(header_y, visible, total)

        if self._save_status.text:
            self._save_status.draw()
        self._draw_actions()

    def _draw_navigation(self, width: int, height: int) -> None:
        rects = self._nav_rects()
        for key, symbol in (("prev", "‹"), ("next", "›")):
            left, bottom, w, h = rects[key]
            enabled = self._can_move(key)
            fill = (_BUTTON_HOVER if self._hover == key else _BUTTON_BG) if enabled else _NAV_BG
            arcade.draw_lbwh_rectangle_filled(left, bottom, w, h, fill)
            self._text_in(
                f"nav:{key}", symbol, left, bottom, w, h,
                PRIMARY_TEXT_COLOR if enabled else _HEADER_COLOR, 18,
            )
        name_left, name_w = self._name_area()
        label = self._nav_text
        label.text = self._selection_label()
        label.color = PRIMARY_TEXT_COLOR
        label.font_size = 14
        fit_button_text(label, name_w - 16, 14)
        label.x = name_left + name_w / 2
        label.y = rects["prev"][1] + rects["prev"][3] / 2
        label.draw()

    def _text_in(self, key, value, left, bottom, w, h, color, size, bold=False) -> None:
        """Texto centralizado num botao; reaproveitado entre quadros por ``key``."""

        text = self._texts.get(key)
        if text is None:
            text = arcade.Text(
                value, 0, 0, color, size, bold=bold, anchor_x="center", anchor_y="center"
            )
            self._texts[key] = text
        text.text = value
        text.color = color
        text.bold = bold
        text.font_size = size
        text.x, text.y = left + w / 2, bottom + h / 2
        fit_button_text(text, w - 12, size)
        text.draw()

    def _draw_actions(self) -> None:
        for key, rect in self._action_rects().items():
            left, bottom, w, h = rect
            hover = self._hover == key
            if key == "home":
                background = _PRIMARY_HOVER if hover else _PRIMARY_BG
            else:
                background = _BUTTON_HOVER if hover else _BUTTON_BG
            arcade.draw_lbwh_rectangle_filled(left, bottom, w, h, background)
            text = self._button_texts[key]
            text.text = _ACTION_LABELS[key]
            text.font_size = 13
            fit_button_text(text, w - 12, 13)
            text.x, text.y = left + w / 2, bottom + h / 2
            text.draw()

    def _draw_scrollbar(self, header_y: float, visible: int, total: int) -> None:
        """Trilho e cursor a direita da tabela; o cursor acompanha ``self._scroll``."""

        track_x = self.window.width - 26
        track_top = header_y - 30 + 12
        track_bottom = _TABLE_BOTTOM
        track_h = track_top - track_bottom
        arcade.draw_lbwh_rectangle_filled(track_x, track_bottom, 4, track_h, _SCROLL_TRACK)
        thumb_h = max(track_h * visible / total, 24)
        thumb_top = track_top - (track_h - thumb_h) * self._scroll / (total - visible)
        arcade.draw_lbwh_rectangle_filled(
            track_x, thumb_top - thumb_h, 4, thumb_h, _HEADER_COLOR
        )


def _gain_text(start: int | None, finish: int, retired: bool) -> str:
    """Posicoes ganhas na etapa: "+2", "-2" ou "-" (sem mudanca); vazio sem dado."""

    if retired or start is None:
        return ""
    delta = start - finish
    if delta > 0:
        return f"+{delta}"
    if delta < 0:
        return str(delta)
    return "="


def _inside(x: float, y: float, rect: tuple[float, float, float, float]) -> bool:
    left, bottom, width, height = rect
    return left <= x <= left + width and bottom <= y <= bottom + height
