from __future__ import annotations

import json
import os
import sqlite3
import tempfile

from app.config import DEFAULT_RACE_DB, RACE_JSON
from fastapi import HTTPException, status


def _total_laps(db_path) -> int:

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT MAX(lap_number) FROM laps").fetchone()
    finally:
        connection.close()
    return int(row[0]) if row and row[0] else 1


def simulate_current_race() -> dict:

    from app.loaders.loader import load_driver_parameters
    from f1_simulator.domain.race_simulation import Competitor, simulate_race

    if not DEFAULT_RACE_DB.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Banco curado ({DEFAULT_RACE_DB.name}) nao encontrado. "
                "Rode POST /simulation/load antes de simular."
            ),
        )

    parameters = load_driver_parameters(DEFAULT_RACE_DB)
    competitors = tuple(
        Competitor(p.driver_id, p.name, float(p.base_lap_time_ms))
        for p in parameters
        if p.base_lap_time_ms is not None
    )
    result = simulate_race(competitors, _total_laps(DEFAULT_RACE_DB))

    _write_json_atomic(RACE_JSON, result)
    return result


def _write_json_atomic(destination, payload: dict) -> None:

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(name, destination)
    except Exception:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise
