"""Tela Arcade de pilotos e grid: montar, inspecionar e editar o grid atual.

O grid e o do backend; a view so o mostra e envia pedidos. Chamadas HTTP rodam
em threads e o resultado volta pela fila lida em ``on_update``, o mesmo padrao
das telas de configuracao. O estado editavel fica em ``GridDraft``.
"""

from __future__ import annotations

from collections.abc import Callable
from queue import Empty, SimpleQueue
from threading import Thread

import arcade

from frontend.arcade import track_client
from frontend.arcade.button_text import fit_button_text
from frontend.arcade.clipboard import handle_clipboard_shortcut
from frontend.arcade.configuration_state import (
    ConfigurationFormError,
    parse_optional_seed,
)
from frontend.arcade.drawing import caret_visible
from frontend.arcade.grid_editor import (
    ARCHETYPE_LABELS,
    ATTRIBUTES,
    MAX_GRID_SIZE,
    MIN_GRID_SIZE,
    RANDOM_GRID_SIZE,
    SOURCE_LABELS,
    GridDraft,
    GridSource,
    format_value,
    grid_sources,
    parse_grid_size,
)
from frontend.arcade.grid_picker import PairPicker, pair_id
from frontend.arcade.theme import (
    BACKGROUND_COLOR,
    ERROR_COLOR,
    PANEL_BORDER_COLOR,
    PANEL_COLOR,
    PRIMARY_TEXT_COLOR,
    SECONDARY_TEXT_COLOR,
    SUCCESS_COLOR,
)

ROW_HEIGHT = 26
# Linha de origem do grid: altura do display e do botao "Montar grid", largura
# do botao e espaco entre os dois.
_SOURCE_ROW_H = 40
_BUILD_BUTTON_W = 190
_PICK_BUTTON_W = 150
_SOURCE_GAP = 10
# Botoes da barra inferior (Voltar, Remover piloto, Adicionar piloto).
_ACTION_X = 40
_ACTION_GAP = 16
_HEADER_COLOR = (130, 140, 150)
_SELECTED_BG = (40, 56, 74)
_BUTTON_BG = (46, 62, 80)
_BUTTON_HOVER = (70, 90, 115)
_PRIMARY_BG = (190, 30, 45)
_PRIMARY_HOVER = (225, 45, 60)
# Cor do valor pela origem: o usuario ve de onde cada numero veio.
SOURCE_COLORS = {
    "generated": (190, 198, 210),
    "preset": (245, 197, 66),
    "manual": (90, 200, 250),
}
# Colunas que nao rolam na horizontal (ficam para dar nome aos pilotos).
_TABLE_FROZEN = ("P", "PILOTO")
# Onde comeca a area que rola na horizontal, e quanto cada giro desloca.
_TABLE_SCROLL_LEFT = 266
_TABLE_SCROLL_STEP = 40
# Folga apos a ultima coluna, para o valor alinhado a direita nao encostar na borda.
_TABLE_COLUMN_MARGIN = 40
_TABLE_COLUMNS = (
    ("P", 30, "right"),
    ("PILOTO", 42, "left"),
    ("EQUIPE", 230, "left"),
    ("ARQUÉTIPO", 380, "left"),
    *((spec.short, 540 + i * 60, "right") for i, spec in enumerate(ATTRIBUTES)),
)
# Rolagem vertical da caixa do piloto: altura de cada atributo e da linha
# inicial em relacao ao topo da area rolavel, e passo de cada giro da roda.
_PANEL_ROW_HEIGHT = 64
_PANEL_FIRST_ROW_OFFSET = 34
# Altura minima, acima da base da area rolavel, em que o ultimo atributo para
# de subir: deixa o aviso de rodape (abaixo dele) visivel.
_PANEL_LAST_ROW_MARGIN = 80
_PANEL_SCROLL_STEP = 32
_PANEL_LEFT_MARGIN = 40
# Caixa lateral do piloto selecionado: largura total (inclui a margem direita
# de 40 px) e posicao dos controles em relacao a borda esquerda da caixa.
_PANEL_TOTAL_WIDTH = 440
# Texto de cada atributo (nome e dica) comeca a 24 px da borda da caixa e
# precisa parar antes do botao "−", com 10 px de folga.
_PANEL_TEXT_X = 24
# Espaco vertical entre as linhas do bloco de texto de cada atributo.
_ATTR_BLOCK_GAP = 2
# Lado dos botoes "−" e "+" de cada atributo (quadrados).
_CONTROL_SIDE = 34
_PANEL_TEXT_WIDTH = 240 - _PANEL_TEXT_X - 10
# Setas de subir e descer na primeira linha da caixa, nas bordas internas; o
# nome do piloto fica centralizado entre elas.
_ARROW_UP_X = 24
_ARROW_DOWN_X = _PANEL_TOTAL_WIDTH - 40 - 24 - 34
_CONTROL_X = {
    "minus": 272,
    "value": 328,
    "plus": 350,
}


class GridView(arcade.View):
    """Monte o grid (aleatorio ou largada de 2024), veja perfis e edite."""

    def __init__(
        self,
        return_view: arcade.View | None = None,
        client=track_client,
    ) -> None:
        super().__init__()
        self._return_view = return_view
        self._client = client
        self._results: SimpleQueue[tuple[str, str, object]] = SimpleQueue()
        self._draft: GridDraft | None = None
        self._sources: tuple[GridSource, ...] = grid_sources(None)
        self._source_index = 0
        self._selected: str | None = None
        self._busy = False
        self._hover: str | None = None
        self._grid_seed_text = ""
        self._editing_grid_seed = False
        self._status = "Carregando o grid atual…"
        self._status_color = SECONDARY_TEXT_COLOR
        self._row_texts: list[dict[str, arcade.Text]] = []
        self._texts: dict[str, arcade.Text] = {}
        # Indice do primeiro piloto visivel na tabela (rolagem).
        self._scroll = 0
        # Deslocamento horizontal das colunas que rolam (pixels).
        self._hscroll = 0
        # Rolagem da caixa de atributos e o piloto a que ela pertence; ao
        # trocar de piloto a caixa volta ao topo.
        self._panel_scroll = 0
        self._panel_owner: str | None = None
        # Faixa (base, altura) do bloco de texto de cada atributo; os botoes usam a mesma.
        self._attr_control_bounds: dict[str, tuple[float, float]] = {}
        # Seletor de pilotos aberto (overlay modal); None quando fechado.
        self._picker: PairPicker | None = None
        # Janela de numero de pilotos do grid aleatorio; None quando fechada.
        self._size_text: str | None = None
        self._size_error: str | None = None
        self._size_replace = True
        self._pending_seed: int | None = None
        # Popup de escolha de temporada e corrida; None-like quando fechado.
        self._popup_open = False
        self._popup_season: int | None = None
        self._popup_scroll = 0
        # Ano digitado no popup (None = nao esta digitando) e o erro da ultima tentativa.
        self._popup_year_text: str | None = None
        self._popup_year_error: str | None = None
        self._run("load-grid", self._client.fetch_current_grid)
        self._run("load-races", self._client.fetch_history_races)

    # -- comunicacao com o backend -------------------------------------------

    def _run(self, kind: str, call: Callable[[], object]) -> None:
        def work() -> None:
            try:
                self._results.put(("ok", kind, call()))
            except (RuntimeError, OSError, ValueError) as error:
                # BackendError e RuntimeError; URLError e OSError.
                self._results.put(("error", kind, str(error)))

        Thread(target=work, name=f"grid-{kind}", daemon=True).start()

    def _start(self, kind: str, call: Callable[[], object], message: str) -> None:
        if self._busy:
            self._set_status("Aguarde a operação em andamento…", SECONDARY_TEXT_COLOR)
            return
        self._busy = True
        self._set_status(message, SECONDARY_TEXT_COLOR)
        self._run(kind, call)

    def on_update(self, delta_time: float) -> None:
        while True:
            try:
                outcome, kind, payload = self._results.get_nowait()
            except Empty:
                return
            if kind in ("build", "save"):
                self._busy = False
            if outcome == "error":
                if kind == "load-races":
                    # Sem historico, o grid aleatorio continua disponivel.
                    continue
                self._set_status(f"Não foi possível concluir: {payload}", ERROR_COLOR)
                continue
            if kind == "load-catalog":
                self._open_picker(payload)
                continue
            if kind == "load-races":
                self._sources = grid_sources(payload)
                continue
            if kind == "load-grid" and payload is None:
                self._set_status(
                    "Nenhum grid no backend. Escolha uma opção e clique em Montar grid.",
                    SECONDARY_TEXT_COLOR,
                )
                continue
            self._accept_grid(payload, kind)

    def _accept_grid(self, payload: dict, kind: str) -> None:
        try:
            self._draft = GridDraft(payload)
        except (KeyError, TypeError, ValueError) as error:
            self._set_status(f"Resposta de grid inválida: {error}", ERROR_COLOR)
            return
        if self._selected not in {e["driver_id"] for e in self._draft.entries}:
            self._selected = (
                self._draft.entries[0]["driver_id"] if self._draft.entries else None
            )
        self._row_texts = []
        self._ensure_selected_visible()
        if self._draft.seed is not None:
            self._grid_seed_text = str(self._draft.seed)
        message = {
            "load-grid": "Grid atual carregado.",
            "build": "Grid montado.",
            "save": "Alterações salvas no grid atual.",
        }[kind]
        self._set_status(
            f"{message} {len(self._draft.entries)} pilotos. Semente {self._draft.seed}.",
            SUCCESS_COLOR,
        )

    # -- acoes -----------------------------------------------------------------

    def build_grid(self) -> None:
        if self._draft is not None and self._draft.has_changes:
            self._set_status(
                "Há alterações não salvas: salve ou descarte antes de montar outro grid.",
                ERROR_COLOR,
            )
            return
        source = self._sources[self._source_index]
        try:
            seed = (
                parse_optional_seed(self._grid_seed_text)
                if source.mode == "random"
                else None
            )
        except ConfigurationFormError as error:
            self._set_status(str(error), ERROR_COLOR)
            return
        if source.mode == "random":
            # O numero de pilotos e pedido antes de montar.
            self._pending_seed = seed
            self._size_text = str(RANDOM_GRID_SIZE)
            self._size_replace = True
            self._size_error = None
            self._set_status(
                "Escolha o número de pilotos do grid.", SECONDARY_TEXT_COLOR
            )
            return
        self._start_build(source, None, None)

    def _start_build(self, source: GridSource, seed: int | None, size: int | None) -> None:
        request = source.request(seed, size if size is not None else RANDOM_GRID_SIZE)
        self._start(
            "build",
            lambda: self._client.build_grid(**request),
            f"Montando: {source.label}…",
        )

    # -- janela do numero de pilotos ------------------------------------------

    def _confirm_size(self) -> None:
        try:
            size = parse_grid_size(self._size_text or "")
        except ValueError as error:
            self._size_error = str(error)
            return
        seed = self._pending_seed
        self._size_text = None
        self._size_error = None
        self._start_build(self._sources[self._source_index], seed, size)

    def _cancel_size(self) -> None:
        self._size_text = None
        self._size_error = None
        self._set_status("Montagem cancelada.", SECONDARY_TEXT_COLOR)

    def _size_layout(self) -> dict:
        width, height = self.window.width, self.window.height
        panel_w, panel_h = 460, 250
        left, bottom = (width - panel_w) / 2, (height - panel_h) / 2
        return {
            "panel": (left, bottom, panel_w, panel_h),
            "field": (left + 30, bottom + 100, panel_w - 60, 44),
            "cancel": (left + 30, bottom + 24, 170, 40),
            "confirm": (left + panel_w - 30 - 190, bottom + 24, 190, 40),
        }

    def _size_click(self, x: float, y: float) -> None:
        layout = self._size_layout()
        if _inside(x, y, layout["cancel"]) or not _inside(x, y, layout["panel"]):
            self._cancel_size()
        elif _inside(x, y, layout["confirm"]):
            self._confirm_size()

    def _size_key(self, symbol: int) -> None:
        if symbol == arcade.key.ESCAPE:
            self._cancel_size()
        elif symbol in (arcade.key.ENTER, arcade.key.NUM_ENTER):
            self._confirm_size()
        elif symbol == arcade.key.BACKSPACE:
            self._size_text = (self._size_text or "")[:-1]
            self._size_replace = False

    def _size_type(self, text: str) -> None:
        if not text.isdigit():
            return
        current = "" if self._size_replace else (self._size_text or "")
        if len(current) < 2:
            self._size_text = current + text
        self._size_replace = False

    def _draw_size_dialog(self, width: int, height: int) -> None:
        layout = self._size_layout()
        arcade.draw_lbwh_rectangle_filled(0, 0, width, height, (0, 0, 0, 170))
        left, bottom, panel_w, panel_h = layout["panel"]
        arcade.draw_lbwh_rectangle_filled(left, bottom, panel_w, panel_h, PANEL_COLOR)
        arcade.draw_lbwh_rectangle_outline(
            left, bottom, panel_w, panel_h, PANEL_BORDER_COLOR, 1
        )
        self._text(
            "sz:title",
            "Número de pilotos",
            left + 30,
            bottom + panel_h - 40,
            PRIMARY_TEXT_COLOR,
            16,
            bold=True,
        ).draw()
        self._text(
            "sz:hint",
            self._size_error or f"Digite de {MIN_GRID_SIZE} a {MAX_GRID_SIZE} pilotos.",
            left + 30,
            bottom + panel_h - 72,
            ERROR_COLOR if self._size_error else SECONDARY_TEXT_COLOR,
            11,
        ).draw()
        f_left, f_bottom, f_w, f_h = layout["field"]
        arcade.draw_lbwh_rectangle_filled(f_left, f_bottom, f_w, f_h, _BUTTON_BG)
        arcade.draw_lbwh_rectangle_outline(
            f_left, f_bottom, f_w, f_h, _PRIMARY_BG, 2
        )
        shown = self._size_text or ""
        self._text(
            "sz:value",
            shown + "|",
            f_left + f_w / 2,
            f_bottom + f_h / 2,
            PRIMARY_TEXT_COLOR,
            18,
            bold=True,
            anchor_x="center",
            anchor_y="center",
        ).draw()
        for key, text, primary in (
            ("cancel", "Cancelar", False),
            ("confirm", "Montar grid", True),
        ):
            b_left, b_bottom, b_w, b_h = layout[key]
            arcade.draw_lbwh_rectangle_filled(
                b_left, b_bottom, b_w, b_h, _PRIMARY_BG if primary else _BUTTON_BG
            )
            self._text(
                f"sz:btn:{key}",
                text,
                b_left + b_w / 2,
                b_bottom + b_h / 2,
                PRIMARY_TEXT_COLOR,
                13,
                bold=primary,
                anchor_x="center",
                anchor_y="center",
            ).draw()

    def save_changes(self) -> None:
        if self._draft is None or not self._draft.has_changes:
            self._set_status("Nenhuma alteração para salvar.", SECONDARY_TEXT_COLOR)
            return
        patch = self._draft.patch()
        self._start(
            "save", lambda: self._client.edit_grid(**patch), "Salvando alterações…"
        )

    def discard_changes(self) -> None:
        if self._draft is not None:
            self._draft.discard()
            self._set_status("Alterações descartadas.", SECONDARY_TEXT_COLOR)

    def step_attribute(self, name: str, direction: int) -> None:
        if self._draft is None or self._selected is None:
            return
        self._draft.step(self._selected, name, direction)

    def move_selected(self, delta: int) -> None:
        """Mova o piloto selecionado sem reutilizar as setas de navegacao."""

        if self._draft is None or self._selected is None:
            return
        if self._draft.move(self._selected, delta):
            self._ensure_selected_visible()
            position = next(
                index
                for index, entry in enumerate(self._draft.entries, start=1)
                if entry["driver_id"] == self._selected
            )
            self._set_status(
                f"Piloto movido para P{position}; salve para confirmar a ordem.",
                SECONDARY_TEXT_COLOR,
            )

    # -- popup de temporada e corrida ------------------------------------------

    def _popup_seasons(self) -> list[int]:
        """Temporadas com corridas no historico, em ordem crescente."""

        return sorted(
            {s.season for s in self._sources if s.mode == "race" and s.season is not None}
        )

    def _open_race_popup(self) -> None:
        seasons = self._popup_seasons()
        if not seasons:
            self._set_status("Não há corridas do histórico para escolher.", ERROR_COLOR)
            return
        current = self._sources[self._source_index]
        # Abre na temporada da corrida atual; se a atual for o aleatorio, na mais recente.
        self._popup_season = current.season if current.season in seasons else seasons[-1]
        self._popup_scroll = 0
        self._popup_year_text = None
        self._popup_year_error = None
        self._popup_open = True

    def _popup_layout(self) -> dict:
        width, height = self.window.width, self.window.height
        panel_w, panel_h = 640, 560
        left, bottom = (width - panel_w) / 2, (height - panel_h) / 2
        return {
            "panel": (left, bottom, panel_w, panel_h),
            "season_prev": (left + 30, bottom + panel_h - 70, 44, 36),
            "season_next": (left + panel_w - 74, bottom + panel_h - 70, 44, 36),
            # Campo central: clicar nele permite digitar o ano.
            "year": (left + panel_w / 2 - 110, bottom + panel_h - 70, 220, 36),
            "list_top": bottom + panel_h - 110,
            "list_bottom": bottom + 70,
            "row_h": 30,
            "close": (left + panel_w - 170, bottom + 20, 150, 36),
        }

    def _popup_races(self) -> list[tuple[int, GridSource]]:
        """(indice em ``_sources``, corrida) das corridas da temporada do popup."""

        return [
            (index, source)
            for index, source in enumerate(self._sources)
            if source.mode == "race" and source.season == self._popup_season
        ]

    def _popup_rows(self) -> list[tuple[int, GridSource, tuple]]:
        layout = self._popup_layout()
        left, _bottom, panel_w, _panel_h = layout["panel"]
        races = self._popup_races()
        count = max(1, int((layout["list_top"] - layout["list_bottom"]) // layout["row_h"]))
        self._popup_scroll = max(0, min(self._popup_scroll, len(races) - count))
        rows = []
        visible = races[self._popup_scroll : self._popup_scroll + count]
        for offset, (index, source) in enumerate(visible):
            y = layout["list_top"] - (offset + 1) * layout["row_h"]
            rows.append((index, source, (left + 20, y, panel_w - 40, layout["row_h"] - 2)))
        return rows

    def _popup_click(self, x: float, y: float) -> None:
        layout = self._popup_layout()
        if _inside(x, y, layout["close"]) or not _inside(x, y, layout["panel"]):
            self._popup_open = False
            return
        if _inside(x, y, layout["year"]):
            self._popup_year_text = ""
            self._popup_year_error = None
            return
        seasons = self._popup_seasons()
        position = seasons.index(self._popup_season)
        if _inside(x, y, layout["season_prev"]) and position > 0:
            self._popup_season = seasons[position - 1]
            self._popup_scroll = 0
            return
        if _inside(x, y, layout["season_next"]) and position < len(seasons) - 1:
            self._popup_season = seasons[position + 1]
            self._popup_scroll = 0
            return
        for index, source, rect in self._popup_rows():
            if _inside(x, y, rect):
                self._source_index = index
                self._popup_open = False
                self._set_status(f"Corrida escolhida: {source.label}.", SUCCESS_COLOR)
                return

    def _popup_type(self, text: str) -> None:
        """Digitos vao para o ano; o campo aceita no maximo 4."""

        if not text.isdigit():
            return
        current = self._popup_year_text or ""
        if len(current) < 4:
            self._popup_year_text = current + text
            self._popup_year_error = None

    def _popup_apply_year(self) -> None:
        """Enter: troca para a temporada digitada, se ela tiver corridas."""

        text = (self._popup_year_text or "").strip()
        if not text:
            self._popup_year_text = None
            return
        seasons = self._popup_seasons()
        year = int(text)
        if year not in seasons:
            self._popup_year_error = (
                f"Não há corridas do histórico em {text}. "
                f"Temporadas: {seasons[0]} a {seasons[-1]}."
            )
            return
        self._popup_year_text = None
        self._popup_year_error = None
        self._popup_season = year
        self._popup_scroll = 0

    def _popup_key_press(self, symbol: int) -> None:
        if symbol == arcade.key.ESCAPE:
            if self._popup_year_text is not None:
                self._popup_year_text = None
                self._popup_year_error = None
            else:
                self._popup_open = False
        elif symbol in (arcade.key.ENTER, arcade.key.NUM_ENTER):
            if self._popup_year_text is not None:
                self._popup_apply_year()
        elif symbol == arcade.key.BACKSPACE and self._popup_year_text:
            self._popup_year_text = self._popup_year_text[:-1]

    @staticmethod
    def _draw_list_scrollbar(layout: dict, total: int, offset: int) -> None:
        """Barra de rolagem na borda direita da lista de um painel (seletor ou popup).

        O cursor mostra a parte da lista visivel e acompanha ``offset``. So aparece
        quando a lista nao cabe inteira.
        """

        list_top, list_bottom = layout["list_top"], layout["list_bottom"]
        count = max(1, int((list_top - list_bottom) // layout["row_h"]))
        if total <= count:
            return
        left, _bottom, panel_w, _panel_h = layout["panel"]
        rail_h = list_top - list_bottom
        thumb_h = max(20.0, rail_h * count / total)
        max_offset = total - count
        travel = rail_h - thumb_h
        thumb_top = list_top - travel * min(offset, max_offset) / max_offset
        # Dentro do painel, a direita das linhas (que terminam 20 px antes da borda).
        x = left + panel_w - 14
        arcade.draw_lbwh_rectangle_filled(x, list_bottom, 6, rail_h, (33, 42, 53))
        arcade.draw_lbwh_rectangle_filled(
            x, thumb_top - thumb_h, 6, thumb_h, (111, 127, 148)
        )

    def _draw_race_popup(self, width: int, height: int) -> None:
        layout = self._popup_layout()
        arcade.draw_lbwh_rectangle_filled(0, 0, width, height, (0, 0, 0, 170))
        left, bottom, panel_w, panel_h = layout["panel"]
        arcade.draw_lbwh_rectangle_filled(left, bottom, panel_w, panel_h, PANEL_COLOR)
        arcade.draw_lbwh_rectangle_outline(
            left, bottom, panel_w, panel_h, PANEL_BORDER_COLOR, 1
        )
        self._text(
            "pop:title",
            "Escolher corrida",
            left + 30,
            bottom + panel_h - 30,
            PRIMARY_TEXT_COLOR,
            16,
            bold=True,
        ).draw()
        seasons = self._popup_seasons()
        position = seasons.index(self._popup_season)
        for key, symbol, enabled in (
            ("season_prev", "‹", position > 0),
            ("season_next", "›", position < len(seasons) - 1),
        ):
            b_left, b_bottom, b_w, b_h = layout[key]
            arcade.draw_lbwh_rectangle_filled(
                b_left, b_bottom, b_w, b_h, _BUTTON_BG if enabled else (30, 36, 46)
            )
            self._text(
                f"pop:{key}",
                symbol,
                b_left + b_w / 2,
                b_bottom + b_h / 2,
                PRIMARY_TEXT_COLOR if enabled else _HEADER_COLOR,
                15,
                anchor_x="center",
                anchor_y="center",
            ).draw()
        y_left, y_bottom, y_w, y_h = layout["year"]
        typing = self._popup_year_text is not None
        arcade.draw_lbwh_rectangle_filled(y_left, y_bottom, y_w, y_h, _BUTTON_BG)
        arcade.draw_lbwh_rectangle_outline(
            y_left,
            y_bottom,
            y_w,
            y_h,
            _PRIMARY_BG if typing else PANEL_BORDER_COLOR,
            2 if typing else 1,
        )
        year_label = (
            f"Temporada {self._popup_year_text}" if typing
            else f"Temporada {self._popup_season}"
        )
        season_label = self._text(
            "pop:season",
            year_label,
            y_left + y_w / 2,
            y_bottom + y_h / 2,
            PRIMARY_TEXT_COLOR,
            14,
            bold=True,
            anchor_x="center",
            anchor_y="center",
        )
        season_label.draw()
        # Cursor como linha logo depois do ano digitado (o texto centralizado nao treme).
        if typing and caret_visible():
            x = season_label.x + season_label.content_width / 2 + 2
            y = season_label.y
            arcade.draw_line(x, y - 8, x, y + 8, PRIMARY_TEXT_COLOR, 2)
        hint, hint_color = (
            (self._popup_year_error, ERROR_COLOR)
            if self._popup_year_error
            else (
                "Digite o ano e tecle Enter, ou use ‹ ›.",
                _HEADER_COLOR,
            )
        )
        self._text(
            "pop:hint",
            hint,
            left + 30,
            layout["list_top"] + 8,
            hint_color,
            10,
            width=panel_w - 60,
        ).draw()
        rows = self._popup_rows()
        self._draw_list_scrollbar(layout, len(self._popup_races()), self._popup_scroll)
        if not rows:
            self._text(
                "pop:empty",
                "Nenhuma corrida nesta temporada.",
                left + 20,
                layout["list_top"] - 20,
                SECONDARY_TEXT_COLOR,
                11,
            ).draw()
        for index, source, (r_left, r_bottom, r_w, r_h) in rows:
            current = index == self._source_index
            arcade.draw_lbwh_rectangle_filled(
                r_left, r_bottom, r_w, r_h, _SELECTED_BG if current else (30, 42, 56)
            )
            label_text = self._text(
                f"pop:row:{index}",
                source.label,
                r_left + 10,
                r_bottom + r_h / 2,
                PRIMARY_TEXT_COLOR,
                11,
                anchor_y="center",
            )
            fit_button_text(label_text, r_w - 20, 11)
            label_text.draw()
        c_left, c_bottom, c_w, c_h = layout["close"]
        arcade.draw_lbwh_rectangle_filled(c_left, c_bottom, c_w, c_h, _BUTTON_BG)
        self._text(
            "pop:close",
            "Fechar",
            c_left + c_w / 2,
            c_bottom + c_h / 2,
            PRIMARY_TEXT_COLOR,
            13,
            anchor_x="center",
            anchor_y="center",
        ).draw()

    # -- elenco: adicionar e remover pilotos ----------------------------------

    def _remove_selected(self) -> None:
        if self._draft is None or self._selected is None:
            return
        ids = [entry["driver_id"] for entry in self._draft.entries]
        index = ids.index(self._selected)
        name = self._draft.entries[index]["driver_name"]
        error = self._draft.remove_driver(self._selected)
        if error is not None:
            self._set_status(f"Não foi possível remover: {error}", ERROR_COLOR)
            return
        remaining = [entry["driver_id"] for entry in self._draft.entries]
        # O selecionado passa a ser o piloto que ocupava a mesma posicao.
        self._selected = remaining[min(index, len(remaining) - 1)] if remaining else None
        self._ensure_selected_visible()
        self._set_status(
            f"{name} removido do grid; salve para confirmar.", SECONDARY_TEXT_COLOR
        )

    def _request_picker(self) -> None:
        if self._draft is None:
            self._set_status(
                "Monte ou carregue um grid antes de adicionar pilotos.", ERROR_COLOR
            )
            return
        if len(self._draft.entries) >= MAX_GRID_SIZE:
            self._set_status(f"O grid já tem {MAX_GRID_SIZE} pilotos.", ERROR_COLOR)
            return
        self._set_status("Carregando os pilotos do histórico…", SECONDARY_TEXT_COLOR)
        self._run("load-catalog", self._client.fetch_catalog)

    def _open_picker(self, payload: dict) -> None:
        if self._draft is None:
            return
        self._picker = PairPicker(
            entries=tuple(payload.get("entries") or ()),
            in_grid=frozenset(entry["driver_id"] for entry in self._draft.entries),
            room=MAX_GRID_SIZE - len(self._draft.entries),
        )
        self._set_status(
            "Escolha os pilotos e clique em Adicionar.", SECONDARY_TEXT_COLOR
        )

    def _close_picker(self, message: str) -> None:
        self._picker = None
        self._set_status(message, SECONDARY_TEXT_COLOR)

    def _confirm_picker(self) -> None:
        if self._picker is None or self._draft is None:
            return
        chosen = self._picker.selected_entries()
        self._picker = None
        if not chosen:
            self._set_status("Nenhum piloto escolhido.", SECONDARY_TEXT_COLOR)
            return
        added = 0
        errors = []
        for entry in chosen:
            error = self._draft.add_pair(entry)
            if error is None:
                added += 1
            else:
                errors.append(error)
        if errors:
            self._set_status(
                f"{added} adicionado(s); {errors[0]}", ERROR_COLOR
            )
        else:
            self._set_status(
                f"{added} piloto(s) adicionado(s) ao fim do grid; salve para confirmar.",
                SUCCESS_COLOR,
            )

    def _picker_layout(self) -> dict:
        width, height = self.window.width, self.window.height
        left, bottom, panel_w, panel_h = 340, 120, width - 680, height - 240
        return {
            "panel": (left, bottom, panel_w, panel_h),
            "search": (left + 20, bottom + panel_h - 70, panel_w - 40, 34),
            "list_top": bottom + panel_h - 92,
            "list_bottom": bottom + 74,
            "row_h": 28,
            "cancel": (left + 20, bottom + 20, 150, 36),
            "confirm": (left + panel_w - 220, bottom + 20, 200, 36),
        }

    def _picker_rows(self) -> list[tuple[dict, tuple]]:
        """Linhas visiveis do seletor, com a rolagem limitada ao fim da lista."""

        layout = self._picker_layout()
        picker = self._picker
        left, _bottom, panel_w, _panel_h = layout["panel"]
        visible = picker.visible()
        count = max(1, int((layout["list_top"] - layout["list_bottom"]) // layout["row_h"]))
        picker.scroll = max(0, min(picker.scroll, len(visible) - count))
        rows = []
        for offset, entry in enumerate(visible[picker.scroll : picker.scroll + count]):
            y = layout["list_top"] - (offset + 1) * layout["row_h"]
            rows.append((entry, (left + 20, y, panel_w - 40, layout["row_h"] - 2)))
        return rows

    def _picker_click(self, x: float, y: float) -> None:
        layout = self._picker_layout()
        if _inside(x, y, layout["cancel"]):
            self._close_picker("Seleção cancelada.")
            return
        if _inside(x, y, layout["confirm"]):
            self._confirm_picker()
            return
        if not _inside(x, y, layout["panel"]):
            self._close_picker("Seleção cancelada.")
            return
        for entry, rect in self._picker_rows():
            if _inside(x, y, rect):
                error = self._picker.toggle(entry)
                if error is not None:
                    self._set_status(error, ERROR_COLOR)
                return

    def _picker_key(self, symbol: int) -> None:
        if symbol == arcade.key.ESCAPE:
            self._close_picker("Seleção cancelada.")
        elif symbol == arcade.key.ENTER:
            self._confirm_picker()
        elif symbol == arcade.key.BACKSPACE:
            self._picker.set_query(self._picker.query[:-1])

    def _draw_picker(self, width: int, height: int) -> None:
        layout = self._picker_layout()
        # Cobre a janela inteira, para que nada por baixo receba clique ou desenho.
        arcade.draw_lbwh_rectangle_filled(0, 0, width, height, (0, 0, 0, 170))
        left, bottom, panel_w, panel_h = layout["panel"]
        arcade.draw_lbwh_rectangle_filled(left, bottom, panel_w, panel_h, PANEL_COLOR)
        arcade.draw_lbwh_rectangle_outline(
            left, bottom, panel_w, panel_h, PANEL_BORDER_COLOR, 1
        )
        picker = self._picker
        self._text(
            "pk:title",
            "Adicionar pilotos ao grid",
            left + 20,
            bottom + panel_h - 30,
            PRIMARY_TEXT_COLOR,
            16,
            bold=True,
        ).draw()
        self._text(
            "pk:count",
            f"Escolhidos: {len(picker.selected)} · vagas: {picker.room}",
            left + panel_w - 20,
            bottom + panel_h - 30,
            SECONDARY_TEXT_COLOR,
            11,
            anchor_x="right",
        ).draw()
        s_left, s_bottom, s_w, s_h = layout["search"]
        arcade.draw_lbwh_rectangle_filled(s_left, s_bottom, s_w, s_h, _BUTTON_BG)
        query_label = self._text(
            "pk:query",
            picker.query or "Buscar piloto ou equipe",
            s_left + 10,
            s_bottom + s_h / 2,
            PRIMARY_TEXT_COLOR if picker.query else SECONDARY_TEXT_COLOR,
            12,
            anchor_y="center",
        )
        query_label.draw()
        # Cursor como linha: no fim do texto digitado, ou no inicio se o campo esta vazio.
        if caret_visible():
            x = s_left + 10 + (query_label.content_width if picker.query else 0)
            y = s_bottom + s_h / 2
            arcade.draw_line(x, y - 8, x, y + 8, PRIMARY_TEXT_COLOR, 2)
        rows = self._picker_rows()
        self._draw_list_scrollbar(layout, len(self._picker.visible()), self._picker.scroll)
        if not rows:
            self._text(
                "pk:empty",
                "Nenhum piloto encontrado.",
                left + 20,
                layout["list_top"] - 20,
                SECONDARY_TEXT_COLOR,
                11,
            ).draw()
        for index, (entry, rect) in enumerate(rows):
            r_left, r_bottom, r_w, r_h = rect
            chosen = pair_id(entry) in picker.selected
            blocked = picker.blocked_reason(entry)
            arcade.draw_lbwh_rectangle_filled(
                r_left, r_bottom, r_w, r_h, _SELECTED_BG if chosen else (30, 42, 56)
            )
            label = f"{'✓ ' if chosen else ''}{entry['driver_name']} · {entry['team_name']}"
            if blocked is not None and not chosen:
                label += f"  ({blocked})"
            self._text(
                f"pk:row:{index}",
                label[:72],
                r_left + 10,
                r_bottom + r_h / 2,
                SECONDARY_TEXT_COLOR if blocked is not None and not chosen else PRIMARY_TEXT_COLOR,
                11,
                anchor_y="center",
            ).draw()
        for key, text, primary in (
            ("cancel", "Cancelar", False),
            ("confirm", f"Adicionar ({len(picker.selected)})", True),
        ):
            b_left, b_bottom, b_w, b_h = layout[key]
            arcade.draw_lbwh_rectangle_filled(
                b_left, b_bottom, b_w, b_h, _PRIMARY_BG if primary else _BUTTON_BG
            )
            self._text(
                f"pk:btn:{key}",
                text,
                b_left + b_w / 2,
                b_bottom + b_h / 2,
                PRIMARY_TEXT_COLOR,
                13,
                bold=primary,
                anchor_x="center",
                anchor_y="center",
            ).draw()

    def _set_status(self, message: str, color) -> None:
        self._status = message
        self._status_color = color

    # -- geometria ---------------------------------------------------------------

    def _panel_left(self) -> int:
        return self.window.width - _PANEL_TOTAL_WIDTH

    def _buttons(self) -> dict[str, tuple[float, float, float, float]]:
        width, height = self.window.width, self.window.height
        top = height - 150
        display_left, display_w = self._source_display_bounds()
        build_left = self._grid_right() - _BUILD_BUTTON_W
        rects = {
            # Setas dentro do display do nome da corrida, uma em cada extremo.
            "prev-source": (display_left + 4, top + 3, 34, 34),
            "next-source": (display_left + display_w - 38, top + 3, 34, 34),
            "build": (build_left, top, _BUILD_BUTTON_W, _SOURCE_ROW_H),

            "save": (width - 230, 20, 190, 36),
            "discard": (self._panel_left(), 20, 190, 36),
        }
        left = self._panel_left()
        # Setas na primeira linha da caixa, com o centro vertical do nome do piloto.
        # "Escolher corrida" logo a direita do display (entre o display e o build).
        rects["pick-race"] = (
            display_left + display_w + _SOURCE_GAP,
            top,
            _PICK_BUTTON_W,
            _SOURCE_ROW_H,
        )
        rects["move-up"] = (left + _ARROW_UP_X, height - 228, 34, 30)
        rects["move-down"] = (left + _ARROW_DOWN_X, height - 228, 34, 30)
        # Elenco na barra inferior, entre "Voltar" e "Salvar alteracoes".
        # Voltar, Remover e Adicionar: mesma largura de botao e mesmo espaco.
        # Voltar, Remover e Adicionar dividem a largura do grid, com o mesmo espaco.
        action_w = (self._grid_right() - _ACTION_X - 2 * _ACTION_GAP) / 3
        rects["back"] = (_ACTION_X, 20, action_w, 36)
        remove_x = _ACTION_X + action_w + _ACTION_GAP
        rects["remove"] = (remove_x, 20, action_w, 36)
        rects["add"] = (remove_x + action_w + _ACTION_GAP, 20, action_w, 36)
        bottom, top = self._panel_region()
        for i, spec in enumerate(ATTRIBUTES):
            # Mesma faixa do bloco de texto medido no ultimo quadro. Antes do
            # primeiro desenho, usa uma estimativa de 46 px (topo y+30).
            bounds = self._attr_control_bounds.get(spec.name)
            if bounds is None:
                bounds = (self._attribute_y(i) - 16, 46)
            block_bottom, block_h = bounds
            # Botoes fora da area rolavel nao sao desenhados nem clicaveis.
            if block_bottom < bottom or block_bottom + block_h > top:
                continue
            # Quadrado de lado fixo, com o meio na altura do meio do bloco de texto.
            side = _CONTROL_SIDE
            square_y = block_bottom + block_h / 2 - side / 2
            rects[f"minus:{spec.name}"] = (
                left + _CONTROL_X["minus"], square_y, side, side
            )
            rects[f"plus:{spec.name}"] = (
                left + _CONTROL_X["plus"], square_y, side, side
            )
        return rects

    def _table_top(self) -> float:
        """Y da primeira linha de pilotos; as demais descem ROW_HEIGHT cada."""

        return self.window.height - 230

    def _visible_count(self) -> int:
        """Quantas linhas cabem entre o topo da tabela e a area de rodape (y=80)."""

        fits = (self._table_top() - 80) // ROW_HEIGHT + 1
        return max(1, int(fits))

    def _clamp_scroll(self) -> None:
        if self._draft is None:
            self._scroll = 0
            return
        max_scroll = max(0, len(self._draft.entries) - self._visible_count())
        self._scroll = min(max(0, self._scroll), max_scroll)

    def _ensure_selected_visible(self) -> None:
        """Role a tabela o minimo para o piloto selecionado aparecer."""

        if self._draft is None or self._selected is None:
            return
        ids = [entry["driver_id"] for entry in self._draft.entries]
        if self._selected not in ids:
            return
        index = ids.index(self._selected)
        visible = self._visible_count()
        if index < self._scroll:
            self._scroll = index
        elif index >= self._scroll + visible:
            self._scroll = index - visible + 1
        self._clamp_scroll()

    def _row_at(self, x: float, y: float) -> str | None:
        if self._draft is None or x > self._panel_left() - 20:
            return None
        top = self._table_top()
        offset = int((top + ROW_HEIGHT / 2 - y) // ROW_HEIGHT)
        if not 0 <= offset < self._visible_count():
            return None
        index = self._scroll + offset
        entries = self._draft.entries
        if index < len(entries):
            return entries[index]["driver_id"]
        return None

    # -- eventos -----------------------------------------------------------------

    def on_show_view(self) -> None:
        arcade.set_background_color(BACKGROUND_COLOR)

    def on_mouse_motion(self, x, y, dx, dy) -> None:
        self._hover = next(
            (key for key, rect in self._buttons().items() if _inside(x, y, rect)),
            None,
        )

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y) -> None:
        """Role a caixa do piloto ou a tabela, conforme o ponteiro esteja sobre."""

        if self._picker is not None:
            layout = self._picker_layout()
            if _inside(x, y, layout["panel"]):
                self._picker.scroll = max(0, self._picker.scroll - int(scroll_y))
            return
        if self._popup_open:
            if _inside(x, y, self._popup_layout()["panel"]):
                self._popup_scroll = max(0, self._popup_scroll - int(scroll_y))
            return
        if self._draft is None:
            return
        # Scroll horizontal (roda lateral ou trackpad) sobre a tabela e sua barra.
        if scroll_x and _TABLE_SCROLL_LEFT <= x <= self._table_right() and 56 <= y <= self.window.height - 190:
            self._hscroll -= scroll_x * _TABLE_SCROLL_STEP
            self._clamp_hscroll()
            return
        bottom, top = self._panel_region()
        if x >= self._panel_left() and bottom <= y <= top:
            self._panel_scroll -= int(scroll_y) * _PANEL_SCROLL_STEP
            self._clamp_panel_scroll()
            return
        if x > self._panel_left() - 20 or y < 80:
            return
        self._scroll -= int(scroll_y)
        self._clamp_scroll()

    def on_mouse_press(self, x, y, button, modifiers) -> None:
        if self._picker is not None:
            # Com o seletor aberto, so ele recebe cliques.
            if button == arcade.MOUSE_BUTTON_LEFT:
                self._picker_click(x, y)
            return
        if self._size_text is not None:
            if button == arcade.MOUSE_BUTTON_LEFT:
                self._size_click(x, y)
            return
        if self._popup_open:
            if button == arcade.MOUSE_BUTTON_LEFT:
                self._popup_click(x, y)
            return
        self._editing_grid_seed = (
            button == arcade.MOUSE_BUTTON_LEFT
            and self._sources[self._source_index].mode == "random"
            and _inside(x, y, self._seed_bounds())
        )
        for key, rect in self._buttons().items():
            if _inside(x, y, rect):
                self._click(key)
                return
        driver_id = self._row_at(x, y)
        if driver_id is not None:
            self._selected = driver_id

    def _click(self, key: str) -> None:
        if key in ("prev-source", "next-source"):
            step = -1 if key == "prev-source" else 1
            self._source_index = (self._source_index + step) % len(self._sources)
        elif key == "build":
            self.build_grid()
        elif key == "save":
            self.save_changes()
        elif key == "discard":
            self.discard_changes()
        elif key == "pick-race":
            self._open_race_popup()
        elif key == "add":
            self._request_picker()
        elif key == "remove":
            self._remove_selected()
        elif key == "move-up":
            self.move_selected(-1)
        elif key == "move-down":
            self.move_selected(1)
        elif key == "back":
            if self._draft is not None and self._draft.has_changes:
                self._set_status(
                    "Há alterações não salvas: salve ou descarte antes de voltar.",
                    ERROR_COLOR,
                )
            elif self._return_view is not None:
                self.window.show_view(self._return_view)
        elif key.startswith(("minus:", "plus:")):
            action, name = key.split(":", 1)
            self.step_attribute(name, -1 if action == "minus" else 1)

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if self._picker is not None:
            self._picker_key(symbol)
            return
        if self._size_text is not None:
            self._size_key(symbol)
            return
        if self._popup_open:
            self._popup_key_press(symbol)
            return
        if self._editing_grid_seed:
            pasted = handle_clipboard_shortcut(
                self.window, symbol, modifiers, self._grid_seed_text
            )
            if pasted is not None:
                self._grid_seed_text = pasted.text
                self._set_status(
                    pasted.message, SUCCESS_COLOR if pasted.ok else ERROR_COLOR
                )
                return
            if symbol == arcade.key.BACKSPACE:
                self._grid_seed_text = self._grid_seed_text[:-1]
            elif symbol in (arcade.key.ENTER, arcade.key.ESCAPE):
                self._editing_grid_seed = False
            return
        if self._draft is None or not self._draft.entries:
            return
        ids = [entry["driver_id"] for entry in self._draft.entries]
        index = ids.index(self._selected) if self._selected in ids else 0
        if symbol == arcade.key.DOWN:
            self._selected = ids[min(index + 1, len(ids) - 1)]
            self._ensure_selected_visible()
        elif symbol == arcade.key.UP:
            self._selected = ids[max(index - 1, 0)]
            self._ensure_selected_visible()

    def on_text(self, text: str) -> None:
        if self._picker is not None:
            if text.isprintable():
                self._picker.set_query(self._picker.query + text)
            return
        if self._size_text is not None:
            self._size_type(text)
            return
        if self._popup_open:
            self._popup_type(text)
            return
        if self._editing_grid_seed and text.isprintable():
            self._grid_seed_text += text

    # -- desenho -----------------------------------------------------------------

    def _text(self, key: str, value: str, x, y, color, size=12, **style) -> arcade.Text:
        """Texto reutilizado entre quadros; so muda o que mudou."""

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
        self._text(
            "title",
            "Pilotos e grid",
            40,
            height - 60,
            PRIMARY_TEXT_COLOR,
            26,
            bold=True,
        ).draw()
        self._draw_source_selector(height)
        self._draw_table(height)
        self._draw_table_scrollbar()
        self._draw_panel(width, height)
        self._draw_buttons()
        # Status logo abaixo do titulo, fora da barra inferior dos botoes.
        self._text(
            "status",
            self._status,
            40,
            height - 100,
            self._status_color,
            12,
            width=width - 80,
            multiline=True,
        ).draw()
        if self._picker is not None:
            self._draw_picker(width, height)
        if self._size_text is not None:
            self._draw_size_dialog(width, height)
        if self._popup_open:
            self._draw_race_popup(width, height)

    def _draw_source_selector(self, height: int) -> None:
        top = height - 150
        display_left, display_w = self._source_display_bounds()
        arcade.draw_lbwh_rectangle_filled(
            display_left, top, display_w, _SOURCE_ROW_H, PANEL_COLOR
        )
        arcade.draw_lbwh_rectangle_outline(
            display_left, top, display_w, _SOURCE_ROW_H, PANEL_BORDER_COLOR, 1
        )
        label = self._sources[self._source_index].label
        label_text = self._text(
            "source",
            label,
            display_left + display_w / 2,
            top + _SOURCE_ROW_H / 2,
            PRIMARY_TEXT_COLOR,
            12,
            anchor_x="center",
            anchor_y="center",
        )
        # Espaco reservado para as setas e o contador nas extremidades.
        fit_button_text(label_text, display_w - 200, 12)
        label_text.draw()
        self._text(
            "source-count",
            f"{self._source_index + 1}/{len(self._sources)}",
            display_left + display_w - 46,
            top + _SOURCE_ROW_H / 2,
            _HEADER_COLOR,
            9,
            anchor_x="right",
            anchor_y="center",
        ).draw()
        if self._sources[self._source_index].mode == "random":
            left, bottom, width, field_height = self._seed_bounds()
            arcade.draw_lbwh_rectangle_filled(
                left, bottom, width, field_height, PANEL_COLOR
            )
            arcade.draw_lbwh_rectangle_outline(
                left,
                bottom,
                width,
                field_height,
                (111, 127, 148) if self._editing_grid_seed else PANEL_BORDER_COLOR,
                1,
            )
            self._text(
                "grid-seed-label",
                "Semente de grid aleatório",
                left,
                bottom + field_height + 5,
                _HEADER_COLOR,
                9,
            ).draw()
            self._text(
                "grid-seed",
                self._grid_seed_text or "Vazio: backend gera",
                left + 10,
                bottom + field_height / 2,
                PRIMARY_TEXT_COLOR if self._grid_seed_text else SECONDARY_TEXT_COLOR,
                11,
                anchor_y="center",
            ).draw()

    def _grid_right(self) -> int:
        """Borda direita do grid: a da linha selecionada (ver ``_row_at``)."""

        return self._panel_left() - 24

    def _source_display_bounds(self) -> tuple[int, int]:
        """(esquerda, largura) do display da corrida.

        Display, espaco e botao "Montar grid" somam a largura do grid, da borda
        esquerda da tabela (x=40) ate ``_grid_right``.
        """

        grid_w = self._grid_right() - 40
        return 40, grid_w - 2 * _SOURCE_GAP - _PICK_BUTTON_W - _BUILD_BUTTON_W

    def _seed_bounds(self) -> tuple[float, float, float, float]:
        # Mesma margem esquerda e largura da caixa de atributos (400 px).
        return (self._panel_left(), self.window.height - 150, 400, 34)

    def _draw_table(self, height: int) -> None:
        if self._draft is None:
            return
        header_y = height - 200
        self._clamp_hscroll()
        for label, x, anchor in _TABLE_COLUMNS:
            self._table_text(
                f"h:{label}", label, label, x, header_y, _HEADER_COLOR, 10,
                anchor, bold=True,
            )
        self._draw_table_hscrollbar()
        self._clamp_scroll()
        top = self._table_top()
        entries = self._draft.entries
        for i in range(self._scroll, len(entries)):
            entry = entries[i]
            y = top - (i - self._scroll) * ROW_HEIGHT
            if y < 80:
                break
            driver_id = entry["driver_id"]
            if driver_id == self._selected:
                arcade.draw_lbwh_rectangle_filled(
                    36, y - 10, self._panel_left() - 60, ROW_HEIGHT - 2, _SELECTED_BG
                )
            attributes = entry["attributes"]
            cells = {
                "P": (str(i + 1), PRIMARY_TEXT_COLOR),
                "PILOTO": (
                    entry["driver_name"][:24],
                    PRIMARY_TEXT_COLOR,
                ),
                "EQUIPE": (entry["team_name"][:20], SECONDARY_TEXT_COLOR),
                "ARQUÉTIPO": (
                    ARCHETYPE_LABELS.get(
                        attributes["archetype"], attributes["archetype"]
                    ),
                    SECONDARY_TEXT_COLOR,
                ),
            }
            for spec in ATTRIBUTES:
                value = self._draft.value(driver_id, spec.name)
                source = self._draft.source(driver_id, spec.name)
                cells[spec.short] = (
                    _display_value(spec.name, value),
                    SOURCE_COLORS.get(source, PRIMARY_TEXT_COLOR),
                )
            for label, x, anchor in _TABLE_COLUMNS:
                value, color = cells[label]
                self._table_text(
                    f"r{i}:{label}", label, value, x, y, color, 12,
                    anchor, anchor_y="center",
                )

    def _table_right(self) -> float:
        """Borda direita da tabela, antes do painel de detalhes."""

        return self._panel_left() - 24

    def _hscroll_max(self) -> float:
        """Deslocamento maximo: quanto a ultima coluna que rola passa da borda da tabela."""

        last_x = max(x for label, x, _ in _TABLE_COLUMNS if label not in _TABLE_FROZEN)
        needed = 40 + last_x + _TABLE_COLUMN_MARGIN - self._table_right()
        return max(0.0, needed)

    def _clamp_hscroll(self) -> None:
        self._hscroll = min(max(0.0, self._hscroll), self._hscroll_max())

    def _column_x(self, label: str, x: int) -> float:
        """Posicao na tela de uma coluna: as fixas ficam; as demais rolam."""

        if label in _TABLE_FROZEN:
            return 40 + x
        return 40 + x - self._hscroll

    def _table_text(
        self,
        key: str,
        label: str,
        value: str,
        x: int,
        y: float,
        color: tuple[int, ...],
        size: float,
        anchor: str,
        bold: bool = False,
        anchor_y: str = "baseline",
    ) -> None:
        """Desenha uma celula da tabela; as colunas que rolam ficam recortadas na area."""

        text = self._text(
            key, value, self._column_x(label, x), y, color, size,
            bold=bold, anchor_x=anchor, anchor_y=anchor_y,
        )
        if label in _TABLE_FROZEN:
            text.draw()
        else:
            left, right = _TABLE_SCROLL_LEFT, self._table_right()
            # Area de linhas: do cabecalho (height-190) ate o rodape (y=80).
            self._draw_clipped(text, left, 80, right - left, self.window.height - 190 - 80)

    def _draw_table_hscrollbar(self) -> None:
        """Barra horizontal sob a tabela; so aparece quando as colunas nao cabem."""

        max_scroll = self._hscroll_max()
        if max_scroll <= 0:
            return
        left, right = _TABLE_SCROLL_LEFT, self._table_right()
        rail_w = right - left
        thumb_w = max(24.0, rail_w * rail_w / (rail_w + max_scroll))
        travel = rail_w - thumb_w
        thumb_x = left + travel * self._hscroll / max_scroll
        y, h = 62, 6
        arcade.draw_lbwh_rectangle_filled(left, y, rail_w, h, (33, 42, 53))
        arcade.draw_lbwh_rectangle_filled(thumb_x, y, thumb_w, h, (111, 127, 148))

    def _panel_region(self) -> tuple[float, float]:
        """(base, topo) da area rolavel da caixa, abaixo da linha de posicao."""

        return 88.0, self.window.height - 332.0

    def _attribute_y(self, index: int) -> float:
        """Y do atributo ``index`` com a rolagem da caixa aplicada."""

        # Rolar para baixo (rolagem crescendo) sobe o conteudo, por isso soma.
        _, top = self._panel_region()
        return (
            top
            - _PANEL_FIRST_ROW_OFFSET
            - index * _PANEL_ROW_HEIGHT
            + self._panel_scroll
        )

    def _clamp_panel_scroll(self) -> None:
        bottom, top = self._panel_region()
        # A rolagem para quando o ultimo atributo sobe ate a margem de baixo
        # (com espaco para o aviso de rodape); nao sobra area vazia no fim.
        last_row_at_rest = top - _PANEL_FIRST_ROW_OFFSET - (len(ATTRIBUTES) - 1) * _PANEL_ROW_HEIGHT
        max_scroll = max(0, bottom + _PANEL_LAST_ROW_MARGIN - last_row_at_rest)
        self._panel_scroll = int(min(max(0, self._panel_scroll), max_scroll))

    def _draw_clipped(self, text: arcade.Text, x: float, y: float, width: float, height: float) -> None:
        """Desenha ``text`` recortado a caixa (x, y, width, height), em pixels da janela.

        O recorte e restaurado depois: o da area rolavel da caixa continua valendo.
        Assim, mesmo com fonte maior que a prevista (outro SO), o texto nao passa
        da coluna e nao cobre os botoes ao lado.
        """

        ratio = self.window.get_pixel_ratio()
        previous = self.window.ctx.scissor
        left, bottom = int(x * ratio), int(y * ratio)
        right, top = left + int(width * ratio), bottom + int(height * ratio)
        if previous is not None:
            # Interseccao com o recorte atual (area rolavel): o texto nao sai dela.
            prev_x, prev_y, prev_w, prev_h = previous
            left, bottom = max(left, prev_x), max(bottom, prev_y)
            right = min(right, prev_x + prev_w)
            top = min(top, prev_y + prev_h)
        self.window.ctx.scissor = (left, bottom, max(0, right - left), max(0, top - bottom))
        try:
            text.draw()
        finally:
            self.window.ctx.scissor = previous

    def _clip_panel_region(self) -> None:
        """Recorta o desenho na area rolavel (coordenadas da janela em pixels)."""

        bottom, top = self._panel_region()
        left = self._panel_left()
        right = self.window.width - 40
        ratio = self.window.get_pixel_ratio()
        self.window.ctx.scissor = (
            int(left * ratio),
            int(bottom * ratio),
            int((right - left) * ratio),
            int((top - bottom) * ratio),
        )

    def _unclip_panel_region(self) -> None:
        self.window.ctx.scissor = None

    def _draw_table_scrollbar(self) -> None:
        """Barra de rolagem da lista de pilotos, na borda esquerda da tabela.

        O cursor (thumb) mostra qual parte da lista esta visivel e acompanha
        ``self._scroll``. So aparece quando a lista nao cabe inteira.
        """

        if self._draft is None:
            return
        total = len(self._draft.entries)
        visible = self._visible_count()
        if total <= visible:
            return
        rail_top = self._table_top() + ROW_HEIGHT / 2
        rail_bottom = 80
        rail_h = rail_top - rail_bottom
        thumb_h = max(24.0, rail_h * visible / total)
        max_scroll = total - visible
        travel = rail_h - thumb_h
        thumb_top = rail_top - travel * min(self._scroll, max_scroll) / max_scroll
        left, width = 6, 6
        arcade.draw_lbwh_rectangle_filled(left, rail_bottom, width, rail_h, (33, 42, 53))
        arcade.draw_lbwh_rectangle_filled(
            left, thumb_top - thumb_h, width, thumb_h, (111, 127, 148)
        )

    def _draw_panel(self, width: int, height: int) -> None:
        left = self._panel_left()
        bottom, top = 80, height - 200
        # Topo da caixa alinhado ao cabecalho do grid (y=height-200, texto) e base
        # alinhada ao fim das linhas de pilotos (y=80).
        box_top = height - 190
        arcade.draw_lbwh_rectangle_filled(
            left, bottom, width - left - 40, box_top - bottom, PANEL_COLOR
        )
        arcade.draw_lbwh_rectangle_outline(
            left, bottom, width - left - 40, box_top - bottom, PANEL_BORDER_COLOR, 1
        )
        if self._draft is None or self._selected is None:
            return
        if self._panel_owner != self._selected:
            self._panel_owner = self._selected
            self._panel_scroll = 0
        self._clamp_panel_scroll()
        entry = next(e for e in self._draft.entries if e["driver_id"] == self._selected)
        x = left + 24
        # Nome centralizado entre as setas, na mesma linha delas.
        name_center = left + (_ARROW_UP_X + 34 + _ARROW_DOWN_X) / 2
        name_text = self._text(
            "p:name",
            entry["driver_name"],
            name_center,
            height - 213,
            PRIMARY_TEXT_COLOR,
            18,
            bold=True,
            anchor_x="center",
            anchor_y="center",
        )
        fit_button_text(name_text, _ARROW_DOWN_X - _ARROW_UP_X - 34 - 16, 18)
        name_text.draw()
        archetype = ARCHETYPE_LABELS.get(entry["attributes"]["archetype"], "")
        self._text(
            "p:team",
            f"{entry['team_name']} · {archetype}",
            x,
            top - 54,
            SECONDARY_TEXT_COLOR,
            12,
        ).draw()
        profile = entry.get("profile")
        characterization = (
            profile["characterization"]
            if profile
            else "Sem perfil nomeado: atributos sorteados no arquétipo."
        )
        profile_text = self._text(
            "p:profile",
            characterization,
            x,
            top - 68,
            (225, 215, 180) if profile else _HEADER_COLOR,
            11,
            width=width - left - 90,
            multiline=True,
            anchor_y="top",
        )
        # Perfil com no maximo 40 px de altura: a linha "Posicao de largada" vem logo
        # abaixo. Se o texto for longo, a fonte diminui em vez de sobrepor.
        _shrink_to_height(profile_text, 40, 11, 8)
        profile_text.draw()
        position = next(
            index
            for index, item in enumerate(self._draft.entries, start=1)
            if item["driver_id"] == self._selected
        )
        self._text(
            "p:position",
            f"Posição de largada: P{position}",
            x,
            height - 318,
            PRIMARY_TEXT_COLOR,
            11,
            bold=True,
        ).draw()
        self._clip_panel_region()
        for i, spec in enumerate(ATTRIBUTES):
            y = self._attribute_y(i)
            source = self._draft.source(self._selected, spec.name)
            # Os tres textos sao ancorados pelo topo e empilhados; a altura medida
            # de cada um define o bloco. Os botoes e o valor usam essa mesma faixa.
            top_edge = y + 30
            label_text = self._text(
                f"a:{spec.name}:label", spec.label, x, top_edge,
                PRIMARY_TEXT_COLOR, 13, bold=True, anchor_y="top",
            )
            # Nome e dica ficam antes do botao "−": a fonte diminui se preciso.
            fit_button_text(label_text, _PANEL_TEXT_WIDTH, 13)
            label_text.y = top_edge
            hint_text = self._text(
                f"a:{spec.name}:hint", spec.hint, x, top_edge,
                _HEADER_COLOR, 10, anchor_y="top",
            )
            fit_button_text(hint_text, _PANEL_TEXT_WIDTH, 10)
            hint_text.y = top_edge - label_text.content_height - _ATTR_BLOCK_GAP
            source_text = self._text(
                f"a:{spec.name}:source", SOURCE_LABELS.get(source, source), x,
                top_edge, _HEADER_COLOR, 9, anchor_y="top",
            )
            source_text.y = hint_text.y - hint_text.content_height - _ATTR_BLOCK_GAP
            block_bottom = source_text.y - source_text.content_height
            block_h = top_edge - block_bottom
            self._attr_control_bounds[spec.name] = (block_bottom, block_h)
            # Recorte por texto: nada sai do bloco, mesmo com fonte maior.
            clip_bottom, clip_h = block_bottom - 4, block_h + 8
            for text in (label_text, hint_text, source_text):
                self._draw_clipped(text, x, clip_bottom, _PANEL_TEXT_WIDTH, clip_h)
            value = _display_value(
                spec.name, self._draft.value(self._selected, spec.name)
            )
            self._text(
                f"a:{spec.name}:value",
                value,
                left + _CONTROL_X["value"],
                (top_edge + block_bottom) / 2,
                SOURCE_COLORS.get(source, PRIMARY_TEXT_COLOR),
                11,
                bold=True,
                anchor_x="center",
                anchor_y="center",
            ).draw()
        if self._draft.disclaimer:
            self._text(
                "p:disclaimer",
                self._draft.disclaimer,
                x,
                self._attribute_y(len(ATTRIBUTES) - 1) - 40,
                _HEADER_COLOR,
                9,
                width=width - left - 90,
                multiline=True,
                anchor_y="top",
            ).draw()
        self._unclip_panel_region()

    def _draw_buttons(self) -> None:
        # Botoes sao desenhados sem recorte: nada de recortes antigos cortando o "+".
        self.window.ctx.scissor = None
        labels = {
            "prev-source": "‹",
            "next-source": "›",
            "build": "Montar grid",
            "back": "‹ Voltar",
            "save": "Salvar alterações",
            "discard": "Descartar",
            "move-up": "↑",
            "move-down": "↓",
            "add": "Adicionar piloto",
            "remove": "Remover piloto",
            "pick-race": "Escolher corrida",
        }
        for key, rect in self._buttons().items():
            if self._draft is None and key.startswith(
                ("minus:", "plus:", "save", "discard", "move-", "add", "remove")
            ):
                continue
            left, bottom, w, h = rect
            primary = key in ("build", "save")
            hover = self._hover == key
            if primary:
                color = _PRIMARY_HOVER if hover else _PRIMARY_BG
            else:
                color = _BUTTON_HOVER if hover else _BUTTON_BG
            arcade.draw_lbwh_rectangle_filled(left, bottom, w, h, color)
            if key.startswith(("minus:", "plus:")):
                # Sinais desenhados como linhas: nao dependem do glifo da fonte.
                _draw_step_sign(left + w / 2, bottom + h / 2, key.startswith("plus:"))
                continue
            label = labels.get(key) or ("−" if key.startswith("minus:") else "+")
            self._text(
                f"b:{key}",
                label,
                left + w / 2,
                bottom + h / 2,
                PRIMARY_TEXT_COLOR,
                13,
                bold=primary,
                anchor_x="center",
                anchor_y="center",
            ).draw()


def _shrink_to_height(text: arcade.Text, max_height: float, base: float, floor: float) -> None:
    """Reduz a fonte de ``text`` ate que a altura dele caiba em ``max_height`` px."""

    size = base
    text.font_size = size
    while text.content_height > max_height and size > floor:
        size -= 1
        text.font_size = size


def _draw_step_sign(cx: float, cy: float, plus: bool) -> None:
    """Desenha "+" ou "−" centrado em (cx, cy), com bracos de 7 px e traco de 2 px."""

    arm = 7
    color = PRIMARY_TEXT_COLOR
    arcade.draw_line(cx - arm, cy, cx + arm, cy, color, 2)
    if plus:
        arcade.draw_line(cx, cy - arm, cx, cy + arm, color, 2)


def _display_value(name: str, value: float | None) -> str:
    """Valor formatado, ou "—" para piloto recem-adicionado sem atributos locais."""

    return "—" if value is None else format_value(name, value)


def _inside(x: float, y: float, rect) -> bool:
    left, bottom, width, height = rect
    return left <= x <= left + width and bottom <= y <= bottom + height
