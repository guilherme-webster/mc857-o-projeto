"""Leitura das observacoes de calibracao a partir do historico canonico.

Adaptador de saida: converte o esquema SQLite produzido pelo ETL do Trotman nas
observacoes que ``application/calibrate_model.py`` consome. Nenhuma regra de
modelo mora aqui -- apenas selecao, filtragem e conversao de unidades.

Os filtros abaixo sao **explicitos e auditaveis** porque determinam o que o
modelo chama de "volta limpa". Nenhum deles identifica safety car com certeza:
o Trotman v128 nao registra bandeiras nem status de pista, limitacao ja
documentada na matriz de fontes do plano. O filtro de 107% e uma heuristica
usual da Formula 1, nao uma deteccao de SC/VSC, e o relatorio de calibracao
informa quantas voltas cada regra removeu.
"""

from __future__ import annotations

import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

from f1_simulator.application.calibrate_model import (
    AttritionObservation,
    CalibrationInput,
    GridObservation,
    LapObservation,
    PitLossObservation,
    PositionChurnObservation,
    QualifyingObservation,
    TeamAttritionObservation,
)

#: Voltas acima deste multiplo da mediana do proprio piloto sao descartadas.
#: Captura safety car, bandeira vermelha, trafego pesado e danos, sem conseguir
#: distingui-los entre si.
SLOW_LAP_THRESHOLD = 1.07

#: Faixa plausivel para a perda total de uma passagem pelos boxes. Fora dela, o
#: registro quase sempre corresponde a uma parada sob bandeira vermelha, em que
#: o carro fica minutos imovel e a "perda" deixa de ser comparavel.
MIN_PIT_LOSS_MS = 5_000
MAX_PIT_LOSS_MS = 60_000

#: Situacoes de termino que representam um carro classificado, e nao um
#: abandono. Tudo o mais conta como abandono para a taxa de atrito.
FINISHED_PREFIXES = ("Finished",)

#: Descricoes de termino que indicam contato entre carros. Sao separadas
#: porque o modelo as produz por um mecanismo diferente: disputa de posicao,
#: e nao falha do carro.
CONTACT_STATUSES = (
    "Collision",
    "Collision damage",
    "Accident",
    "Spun off",
    "Damage",
    "Debris",
)


def _connect(database: Path) -> sqlite3.Connection:
    """Abra o banco em modo somente leitura; a calibracao nunca escreve nele."""

    if not database.exists():
        raise FileNotFoundError(f"historico canonico nao encontrado: {database}")
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def load_calibration_input(
    database: Path,
    *,
    seasons: tuple[int, ...],
    minimum_laps_per_driver: int = 20,
) -> tuple[CalibrationInput, dict[str, int]]:
    """Leia o historico e devolva as observacoes mais o diario de exclusoes.

    O segundo elemento do retorno conta quantas voltas cada filtro removeu. Ele
    existe para que o relatorio possa mostrar o custo de cada regra em vez de
    apenas afirmar que as voltas foram "limpas".
    """

    if not seasons:
        raise ValueError("informe ao menos uma temporada para calibrar")

    connection = _connect(database)
    try:
        placeholders = ",".join("?" * len(seasons))
        races = {
            row["race_id"]: row
            for row in connection.execute(
                f"SELECT race_id, circuit_id, season FROM races "
                f"WHERE season IN ({placeholders})",
                seasons,
            )
        }
        if not races:
            raise ValueError(f"nenhuma corrida encontrada para {seasons}")

        circuit_names = {
            row["circuit_id"]: row["name"]
            for row in connection.execute("SELECT circuit_id, name FROM circuits")
        }

        race_ids = list(races)
        race_placeholders = ",".join("?" * len(race_ids))

        pit_laps: dict[tuple[str, str], set[int]] = defaultdict(set)
        for row in connection.execute(
            f"SELECT race_id, driver_id, lap_number FROM pit_stops "
            f"WHERE race_id IN ({race_placeholders})",
            race_ids,
        ):
            pit_laps[(row["race_id"], row["driver_id"])].add(row["lap_number"])

        series: dict[tuple[str, str], dict[int, int]] = defaultdict(dict)
        # Ordem por volta, guardada por corrida: e a materia-prima do proxy
        # de dificuldade de ultrapassagem.
        order: dict[str, dict[int, dict[str, int]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        for row in connection.execute(
            f"SELECT race_id, driver_id, lap_number, lap_time_ms, position "
            f"FROM laps WHERE race_id IN ({race_placeholders})",
            race_ids,
        ):
            series[(row["race_id"], row["driver_id"])][row["lap_number"]] = row[
                "lap_time_ms"
            ]
            order[row["race_id"]][row["lap_number"]][row["driver_id"]] = row[
                "position"
            ]

        grid_positions = {
            (row["race_id"], row["driver_id"]): row["grid_position"]
            for row in connection.execute(
                f"SELECT race_id, driver_id, grid_position FROM race_results "
                f"WHERE race_id IN ({race_placeholders})",
                race_ids,
            )
        }

        # A taxa de abandono precisa ser medida sobre a MESMA populacao que a
        # simulacao coloca na pista: pilotos que efetivamente completaram ao
        # menos uma volta. Incluir quem nao largou inflaria o risco por volta e
        # faria o motor aposentar carros demais.
        # Escalonamento das paradas: desvio da volta da PRIMEIRA parada entre
        # os carros de cada corrida, agregado pela mediana dos eventos.
        first_stop_laps: dict[str, list[int]] = defaultdict(list)
        for row in connection.execute(
            f"SELECT race_id, driver_id, MIN(lap_number) AS lap FROM pit_stops "
            f"WHERE race_id IN ({race_placeholders}) GROUP BY race_id, driver_id",
            race_ids,
        ):
            first_stop_laps[row["race_id"]].append(row["lap"])

        contact_placeholders = ",".join("?" * len(CONTACT_STATUSES))
        attrition_row = connection.execute(
            f"""
            SELECT COUNT(*) AS entries,
                   SUM(CASE WHEN s.description = 'Finished'
                             OR s.description LIKE '+%Lap%'
                            THEN 0 ELSE 1 END) AS retirements,
                   SUM(CASE WHEN s.description IN ({contact_placeholders})
                            THEN 1 ELSE 0 END) AS contact
            FROM race_results AS rr
            JOIN statuses AS s ON s.status_id = rr.status_id
            WHERE rr.race_id IN ({race_placeholders})
              AND EXISTS (
                  SELECT 1 FROM laps AS l
                  WHERE l.race_id = rr.race_id AND l.driver_id = rr.driver_id
              )
            """,
            (*CONTACT_STATUSES, *race_ids),
        ).fetchone()
        # Melhor volta de classificacao por piloto: Q3 quando houve, senao a
        # melhor sessao alcancada. Zeros no dataset significam "nao participou
        # desta fase", nao "volta de zero milissegundos".
        qualifying_best = {
            (row["race_id"], row["driver_id"]): row["best"]
            for row in connection.execute(
                f"""
                SELECT race_id, driver_id,
                       MIN(COALESCE(NULLIF(q3_ms, 0),
                                    NULLIF(q2_ms, 0),
                                    NULLIF(q1_ms, 0))) AS best
                FROM qualifying
                WHERE race_id IN ({race_placeholders})
                GROUP BY race_id, driver_id
                """,
                race_ids,
            )
            if row["best"]
        }

        team_rows = connection.execute(
            f"""
            SELECT rr.team_id AS team_id, t.name AS name,
                   COUNT(*) AS entries,
                   SUM(CASE WHEN s.description = 'Finished'
                             OR s.description LIKE '+%Lap%'
                            THEN 0 ELSE 1 END) AS retirements
            FROM race_results AS rr
            JOIN statuses AS s ON s.status_id = rr.status_id
            JOIN teams AS t ON t.team_id = rr.team_id
            WHERE rr.race_id IN ({race_placeholders})
              AND EXISTS (
                  SELECT 1 FROM laps AS l
                  WHERE l.race_id = rr.race_id AND l.driver_id = rr.driver_id
              )
            GROUP BY rr.team_id, t.name
            """,
            race_ids,
        ).fetchall()
    finally:
        connection.close()

    # Trocas de posicao por volta em cada evento. Conta quantos carros mudaram
    # de posicao entre voltas consecutivas, normalizado pelo numero de voltas.
    churn: list[PositionChurnObservation] = []
    for race_id, by_lap in order.items():
        laps_sorted = sorted(by_lap)
        if len(laps_sorted) < 10:
            continue
        changes = 0
        for previous, current in zip(laps_sorted, laps_sorted[1:]):
            before, after = by_lap[previous], by_lap[current]
            changes += sum(
                1
                for driver_id in before.keys() & after.keys()
                if before[driver_id] != after[driver_id]
            )
        churn.append(
            PositionChurnObservation(
                circuit_id=races[race_id]["circuit_id"],
                changes_per_lap=changes / len(laps_sorted),
            )
        )

    team_attrition = tuple(
        TeamAttritionObservation(
            team_id=row["team_id"],
            name=row["name"],
            entries=row["entries"],
            retirements=row["retirements"] or 0,
        )
        for row in team_rows
    )

    excluded: dict[str, int] = defaultdict(int)
    laps: list[LapObservation] = []
    pit_losses: list[PitLossObservation] = []
    grid: list[GridObservation] = []
    qualifying_pairs: list[QualifyingObservation] = []
    race_lengths: list[int] = []

    for (race_id, driver_id), by_lap in series.items():
        if len(by_lap) < minimum_laps_per_driver:
            excluded["few_laps"] += len(by_lap)
            continue
        race_lengths.append(max(by_lap))
        circuit_id = races[race_id]["circuit_id"]
        stops = pit_laps.get((race_id, driver_id), set())
        median_ms = statistics.median(by_lap.values())
        threshold = SLOW_LAP_THRESHOLD * median_ms

        clean: list[LapObservation] = []
        for lap_number, lap_time_ms in sorted(by_lap.items()):
            if lap_number == 1:
                excluded["first_lap"] += 1
                continue
            if lap_number in stops:
                excluded["pit_in_lap"] += 1
                continue
            if (lap_number - 1) in stops:
                excluded["pit_out_lap"] += 1
                continue
            if lap_time_ms > threshold:
                excluded["slow_lap_over_107pct"] += 1
                continue
            last_stop = max((s for s in stops if s < lap_number), default=0)
            clean.append(
                LapObservation(
                    race_id=race_id,
                    circuit_id=circuit_id,
                    driver_id=driver_id,
                    lap_number=lap_number,
                    tyre_age_laps=lap_number - 1 - last_stop,
                    lap_time_ms=lap_time_ms,
                )
            )
        if len(clean) < 10:
            excluded["driver_race_discarded"] += len(clean)
            continue
        laps.extend(clean)

        # Ritmo limpo do proprio piloto, usado como linha de base das duas
        # medidas seguintes. Usar o ritmo do piloto (e nao o da corrida) evita
        # atribuir a um pit lane lento o que e apenas um carro lento.
        pace = statistics.median(o.lap_time_ms for o in clean)

        for stop_lap in sorted(stops):
            entry, exit_ = by_lap.get(stop_lap), by_lap.get(stop_lap + 1)
            if entry is None or exit_ is None:
                continue
            loss = (entry - pace) + (exit_ - pace)
            if not MIN_PIT_LOSS_MS < loss < MAX_PIT_LOSS_MS:
                excluded["implausible_pit_loss"] += 1
                continue
            pit_losses.append(PitLossObservation(circuit_id, loss))

        best_qualifying = qualifying_best.get((race_id, driver_id))
        if best_qualifying:
            qualifying_pairs.append(
                QualifyingObservation(
                    qualifying_ms=best_qualifying,
                    race_reference_ms=statistics.median(
                        sorted(o.lap_time_ms for o in clean)[
                            : max(1, len(clean) // 4)
                        ]
                    ),
                )
            )

        first_lap = by_lap.get(1)
        start = grid_positions.get((race_id, driver_id))
        if first_lap is not None and start and start > 0:
            grid.append(GridObservation(start, first_lap - pace))

    if not race_lengths:
        raise ValueError("nenhum piloto com voltas suficientes na amostra")

    spreads = [
        statistics.pstdev(laps_of_race)
        for laps_of_race in first_stop_laps.values()
        if len(laps_of_race) >= 10
    ]
    pit_spread = statistics.median(spreads) if spreads else 0.0

    attrition = AttritionObservation(
        entries=attrition_row["entries"],
        retirements=attrition_row["retirements"] or 0,
        mean_race_laps=statistics.fmean(race_lengths),
        contact_retirements=attrition_row["contact"] or 0,
    )

    data = CalibrationInput(
        source_name="jtrotman/formula-1-race-data",
        source_version=128,
        seasons=tuple(sorted(seasons)),
        laps=tuple(laps),
        pit_losses=tuple(pit_losses),
        grid=tuple(grid),
        attrition=attrition,
        pit_window_spread_laps=pit_spread,
        position_churn=tuple(churn),
        qualifying=tuple(qualifying_pairs),
        team_attrition=team_attrition,
        circuit_names=circuit_names,
    )
    return data, dict(excluded)
