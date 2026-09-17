from __future__ import annotations

import sqlite3

from app.config import HISTORY_DB, RAW_SOURCE
from fastapi import HTTPException, status


def get_history_connection() -> sqlite3.Connection:

    if not HISTORY_DB.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Banco historico ({HISTORY_DB.name}) ainda nao foi gerado. "
                "Rode POST /api/history/build para importar o historico completo."
            ),
        )
    connection = sqlite3.connect(f"file:{HISTORY_DB}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def validate_history_table(connection: sqlite3.Connection, table_name: str) -> None:

    cursor = connection.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    )
    if not cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tabela '{table_name}' nao existe no banco historico.",
        )


class HistoryBuildError(RuntimeError):

    def __init__(self, message: str, *, reason: str = "storage") -> None:
        super().__init__(message)
        self.reason = reason


def build_history() -> dict[str, object]:

    from f1_simulator.adapters.datasets.trotman import TrotmanDatasetError
    from f1_simulator.adapters.datasets.trotman_history import TrotmanHistoryAdapter
    from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryWriter
    from f1_simulator.application.history_etl import run_history_etl
    from f1_simulator.factories.history_factory import HistoryValidationError

    if not RAW_SOURCE.exists():
        raise HistoryBuildError(
            f"raw source not found: {RAW_SOURCE}", reason="source"
        )

    try:
        report = run_history_etl(
            TrotmanHistoryAdapter(RAW_SOURCE),
            SQLiteHistoryWriter(),
            HISTORY_DB,
            overwrite=True,
        )
    except HistoryValidationError as error:
        raise HistoryBuildError(str(error), reason="validation") from error
    except TrotmanDatasetError as error:
        raise HistoryBuildError(str(error), reason="source") from error
    except (OSError, sqlite3.Error) as error:
        raise HistoryBuildError(str(error), reason="storage") from error

    return report
