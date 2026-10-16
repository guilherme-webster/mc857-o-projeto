"""Tela Arcade com a classificacao final de um torneio simulado.

So desenha: a tabela e calculada pelo backend (``POST
/championship/standings``) numa thread, e a view mostra "calculando" ou o erro
ate a resposta chegar.
"""

from __future__ import annotations

from collections.abc import Callable
from queue import Empty, SimpleQueue
from threading import Thread

import arcade

from frontend.arcade.theme import (
    BACKGROUND_COLOR,
    PRIMARY_TEXT_COLOR,
    SECONDARY_TEXT_COLOR,
)
from frontend.arcade.track_client import fetch_championship_standings
from frontend.arcade.tournament_session import (
    StandingLine,
    TournamentSession,
    parse_standings,
)

_HEADER_COLOR = (130, 140, 150)
_GOLD = (245, 197, 66)
_SILVER = (200, 205, 215)
_BRONZE = (205, 127, 50)
_RETIRED_COLOR = (255, 112, 112)
_BUTTON_BG = (46, 62, 80)
_BUTTON_HOVER = (70, 90, 115)
_PRIMARY_BG = (190, 30, 45)
_PRIMARY_HOVER = (225, 45, 60)
# Acima disso as colunas por etapa nao cabem; a tabela mostra as ultimas.
MAX_STAGE_COLUMNS = 12
ROW_HEIGHT = 24


class TournamentResultView(arcade.View):
    """Campeonato apos a ultima etapa, com a posicao em cada corrida."""

    def __init__(
        self,
        tournament: TournamentSession,
        return_view: arcade.View | None = None,
        standings_loader: Callable[[dict], dict] = fetch_championship_standings,
    ) -> None:
        super().__init__()
        self._tournament = tournament
        self._return_view = return_view
        self._rows: list[StandingLine] = []
        self._names = tournament.driver_names()
        self._cells: list[tuple[arcade.Text, int]] = []
        self._results: SimpleQueue[tuple[str, object]] = SimpleQueue()
        self._message = arcade.Text(
            "Calculando a classificação do campeonato…",
            40,
            0,
            SECONDARY_TEXT_COLOR,
            14,
        )
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
        self._hover: str | None = None
        self._buttons = {
            "back": "Voltar à última etapa",
            "saved": "Corridas salvas",
            "new": "Nova simulação",
        }
        self._title = arcade.Text(
            tournament.rules.name, 40, 0, PRIMARY_TEXT_COLOR, 24, bold=True
        )
        scoring = (
            "pontuação F1 (25-18-15-12-10-8-6-4-2-1, sem ponto de volta rápida)"
            if tournament.scored
            else "sem pontuação"
        )
        self._subtitle = arcade.Text(
            f"Resultado final · {tournament.total_stages} etapa(s) · {scoring} · "
            f"desempate: {tournament.rules.tiebreak.lower()}",
            40,
            0,
            SECONDARY_TEXT_COLOR,
            12,
        )
        self._button_texts = {
            key: arcade.Text(
                label,
                0,
                0,
                PRIMARY_TEXT_COLOR,
                13,
                bold=key == "new",
                anchor_x="center",
                anchor_y="center",
            )
            for key, label in self._buttons.items()
        }

    def _build_cells(self) -> list[tuple[arcade.Text, int]]:
        stages = self._tournament.total_stages
        first_stage = max(1, stages - MAX_STAGE_COLUMNS + 1)
        columns = [
            ("P", 60, "right"),
            ("PILOTO", 76, "left"),
            ("PTS", 330, "right"),
            ("V", 370, "right"),
            ("PÓD", 415, "right"),
            ("MÉD", 470, "right"),
        ]
        if not self._tournament.scored:
            columns = [column for column in columns if column[0] != "PTS"]
        stage_x = 520
        for stage in range(first_stage, stages + 1):
            columns.append((f"E{stage}", stage_x, "right"))
            stage_x += 46

        cells = [
            (arcade.Text(label, x, 0, _HEADER_COLOR, 10, bold=True, anchor_x=anchor), 0)
            for label, x, anchor in columns
        ]
        for i, row in enumerate(self._rows):
            offset = 30 + i * ROW_HEIGHT
            color = {1: _GOLD, 2: _SILVER, 3: _BRONZE}.get(
                row.position, PRIMARY_TEXT_COLOR
            )
            values = {
                "P": str(row.position),
                "PILOTO": self._names.get(row.driver_id, row.driver_id)[:26],
                "PTS": str(row.points),
                "V": str(row.wins),
                "PÓD": str(row.podiums),
                "MÉD": f"{row.average_position:.1f}",
            }
            for label, x, anchor in columns:
                if label in values:
                    value, cell_color, bold = values[label], color, label == "PTS"
                else:
                    index = int(label[1:]) - 1
                    position = row.stage_positions[index]
                    retired = row.stage_retired[index]
                    value = (
                        "-"
                        if position is None
                        else ("Ab" if retired else str(position))
                    )
                    cell_color = _RETIRED_COLOR if retired else SECONDARY_TEXT_COLOR
                    bold = False
                text = arcade.Text(
                    value, x, 0, cell_color, 13, bold=bold, anchor_x=anchor
                )
                cells.append((text, offset))
        return cells

    def on_show_view(self) -> None:
        arcade.set_background_color(BACKGROUND_COLOR)

    def on_update(self, delta_time: float) -> None:
        """Receba a tabela do backend na thread do Arcade."""

        try:
            outcome, payload = self._results.get_nowait()
        except Empty:
            return
        if outcome == "error":
            self._message.text = f"Não foi possível calcular o campeonato: {payload}"
            self._message.color = _RETIRED_COLOR
            return
        self._rows = payload
        # A tabela nao muda: os textos sao montados uma vez, com o deslocamento
        # vertical a partir do topo, e cada quadro so os reposiciona.
        self._cells = self._build_cells()

    def _button_rects(self) -> dict[str, tuple[int, int, int, int]]:
        width, height, gap = 210, 36, 12
        right = self.window.width - 40
        rects = {}
        for key in ("new", "saved", "back"):
            if key == "back" and self._return_view is None:
                continue
            rects[key] = (right - width, 24, width, height)
            right -= width + gap
        return rects

    def on_mouse_motion(self, x, y, dx, dy) -> None:
        self._hover = next(
            (key for key, rect in self._button_rects().items() if _inside(x, y, rect)),
            None,
        )

    def on_mouse_press(self, x, y, button, modifiers) -> None:
        for key, rect in self._button_rects().items():
            if not _inside(x, y, rect):
                continue
            if key == "back":
                self.window.show_view(self._return_view)
            elif key == "saved":
                from frontend.arcade.track_view import MenuView

                self.window.show_view(MenuView())
            else:
                from frontend.arcade.parameters_view import (
                    ParametersView,
                    backend_simulation_runner,
                )

                self.window.show_view(
                    ParametersView(simulation_runner=backend_simulation_runner)
                )
            return

    def on_draw(self) -> None:
        self.clear()
        height = self.window.height
        self._title.y = height - 60
        self._title.draw()
        self._subtitle.y = height - 88
        self._subtitle.draw()

        header_y = height - 130
        if not self._cells:
            self._message.y = header_y
            self._message.draw()
        for text, offset in self._cells:
            y = header_y - offset
            if y < 80:
                # Janela baixa demais: as ultimas linhas ficam de fora.
                continue
            text.y = y
            text.draw()

        for key, rect in self._button_rects().items():
            left, bottom, w, h = rect
            hover = self._hover == key
            if key == "new":
                background = _PRIMARY_HOVER if hover else _PRIMARY_BG
            else:
                background = _BUTTON_HOVER if hover else _BUTTON_BG
            arcade.draw_lbwh_rectangle_filled(left, bottom, w, h, background)
            text = self._button_texts[key]
            text.x, text.y = left + w / 2, bottom + h / 2
            text.draw()


def _inside(x: float, y: float, rect: tuple[int, int, int, int]) -> bool:
    left, bottom, width, height = rect
    return left <= x <= left + width and bottom <= y <= bottom + height
