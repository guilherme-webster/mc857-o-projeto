from __future__ import annotations

import json
import os
import sqlite3
import tempfile

from app.config import (
    CURRENT_RACE_DB,
    CURRENT_RACE_REPORT,
    DEFAULT_RACE_DB,
    RACE_JSON,
    RAW_SOURCE,
)
from fastapi import HTTPException, status


def get_db_connection() -> sqlite3.Connection:

    if not DEFAULT_RACE_DB.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Arquivo {DEFAULT_RACE_DB} não encontrado no volume.",
        )
    conn = sqlite3.connect(f"file:{DEFAULT_RACE_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def validate_table_exists(conn: sqlite3.Connection, table_name: str) -> None:

    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    )
    if not cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tabela '{table_name}' não existe no banco de dados.",
        )


class RaceLoadError(RuntimeError):

    def __init__(self, message: str, *, reason: str = "storage") -> None:
        super().__init__(message)
        self.reason = reason


def load_race_into_current(race_id: int) -> dict[str, object]:

    from f1_simulator.adapters.datasets.trotman import (
        TrotmanDatasetAdapter,
        TrotmanDatasetError,
    )
    from f1_simulator.adapters.persistence.sqlite_race_data import (
        SQLiteRaceDataWriter,
    )
    from f1_simulator.application.etl import run_race_etl
    from f1_simulator.factories.race_data_factory import RaceDataValidationError

    if not RAW_SOURCE.exists():
        raise RaceLoadError(f"raw source not found: {RAW_SOURCE}", reason="source")

    try:
        dataset = TrotmanDatasetAdapter(RAW_SOURCE)
        writer = SQLiteRaceDataWriter()
        report = run_race_etl(
            dataset,
            writer,
            race_id,
            CURRENT_RACE_DB,
            CURRENT_RACE_REPORT,
            overwrite=True,
        )
    except RaceDataValidationError as error:
        raise RaceLoadError(str(error), reason="validation") from error
    except TrotmanDatasetError as error:
        raise RaceLoadError(str(error), reason="source") from error
    except (OSError, sqlite3.Error) as error:
        raise RaceLoadError(str(error), reason="storage") from error

    return report


def _total_laps(db_path) -> int:

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT MAX(lap_number) FROM laps").fetchone()
    finally:
        connection.close()
    return int(row[0]) if row and row[0] else 1


def simulate_current_race() -> dict:

    from app.engine.loader import load_driver_parameters
    from f1_simulator.domain.race_simulation import Competitor, simulate_race

    if not DEFAULT_RACE_DB.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Banco curado ({DEFAULT_RACE_DB.name}) nao encontrado. "
                "Rode POST /simulation/load antes de simular."
            ),
        )

    parameters = load_driver_parameters(DEFAULT_RACE_DB)
    competitors = tuple(
        Competitor(p.driver_id, p.name, float(p.base_lap_time_ms))
        for p in parameters
        if p.base_lap_time_ms is not None
    )
    result = simulate_race(competitors, _total_laps(DEFAULT_RACE_DB))

    _write_json_atomic(RACE_JSON, result)
    return result


def _write_json_atomic(destination, payload: dict) -> None:

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(name, destination)
    except Exception:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise
