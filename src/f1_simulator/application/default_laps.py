"""Derive um número padrão de voltas rastreável para configurar um circuito.

O histórico observado tem precedência porque preserva as voltas realmente
completadas no evento mais recente do histórico canônico Trotman. Isso também
faz uma corrida encurtada por bandeira vermelha virar deliberadamente o padrão
observado; o caso de uso não infere a distância originalmente programada.

Sem uma observação utilizável, a regra assumida escolhe o menor inteiro de
voltas cuja distância seja estritamente maior que 305 km, ou 260 km em Mônaco.
Mônaco é identificado pelo ID estável do circuito Trotman, nunca pelo nome de
exibição traduzível. A geometria FastF1 reduzida é aproximada, portanto essa
reserva pode divergir uma ou duas voltas da distância oficial.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from f1_simulator.application.ports.history import HistoryRepository

LATEST_OBSERVED_RACE = "latest_observed_race"
ASSUMED_DISTANCE_RULE = "assumed_distance_rule"
ASSUMED_DISTANCE_RULE_VERSION = "assumed-distance-rule-v1"

STANDARD_DISTANCE_M = 305_000.0
MONACO_DISTANCE_M = 260_000.0
MONACO_CIRCUIT_ID = "circuit:6"


@dataclass(frozen=True, slots=True)
class DefaultLapsRace:
    """Proveniência canônica da corrida histórica que forneceu o padrão."""

    race_id: str
    season: int
    round_number: int


@dataclass(frozen=True, slots=True)
class DefaultLaps:
    """Padrão de voltas e sua proveniência observada ou explicitamente assumida."""

    laps: int
    source: Literal["latest_observed_race", "assumed_distance_rule"]
    race: DefaultLapsRace | None = None


def default_laps_for_circuit(
    circuit_id: str,
    lap_length_m: float,
    history: HistoryRepository | None = None,
) -> DefaultLaps:
    """Devolva o padrão de um circuito canônico.

    ``lap_length_m`` só é consultado quando não existe observação de volta
    completa na corrida mais recente. O repositório é opcional para que um
    backend sem histórico construído continue listando as pistas com geometria.
    """

    canonical_id = _canonical_circuit_id(circuit_id)
    if history is not None:
        observed = _latest_observed_default(canonical_id, history)
        if observed is not None:
            return observed
    return _assumed_distance_default(canonical_id, lap_length_m)


def _latest_observed_default(
    circuit_id: str, history: HistoryRepository
) -> DefaultLaps | None:
    races = tuple(history.records("races", circuit_id=circuit_id))
    if not races:
        return None
    newest_first = sorted(
        races,
        key=lambda race: (
            _required_int(race["season"]),
            _required_int(race["round_number"]),
        ),
        reverse=True,
    )
    for race in newest_first:
        race_id = _required_text(race["race_id"])
        completed = [
            _required_int(result["laps_completed"])
            for result in history.records("race_results", race_id=race_id)
        ]
        observed_laps = max(completed, default=0)
        if observed_laps < 1:
            continue
        return DefaultLaps(
            laps=observed_laps,
            source=LATEST_OBSERVED_RACE,
            race=DefaultLapsRace(
                race_id=race_id,
                season=_required_int(race["season"]),
                round_number=_required_int(race["round_number"]),
            ),
        )
    return None


def _assumed_distance_default(circuit_id: str, lap_length_m: float) -> DefaultLaps:
    if isinstance(lap_length_m, bool) or not isinstance(lap_length_m, (int, float)):
        raise ValueError("lap_length_m deve ser numérico")
    if not math.isfinite(lap_length_m) or lap_length_m <= 0:
        raise ValueError("lap_length_m deve ser finito e positivo")
    target_m = (
        MONACO_DISTANCE_M if circuit_id == MONACO_CIRCUIT_ID else STANDARD_DISTANCE_M
    )
    return DefaultLaps(
        laps=math.floor(target_m / lap_length_m) + 1,
        source=ASSUMED_DISTANCE_RULE,
    )


def _canonical_circuit_id(circuit_id: str) -> str:
    if not isinstance(circuit_id, str) or not circuit_id.strip():
        raise ValueError("circuit_id deve ser texto não vazio")
    value = circuit_id.strip()
    return value if value.startswith("circuit:") else f"circuit:{value}"


def _required_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("inteiro do histórico canônico ausente ou inválido")
    return value


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("identificador do histórico canônico ausente ou inválido")
    return value
