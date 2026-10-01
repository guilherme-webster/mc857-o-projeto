"""Read-only SQLite inspection, keeping SQL and PRAGMA out of consumers."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from f1_simulator.application.ports.inspection import (
    DatabaseInspectionError,
    DatabaseNotFoundError,
    TableNotFoundError,
)


class SQLiteDatabaseInspector:
    """Expose generic read-only browsing of one SQLite file.

    The connection uses URI read-only mode so a missing file is never mistaken
    for a new empty database. Table names are validated against ``sqlite_master``
    before being interpolated, so only existing identifiers reach a query.
    """

    def __init__(self, source: Path) -> None:
        self._source = Path(source).resolve()

    def list_tables(self, *, with_counts: bool = False) -> list:
        with self._connect() as connection:
            return self._list_tables(connection, with_counts=with_counts)

    def table_schema(self, table_name: str) -> list[dict]:
        with self._connect() as connection:
            self._require_table(connection, table_name)
            return [
                {
                    "column_id": row[0],
                    "name": row[1],
                    "type": row[2],
                    "notnull": bool(row[3]),
                }
                for row in connection.execute(f'PRAGMA table_info("{table_name}")')
            ]

    def preview_table(self, table_name: str, limit: int) -> list[dict]:
        with self._connect() as connection:
            self._require_table(connection, table_name)
            return [
                dict(row)
                for row in connection.execute(
                    f'SELECT * FROM "{table_name}" LIMIT ?', (limit,)
                )
            ]

    def full_table(self, table_name: str) -> list[dict]:
        with self._connect() as connection:
            self._require_table(connection, table_name)
            return [dict(row) for row in connection.execute(f'SELECT * FROM "{table_name}"')]

    def dump(self) -> dict[str, list[dict]]:
        with self._connect() as connection:
            names = self._list_tables(connection)
            return {
                name: [dict(row) for row in connection.execute(f'SELECT * FROM "{name}"')]
                for name in names
            }

    def _connect(self):
        if not self._source.is_file():
            raise DatabaseNotFoundError(f"database not found: {self._source}")
        try:
            connection = sqlite3.connect(f"{self._source.as_uri()}?mode=ro", uri=True)
        except sqlite3.Error as error:
            raise DatabaseInspectionError(
                f"cannot open database {self._source}: {error}"
            ) from error
        connection.row_factory = sqlite3.Row
        return closing(connection)

    @staticmethod
    def _list_tables(connection: sqlite3.Connection, *, with_counts: bool = False) -> list:
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
            {
                "name": name,
                "rows": connection.execute(
                    f'SELECT COUNT(*) FROM "{name}"'
                ).fetchone()[0],
            }
            for name in names
        ]

    @staticmethod
    def _require_table(connection: sqlite3.Connection, table_name: str) -> None:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        ).fetchone()
        if not row:
            raise TableNotFoundError(f"table does not exist: {table_name}")
