from __future__ import annotations

import sqlite3

from fastapi import HTTPException, status

from app.config import HISTORY_DB, RAW_SOURCE
from app.services.errors import HistoryBuildError
from app.services.inspection import inspector

_NOT_FOUND = (
    f"history database ({HISTORY_DB.name}) has not been built yet; "
    "run POST /api/history/build to import the full history"
)


def build_history() -> dict[str, object]:
    from f1_simulator.adapters.datasets.trotman import TrotmanDatasetError
    from f1_simulator.adapters.datasets.trotman_history import TrotmanHistoryAdapter
    from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryWriter
    from f1_simulator.application.history_etl import run_history_etl
    from f1_simulator.factories.history_factory import HistoryValidationError

    if not RAW_SOURCE.exists():
        raise HistoryBuildError(f"raw source not found: {RAW_SOURCE}", reason="source")

    try:
        return run_history_etl(
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


def _inspector():
    return inspector(HISTORY_DB, _NOT_FOUND)


def list_tables() -> dict:
    tables = _inspector().list_tables(with_counts=True)
    return {"tables": tables, "count": len(tables)}


def table_schema(table_name: str) -> dict:
    return {
        "table": table_name,
        "columns": _inspector().table_schema(table_name),
    }


def preview_table(table_name: str, limit: int) -> dict:
    rows = _inspector().preview_table(table_name, limit)
    return {"table": table_name, "count": len(rows), "data": rows}


def list_reports() -> dict:
    from f1_simulator.adapters.persistence.sqlite_history import (
        SQLiteHistoryRepository,
    )

    if not HISTORY_DB.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND
        )
    try:
        reports = SQLiteHistoryRepository(HISTORY_DB).reports()
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error
    return {"count": len(reports), "reports": reports}


def list_races():
    from f1_simulator.adapters.persistence.sqlite_history import (
        SQLiteHistoryRepository,
    )
    from f1_simulator.application.catalog import list_races as core_list_races

    if not HISTORY_DB.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    try:
        return core_list_races(SQLiteHistoryRepository(HISTORY_DB))
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error
