from __future__ import annotations

import json
import os
import sqlite3
import tempfile

from fastapi import HTTPException, status

from app.config import CURRENT_GRID_JSON, CURRENT_RACE_JSON, HISTORY_DB
from f1_simulator.application import catalog as core_catalog

_HISTORY_NOT_FOUND = (
    f"history database ({HISTORY_DB.name}) has not been built yet; "
    "run POST /api/history/build to import the full history"
)
_GRID_NOT_FOUND = "no current grid; run POST /catalog/grid to build one"


def _repository():
    from f1_simulator.adapters.persistence.sqlite_history import (
        SQLiteHistoryRepository,
    )

    if not HISTORY_DB.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_HISTORY_NOT_FOUND
        )
    return SQLiteHistoryRepository(HISTORY_DB)


def list_entries() -> tuple[core_catalog.CatalogEntry, ...]:
    try:
        return core_catalog.list_entries(_repository())
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error


def _select_pairs(pool, size, mode, manual_pair_ids, seed):
    from f1_simulator.application.build_grid import build_grid as core_build_grid
    from f1_simulator.domain.random_source import SeededRandomSource

    rng = SeededRandomSource(seed).spawn("grid") if mode == "random" else None
    try:
        return core_build_grid(
            size, pool, mode=mode, manual_pair_ids=manual_pair_ids, rng=rng
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


def _generate(driver_ids, seed):
    from f1_simulator.application.generate_attributes import generate_attributes
    from f1_simulator.domain.random_source import SeededRandomSource

    source = SeededRandomSource(seed).spawn("attributes")
    attributes = generate_attributes(driver_ids, source)
    return {item.driver_id: item for item in attributes}


def build_grid(size, *, mode, manual_pair_ids, seed):
    used_seed = seed if seed is not None else _new_seed()
    pairs = _select_pairs(list_entries(), size, mode, manual_pair_ids, used_seed)
    attributes = _generate([entry.driver_id for entry in pairs], used_seed)
    _write_current_grid(pairs, attributes, used_seed)
    return pairs, attributes, used_seed


def read_current_grid():
    if not CURRENT_GRID_JSON.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_GRID_NOT_FOUND)
    try:
        state = json.loads(CURRENT_GRID_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error
    return _deserialize_grid(state)


def edit_current_grid(overrides):
    from f1_simulator.application.generate_attributes import apply_overrides

    pairs, attributes, seed = read_current_grid()
    patch = {
        item.driver_id: {
            field: value
            for field, value in (
                ("pace_offset_pct", item.pace_offset_pct),
                ("consistency_factor", item.consistency_factor),
                ("tyre_management_factor", item.tyre_management_factor),
            )
            if value is not None
        }
        for item in overrides
    }
    try:
        edited = apply_overrides(list(attributes.values()), patch)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    attributes = {item.driver_id: item for item in edited}
    _write_current_grid(pairs, attributes, seed)
    return pairs, attributes, seed


def run_grid(*, total_laps, track_id, weather):
    from f1_simulator.application.run_grid_simulation import (
        RaceSetup,
        run_grid_simulation,
    )
    from f1_simulator.domain.random_source import SeededRandomSource

    pairs, attributes, seed = read_current_grid()
    setup = RaceSetup(total_laps=total_laps, track_id=track_id, weather=weather)
    rng = SeededRandomSource(seed).spawn("race")
    try:
        result = run_grid_simulation(pairs, attributes, setup, rng=rng)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    result["seed"] = seed
    _write_json(CURRENT_RACE_JSON, result)
    return result


def _serialize_grid(pairs, attributes, seed) -> dict:
    return {
        "seed": seed,
        "grid": [
            {
                "driver_id": entry.driver_id,
                "driver_name": entry.driver_name,
                "team_id": entry.team_id,
                "team_name": entry.team_name,
                "attributes": {
                    "archetype": attributes[entry.driver_id].archetype,
                    "pace_offset_pct": attributes[entry.driver_id].pace_offset_pct,
                    "consistency_factor": attributes[entry.driver_id].consistency_factor,
                    "tyre_management_factor": attributes[
                        entry.driver_id
                    ].tyre_management_factor,
                    "sources": dict(attributes[entry.driver_id].sources),
                },
            }
            for entry in pairs
        ],
    }


def _deserialize_grid(state: dict):
    from f1_simulator.application.build_grid import GridEntry
    from f1_simulator.domain.driver_attributes import DriverAttributes

    pairs = []
    attributes = {}
    for row in state["grid"]:
        pairs.append(
            GridEntry(
                driver_id=row["driver_id"],
                driver_name=row["driver_name"],
                team_id=row["team_id"],
                team_name=row["team_name"],
            )
        )
        attribute = row["attributes"]
        attributes[row["driver_id"]] = DriverAttributes(
            driver_id=row["driver_id"],
            archetype=attribute["archetype"],
            pace_offset_pct=attribute["pace_offset_pct"],
            consistency_factor=attribute["consistency_factor"],
            tyre_management_factor=attribute["tyre_management_factor"],
            sources=attribute["sources"],
        )
    return tuple(pairs), attributes, state["seed"]


def _write_current_grid(pairs, attributes, seed) -> None:
    _write_json(CURRENT_GRID_JSON, _serialize_grid(pairs, attributes, seed))


def _write_json(destination, payload: dict) -> None:
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


def _new_seed() -> int:
    import secrets

    # 53 bits fit a JSON client's double without losing reproducibility.
    return secrets.randbelow(2**53)
