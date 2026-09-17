from __future__ import annotations

from app.config import DEFAULT_RACE_DB
from app.race_store import get_db_connection, validate_table_exists
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/etl", tags=["Race Inspector (ETL A)"])


@router.get("/tables")
def list_tables() -> dict:

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    )
    tables = [row["name"] for row in cursor.fetchall()]
    conn.close()
    return {"tables": tables, "count": len(tables)}


@router.get("/schema/{table_name}")
def get_table_schema(table_name: str) -> dict:

    conn = get_db_connection()
    validate_table_exists(conn, table_name)
    cursor = conn.cursor()
    cursor.execute(f'PRAGMA table_info("{table_name}");')
    columns = [
        {
            "column_id": row[0],
            "name": row[1],
            "type": row[2],
            "notnull": bool(row[3]),
        }
        for row in cursor.fetchall()
    ]
    conn.close()
    return {"table": table_name, "columns": columns}


@router.get("/preview/{table_name}")
def preview_table_data(
    table_name: str,
    limit: int = Query(
        default=10, ge=1, le=1000, description="Quantidade de linhas a retornar"
    ),
) -> dict:

    conn = get_db_connection()
    validate_table_exists(conn, table_name)
    cursor = conn.cursor()
    cursor.execute(f'SELECT * FROM "{table_name}" LIMIT ?', (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"table": table_name, "count": len(rows), "data": rows}


@router.get("/table/{table_name}")
def get_full_table(table_name: str) -> dict:

    conn = get_db_connection()
    validate_table_exists(conn, table_name)
    cursor = conn.cursor()
    cursor.execute(f'SELECT * FROM "{table_name}"')
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"table": table_name, "total_rows": len(rows), "data": rows}


@router.get("/database/dump")
def dump_entire_database() -> dict:

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    )
    tables = [row["name"] for row in cursor.fetchall()]

    full_database = {}
    for table in tables:
        cursor.execute(f'SELECT * FROM "{table}"')
        full_database[table] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return {
        "database": DEFAULT_RACE_DB.name,
        "tables_count": len(tables),
        "data": full_database,
    }
