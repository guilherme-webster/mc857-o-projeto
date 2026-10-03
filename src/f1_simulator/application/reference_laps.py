"""Tempo de volta de referencia por circuito, tirado do historico de corridas.

O motor detalhado parte de uma volta de referencia "ideal" (pneu novo, pouco
combustivel, ar livre) e soma penalidades a ela. Um ritmo unico em ms/km para
todas as pistas e grosseiro: deu volta de 56 s em Monaco (real ~72-77 s) e de
118 s em Spa (real ~106-110 s), o que tambem distorce a relacao entre a perda
de boxes e o tempo de volta, e portanto a estrategia.

Metodo, deliberadamente simples:

1. por corrida, a **mediana das voltas mais rapidas de cada piloto**
   (``race_results.fastest_lap_time_ms``). A volta mais rapida de um piloto
   costuma acontecer com pouco combustivel e pneu em bom estado -- a mesma
   condicao "ideal" que o motor assume para a referencia --, e a mediana do
   pelotao evita depender do melhor carro;
2. por circuito, a **mediana entre as corridas** do intervalo de temporadas.
   Com tres temporadas, uma corrida de chuva isolada (Suzuka 2022, Sao Paulo
   2024) nao desloca o valor.

Nao e um parametro de comportamento: os perfis de pilotos continuam heuristicos
e o desempenho relativo nao sai daqui. Por isso usar 2024 nao afeta a reserva de
validacao da calibracao do motor; 2024 entra porque Xangai so voltou ao
calendario naquele ano. Mudancas de traçado dentro do intervalo sao ignoradas.

Esta camada so le registros canonicos pela porta ``HistoryRepository``; nao
conhece SQLite, arquivos nem JSON.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import isfinite
from statistics import median

from f1_simulator.application.ports.history import HistoryRepository

METHOD_VERSION = "historical-median-fastest-laps-v1"


@dataclass(frozen=True, slots=True)
class ReferenceLap:
    """Volta de referencia de um circuito e o suporte que a sustenta."""

    circuit_id: str
    reference_lap_time_ms: float
    races: int
    seasons: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.circuit_id, str) or not self.circuit_id.strip():
            raise ValueError("circuit_id deve ser texto nao vazio")
        value = self.reference_lap_time_ms
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value <= 0
        ):
            raise ValueError("reference_lap_time_ms deve ser positivo e finito")
        if type(self.races) is not int or self.races <= 0:
            raise ValueError("races deve ser um inteiro positivo")
        if not self.seasons or any(type(s) is not int for s in self.seasons):
            raise ValueError("seasons deve conter inteiros")


def build_reference_laps(
    repository: HistoryRepository,
    *,
    circuit_ids: Iterable[str],
    seasons: Sequence[int],
) -> tuple[ReferenceLap, ...]:
    """Calcule a volta de referencia de cada circuito pedido.

    Circuitos sem nenhuma corrida com voltas rapidas no intervalo ficam de fora
    do resultado (em vez de receberem um valor inventado); quem consome a
    tabela decide o que fazer com a ausencia. A saida e ordenada por
    ``circuit_id``, para que o artefato gerado seja estavel.
    """

    wanted = sorted(set(circuit_ids))
    season_list = sorted(set(seasons))
    if not wanted:
        raise ValueError("informe ao menos um circuito")
    if not season_list or any(type(s) is not int for s in season_list):
        raise ValueError("seasons deve conter ao menos um inteiro")

    per_circuit: dict[str, list[tuple[int, float]]] = {cid: [] for cid in wanted}
    for season in season_list:
        for race in repository.records("races", season=season):
            circuit_id = race["circuit_id"]
            if circuit_id not in per_circuit:
                continue
            fastest = [
                result["fastest_lap_time_ms"]
                for result in repository.records(
                    "race_results", race_id=race["race_id"]
                )
                if result["fastest_lap_time_ms"] is not None
            ]
            if fastest:
                per_circuit[circuit_id].append((season, float(median(fastest))))

    laps = []
    for circuit_id in wanted:
        races = per_circuit[circuit_id]
        if not races:
            continue
        laps.append(
            ReferenceLap(
                circuit_id=circuit_id,
                reference_lap_time_ms=round(median(ms for _, ms in races), 1),
                races=len(races),
                seasons=tuple(sorted({season for season, _ in races})),
            )
        )
    return tuple(laps)
