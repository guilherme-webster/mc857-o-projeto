"""Classificacao de um campeonato a partir dos resultados finais de cada etapa.

Regra pura, sem dependencia de interface ou de formato de dados: recebe, por
etapa, a ordem final de chegada e quem abandonou, e devolve a tabela do
campeonato. Nao simula nada e nao consome aleatoriedade.

Pontuacao "F1 oficial": 25-18-15-12-10-8-6-4-2-1 para os dez primeiros, como
no regulamento esportivo da FIA vigente desde 2010. O ponto extra de volta
mais rapida (2019-2024) nao e aplicado: o motor nao publica a volta mais
rapida de cada piloto. Um piloto que abandonou nao pontua, mesmo que a
classificacao o coloque entre os dez, porque o motor nao aplica a regra de
classificacao por 90% da distancia.

Desempate (e ordenacao quando nao ha pontuacao):

- ``"best_average"``: menor posicao media entre as etapas disputadas;
- ``"most_wins"``: mais vitorias.

Persistindo o empate, vale o outro criterio, depois a melhor posicao
individual e por fim o ``driver_id``, para que a tabela seja deterministica.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

F1_POINTS = (25, 18, 15, 12, 10, 8, 6, 4, 2, 1)

Scoring = Literal["f1", "none"]
Tiebreak = Literal["best_average", "most_wins"]


@dataclass(frozen=True, slots=True)
class StageResult:
    """Chegada de um piloto numa etapa: ``position`` comeca em 1."""

    driver_id: str
    position: int
    retired: bool


@dataclass(frozen=True, slots=True)
class ChampionshipRow:
    position: int
    driver_id: str
    points: int
    wins: int
    podiums: int
    average_position: float
    # ``None`` quando o piloto nao disputou a etapa.
    stage_positions: tuple[int | None, ...]
    stage_retired: tuple[bool, ...]


def championship_standings(
    stages: Sequence[Sequence[StageResult]],
    *,
    scoring: Scoring = "f1",
    tiebreak: Tiebreak = "best_average",
) -> list[ChampionshipRow]:
    """Tabela do campeonato apos todas as ``stages``, na ordem recebida."""

    if not stages:
        raise ValueError("o campeonato precisa de pelo menos uma etapa")
    if scoring not in ("f1", "none"):
        raise ValueError(f"pontuacao desconhecida: {scoring!r}")
    if tiebreak not in ("best_average", "most_wins"):
        raise ValueError(f"desempate desconhecido: {tiebreak!r}")

    by_stage: list[Mapping[str, StageResult]] = []
    drivers: list[str] = []
    for index, stage in enumerate(stages, start=1):
        results = {result.driver_id: result for result in stage}
        if len(results) != len(stage):
            raise ValueError(f"etapa {index}: piloto repetido")
        positions = sorted(result.position for result in stage)
        if positions != list(range(1, len(stage) + 1)):
            raise ValueError(f"etapa {index}: posicoes devem ser 1..{len(stage)}")
        by_stage.append(results)
        drivers.extend(d for d in results if d not in drivers)

    rows = []
    for driver_id in drivers:
        entries = [stage.get(driver_id) for stage in by_stage]
        raced = [entry for entry in entries if entry is not None]
        points = sum(_points(entry) for entry in raced) if scoring == "f1" else 0
        rows.append(
            {
                "driver_id": driver_id,
                "points": points,
                "wins": sum(1 for e in raced if e.position == 1 and not e.retired),
                "podiums": sum(1 for e in raced if e.position <= 3 and not e.retired),
                "average_position": sum(e.position for e in raced) / len(raced),
                "best_position": min(e.position for e in raced),
                "stage_positions": tuple(
                    entry.position if entry else None for entry in entries
                ),
                "stage_retired": tuple(
                    bool(entry and entry.retired) for entry in entries
                ),
            }
        )

    def criteria(row: dict) -> tuple:
        average = row["average_position"]
        wins = -row["wins"]
        ordered = (average, wins) if tiebreak == "best_average" else (wins, average)
        return (-row["points"], *ordered, row["best_position"], row["driver_id"])

    rows.sort(key=criteria)
    return [
        ChampionshipRow(
            position=index,
            driver_id=row["driver_id"],
            points=row["points"],
            wins=row["wins"],
            podiums=row["podiums"],
            average_position=row["average_position"],
            stage_positions=row["stage_positions"],
            stage_retired=row["stage_retired"],
        )
        for index, row in enumerate(rows, start=1)
    ]


def _points(result: StageResult) -> int:
    if result.retired or result.position > len(F1_POINTS):
        return 0
    return F1_POINTS[result.position - 1]
