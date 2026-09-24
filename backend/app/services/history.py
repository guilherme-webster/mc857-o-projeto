from __future__ import annotations

import json
import sqlite3
from contextlib import closing

from app.config import HISTORY_DB, RAW_SOURCE
from app.services import sqlite_inspection
from app.services.errors import HistoryBuildError

_NOT_FOUND = (
    f"Banco historico ({HISTORY_DB.name}) ainda nao foi gerado. "
    "Rode POST /api/history/build para importar o historico completo."
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


def _connect():
    return closing(sqlite_inspection.connect_readonly(HISTORY_DB, _NOT_FOUND))


def list_tables() -> dict:
    with _connect() as conn:
        tables = sqlite_inspection.list_tables(conn, with_counts=True)
    return {"tables": tables, "count": len(tables)}


def table_schema(table_name: str) -> dict:
    with _connect() as conn:
        return {
            "table": table_name,
            "columns": sqlite_inspection.table_schema(conn, table_name),
        }


def preview_table(table_name: str, limit: int) -> dict:
    with _connect() as conn:
        rows = sqlite_inspection.preview_table(conn, table_name, limit)
    return {"table": table_name, "count": len(rows), "data": rows}


def list_reports() -> dict:
    with _connect() as conn:
        sqlite_inspection.validate_table(conn, "imports")
        reports = [
            json.loads(row[0])
            for row in conn.execute("SELECT report_json FROM imports ORDER BY import_key")
        ]
    return {"count": len(reports), "reports": reports}
