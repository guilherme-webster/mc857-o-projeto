"""Estado da tela de pilotos e grid, sem Arcade.

O grid vive no backend (``GET/POST/PATCH /catalog/grid``). Este modulo guarda
a copia recebida, as edicoes ainda nao salvas e as regras de apresentacao:
rotulos, passo de cada atributo e a leitura de "maior e melhor ou pior", que
nao e obvia (``consistency_factor`` maior e *mais* ruido; ``pace_offset_pct``
negativo e mais rapido).

As faixas por arquetipo sao do dominio (``domain/driver_attributes.py``) e o
backend aceita valores fora delas pelo override manual, com origem
``manual``. Aqui so se impede o que o contrato rejeita: fatores precisam ser
positivos.
"""

from __future__ import annotations

from dataclasses import dataclass, field

RANDOM_GRID_SIZE = 20


@dataclass(frozen=True, slots=True)
class AttributeSpec:
    name: str
    label: str
    short: str
    hint: str
    step: float
    minimum: float | None
    decimals: int


ATTRIBUTES = (
    AttributeSpec(
        "pace_offset_pct",
        "Ritmo",
        "RITMO",
        "% na volta; negativo = mais rápido",
        0.05,
        None,
        2,
    ),
    AttributeSpec(
        "consistency_factor",
        "Consistência",
        "CONS",
        "maior = mais variação",
        0.05,
        0.05,
        2,
    ),
    AttributeSpec(
        "tyre_management_factor",
        "Gestão de pneus",
        "PNEU",
        "maior = mais desgaste",
        0.05,
        0.05,
        2,
    ),
    AttributeSpec(
        "aggression",
        "Agressividade",
        "AGR",
        "maior = ataca e arrisca mais",
        0.05,
        0.05,
        2,
    ),
    AttributeSpec(
        "composure",
        "Firmeza",
        "FIRM",
        "maior = defende melhor",
        0.05,
        0.05,
        2,
    ),
)
ATTRIBUTE_BY_NAME = {spec.name: spec for spec in ATTRIBUTES}

ARCHETYPE_LABELS = {
    "aggressive": "Agressivo",
    "balanced": "Equilibrado",
    "conservative": "Conservador",
}
SOURCE_LABELS = {
    "generated": "sorteado",
    "preset": "perfil",
    "manual": "editado",
}


@dataclass(frozen=True, slots=True)
class GridSource:
    """Opcao de montagem: grid aleatorio ou largada de uma corrida."""

    label: str
    mode: str
    race_id: str | None = None

    def request(self, seed: int | None = None) -> dict:
        """Argumentos de ``track_client.build_grid`` para esta opcao."""

        if self.mode == "race":
            return {"mode": "race", "race_id": self.race_id}
        request = {"mode": "random", "size": RANDOM_GRID_SIZE}
        if seed is not None:
            request["seed"] = seed
        return request


def grid_sources(races_payload: dict | None, season: int) -> tuple[GridSource, ...]:
    """Aleatorio primeiro; depois a largada de cada corrida da temporada.

    A lista de corridas vem de ``/api/history/races``; sem ela (historico nao
    construido) so o grid aleatorio e oferecido.
    """

    sources = [GridSource("Aleatório (todo o histórico)", "random")]
    races = (races_payload or {}).get("races") or []
    for race in sorted(races, key=lambda item: item.get("round_number", 0)):
        if race.get("season") != season:
            continue
        sources.append(
            GridSource(
                f"Largada: {race['name']} {season}",
                "race",
                str(race["race_id"]),
            )
        )
    return tuple(sources)


def format_value(name: str, value: float) -> str:
    spec = ATTRIBUTE_BY_NAME[name]
    if name == "pace_offset_pct":
        return f"{value:+.{spec.decimals}f}"
    return f"{value:.{spec.decimals}f}"


@dataclass(slots=True)
class GridDraft:
    """Grid do backend mais as edicoes locais ainda nao enviadas."""

    payload: dict
    edits: dict[str, dict[str, float]] = field(default_factory=dict)
    _index: dict[str, dict] = field(init=False, repr=False, default_factory=dict)

    def __post_init__(self) -> None:
        grid = self.payload.get("grid")
        if not isinstance(grid, list):
            raise ValueError("resposta de grid sem lista de pilotos")
        self._index = {str(entry["driver_id"]): entry for entry in grid}

    @property
    def entries(self) -> list[dict]:
        return self.payload["grid"]

    @property
    def seed(self) -> int | None:
        return self.payload.get("seed")

    @property
    def disclaimer(self) -> str | None:
        return self.payload.get("profiles_disclaimer")

    @property
    def has_changes(self) -> bool:
        return any(self.edits.values())

    def value(self, driver_id: str, name: str) -> float:
        pending = self.edits.get(driver_id, {})
        if name in pending:
            return pending[name]
        return float(self._index[driver_id]["attributes"][name])

    def source(self, driver_id: str, name: str) -> str:
        if name in self.edits.get(driver_id, {}):
            return "manual"
        return str(self._index[driver_id]["attributes"]["sources"].get(name, ""))

    def step(self, driver_id: str, name: str, direction: int) -> float:
        """Some ``direction`` passos ao atributo; devolve o novo valor."""

        spec = ATTRIBUTE_BY_NAME[name]
        value = round(self.value(driver_id, name) + direction * spec.step, 6)
        if spec.minimum is not None:
            value = max(spec.minimum, value)
        value = round(value, spec.decimals)
        original = float(self._index[driver_id]["attributes"][name])
        pending = self.edits.setdefault(driver_id, {})
        if round(original, spec.decimals) == value:
            # Voltar ao valor original nao e uma edicao: preserva a origem.
            pending.pop(name, None)
        else:
            pending[name] = value
        return self.value(driver_id, name)

    def discard(self) -> None:
        self.edits.clear()

    def overrides(self) -> list[dict]:
        """Corpo ``overrides`` de ``PATCH /catalog/grid``."""

        return [
            {"driver_id": driver_id, **fields}
            for driver_id, fields in self.edits.items()
            if fields
        ]
