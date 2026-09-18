from __future__ import annotations

from contextlib import closing

from app.config import DEFAULT_RACE_DB
from app.services import sqlite_inspection

_NOT_FOUND = f"Arquivo {DEFAULT_RACE_DB} nao encontrado no volume."


def _connect():
    return closing(sqlite_inspection.connect_readonly(DEFAULT_RACE_DB, _NOT_FOUND))


def list_tables() -> list[str]:
    with _connect() as conn:
        return sqlite_inspection.list_tables(conn)


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


def full_table(table_name: str) -> dict:
    with _connect() as conn:
        sqlite_inspection.validate_table(conn, table_name)
        rows = [dict(r) for r in conn.execute(f'SELECT * FROM "{table_name}"')]
    return {"table": table_name, "total_rows": len(rows), "data": rows}


def dump_database() -> dict:
    with _connect() as conn:
        names = sqlite_inspection.list_tables(conn)
        data = {
            name: [dict(r) for r in conn.execute(f'SELECT * FROM "{name}"')]
            for name in names
        }
    return {"database": DEFAULT_RACE_DB.name, "tables_count": len(names), "data": data}
