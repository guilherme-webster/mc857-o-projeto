from __future__ import annotations

from pathlib import Path


def _load_race_data(db_path: Path):
    from f1_simulator.adapters.persistence.sqlite_race_data_repository import (
        SQLiteRaceDataRepository,
    )
    from f1_simulator.application.ports.race_data import (
        RaceDataNotFoundError,
        RaceDataRepositoryError,
    )

    if not db_path.exists():
        raise FileNotFoundError(f"curated race database not found: {db_path}")

    repository = SQLiteRaceDataRepository(db_path)
    try:
        race_ids = repository.list_race_ids()
        if not race_ids:
            raise ValueError(f"curated database has no race: {db_path}")
        return repository.get_race(race_ids[0])
    except (RaceDataNotFoundError, RaceDataRepositoryError) as error:
        raise ValueError(str(error)) from error


def load_driver_parameters(db_path: Path, *, limit: int | None = None) -> list:
    from f1_simulator.application.derive_race_parameters import derive_parameters

    parameters = derive_parameters(_load_race_data(db_path))
    return parameters[:limit] if limit is not None else parameters


def load_total_laps(db_path: Path) -> int:
    race_data = _load_race_data(db_path)
    return max((lap.lap_number for lap in race_data.laps), default=1)


def load_race_summary(db_path: Path) -> dict[str, object]:
    race_data = _load_race_data(db_path)
    race = race_data.race
    circuit = race_data.circuit
    return {
        "source": {
            "name": race_data.source_name,
            "version": str(race_data.source_version),
            "sha256": race_data.source_sha256,
        },
        "race": {
            "race_id": race.race_id,
            "name": race.name,
            "season": race.season,
            "round_number": race.round_number,
            "race_date": race.race_date.isoformat(),
            "start_time_utc": (
                race.start_time_utc.isoformat() if race.start_time_utc else None
            ),
        },
        "circuit": {
            "circuit_id": circuit.circuit_id,
            "name": circuit.name,
            "location": circuit.location,
            "country": circuit.country,
            "latitude_deg": circuit.latitude_deg,
            "longitude_deg": circuit.longitude_deg,
            "altitude_m": circuit.altitude_m,
        },
        "counts": {
            "drivers": len(race_data.drivers),
            "teams": len(race_data.teams),
            "race_entries": len(race_data.entries),
            "laps": len(race_data.laps),
            "pit_stops": len(race_data.pit_stops),
        },
    }
