"""Ponte entre o historico Trotman e o estimador de perfis da issue #40.

Por que esta ponte existe
-------------------------
O metodo de perfilamento de ``domain/driver_profile.py`` foi escrito para
sessoes FastF1, que trazem composto, idade de pneu, clima e status de pista.
Mas ``estimate_profiles`` em si **nao depende dessa fonte**: ele recebe
``LapAssessment`` ja avaliadas e faz o resto -- comparacao por medianas de peso
igual dentro de cada contexto, agregacao por evento e indisponibilidade
explicita. Esse nucleo e agnostico de origem.

Este adaptador constroi ``LapAssessment`` a partir do Trotman, para que o
estimador da #40 possa rodar sem FastF1 instalado nem acesso a rede. O preco e
um contexto mais pobre, e ele fica declarado no proprio dado:

- ``compound`` vale ``"UNKNOWN"`` -- o Trotman nao registra composto;
- ``rainfall`` vale ``False`` -- ausencia de observacao, nao ceu limpo
  confirmado. Nenhuma corrida e afirmada como seca; o campo apenas nao
  particiona os contextos.

A idade do pneu e derivada dos pit stops registrados, exatamente como na
calibracao. O que se preserva do metodo original e o mais importante: a
comparacao so acontece entre pilotos que rodaram o **mesmo** contexto.
"""

from __future__ import annotations

import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

from f1_simulator.domain.driver_profile import LapAssessment, PaceContext, ProfileConfig

#: Mesmo limiar de volta lenta da calibracao, pelo mesmo motivo: sem status de
#: pista no Trotman, safety car e trafego pesado so podem ser tratados como
#: voltas anomalas, nunca identificados.
SLOW_LAP_THRESHOLD = 1.07

#: Marcadores de contexto indisponivel. Existem para tornar visivel, em cada
#: linha, que o recorte e mais pobre que o de uma sessao FastF1.
UNKNOWN_COMPOUND = "UNKNOWN"
ASSUMED_RAINFALL = False


def _connect(database: Path) -> sqlite3.Connection:
    if not database.exists():
        raise FileNotFoundError(f"historico canonico nao encontrado: {database}")
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def assess_trotman_races(
    database: Path,
    race_ids: tuple[str, ...],
    config: ProfileConfig,
    *,
    minimum_laps_per_driver: int = 20,
) -> tuple[tuple[LapAssessment, ...], tuple[str, ...]]:
    """Converta corridas do Trotman em avaliacoes de volta da #40.

    Devolve as avaliacoes e os ``driver_id`` presentes, que e o segundo
    argumento esperado por ``estimate_profiles``.

    Cada volta recebe **todos** os motivos de exclusao aplicaveis, e nao apenas
    o primeiro, preservando a auditoria que o metodo original oferece.
    """

    if not race_ids:
        return (), ()

    connection = _connect(database)
    try:
        placeholders = ",".join("?" * len(race_ids))
        races = {
            row["race_id"]: row
            for row in connection.execute(
                f"SELECT race_id, season, circuit_id FROM races "
                f"WHERE race_id IN ({placeholders})",
                race_ids,
            )
        }
        teams = {
            (row["race_id"], row["driver_id"]): row["team_id"]
            for row in connection.execute(
                f"SELECT race_id, driver_id, team_id FROM race_results "
                f"WHERE race_id IN ({placeholders})",
                race_ids,
            )
        }
        pit_laps: dict[tuple[str, str], set[int]] = defaultdict(set)
        for row in connection.execute(
            f"SELECT race_id, driver_id, lap_number FROM pit_stops "
            f"WHERE race_id IN ({placeholders})",
            race_ids,
        ):
            pit_laps[(row["race_id"], row["driver_id"])].add(row["lap_number"])

        series: dict[tuple[str, str], dict[int, int]] = defaultdict(dict)
        for row in connection.execute(
            f"SELECT race_id, driver_id, lap_number, lap_time_ms FROM laps "
            f"WHERE race_id IN ({placeholders})",
            race_ids,
        ):
            series[(row["race_id"], row["driver_id"])][row["lap_number"]] = row[
                "lap_time_ms"
            ]
    finally:
        connection.close()

    assessments: list[LapAssessment] = []
    drivers: set[str] = set()

    for (race_id, driver_id), by_lap in sorted(series.items()):
        race = races.get(race_id)
        if race is None or len(by_lap) < minimum_laps_per_driver:
            continue
        drivers.add(driver_id)
        session_id = f"{race_id}:R"
        team_id = teams.get((race_id, driver_id))
        stops = pit_laps.get((race_id, driver_id), set())
        threshold = SLOW_LAP_THRESHOLD * statistics.median(by_lap.values())

        for lap_number, lap_time_ms in sorted(by_lap.items()):
            reasons: list[str] = []
            if team_id is None:
                reasons.append("missing_or_ambiguous_team")
            if lap_number == 1:
                reasons.append("first_lap")
            if lap_number in stops:
                reasons.append("pit_lap")
            if (lap_number - 1) in stops:
                reasons.append("out_lap")
            if lap_time_ms is None or lap_time_ms <= 0:
                reasons.append("invalid_lap_time")
            elif lap_time_ms > threshold:
                reasons.append("slow_lap_over_107pct")

            last_stop = max((s for s in stops if s < lap_number), default=0)
            tyre_age = max(0, lap_number - 1 - last_stop)
            stint = sum(1 for s in stops if s < lap_number) + 1

            context = None
            if not reasons:
                context = PaceContext(
                    session_id=session_id,
                    race_id=race_id,
                    season=race["season"],
                    circuit_id=race["circuit_id"],
                    compound=UNKNOWN_COMPOUND,
                    rainfall=ASSUMED_RAINFALL,
                    lap_window_start=(
                        (lap_number - 1) // config.lap_window
                    )
                    * config.lap_window
                    + 1,
                    tyre_age_window_start=(tyre_age // config.tyre_age_window)
                    * config.tyre_age_window,
                )
            assessments.append(
                LapAssessment(
                    session_id=session_id,
                    driver_id=driver_id,
                    team_id=team_id,
                    lap_number=lap_number,
                    stint=stint,
                    lap_time_ms=lap_time_ms,
                    context=context,
                    exclusions=tuple(reasons),
                )
            )

    return tuple(assessments), tuple(sorted(drivers))


def races_before(
    database: Path, race_id: str, *, max_races: int = 12
) -> tuple[str, ...]:
    """Corridas anteriores a ``race_id``, em ordem cronologica de calendario.

    E isto que torna o perfil **fora da amostra**: a corrida que sera simulada
    nunca entra na estimativa do proprio ritmo de seus pilotos. Sem esse corte,
    o experimento mediria memorizacao.

    A janela e limitada porque o ritmo relativo de um carro muda ao longo da
    temporada; misturar o inicio de uma era com o fim de outra atribuiria a um
    piloto uma forma que ele ja nao tem.
    """

    connection = _connect(database)
    try:
        target = connection.execute(
            "SELECT season, round_number FROM races WHERE race_id = ?", (race_id,)
        ).fetchone()
        if target is None:
            raise ValueError(f"corrida {race_id!r} nao existe no historico")
        rows = connection.execute(
            """
            SELECT race_id FROM races
            WHERE (season < ?) OR (season = ? AND round_number < ?)
            ORDER BY season DESC, round_number DESC
            LIMIT ?
            """,
            (target["season"], target["season"], target["round_number"], max_races),
        ).fetchall()
    finally:
        connection.close()
    return tuple(row["race_id"] for row in reversed(rows))
