from __future__ import annotations

from app.config import DEFAULT_RACE_DB
from app.services.inspection import inspector


def _inspector():
    return inspector(DEFAULT_RACE_DB)


def list_tables() -> list[str]:
    return _inspector().list_tables()


def table_schema(table_name: str) -> dict:
    return {
        "table": table_name,
        "columns": _inspector().table_schema(table_name),
    }


def preview_table(table_name: str, limit: int) -> dict:
    rows = _inspector().preview_table(table_name, limit)
    return {"table": table_name, "count": len(rows), "data": rows}


def full_table(table_name: str) -> dict:
    rows = _inspector().full_table(table_name)
    return {"table": table_name, "total_rows": len(rows), "data": rows}


def dump_database() -> dict:
    data = _inspector().dump()
    return {
        "database": DEFAULT_RACE_DB.name,
        "tables_count": len(data),
        "data": data,
    }
