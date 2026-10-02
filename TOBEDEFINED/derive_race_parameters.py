"""Deriva parametros de simulacao por piloto a partir de um RaceData validado.

Le apenas o agregado canonico do dominio (nunca SQLite ou linhas cruas). O ritmo
base e a mediana do quartil mais rapido; degradacao e a inclinacao linear do
tempo por volta; perda no pit e a media das duracoes. Pilotos sem voltas ficam
com ``base_lap_time_ms`` None e nao entram na simulacao.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from f1_simulator.domain.race_data import RaceData


@dataclass(frozen=True, slots=True)
class SimulationParameters:
    driver_id: str
    name: str
    team_id: str | None
    grid_position: int
    base_lap_time_ms: float | None
    degradation_ms_per_lap: float
    pit_loss_ms: float
    retirement_per_lap: float = 0.0


def derive_parameters(race_data: RaceData) -> list[SimulationParameters]:
    # Voltas na ordem de lap_number: base pace ordena por valor internamente,
    # mas a degradacao (regressao no tempo) precisa da sequencia da corrida.
    laps_by_driver: dict[str, list[int]] = {}
    for lap in sorted(race_data.laps, key=lambda l: (l.driver_id, l.lap_number)):
        laps_by_driver.setdefault(lap.driver_id, []).append(lap.lap_time_ms)

    pit_by_driver: dict[str, list[int]] = {}
    for stop in race_data.pit_stops:
        if stop.duration_ms is not None:
            pit_by_driver.setdefault(stop.driver_id, []).append(stop.duration_ms)

    names = {d.driver_id: _display_name(d) for d in race_data.drivers}

    ordered = sorted(
        race_data.entries,
        key=lambda e: (e.grid_position <= 0, e.grid_position),
    )
    parameters = []
    for entry in ordered:
        lap_times = laps_by_driver.get(entry.driver_id, [])
        parameters.append(
            SimulationParameters(
                driver_id=entry.driver_id,
                name=names.get(entry.driver_id, entry.driver_id),
                team_id=entry.team_id,
                grid_position=entry.grid_position,
                base_lap_time_ms=_base_pace(lap_times) if lap_times else None,
                degradation_ms_per_lap=_degradation(lap_times),
                pit_loss_ms=_pit_loss(pit_by_driver.get(entry.driver_id, [])),
            )
        )
    return parameters


def _base_pace(lap_times: list[int]) -> float:
    quartile = max(1, len(lap_times) // 4)
    return float(statistics.median(sorted(lap_times)[:quartile]))


def _degradation(lap_times: list[int]) -> float:
    count = len(lap_times)
    if count < 3:
        return 0.0
    mean_x = (count - 1) / 2
    mean_y = statistics.fmean(lap_times)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in enumerate(lap_times))
    denominator = sum((x - mean_x) ** 2 for x in range(count))
    if denominator == 0:
        return 0.0
    return max(0.0, numerator / denominator)


def _pit_loss(durations: list[int]) -> float:
    return float(statistics.fmean(durations)) if durations else 0.0


def _display_name(driver) -> str:
    full = f"{driver.given_name or ''} {driver.family_name or ''}".strip()
    return full or driver.driver_id
