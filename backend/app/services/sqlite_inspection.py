from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import HTTPException, status


def connect_readonly(db_path: Path, not_found_detail: str) -> sqlite3.Connection:
    if not db_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail
        )
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def validate_table(connection: sqlite3.Connection, table_name: str) -> None:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tabela '{table_name}' nao existe no banco de dados.",
        )


def list_tables(connection: sqlite3.Connection, *, with_counts: bool = False) -> list:
    names = [
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    if not with_counts:
        return names
    return [
        {"name": name, "rows": connection.execute(
            f'SELECT COUNT(*) FROM "{name}"'
        ).fetchone()[0]}
        for name in names
    ]


def table_schema(connection: sqlite3.Connection, table_name: str) -> list[dict]:
    validate_table(connection, table_name)
    return [
        {"column_id": row[0], "name": row[1], "type": row[2], "notnull": bool(row[3])}
        for row in connection.execute(f'PRAGMA table_info("{table_name}")')
    ]


def preview_table(
    connection: sqlite3.Connection, table_name: str, limit: int
) -> list[dict]:
    validate_table(connection, table_name)
    return [
        dict(row)
        for row in connection.execute(
            f'SELECT * FROM "{table_name}" LIMIT ?', (limit,)
        )
    ]
