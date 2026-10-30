"""Tela Arcade dos torneios salvos: abrir sem simular ou reexecutar (#109).

So desenha e despacha: listar, reabrir e reexecutar falam com o backend numa
thread, e o resultado volta pela fila para a thread do Arcade, como na
``ParametersView``. A traducao entre registro e objetos da apresentacao fica
em ``saved_tournaments.py``, testavel sem janela.
"""

from __future__ import annotations

from collections.abc import Callable
from queue import Empty, SimpleQueue
from threading import Thread

import arcade

from frontend.arcade import track_client
from frontend.arcade.race_launcher import LaunchOutcome
from frontend.arcade.saved_tournaments import (
    HttpTournamentClient,
    reopen,
    rerun,
    session_from_outcome,
)
from frontend.arcade.theme import (
    ERROR_COLOR,
    PRIMARY_TEXT_COLOR,
    SECONDARY_TEXT_COLOR,
)

_MENU_BG = (16, 22, 30)
_ROW_BG = (30, 41, 53)
_BUTTON_BG = (46, 62, 80)
_BUTTON_HOVER = (70, 90, 115)
_PRIMARY_BG = (190, 30, 45)
_PRIMARY_HOVER = (225, 45, 60)
ROW_H = 58
LIST_TOP = 130
ACTION_W = 130


class SavedTournamentsView(arcade.View):
    """Lista os torneios salvos com as acoes "Abrir" e "Reexecutar"."""

    def __init__(
        self,
        return_view: arcade.View | None = None,
        lister: Callable[[], dict] = track_client.fetch_saved_tournaments,
        loader: Callable[[str], dict] = track_client.fetch_saved_tournament,
        reopener: Callable[[dict], LaunchOutcome] = reopen,
        rerunner: Callable[[dict, Callable[[str], None]], LaunchOutcome] = (
            lambda record, progress: rerun(record, HttpTournamentClient(), progress)
        ),
    ) -> None:
        super().__init__()
        self._return_view = return_view
        self._lister = lister
        self._loader = loader
        self._reopener = reopener
        self._rerunner = rerunner
        self._saved: list[dict] = []
        # Textos montados uma vez por listagem; cada quadro so os reposiciona
        # (``arcade.draw_text`` recria a textura a cada chamada).
        self._row_texts: list[tuple[arcade.Text, arcade.Text]] = []
        self._label_texts = {
            label: arcade.Text(
                label,
                0,
                0,
                PRIMARY_TEXT_COLOR,
                12,
                anchor_x="center",
                anchor_y="center",
            )
            for label in ("‹  Voltar", "Atualizar", "Abrir", "Reexecutar")
        }
        self._results: SimpleQueue[tuple[str, object]] = SimpleQueue()
        self._busy = False
        self._hover: str | None = None
        self._status = "Carregando torneios salvos…"
        self._status_color = SECONDARY_TEXT_COLOR
        self._title = arcade.Text(
            "Torneios salvos", 40, 0, PRIMARY_TEXT_COLOR, 24, bold=True
        )
        self._subtitle = arcade.Text("", 40, 0, SECONDARY_TEXT_COLOR, 12)
        self.refresh()

    # Acoes (chamadas pelos cliques; publicas para os testes) ---------------

    def refresh(self) -> None:
        self._run("list", lambda progress: self._lister().get("saved", []))

    def open_saved(self, tournament_id: str) -> None:
        """Mostre o torneio com as corridas guardadas, sem simular."""

        self._run(
            "open",
            lambda progress: self._reopener(self._loader(tournament_id)),
            "Abrindo o torneio salvo…",
        )

    def rerun_saved(self, tournament_id: str) -> None:
        """Restaure o grid salvo e simule de novo cada etapa."""

        self._run(
            "open",
            lambda progress: self._rerunner(self._loader(tournament_id), progress),
            "Reexecutando o torneio…",
        )

    def _run(self, kind: str, work, message: str | None = None) -> None:
        if self._busy:
            self._set_status("Aguarde a operação em andamento…", SECONDARY_TEXT_COLOR)
            return
        self._busy = True
        if message:
            self._set_status(message, SECONDARY_TEXT_COLOR)
        results = self._results

        def target() -> None:
            try:
                payload = work(lambda text: results.put(("progress", text)))
            except (RuntimeError, OSError, ValueError, KeyError, TypeError) as error:
                # BackendError e RuntimeError; URLError e OSError; registro
                # malformado vira ValueError/KeyError/TypeError.
                results.put(("error", str(error)))
            else:
                results.put((kind, payload))

        Thread(target=target, name=f"saved-tournaments-{kind}", daemon=True).start()

    def on_update(self, delta_time: float) -> None:
        """Aplique, na thread do Arcade, o que a thread publicou."""

        while True:
            try:
                kind, payload = self._results.get_nowait()
            except Empty:
                return
            if kind == "progress":
                self._set_status(str(payload), SECONDARY_TEXT_COLOR)
                continue
            self._busy = False
            if kind == "error":
                self._set_status(f"Falha: {payload}", ERROR_COLOR)
            elif kind == "list":
                self._saved = list(payload)
                self._row_texts = [_row_texts(item) for item in self._saved]
                self._set_status(
                    f"{len(self._saved)} torneio(s) · Abrir mostra o resultado "
                    "salvo; Reexecutar simula de novo com o grid salvo",
                    SECONDARY_TEXT_COLOR,
                )
            else:
                self._show_outcome(payload)
            return

    def _show_outcome(self, outcome: LaunchOutcome) -> None:
        from frontend.arcade.track_view import TrackView

        try:
            tournament = session_from_outcome(outcome)
            first = outcome.races[0]
            view = TrackView(
                first.track,
                first.race,
                notices=tournament.notices,
                tournament=tournament,
                stage_index=1,
            )
        except (KeyError, TypeError, ValueError) as error:
            self._set_status(f"Não foi possível exibir o torneio: {error}", ERROR_COLOR)
            return
        self.window.show_view(view)

    def _set_status(self, message: str, color) -> None:
        self._status = message
        self._status_color = color

    # Layout e eventos ---------------------------------------------------------

    def _row_rect(self, index: int) -> tuple[int, int, int, int]:
        top = self.window.height - LIST_TOP
        bottom = top - (index + 1) * ROW_H + 8
        return 40, bottom, self.window.width - 80, ROW_H - 12

    def _button_rects(self) -> dict[str, tuple[int, int, int, int]]:
        rects = {"back": (40, 24, 160, 36), "refresh": (212, 24, 160, 36)}
        for index, item in enumerate(self._saved):
            left, bottom, width, height = self._row_rect(index)
            if bottom < 72:
                break
            right = left + width - 12
            rects[f"rerun:{item['id']}"] = (
                right - ACTION_W,
                bottom + 7,
                ACTION_W,
                height - 14,
            )
            right -= ACTION_W + 10
            rects[f"open:{item['id']}"] = (
                right - ACTION_W,
                bottom + 7,
                ACTION_W,
                height - 14,
            )
        return rects

    def on_show_view(self) -> None:
        arcade.set_background_color(_MENU_BG)

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
                self._go_back()
            elif key == "refresh":
                self.refresh()
            elif key.startswith("open:"):
                self.open_saved(key.split(":", 1)[1])
            elif key.startswith("rerun:"):
                self.rerun_saved(key.split(":", 1)[1])
            return

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol == arcade.key.R:
            self.refresh()
        elif symbol == arcade.key.ESCAPE:
            self._go_back()

    def _go_back(self) -> None:
        if self._return_view is not None:
            self.window.show_view(self._return_view)
            return
        from frontend.arcade.parameters_view import (
            ParametersView,
            backend_simulation_runner,
        )

        self.window.show_view(
            ParametersView(simulation_runner=backend_simulation_runner)
        )

    def on_draw(self) -> None:
        self.clear()
        height = self.window.height
        self._title.y = height - 60
        self._title.draw()
        self._subtitle.text = self._status
        self._subtitle.color = self._status_color
        self._subtitle.y = height - 92
        self._subtitle.draw()

        for index, (name, detail) in enumerate(self._row_texts):
            left, bottom, width, row_height = self._row_rect(index)
            if bottom < 72:
                break
            arcade.draw_lbwh_rectangle_filled(left, bottom, width, row_height, _ROW_BG)
            name.x, name.y = left + 16, bottom + row_height - 22
            name.draw()
            detail.x, detail.y = left + 16, bottom + 6
            detail.draw()

        labels = {"back": "‹  Voltar", "refresh": "Atualizar"}
        for key, (left, bottom, width, button_height) in self._button_rects().items():
            hover = self._hover == key
            if key.startswith("rerun:"):
                background = _PRIMARY_HOVER if hover else _PRIMARY_BG
                label = "Reexecutar"
            else:
                background = _BUTTON_HOVER if hover else _BUTTON_BG
                label = "Abrir" if key.startswith("open:") else labels[key]
            arcade.draw_lbwh_rectangle_filled(
                left, bottom, width, button_height, background
            )
            text = self._label_texts[label]
            text.x, text.y = left + width / 2, bottom + button_height / 2
            text.draw()


def _row_texts(item: dict) -> tuple[arcade.Text, arcade.Text]:
    """Nome e linha de detalhes de um torneio da listagem."""

    seed = item.get("tournament_seed")
    detail = (
        f"{item['stage_count']} etapa(s) · {item['car_count']} carros · "
        f"semente do grid {item['grid_seed']} · "
        + ("sem seed de torneio" if seed is None else f"seed {seed}")
        + f" · salvo em {item['saved_at'][:16].replace('T', ' ')}"
    )
    return (
        arcade.Text(item["name"], 0, 0, PRIMARY_TEXT_COLOR, 14, bold=True),
        arcade.Text(detail, 0, 0, SECONDARY_TEXT_COLOR, 10),
    )


def _inside(x: float, y: float, rect: tuple[int, int, int, int]) -> bool:
    left, bottom, width, height = rect
    return left <= x <= left + width and bottom <= y <= bottom + height
