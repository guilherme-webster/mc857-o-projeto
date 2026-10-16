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
from frontend.arcade.grid_editor import (
    ARCHETYPE_LABELS,
    ATTRIBUTES,
    SOURCE_LABELS,
    GridDraft,
    GridSource,
    format_value,
    grid_sources,
)
from frontend.arcade.theme import (
    BACKGROUND_COLOR,
    ERROR_COLOR,
    PANEL_BORDER_COLOR,
    PANEL_COLOR,
    PRIMARY_TEXT_COLOR,
    SECONDARY_TEXT_COLOR,
    SUCCESS_COLOR,
)

SEASON = 2024
ROW_HEIGHT = 26
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
_TABLE_COLUMNS = (
    ("P", 30, "right"),
    ("PILOTO", 42, "left"),
    ("EQUIPE", 250, "left"),
    ("ARQUÉTIPO", 430, "left"),
    *((spec.short, 610 + i * 78, "right") for i, spec in enumerate(ATTRIBUTES)),
)
_PANEL_LEFT_MARGIN = 40


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
        self._sources: tuple[GridSource, ...] = grid_sources(None, SEASON)
        self._source_index = 0
        self._selected: str | None = None
        self._busy = False
        self._hover: str | None = None
        self._status = "Carregando o grid atual…"
        self._status_color = SECONDARY_TEXT_COLOR
        self._row_texts: list[dict[str, arcade.Text]] = []
        self._texts: dict[str, arcade.Text] = {}
        self._run("load-grid", self._client.fetch_current_grid)
        self._run("load-races", lambda: self._client.fetch_history_races(SEASON))

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
            if kind == "load-races":
                self._sources = grid_sources(payload, SEASON)
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
        message = {
            "load-grid": "Grid atual carregado.",
            "build": "Grid montado. O Iniciar da configuração usará este grid.",
            "save": "Alterações salvas no grid atual.",
        }[kind]
        self._set_status(
            f"{message} {len(self._draft.entries)} pilotos, semente {self._draft.seed}.",
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
        self._start(
            "build",
            lambda: self._client.build_grid(**source.request()),
            f"Montando: {source.label}…",
        )

    def save_changes(self) -> None:
        if self._draft is None or not self._draft.has_changes:
            self._set_status("Nenhuma alteração para salvar.", SECONDARY_TEXT_COLOR)
            return
        overrides = self._draft.overrides()
        self._start(
            "save", lambda: self._client.edit_grid(overrides), "Salvando alterações…"
        )

    def discard_changes(self) -> None:
        if self._draft is not None:
            self._draft.discard()
            self._set_status("Alterações descartadas.", SECONDARY_TEXT_COLOR)

    def step_attribute(self, name: str, direction: int) -> None:
        if self._draft is None or self._selected is None:
            return
        self._draft.step(self._selected, name, direction)

    def _set_status(self, message: str, color) -> None:
        self._status = message
        self._status_color = color

    # -- geometria ---------------------------------------------------------------

    def _panel_left(self) -> int:
        return self.window.width - 560

    def _buttons(self) -> dict[str, tuple[float, float, float, float]]:
        width, height = self.window.width, self.window.height
        top = height - 150
        rects = {
            "prev-source": (40, top, 34, 34),
            "next-source": (520, top, 34, 34),
            "build": (570, top, 170, 34),
            "back": (40, 20, 150, 36),
            "save": (width - 230, 20, 190, 36),
            "discard": (width - 430, 20, 190, 36),
        }
        panel = self._panel_left() + 24
        for i, spec in enumerate(ATTRIBUTES):
            y = height - 380 - i * 64
            rects[f"minus:{spec.name}"] = (panel + 330, y - 6, 34, 30)
            rects[f"plus:{spec.name}"] = (panel + 440, y - 6, 34, 30)
        return rects

    def _row_at(self, x: float, y: float) -> str | None:
        if self._draft is None or x > self._panel_left() - 20:
            return None
        top = self.window.height - 230
        index = int((top + ROW_HEIGHT / 2 - y) // ROW_HEIGHT)
        entries = self._draft.entries
        if 0 <= index < len(entries):
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

    def on_mouse_press(self, x, y, button, modifiers) -> None:
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
        if self._draft is None or not self._draft.entries:
            return
        ids = [entry["driver_id"] for entry in self._draft.entries]
        index = ids.index(self._selected) if self._selected in ids else 0
        if symbol == arcade.key.DOWN:
            self._selected = ids[min(index + 1, len(ids) - 1)]
        elif symbol == arcade.key.UP:
            self._selected = ids[max(index - 1, 0)]

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
        self._text(
            "subtitle",
            "Monte o grid usado pelo Iniciar, veja os perfis e ajuste atributos. "
            "Cores: sorteado · perfil · editado.",
            40,
            height - 92,
            SECONDARY_TEXT_COLOR,
            12,
        ).draw()
        self._draw_source_selector(height)
        self._draw_table(height)
        self._draw_panel(width, height)
        self._draw_buttons()
        self._text(
            "status",
            self._status,
            210,
            32,
            self._status_color,
            12,
            width=width - 700,
            multiline=True,
        ).draw()

    def _draw_source_selector(self, height: int) -> None:
        top = height - 150
        arcade.draw_lbwh_rectangle_filled(80, top, 434, 34, PANEL_COLOR)
        arcade.draw_lbwh_rectangle_outline(80, top, 434, 34, PANEL_BORDER_COLOR, 1)
        label = self._sources[self._source_index].label
        self._text(
            "source",
            label,
            297,
            top + 17,
            PRIMARY_TEXT_COLOR,
            12,
            anchor_x="center",
            anchor_y="center",
        ).draw()
        self._text(
            "source-count",
            f"{self._source_index + 1}/{len(self._sources)}",
            760,
            top + 17,
            _HEADER_COLOR,
            11,
            anchor_y="center",
        ).draw()

    def _draw_table(self, height: int) -> None:
        if self._draft is None:
            return
        header_y = height - 200
        for label, x, anchor in _TABLE_COLUMNS:
            self._text(
                f"h:{label}",
                label,
                40 + x,
                header_y,
                _HEADER_COLOR,
                10,
                bold=True,
                anchor_x=anchor,
            ).draw()
        top = height - 230
        for i, entry in enumerate(self._draft.entries):
            y = top - i * ROW_HEIGHT
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
                    format_value(spec.name, value),
                    SOURCE_COLORS.get(source, PRIMARY_TEXT_COLOR),
                )
            for label, x, anchor in _TABLE_COLUMNS:
                value, color = cells[label]
                self._text(
                    f"r{i}:{label}",
                    value,
                    40 + x,
                    y,
                    color,
                    12,
                    anchor_x=anchor,
                    anchor_y="center",
                ).draw()

    def _draw_panel(self, width: int, height: int) -> None:
        left = self._panel_left()
        bottom, top = 80, height - 200
        arcade.draw_lbwh_rectangle_filled(
            left, bottom, width - left - 40, top - bottom + 30, PANEL_COLOR
        )
        arcade.draw_lbwh_rectangle_outline(
            left, bottom, width - left - 40, top - bottom + 30, PANEL_BORDER_COLOR, 1
        )
        if self._draft is None or self._selected is None:
            return
        entry = next(e for e in self._draft.entries if e["driver_id"] == self._selected)
        x = left + 24
        self._text(
            "p:name",
            entry["driver_name"],
            x,
            top - 10,
            PRIMARY_TEXT_COLOR,
            18,
            bold=True,
        ).draw()
        archetype = ARCHETYPE_LABELS.get(entry["attributes"]["archetype"], "")
        self._text(
            "p:team",
            f"{entry['team_name']} · {archetype}",
            x,
            top - 36,
            SECONDARY_TEXT_COLOR,
            12,
        ).draw()
        profile = entry.get("profile")
        characterization = (
            profile["characterization"]
            if profile
            else "Sem perfil nomeado: atributos sorteados no arquétipo."
        )
        self._text(
            "p:profile",
            characterization,
            x,
            top - 62,
            (225, 215, 180) if profile else _HEADER_COLOR,
            11,
            width=width - left - 90,
            multiline=True,
            anchor_y="top",
        ).draw()
        for i, spec in enumerate(ATTRIBUTES):
            y = height - 380 - i * 64
            source = self._draft.source(self._selected, spec.name)
            self._text(
                f"a:{spec.name}:label",
                spec.label,
                x,
                y + 10,
                PRIMARY_TEXT_COLOR,
                13,
                bold=True,
            ).draw()
            self._text(
                f"a:{spec.name}:hint",
                f"{spec.hint} · {SOURCE_LABELS.get(source, source)}",
                x,
                y - 8,
                _HEADER_COLOR,
                10,
            ).draw()
            value = format_value(
                spec.name, self._draft.value(self._selected, spec.name)
            )
            self._text(
                f"a:{spec.name}:value",
                value,
                x + 407,
                y + 9,
                SOURCE_COLORS.get(source, PRIMARY_TEXT_COLOR),
                14,
                bold=True,
                anchor_x="center",
                anchor_y="center",
            ).draw()
        if self._draft.disclaimer:
            self._text(
                "p:disclaimer",
                self._draft.disclaimer,
                x,
                bottom + 64,
                _HEADER_COLOR,
                9,
                width=width - left - 90,
                multiline=True,
            ).draw()

    def _draw_buttons(self) -> None:
        labels = {
            "prev-source": "‹",
            "next-source": "›",
            "build": "Montar grid",
            "back": "‹ Voltar",
            "save": "Salvar alterações",
            "discard": "Descartar",
        }
        for key, rect in self._buttons().items():
            if self._draft is None and key.startswith(
                ("minus:", "plus:", "save", "discard")
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


def _inside(x: float, y: float, rect) -> bool:
    left, bottom, width, height = rect
    return left <= x <= left + width and bottom <= y <= bottom + height
