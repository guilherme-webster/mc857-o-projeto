from __future__ import annotations

import sqlite3
import statistics
from pathlib import Path

from app.models.models import DriverParameters


def _load_model_parameters():
    """Leia os parametros calibrados, ou devolva ``None`` se ainda nao existirem.

    A ausencia nao e fatal para esta consulta: o cadastro de pilotos continua
    util sem os coeficientes do modelo. Quem exige os parametros e a simulacao,
    que falha explicitamente em ``services/race_simulation.py``.
    """

    from app.config import MODEL_PARAMETERS
    from f1_simulator.adapters.model_parameters_json import read_parameters

    try:
        return read_parameters(Path(MODEL_PARAMETERS))
    except (FileNotFoundError, KeyError, ValueError):
        return None


def load_driver_parameters(
    db_path: Path, *, limit: int | None = None
) -> list[DriverParameters]:

    if not db_path.exists():
        raise FileNotFoundError(f"curated race database not found: {db_path}")

    model = _load_model_parameters()

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        circuit = connection.execute(
            "SELECT circuit_id FROM races LIMIT 1"
        ).fetchone()
        track = model.track(circuit["circuit_id"]) if model and circuit else None
        entries = _read_entries(connection)
        parameters = [
            _build_parameters(connection, entry, model, track) for entry in entries
        ]
    finally:
        connection.close()

    if limit is not None:
        parameters = parameters[:limit]
    return parameters


def _read_entries(connection: sqlite3.Connection) -> list[sqlite3.Row]:

    return connection.execute(
        """
        SELECT
            e.driver_id AS driver_id,
            e.team_id AS team_id,
            e.grid_position AS grid_position,
            d.given_name AS given_name,
            d.family_name AS family_name
        FROM race_entries AS e
        JOIN drivers AS d ON d.driver_id = e.driver_id
        ORDER BY
            CASE WHEN e.grid_position <= 0 THEN 1 ELSE 0 END,
            e.grid_position
        """
    ).fetchall()


def _build_parameters(
    connection: sqlite3.Connection,
    entry: sqlite3.Row,
    model=None,
    track=None,
) -> DriverParameters:
    """Monte os parametros expostos pela API para um participante.

    Divisao de responsabilidades, corrigida em relacao a versao anterior:

    - ``base_lap_time_ms`` e **por piloto**, estimado das voltas daquele carro;
    - degradacao, perda de boxes e risco de abandono sao **parametros do
      modelo**, iguais para todos os carros, vindos da calibracao versionada.

    Antes, os tres ultimos eram estimados por piloto dentro desta funcao e
    estavam errados: a degradacao regredia a corrida inteira (o que mistura
    combustivel e pneu, dois efeitos de sinais opostos) e a perda de boxes usava
    a media de ``duration_ms``, inflada varias vezes pelas paradas sob bandeira
    vermelha. Separar piloto de modelo resolve as duas coisas.
    """

    driver_id = entry["driver_id"]
    lap_times = [
        row["lap_time_ms"]
        for row in connection.execute(
            "SELECT lap_time_ms FROM laps WHERE driver_id = ? ORDER BY lap_number",
            (driver_id,),
        )
    ]
    base_lap_time_ms = _estimate_base_pace(lap_times) if lap_times else None

    degradation = 0.0
    pit_loss = 0.0
    retirement = 0.0
    if model is not None and track is not None:
        compound = model.compound(model.reference_compound)
        degradation = compound.degradation_ms_per_lap * track.tyre_severity
        pit_loss = track.pit_loss_ms
        retirement = model.dnf_hazard_per_lap

    return DriverParameters(
        driver_id=driver_id,
        name=_display_name(entry),
        team_id=entry["team_id"],
        grid_position=entry["grid_position"],
        base_lap_time_ms=base_lap_time_ms,
        degradation_ms_per_lap=degradation,
        pit_loss_ms=pit_loss,
        retirement_per_lap=retirement,
    )


def _estimate_base_pace(lap_times: list[int]) -> float:
    """Mediana do quartil mais rapido: a volta limpa de referencia do piloto.

    As voltas mais rapidas de uma corrida sao tipicamente as de pneu novo,
    combustivel baixo e ar livre -- exatamente a condicao que o modelo assume
    para a referencia, o que permite somar as penalidades sem contar duas vezes
    o mesmo efeito. A mesma definicao e usada pelo backtest em
    ``adapters/persistence/sqlite_race_scenario.py``, de modo que as metricas
    publicadas descrevem o modelo que a aplicacao realmente executa.
    """

    ordered = sorted(lap_times)
    quartile = max(1, len(ordered) // 4)
    return float(statistics.median(ordered[:quartile]))


def _display_name(entry: sqlite3.Row) -> str:

    given = (entry["given_name"] or "").strip()
    family = (entry["family_name"] or "").strip()
    full = f"{given} {family}".strip()
    return full or entry["driver_id"]


_COUNTED_TABLES = ("drivers", "teams", "race_entries", "laps", "pit_stops")


def load_race_summary(db_path: Path) -> dict[str, object]:

    if not db_path.exists():
        raise FileNotFoundError(f"curated race database not found: {db_path}")

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        metadata = {
            row["key"]: row["value"]
            for row in connection.execute("SELECT key, value FROM metadata")
        }
        race = connection.execute("SELECT * FROM races LIMIT 1").fetchone()
        circuit = connection.execute("SELECT * FROM circuits LIMIT 1").fetchone()
        counts = {
            table: connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()[
                "n"
            ]
            for table in _COUNTED_TABLES
        }
    finally:
        connection.close()

    if race is None or circuit is None:
        raise ValueError(f"curated database has no race or circuit: {db_path}")

    return {
        "source": {
            "name": metadata.get("source_name"),
            "version": metadata.get("source_version"),
            "sha256": metadata.get("source_sha256"),
        },
        "race": {
            "race_id": race["race_id"],
            "name": race["name"],
            "season": race["season"],
            "round_number": race["round_number"],
            "race_date": race["race_date"],
            "start_time_utc": race["start_time_utc"],
        },
        "circuit": {
            "circuit_id": circuit["circuit_id"],
            "name": circuit["name"],
            "location": circuit["location"],
            "country": circuit["country"],
            "latitude_deg": circuit["latitude_deg"],
            "longitude_deg": circuit["longitude_deg"],
            "altitude_m": circuit["altitude_m"],
        },
        "counts": counts,
    }
