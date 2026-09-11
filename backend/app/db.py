from __future__ import annotations

import sqlite3

from app.config import DEFAULT_RACE_DB
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
