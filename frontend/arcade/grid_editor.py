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

Elenco: pilotos adicionados ou removidos ficam pendentes ate o usuario salvar.
Um piloto recem-adicionado ainda nao tem atributos locais (quem os sorteia e o
backend), entao a tabela o mostra com origem ``pending`` e sem valores.
"""

from __future__ import annotations

from dataclasses import dataclass, field

RANDOM_GRID_SIZE = 20
# Ultima corrida com resultados no historico (Dutch Grand Prix 2026, rodada 12).
# As seguintes do calendario de 2026 nao tem resultados e nao aparecem na tela.
LAST_HISTORY_RACE_ID = "race:1180"
# Mesmos limites do backend (``MIN_GRID_SIZE``/``MAX_GRID_SIZE`` em
# ``backend/app/services/catalog.py``).
MIN_GRID_SIZE = 1
MAX_GRID_SIZE = 40


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
    AttributeSpec(
        "v_max_kmh",
        "Vel. Máx",
        "VMAX",
        "km/h velocidade máxima",
        1.0,
        300.0,
        0,
    ),
    AttributeSpec(
        "a_max_ms2",
        "Aceleração",
        "AMAX",
        "m/s² aceleração base",
        0.1,
        5.0,
        1,
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
    "pending": "a salvar",
}


@dataclass(frozen=True, slots=True)
class GridSource:
    """Opcao de montagem: grid aleatorio ou largada de uma corrida."""

    label: str
    mode: str
    race_id: str | None = None
    season: int | None = None

    def request(self, seed: int | None = None, size: int = RANDOM_GRID_SIZE) -> dict:
        """Argumentos de ``track_client.build_grid`` para esta opcao."""

        if self.mode == "race":
            return {"mode": "race", "race_id": self.race_id}
        request = {"mode": "random", "size": size}
        if seed is not None:
            request["seed"] = seed
        return request


def grid_sources(races_payload: dict | None) -> tuple[GridSource, ...]:
    """Aleatorio primeiro; depois a largada de cada corrida do historico.

    As corridas vem de ``/api/history/races`` (todas as temporadas) e saem em
    ordem cronologica: temporada e, dentro dela, rodada. Sem a lista (historico
    nao construido) so o grid aleatorio e oferecido.
    """

    sources = [GridSource("Aleatório (todo o histórico)", "random")]
    races = (races_payload or {}).get("races") or []
    ordered = sorted(
        races,
        key=lambda item: (item.get("season", 0), item.get("round_number", 0)),
    )
    for race in ordered:
        season = int(race["season"])
        sources.append(
            GridSource(
                f"{race['name']} {season}",
                "race",
                str(race["race_id"]),
                season,
            )
        )
        if str(race["race_id"]) == LAST_HISTORY_RACE_ID:
            # Corridas depois dela ainda nao tem resultados: fora da lista.
            break
    return tuple(sources)


def parse_grid_size(text: str) -> int:
    """Numero de pilotos digitado para um grid aleatorio; ``ValueError`` se invalido."""

    stripped = text.strip()
    if not stripped.isdigit():
        raise ValueError("digite um número inteiro de pilotos")
    value = int(stripped)
    if not MIN_GRID_SIZE <= value <= MAX_GRID_SIZE:
        raise ValueError(
            f"o número de pilotos deve estar entre {MIN_GRID_SIZE} e {MAX_GRID_SIZE}"
        )
    return value


def format_value(name: str, value: float) -> str:
    spec = ATTRIBUTE_BY_NAME[name]
    if name == "pace_offset_pct":
        return f"{value:+.{spec.decimals}f}"
    if spec.decimals == 0:
        return f"{int(round(value))}"
    return f"{value:.{spec.decimals}f}"


@dataclass(slots=True)
class GridDraft:
    """Grid do backend mais as edicoes locais ainda nao enviadas.

    Edicoes de elenco (``add_pair`` e ``remove_driver``) so mudam o rascunho.
    ``patch()`` as traduz para o corpo de ``PATCH /catalog/grid``: ``remove``
    recebe ``driver_id``, ``add`` recebe ``pair_id`` (``piloto@equipe``) e
    ``order`` sempre traz a ordem final quando o elenco muda, para que o
    backend nao precise adivinhar a posicao dos novos pilotos.
    """

    payload: dict
    edits: dict[str, dict[str, float]] = field(default_factory=dict)
    _index: dict[str, dict] = field(init=False, repr=False, default_factory=dict)
    _original_order: tuple[str, ...] = field(init=False, repr=False, default=())
    _order: list[str] = field(init=False, repr=False, default_factory=list)
    # Pilotos originais removidos, na ordem em que saíram.
    _removed: list[str] = field(init=False, repr=False, default_factory=list)
    # driver_id -> entrada pendente; a ordem de insercao e a do ``add`` enviado.
    _added: dict[str, dict] = field(init=False, repr=False, default_factory=dict)

    def __post_init__(self) -> None:
        grid = self.payload.get("grid")
        if not isinstance(grid, list):
            raise ValueError("resposta de grid sem lista de pilotos")
        self._index = {str(entry["driver_id"]): entry for entry in grid}
        if len(self._index) != len(grid):
            raise ValueError("resposta de grid com driver_id duplicado")
        self._original_order = tuple(str(entry["driver_id"]) for entry in grid)
        self._order = list(self._original_order)

    @property
    def entries(self) -> list[dict]:
        """Entradas na ordem pendente, usada diretamente pela tabela."""

        return [self._entry_for(driver_id) for driver_id in self._order]

    def _entry_for(self, driver_id: str) -> dict:
        # Um piloto removido e adicionado de volta (outra equipe) usa a entrada
        # pendente, nao a original.
        if driver_id in self._added:
            return self._added[driver_id]
        return self._index[driver_id]

    @property
    def seed(self) -> int | None:
        return self.payload.get("seed")

    @property
    def disclaimer(self) -> str | None:
        return self.payload.get("profiles_disclaimer")

    @property
    def has_changes(self) -> bool:
        return (
            any(self.edits.values())
            or tuple(self._order) != self._original_order
            or bool(self._removed)
            or bool(self._added)
        )

    def value(self, driver_id: str, name: str) -> float | None:
        """Valor atual do atributo; ``None`` para piloto ainda nao salvo."""

        if driver_id in self._added:
            return None
        pending = self.edits.get(driver_id, {})
        if name in pending:
            return pending[name]
        attrs = self._index[driver_id].get("attributes", {})
        if name in attrs:
            return float(attrs[name])
        if name == "v_max_kmh":
            return 338.0
        if name == "a_max_ms2":
            return 14.1
        return None

    def source(self, driver_id: str, name: str) -> str:
        if driver_id in self._added:
            return "pending"
        if name in self.edits.get(driver_id, {}):
            return "manual"
        attrs = self._index[driver_id].get("attributes", {})
        sources = attrs.get("sources", {})
        if name in sources:
            return str(sources[name])
        return "generated"

    def step(self, driver_id: str, name: str, direction: int) -> float | None:
        """Some ``direction`` passos ao atributo; devolve o novo valor.

        Piloto ainda nao salvo nao tem valor local para ajustar: devolve
        ``None`` e nada muda.
        """

        if driver_id in self._added:
            return None
        spec = ATTRIBUTE_BY_NAME[name]
        cur = self.value(driver_id, name)
        if cur is None:
            return None
        value = round(cur + direction * spec.step, 6)
        if spec.minimum is not None:
            value = max(spec.minimum, value)
        value = round(value, spec.decimals)
        attrs = self._index[driver_id].get("attributes", {})
        if name in attrs:
            original = float(attrs[name])
        elif name == "v_max_kmh":
            original = 338.0
        elif name == "a_max_ms2":
            original = 14.1
        else:
            original = value
        pending = self.edits.setdefault(driver_id, {})
        if round(original, spec.decimals) == value:
            # Voltar ao valor original nao e uma edicao: preserva a origem.
            pending.pop(name, None)
        else:
            pending[name] = value
        return self.value(driver_id, name)

    def move(self, driver_id: str, delta: int) -> bool:
        """Mova um piloto na ordem pendente, sem ultrapassar topo ou fundo.

        ``delta`` e medido em posicoes da tabela. O retorno distingue um
        movimento efetivo de um clique no limite, util para a mensagem da view.
        """

        if type(delta) is not int:
            raise ValueError("delta da ordem deve ser inteiro")
        try:
            current = self._order.index(driver_id)
        except ValueError as error:
            raise KeyError(f"piloto fora do grid: {driver_id}") from error
        target = min(max(current + delta, 0), len(self._order) - 1)
        if target == current:
            return False
        self._order.insert(target, self._order.pop(current))
        return True

    def add_pair(self, entry: dict) -> str | None:
        """Acrescente um piloto (``driver_id``, ``driver_name``, ``team_id``,
        ``team_name``) ao fim do grid pendente.

        Devolve a mensagem de erro, ou ``None`` se foi aceito.
        """

        driver_id = str(entry["driver_id"])
        if driver_id in self._order:
            return f"piloto já está no grid: {entry['driver_name']}"
        if len(self._order) >= MAX_GRID_SIZE:
            return f"o grid aceita no máximo {MAX_GRID_SIZE} pilotos"
        team_id = str(entry["team_id"])
        self._added[driver_id] = {
            "driver_id": driver_id,
            "driver_name": str(entry["driver_name"]),
            "team_id": team_id,
            "team_name": str(entry["team_name"]),
            "pair_id": f"{driver_id}@{team_id}",
            "attributes": {"archetype": "", "sources": {}},
            "profile": None,
        }
        self._order.append(driver_id)
        return None

    def remove_driver(self, driver_id: str) -> str | None:
        """Tire um piloto do grid pendente; devolve a mensagem de erro ou ``None``."""

        if driver_id in self._added:
            del self._added[driver_id]
            self._order.remove(driver_id)
            return None
        if driver_id not in self._index or driver_id in self._removed:
            return "piloto não está no grid"
        if len(self._order) <= MIN_GRID_SIZE:
            return "o grid precisa ter ao menos um piloto"
        self._removed.append(driver_id)
        self._order.remove(driver_id)
        self.edits.pop(driver_id, None)
        return None

    def discard(self) -> None:
        self.edits.clear()
        self._order = list(self._original_order)
        self._removed.clear()
        self._added.clear()

    def overrides(self) -> list[dict]:
        """Corpo ``overrides`` de ``PATCH /catalog/grid``: so pilotos originais."""

        return [
            {"driver_id": driver_id, **fields}
            for driver_id, fields in self.edits.items()
            if fields and driver_id in self._index and driver_id not in self._added
        ]

    def patch(self) -> dict:
        """Payload minimo de ``PATCH /catalog/grid`` para as mudancas locais."""

        payload = {}
        overrides = self.overrides()
        if overrides:
            payload["overrides"] = overrides
        if self._removed:
            payload["remove"] = list(self._removed)
        if self._added:
            payload["add"] = [entry["pair_id"] for entry in self._added.values()]
        if tuple(self._order) != self._original_order or self._removed or self._added:
            payload["order"] = list(self._order)
        return payload
