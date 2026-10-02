from __future__ import annotations

import sqlite3

from fastapi import HTTPException, status

from app.config import HISTORY_DB
from f1_simulator.application import catalog as core_catalog

_NOT_FOUND = (
    f"history database ({HISTORY_DB.name}) has not been built yet; "
    "run POST /api/history/build to import the full history"
)


def _repository():
    from f1_simulator.adapters.persistence.sqlite_history import (
        SQLiteHistoryRepository,
    )

    if not HISTORY_DB.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return SQLiteHistoryRepository(HISTORY_DB)


def list_entries() -> tuple[core_catalog.CatalogEntry, ...]:
    try:
        return core_catalog.list_entries(_repository())
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error


def build_grid(
    size: int,
    *,
    mode: str,
    manual_pair_ids: list[str],
    seed: int | None,
) -> tuple[tuple, int | None]:
    from f1_simulator.application.build_grid import build_grid as core_build_grid
    from f1_simulator.domain.random_source import SeededRandomSource

    try:
        pool = core_catalog.list_entries(_repository())
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error

    is_random = mode == "random"
    used_seed = seed if seed is not None else (_new_seed() if is_random else None)
    rng = SeededRandomSource(used_seed) if is_random else None

    try:
        grid = core_build_grid(
            size,
            pool,
            mode=mode,
            manual_pair_ids=manual_pair_ids,
            rng=rng,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error

    return grid, used_seed


def _new_seed() -> int:
    import secrets

    # 53 bits fit a JSON client's double without losing reproducibility.
    return secrets.randbelow(2**53)
