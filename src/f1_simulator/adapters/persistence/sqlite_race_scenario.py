"""Montagem de cenarios de corrida observados, para validacao do modelo.

Adaptador de saida que le o historico canonico e devolve ``ObservedRace``. O
ritmo de referencia de cada piloto usa **exatamente** a mesma definicao adotada
pelo backend em ``backend/app/loaders/loader.py`` -- a mediana do quartil mais
rapido de suas voltas limpas.

Essa coincidencia e proposital e importante: se as duas definicoes divergissem,
o backtest estaria validando um modelo diferente daquele que a aplicacao
realmente executa, e as metricas publicadas nao descreveriam o produto.
"""

from __future__ import annotations

import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

from f1_simulator.application.backtest_model import ObservedEntry, ObservedRace

#: Mesmo limiar de volta lenta usado na calibracao.
SLOW_LAP_THRESHOLD = 1.07


def estimate_reference_pace_ms(lap_times_ms: list[int]) -> float | None:
    """Mediana do quartil mais rapido: a volta limpa de referencia do piloto.

    As voltas mais rapidas de uma corrida sao tipicamente as de pneu novo,
    combustivel baixo e ar livre -- exatamente a condicao que ``lap_time.py``
    assume para a referencia. E por isso que as penalidades do modelo podem ser
    somadas a este valor sem contar duas vezes o mesmo efeito.

    Devolve ``None`` quando nao ha volta alguma: ausencia e uma condicao
    legivel, nunca zero.
    """

    if not lap_times_ms:
        return None
    ordered = sorted(lap_times_ms)
    quartile = max(1, len(ordered) // 4)
    return float(statistics.median(ordered[:quartile]))


def _connect(database: Path) -> sqlite3.Connection:
    if not database.exists():
        raise FileNotFoundError(f"historico canonico nao encontrado: {database}")
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def list_races(database: Path, seasons: tuple[int, ...]) -> list[str]:
    """Liste os ``race_id`` das temporadas pedidas, em ordem de calendario."""

    connection = _connect(database)
    try:
        placeholders = ",".join("?" * len(seasons))
        return [
            row["race_id"]
            for row in connection.execute(
                f"SELECT race_id FROM races WHERE season IN ({placeholders}) "
                f"ORDER BY season, round_number",
                seasons,
            )
        ]
    finally:
        connection.close()


def load_observed_race(database: Path, race_id: str) -> ObservedRace:
    """Reconstrua uma corrida observada completa a partir do historico.

    ``finish_position`` usa ``classification_order`` quando a posicao final e
    nula -- o que acontece justamente com quem abandonou. Assim todo
    participante recebe uma posicao comparavel, que e o que a metrica de erro de
    posicao exige, sem inventar um resultado para quem nao terminou.
    """

    connection = _connect(database)
    try:
        race = connection.execute(
            "SELECT race_id, name, season, circuit_id FROM races WHERE race_id = ?",
            (race_id,),
        ).fetchone()
        if race is None:
            raise ValueError(f"corrida {race_id!r} nao existe no historico")

        laps: dict[str, dict[int, int]] = defaultdict(dict)
        order: dict[int, dict[str, int]] = defaultdict(dict)
        for row in connection.execute(
            "SELECT driver_id, lap_number, lap_time_ms, position FROM laps "
            "WHERE race_id = ?",
            (race_id,),
        ):
            laps[row["driver_id"]][row["lap_number"]] = row["lap_time_ms"]
            order[row["lap_number"]][row["driver_id"]] = row["position"]
        if not laps:
            raise ValueError(f"corrida {race_id!r} nao tem tempos de volta")

        stops: dict[str, int] = defaultdict(int)
        pit_laps: dict[str, set[int]] = defaultdict(set)
        for row in connection.execute(
            "SELECT driver_id, lap_number FROM pit_stops WHERE race_id = ?",
            (race_id,),
        ):
            stops[row["driver_id"]] += 1
            pit_laps[row["driver_id"]].add(row["lap_number"])

        qualifying = {
            row["driver_id"]: row["best"]
            for row in connection.execute(
                """
                SELECT driver_id,
                       MIN(COALESCE(NULLIF(q3_ms, 0),
                                    NULLIF(q2_ms, 0),
                                    NULLIF(q1_ms, 0))) AS best
                FROM qualifying WHERE race_id = ? GROUP BY driver_id
                """,
                (race_id,),
            )
            if row["best"]
        }

        results = connection.execute(
            """
            SELECT rr.driver_id, rr.team_id, rr.grid_position, rr.finish_position,
                   rr.classification_order, rr.laps_completed, rr.elapsed_time_ms,
                   s.description AS status_text,
                   d.given_name, d.family_name
            FROM race_results AS rr
            JOIN drivers AS d ON d.driver_id = rr.driver_id
            LEFT JOIN statuses AS s ON s.status_id = rr.status_id
            WHERE rr.race_id = ?
            ORDER BY rr.classification_order
            """,
            (race_id,),
        ).fetchall()
    finally:
        connection.close()

    total_laps = max(max(by_lap) for by_lap in laps.values())

    # Ritmo de reserva para quem abandonou cedo demais para ter voltas limpas.
    #
    # Sem ele esses pilotos sairiam do cenario, e a comparacao de abandonos
    # ficaria enviesada: a simulacao poderia retirar carros que o lado
    # observado nem contaria, fazendo o modelo parecer muito pior do que e. O
    # grid precisa conter os mesmos participantes dos dois lados.
    all_references = [
        pace
        for by_lap in laps.values()
        if (pace := estimate_reference_pace_ms(list(by_lap.values()))) is not None
    ]
    field_reference = statistics.median(all_references) if all_references else None

    entries: list[ObservedEntry] = []
    winner_time: int | None = None
    for row in results:
        driver_id = row["driver_id"]
        by_lap = laps.get(driver_id)
        if not by_lap:
            continue
        median_ms = statistics.median(by_lap.values())
        clean = [
            value
            for lap_number, value in by_lap.items()
            if lap_number > 1
            and lap_number not in pit_laps[driver_id]
            and (lap_number - 1) not in pit_laps[driver_id]
            and value <= SLOW_LAP_THRESHOLD * median_ms
        ]
        reference = estimate_reference_pace_ms(clean)
        if reference is None:
            reference = estimate_reference_pace_ms(list(by_lap.values()))
        if reference is None:
            reference = field_reference
        if reference is None:
            continue

        status = (row["status_text"] or "").strip()
        retired = not (status == "Finished" or status.startswith("+"))
        position = row["finish_position"] or row["classification_order"]
        if position == 1 and row["elapsed_time_ms"]:
            winner_time = row["elapsed_time_ms"]

        entries.append(
            ObservedEntry(
                driver_id=driver_id,
                name=f"{row['given_name']} {row['family_name']}".strip(),
                team_id=row["team_id"],
                grid_position=row["grid_position"] or len(results),
                reference_lap_time_ms=reference,
                finish_position=position,
                laps_completed=row["laps_completed"],
                retired=retired,
                stops_made=stops.get(driver_id, 0),
                qualifying_ms=qualifying.get(driver_id),
            )
        )

    if not entries:
        raise ValueError(f"corrida {race_id!r} nao produziu participantes validos")

    flat = {
        (driver_id, lap_number): value
        for driver_id, by_lap in laps.items()
        for lap_number, value in by_lap.items()
    }

    # Trocas de posicao por volta observadas, com a mesma definicao usada
    # do lado simulado.
    lap_numbers = sorted(order)
    observed_changes = 0
    for previous, current in zip(lap_numbers, lap_numbers[1:]):
        before, after = order[previous], order[current]
        observed_changes += sum(
            1 for d in before.keys() & after.keys() if before[d] != after[d]
        )
    churn = observed_changes / len(lap_numbers) if lap_numbers else 0.0

    return ObservedRace(
        race_id=race["race_id"],
        name=race["name"],
        season=race["season"],
        circuit_id=race["circuit_id"],
        total_laps=total_laps,
        entries=tuple(entries),
        winner_total_time_ms=winner_time,
        lap_times_ms=flat,
        position_changes_per_lap=churn,
    )
