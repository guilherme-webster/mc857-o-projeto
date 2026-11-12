"""Tela unica das simulacoes salvas: torneios e corridas avulsas.

Lista os dois tipos em ordem de data, com rolagem. Torneio: "Abrir" mostra o
resultado salvo, "Reexecutar" simula de novo com o grid salvo. Corrida: "Abrir"
mostra a corrida. Todo item pode ser renomeado ou excluido. Excluir pede um
segundo clique em "Confirmar"; renomear edita o nome na propria linha (Enter
grava, Esc cancela).

A tela e aberta pelo menu da ``ParametersView``, pelo resultado do torneio e
pela ``TrackView``; voltar retorna a quem a abriu.

So desenha e despacha: listar, abrir, renomear e excluir falam com o backend
numa thread, e o resultado volta pela fila para a thread do Arcade. Objetos
Arcade (``TrackView``, textos) so sao criados na thread do Arcade.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from queue import Empty, SimpleQueue
from threading import Thread

import arcade

from frontend.arcade import track_client
from frontend.arcade.race_launcher import LaunchOutcome
from frontend.arcade.saved_tournaments import (
    HttpTournamentClient,
    plan_from_record,
    reopen,
    rerun_runner,
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
_DANGER_BG = (120, 40, 50)
_DANGER_HOVER = (160, 55, 65)
# Cada linha ocupa ROW_H, com ROW_GAP de espaco entre uma e outra.
ROW_H = 74
ROW_GAP = 8
# Distancia do topo da janela ate o topo da primeira linha.
LIST_TOP = 130
ACTION_W = 110
ACTION_GAP = 8
ACTION_H = 36
# Limite de caracteres das linhas de texto; o que passa disso e cortado.
_NAME_LIMIT = 60
_STAGES_LIMIT = 90
_NEW_NAME_LIMIT = 120
_TITLE_X = 200
_TOURNAMENT = "tournament"
_RACE = "race"
_LABELS = (
    "‹  Voltar",
    "Atualizar",
    "Abrir",
    "Reexecutar",
    "Renomear",
    "Cancelar",
    "Excluir",
    "Confirmar",
)


class SavedTournamentsView(arcade.View):
    """Lista torneios e corridas salvos, com as acoes de cada tipo."""

    def __init__(
        self,
        return_view: arcade.View | None = None,
        lister: Callable[[], dict] = track_client.fetch_saved_tournaments,
        loader: Callable[[str], dict] = track_client.fetch_saved_tournament,
        reopener: Callable[[dict], LaunchOutcome] = reopen,
        rerunner: Callable[[dict], Callable[..., LaunchOutcome]] = (
            lambda record: rerun_runner(record, HttpTournamentClient())
        ),
        race_lister: Callable[[], dict] = track_client.fetch_saved_races,
        race_renamer: Callable[[str, str], dict] = track_client.rename_saved_race,
        race_deleter: Callable[[str], dict] = track_client.delete_saved_race,
        tournament_renamer: Callable[[str, str], dict] = track_client.rename_saved_tournament,
        tournament_deleter: Callable[[str], dict] = track_client.delete_saved_tournament,
    ) -> None:
        super().__init__()
        self._return_view = return_view
        self._lister = lister
        self._loader = loader
        self._reopener = reopener
        self._rerunner = rerunner
        self._race_lister = race_lister
        self._race_renamer = race_renamer
        self._race_deleter = race_deleter
        self._tournament_renamer = tournament_renamer
        self._tournament_deleter = tournament_deleter
        self._tournaments: list[dict] = []
        self._races: list[dict] = []
        # Linhas ordenadas por data: (tipo, registro, textos). Os textos sao
        # montados uma vez por listagem; cada quadro so os reposiciona.
        self._rows: list[tuple[str, dict, tuple[arcade.Text, arcade.Text, arcade.Text]]] = []
        # Primeira linha visivel da lista (rolagem).
        self._scroll = 0
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
            for label in _LABELS
        }
        # Renomear: (tipo, id) da linha em edicao e o texto digitado. A linha
        # em edicao desenha este texto no lugar do nome.
        self._renaming: tuple[str, str] | None = None
        self._rename_buffer = ""
        self._edit_text = arcade.Text("", 0, 0, PRIMARY_TEXT_COLOR, 14, bold=True)
        # Excluir pede confirmacao: a primeira chave clicada fica pendente.
        self._pending_delete: str | None = None
        self._results: SimpleQueue[tuple[str, object]] = SimpleQueue()
        self._busy = False
        self._hover: str | None = None
        self._status = "Carregando as simulações salvas…"
        self._status_color = SECONDARY_TEXT_COLOR
        self._title = arcade.Text(
            "Corridas e torneios salvos",
            _TITLE_X,
            0,
            PRIMARY_TEXT_COLOR,
            24,
            bold=True,
            anchor_y="center",
        )
        self._subtitle = arcade.Text("", _TITLE_X, 0, SECONDARY_TEXT_COLOR, 12)
        self.refresh()

    # Acoes (chamadas pelos cliques; publicas para os testes) ---------------

    def refresh(self) -> None:
        self._run("list", self._load_listing)

    def open_saved(self, tournament_id: str) -> None:
        """Mostre o torneio com as corridas guardadas, sem simular."""

        self._run(
            "open",
            lambda progress: self._reopener(self._loader(tournament_id)),
            "Abrindo o torneio salvo…",
        )

    def rerun_saved(self, tournament_id: str) -> None:
        """Restaure o grid salvo e simule de novo cada etapa.

        So o registro e buscado fora da janela; a reexecucao em si roda na
        ``SimulationLoadingView`` (grid, etapa em foco, progresso por volta e
        abortar), a mesma de uma simulacao nova.
        """

        self._run(
            "rerun",
            lambda progress: self._loader(tournament_id),
            "Carregando o torneio salvo…",
        )

    def show_message(self, message: str, color) -> None:
        """Aviso da tela de carregamento ao voltar (abortou ou deu erro)."""

        self._set_status(message, color)

    def _start_rerun(self, record: dict) -> None:
        from frontend.arcade.simulation_loading_view import SimulationLoadingView

        try:
            plan = plan_from_record(record)
            runner = self._rerunner(record)
        except (KeyError, TypeError, ValueError) as error:
            self._set_status(f"Não foi possível reexecutar o torneio: {error}", ERROR_COLOR)
            return
        self.window.show_view(
            SimulationLoadingView(
                plan,
                runner,
                return_view=self,
                on_done=self._show_outcome,
                # O grid que sera restaurado esta no registro; o grid atual do
                # backend ainda e outro ate o restore-grid rodar.
                grid_loader=lambda: record.get("grid"),
            )
        )

    def open_race(self, race_id: str) -> None:
        """Abra uma corrida salva; so os dados sao buscados fora da janela."""

        def work(progress):
            from frontend.arcade.track_view import saved_race_inputs

            return saved_race_inputs(race_id)

        self._run("race", work, "Abrindo a corrida salva…")

    def start_rename(self, kind: str, item_id: str) -> None:
        """Abra a linha para editar o nome, com o nome atual preenchido."""

        for row_kind, item, _texts in self._rows:
            if row_kind == kind and item["id"] == item_id:
                self._rename_buffer = str(item.get("name", ""))[:_NEW_NAME_LIMIT]
        self._renaming = (kind, item_id)
        self._pending_delete = None
        self._set_status("Digite o novo nome e tecle Enter (Esc cancela).", SECONDARY_TEXT_COLOR)

    def rename(self, kind: str, item_id: str, name: str) -> None:
        name = name.strip()
        self._renaming = None
        if not name:
            self._set_status("O nome não pode ficar vazio.", ERROR_COLOR)
            return
        renamer = self._race_renamer if kind == _RACE else self._tournament_renamer

        def work(progress):
            renamer(item_id, name)
            return {"kind": kind, "id": item_id, "name": name}

        self._run("renamed", work, "Renomeando…")

    def delete(self, kind: str, item_id: str) -> None:
        deleter = self._race_deleter if kind == _RACE else self._tournament_deleter
        self._pending_delete = None
        def work(progress):
            deleter(item_id)
            return {"kind": kind, "id": item_id}

        self._run("deleted", work, "Excluindo…")

    def _load_listing(self, progress) -> dict:
        """Torneios e corridas. Se as corridas falharem, os torneios ainda aparecem."""

        tournaments = list(self._lister().get("saved", []))
        try:
            races = list(self._race_lister().get("saved", []))
            race_error = None
        except (OSError, RuntimeError, ValueError) as error:
            races, race_error = [], str(error)
        return {"tournaments": tournaments, "races": races, "race_error": race_error}

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

        Thread(target=target, name=f"saved-listing-{kind}", daemon=True).start()

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
                self._apply_listing(payload)
            elif kind == "race":
                self._show_race(payload)
            elif kind == "open":
                self._show_outcome(payload)
            elif kind == "rerun":
                self._start_rerun(payload)
            elif kind == "renamed":
                self._apply_rename(payload)
                self._set_status("Nome atualizado.", SECONDARY_TEXT_COLOR)
                self.refresh()
            elif kind == "deleted":
                self._apply_delete(payload)
                self._set_status("Simulação excluída.", SECONDARY_TEXT_COLOR)
                self.refresh()
            return

    def _apply_rename(self, change: dict) -> None:
        """Mostra o novo nome ja na lista local, sem esperar a nova listagem."""

        if change["kind"] == _RACE:
            self._races = renamed_items(self._races, change["id"], change["name"])
        else:
            self._tournaments = renamed_items(self._tournaments, change["id"], change["name"])
        self._rows = _build_rows(self._tournaments, self._races)

    def _apply_delete(self, change: dict) -> None:
        """Tira a linha excluida da lista local, sem esperar a nova listagem."""

        if change["kind"] == _RACE:
            self._races = without_item(self._races, change["id"])
        else:
            self._tournaments = without_item(self._tournaments, change["id"])
        self._rows = _build_rows(self._tournaments, self._races)
        if self._renaming is not None and self._renaming[1] == change["id"]:
            self._renaming = None
        self._clamp_scroll()

    def _apply_listing(self, payload: dict) -> None:
        self._tournaments = list(payload["tournaments"])
        self._races = list(payload["races"])
        self._rows = _build_rows(self._tournaments, self._races)
        message = (
            f"{len(self._tournaments)} torneio(s) · {len(self._races)} corrida(s) · "
            "Reexecutar simula de novo com o grid salvo"
        )
        if payload.get("race_error"):
            message += f" · corridas indisponíveis: {payload['race_error']}"
            self._set_status(message, ERROR_COLOR)
        else:
            self._set_status(message, SECONDARY_TEXT_COLOR)

    def _show_race(self, inputs: tuple[dict, dict]) -> None:
        from frontend.arcade.track_view import TrackView

        track, race = inputs
        try:
            view = TrackView(track, race, list_view=self, saveable=False)
        except (KeyError, TypeError, ValueError) as error:
            self._set_status(f"Não foi possível abrir a corrida: {error}", ERROR_COLOR)
            return
        self.window.show_view(view)

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
                saveable=False,
            )
        except (KeyError, TypeError, ValueError) as error:
            self._set_status(f"Não foi possível exibir o torneio: {error}", ERROR_COLOR)
            return
        self.window.show_view(view)

    def _set_status(self, message: str, color) -> None:
        self._status = message
        self._status_color = color

    # Layout e rolagem --------------------------------------------------------

    def _visible_slots(self) -> int:
        """Linhas inteiras que cabem entre o topo da lista e a margem inferior."""

        room = self.window.height - LIST_TOP - (ROW_H - ROW_GAP) - 24
        return max(1, int(room // ROW_H) + 1)

    def _clamp_scroll(self) -> None:
        self._scroll = min(max(self._scroll, 0), max(0, len(self._rows) - self._visible_slots()))

    def _row_rect(self, index: int) -> tuple[int, int, int, int]:
        """Retangulo da linha ``index``; a primeira visivel e a de ``self._scroll``."""

        top = self.window.height - LIST_TOP - (index - self._scroll) * ROW_H
        height = ROW_H - ROW_GAP
        return 40, top - height, self.window.width - 80, height

    def _visible_indices(self) -> list[int]:
        self._clamp_scroll()
        indices = []
        for index in range(self._scroll, len(self._rows)):
            _left, bottom, _width, _height = self._row_rect(index)
            if bottom < 24:
                break
            indices.append(index)
        return indices

    def _draw_scrollbar(self) -> None:
        """Trilho a direita da lista; so aparece quando ha linhas ocultas."""

        total = len(self._rows)
        visible = len(self._visible_indices())
        if total <= visible:
            return
        top, bottom = self.window.height - LIST_TOP, 24
        track_x = self.window.width - 30
        track_h = top - bottom
        arcade.draw_lbwh_rectangle_filled(track_x, bottom, 4, track_h, _BUTTON_BG)
        thumb_h = max(track_h * visible / total, 24)
        thumb_top = top - (track_h - thumb_h) * self._scroll / (total - visible)
        arcade.draw_lbwh_rectangle_filled(
            track_x, thumb_top - thumb_h, 4, thumb_h, SECONDARY_TEXT_COLOR
        )

    def _action_keys(self, kind: str, item: dict) -> list[str]:
        """Chaves das acoes de uma linha, da direita para a esquerda."""

        item_id = item["id"]
        keys = [f"delete:{kind}:{item_id}", f"rename:{kind}:{item_id}"]
        if kind == _RACE:
            keys.append(f"race:{item_id}")
        else:
            keys += [f"rerun:{item_id}", f"open:{item_id}"]
        return keys

    def _button_rects(self) -> dict[str, tuple[int, int, int, int]]:
        height = self.window.height
        width = self.window.width
        rects = {
            "back": (40, height - 84, 140, 40),
            "refresh": (width - 40 - 140, height - 84, 140, 40),
        }
        for index in self._visible_indices():
            kind, item, _texts = self._rows[index]
            left, bottom, row_width, row_height = self._row_rect(index)
            button_y = bottom + (row_height - ACTION_H) // 2
            right = left + row_width - 16
            for key in self._action_keys(kind, item):
                rects[key] = (right - ACTION_W, button_y, ACTION_W, ACTION_H)
                right -= ACTION_W + ACTION_GAP
        return rects

    def _button_style(self, key: str) -> tuple[str, str]:
        """(rotulo, estilo) de um botao: estilo e "primary", "danger" ou "plain"."""

        if key == "back":
            return "‹  Voltar", "plain"
        if key == "refresh":
            return "Atualizar", "plain"
        verb, _, rest = key.partition(":")
        if verb == "delete":
            if self._pending_delete == key:
                return "Confirmar", "danger"
            return "Excluir", "danger"
        if verb == "rename":
            kind, _, item_id = rest.partition(":")
            if self._renaming == (kind, item_id):
                return "Cancelar", "plain"
            return "Renomear", "plain"
        if verb == "rerun":
            return "Reexecutar", "primary"
        return "Abrir", "plain"

    # Eventos -------------------------------------------------------------------

    def on_show_view(self) -> None:
        arcade.set_background_color(_MENU_BG)

    def on_mouse_motion(self, x, y, dx, dy) -> None:
        self._hover = next(
            (key for key, rect in self._button_rects().items() if _inside(x, y, rect)),
            None,
        )

    def on_mouse_scroll(self, x, y, scroll_x: float, scroll_y: float) -> None:
        """Roda do mouse rola uma linha por passo."""

        self._scroll += -1 if scroll_y > 0 else 1 if scroll_y < 0 else 0
        self._clamp_scroll()

    def on_mouse_press(self, x, y, button, modifiers) -> None:
        for key, rect in self._button_rects().items():
            if not _inside(x, y, rect):
                continue
            # Qualquer clique cancela a confirmacao de exclusao pendente.
            pending, self._pending_delete = self._pending_delete, None
            if key == "back":
                self._go_back()
            elif key == "refresh":
                self.refresh()
            elif key.startswith("delete:"):
                kind, item_id = key.split(":", 2)[1:]
                if pending == key:
                    self.delete(kind, item_id)
                else:
                    self._pending_delete = key
                    self._set_status(
                        "Clique de novo em Confirmar para excluir.", ERROR_COLOR
                    )
            elif key.startswith("rename:"):
                kind, item_id = key.split(":", 2)[1:]
                if self._renaming == (kind, item_id):
                    self._renaming = None
                else:
                    self.start_rename(kind, item_id)
            elif key.startswith("open:"):
                self.open_saved(key.split(":", 1)[1])
            elif key.startswith("rerun:"):
                self.rerun_saved(key.split(":", 1)[1])
            elif key.startswith("race:"):
                self.open_race(key.split(":", 1)[1])
            return

    def on_text(self, text: str) -> None:
        """Digitacao do novo nome, so enquanto uma linha esta em renomeacao."""

        if self._renaming is None:
            return
        printable = "".join(char for char in text if char.isprintable())
        room = _NEW_NAME_LIMIT - len(self._rename_buffer)
        self._rename_buffer += printable[:room]

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if self._renaming is not None:
            if symbol == arcade.key.BACKSPACE:
                self._rename_buffer = self._rename_buffer[:-1]
            elif symbol in (arcade.key.ENTER, arcade.key.RETURN):
                kind, item_id = self._renaming
                self.rename(kind, item_id, self._rename_buffer)
            elif symbol == arcade.key.ESCAPE:
                self._renaming = None
                self._set_status("Renomear cancelado.", SECONDARY_TEXT_COLOR)
            return
        if symbol == arcade.key.R:
            self.refresh()
        elif symbol == arcade.key.ESCAPE:
            self._go_back()
        elif symbol == arcade.key.UP:
            self._scroll -= 1
            self._clamp_scroll()
        elif symbol == arcade.key.DOWN:
            self._scroll += 1
            self._clamp_scroll()

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
        # Cabecalho: voltar e atualizar nas pontas, titulo e status ao centro.
        self._title.x, self._title.y = _TITLE_X, height - 64
        self._title.draw()
        self._subtitle.text = self._status
        self._subtitle.color = self._status_color
        self._subtitle.x, self._subtitle.y = _TITLE_X, height - 102
        self._subtitle.draw()

        for index in self._visible_indices():
            kind, item, (name, stages, details) = self._rows[index]
            left, bottom, width, row_height = self._row_rect(index)
            arcade.draw_lbwh_rectangle_filled(left, bottom, width, row_height, _ROW_BG)
            if self._renaming == (kind, item["id"]):
                self._edit_text.text = self._rename_buffer + "|"
                name = self._edit_text
            name.x, name.y = left + 16, bottom + row_height - 24
            name.draw()
            stages.x, stages.y = left + 16, bottom + row_height - 42
            stages.draw()
            details.x, details.y = left + 16, bottom + 8
            details.draw()

        self._draw_scrollbar()
        for key, (left, bottom, width, button_height) in self._button_rects().items():
            label, style = self._button_style(key)
            hover = self._hover == key
            if style == "primary":
                background = _PRIMARY_HOVER if hover else _PRIMARY_BG
            elif style == "danger":
                background = _DANGER_HOVER if hover else _DANGER_BG
            else:
                background = _BUTTON_HOVER if hover else _BUTTON_BG
            arcade.draw_lbwh_rectangle_filled(left, bottom, width, button_height, background)
            text = self._label_texts[label]
            text.x, text.y = left + width / 2, bottom + button_height / 2
            text.draw()


def row_lines(kind: str, item: dict) -> tuple[str, str, str]:
    """Nome, linha de pistas e linha de detalhes de uma simulacao salva.

    Mostra o nome das pistas, nunca so o id do circuito. Registros antigos sem
    nome de pista caem no id, para a linha nao ficar vazia.
    """

    name = _clip(str(item.get("name") or item.get("id", "")), _NAME_LIMIT)
    when = _saved_label(str(item.get("saved_at", "")))
    if kind == _TOURNAMENT:
        names = item.get("stage_names") or item.get("circuits") or []
        stages = "Pistas: " + " · ".join(str(value) for value in names)
        details = (
            f"Torneio · {item.get('stage_count', '?')} etapa(s) · "
            f"{item.get('car_count', '?')} carros · salvo em {when}"
        )
    else:
        track = item.get("track_name") or item.get("track_id") or "-"
        stages = f"Pista: {track}"
        details = (
            f"Corrida · {item.get('total_laps') or '?'} voltas · "
            f"{item.get('car_count') or '?'} carros · salvo em {when}"
        )
    return name, _clip(stages, _STAGES_LIMIT), details


def _build_rows(
    tournaments: list[dict], races: list[dict]
) -> list[tuple[str, dict, tuple[arcade.Text, arcade.Text, arcade.Text]]]:
    entries = [(_TOURNAMENT, item) for item in tournaments]
    entries += [(_RACE, item) for item in races]
    entries.sort(key=lambda entry: str(entry[1].get("saved_at", "")), reverse=True)
    rows = []
    for kind, item in entries:
        name, stages, details = row_lines(kind, item)
        rows.append(
            (
                kind,
                item,
                (
                    arcade.Text(name, 0, 0, PRIMARY_TEXT_COLOR, 14, bold=True),
                    arcade.Text(stages, 0, 0, SECONDARY_TEXT_COLOR, 11),
                    arcade.Text(details, 0, 0, SECONDARY_TEXT_COLOR, 10),
                ),
            )
        )
    return rows


def renamed_items(items: list[dict], item_id: str, name: str) -> list[dict]:
    """Copia da lista com o nome do item ``item_id`` trocado."""

    return [{**item, "name": name} if item.get("id") == item_id else item for item in items]


def without_item(items: list[dict], item_id: str) -> list[dict]:
    """Copia da lista sem o item ``item_id``."""

    return [item for item in items if item.get("id") != item_id]


def _saved_label(saved_at: str) -> str:
    """Data e hora locais, como ``07/11/2026 15:34``; sem parse, o texto cru."""

    try:
        moment = datetime.fromisoformat(saved_at).astimezone()
    except ValueError:
        return saved_at[:16].replace("T", " ")
    return moment.strftime("%d/%m/%Y %H:%M")


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _inside(x: float, y: float, rect: tuple[int, int, int, int]) -> bool:
    left, bottom, width, height = rect
    return left <= x <= left + width and bottom <= y <= bottom + height
