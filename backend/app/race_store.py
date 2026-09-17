from __future__ import annotations

import sqlite3

from app.config import (
    CURRENT_RACE_DB,
    CURRENT_RACE_REPORT,
    DEFAULT_RACE_DB,
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
