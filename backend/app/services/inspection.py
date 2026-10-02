from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException, status

from f1_simulator.application.ports.inspection import (
    DatabaseInspectionError,
    DatabaseNotFoundError,
    TableNotFoundError,
)
from f1_simulator.adapters.persistence.sqlite_inspection import (
    SQLiteDatabaseInspector,
)


class _HTTPInspector:
    def __init__(self, db_path: Path, not_found_detail: str) -> None:
        if not db_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail
            )
        self._inspector = SQLiteDatabaseInspector(db_path)

    def list_tables(self, *, with_counts: bool = False) -> list:
        with self._translate():
            return self._inspector.list_tables(with_counts=with_counts)

    def table_schema(self, table_name: str) -> list[dict]:
        with self._translate():
            return self._inspector.table_schema(table_name)

    def preview_table(self, table_name: str, limit: int) -> list[dict]:
        with self._translate():
            return self._inspector.preview_table(table_name, limit)

    def full_table(self, table_name: str) -> list[dict]:
        with self._translate():
            return self._inspector.full_table(table_name)

    def dump(self) -> dict[str, list[dict]]:
        with self._translate():
            return self._inspector.dump()

    @contextmanager
    def _translate(self):
        try:
            yield
        except DatabaseNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
            ) from error
        except TableNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
            ) from error
        except DatabaseInspectionError as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
            ) from error


def inspector(db_path: Path, not_found_detail: str | None = None) -> _HTTPInspector:
    detail = not_found_detail or f"file not found: {db_path}"
    return _HTTPInspector(db_path, detail)
