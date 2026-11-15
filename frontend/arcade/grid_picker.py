"""Seletor de pilotos para o grid, sem Arcade.

Recebe os pares piloto-equipe do catalogo (``GET /catalog``) e guarda a busca,
a selecao e as regras de elenco: um piloto por grid (escolha uma equipe) e no
maximo as vagas que ainda restam. A janela so desenha e repassa os cliques.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def pair_id(entry: dict) -> str:
    """Mesmo formato de ``piloto@equipe`` aceito por ``POST/PATCH /catalog/grid``."""

    return f"{entry['driver_id']}@{entry['team_id']}"


@dataclass(slots=True)
class PairPicker:
    entries: tuple[dict, ...] = ()
    # driver_ids ja presentes no grid pendente: nao podem ser escolhidos de novo.
    in_grid: frozenset[str] = frozenset()
    # Vagas restantes no grid (limite maximo menos o tamanho atual).
    room: int = 0
    query: str = ""
    # pair_ids escolhidos, na ordem em que foram marcados.
    selected: list[str] = field(default_factory=list)
    # Indice da primeira linha visivel na lista filtrada.
    scroll: int = 0

    def visible(self) -> list[dict]:
        """Pares que batem com a busca (nome do piloto ou da equipe)."""

        needle = self.query.strip().casefold()
        if not needle:
            return list(self.entries)
        return [
            entry
            for entry in self.entries
            if needle in str(entry["driver_name"]).casefold()
            or needle in str(entry["team_name"]).casefold()
        ]

    def blocked_reason(self, entry: dict) -> str | None:
        """Motivo para o par nao poder ser escolhido agora, ou ``None``."""

        if entry["driver_id"] in self.in_grid:
            return "já está no grid"
        key = pair_id(entry)
        if any(
            chosen != key and chosen.split("@", 1)[0] == entry["driver_id"]
            for chosen in self.selected
        ):
            return "já escolhido com outra equipe"
        return None

    def toggle(self, entry: dict) -> str | None:
        """Marque ou desmarque um par; devolve a mensagem de erro ou ``None``."""

        key = pair_id(entry)
        if key in self.selected:
            self.selected.remove(key)
            return None
        reason = self.blocked_reason(entry)
        if reason is not None:
            return f"{entry['driver_name']}: {reason}"
        if len(self.selected) >= self.room:
            if self.room <= 0:
                return "o grid já está no limite de pilotos"
            return f"o grid aceita no máximo {self.room} piloto(s) nesta escolha"
        self.selected.append(key)
        return None

    def selected_entries(self) -> list[dict]:
        """Pares escolhidos, na ordem de escolha."""

        by_id = {pair_id(entry): entry for entry in self.entries}
        return [by_id[key] for key in self.selected if key in by_id]

    def set_query(self, text: str) -> None:
        self.query = text
        self.scroll = 0
