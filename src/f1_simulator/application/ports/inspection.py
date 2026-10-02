"""Read-only inspection boundary for curated SQLite databases.

The application owns this contract so UI/HTTP adapters can browse a curated or
historical database (tables, schema, sample and full rows) without embedding
SQL or SQLite exceptions. Implementations expose only read operations and
translate storage-level failures into the errors declared here.
"""

from __future__ import annotations

from typing import Protocol


class DatabaseInspectionError(RuntimeError):
    """Report that a database could not be inspected safely."""


class DatabaseNotFoundError(DatabaseInspectionError):
    """Report that the inspected database file does not exist."""


class TableNotFoundError(DatabaseInspectionError):
    """Report that a requested table is absent from the database."""


class DatabaseInspectionPort(Protocol):
    """Browse a database read-only, returning plain Python values."""

    def list_tables(self, *, with_counts: bool = False) -> list:
        """Return user table names, optionally paired with row counts."""
        ...

    def table_schema(self, table_name: str) -> list[dict]:
        """Return the column definitions of one table."""
        ...

    def preview_table(self, table_name: str, limit: int) -> list[dict]:
        """Return up to ``limit`` rows of one table as dictionaries."""
        ...

    def full_table(self, table_name: str) -> list[dict]:
        """Return every row of one table as dictionaries."""
        ...

    def dump(self) -> dict[str, list[dict]]:
        """Return every user table mapped to all of its rows."""
        ...
