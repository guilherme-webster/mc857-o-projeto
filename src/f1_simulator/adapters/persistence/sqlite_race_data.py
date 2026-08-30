from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

from f1_simulator.domain.race_data import RaceData


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE source_ids (
    entity_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    external_id TEXT NOT NULL,
    canonical_id TEXT NOT NULL,
    PRIMARY KEY (entity_type, source_name, external_id)
);

CREATE TABLE circuits (
    circuit_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT NOT NULL,
    country TEXT NOT NULL,
    latitude_deg REAL NOT NULL,
    longitude_deg REAL NOT NULL,
    altitude_m INTEGER
);

CREATE TABLE drivers (
    driver_id TEXT PRIMARY KEY,
    code TEXT,
    given_name TEXT NOT NULL,
    family_name TEXT NOT NULL
);

CREATE TABLE teams (
    team_id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE races (
    race_id TEXT PRIMARY KEY,
    circuit_id TEXT NOT NULL REFERENCES circuits(circuit_id),
    season INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    name TEXT NOT NULL,
    race_date TEXT NOT NULL,
    start_time_utc TEXT
);

CREATE TABLE race_entries (
    race_id TEXT NOT NULL REFERENCES races(race_id),
    driver_id TEXT NOT NULL REFERENCES drivers(driver_id),
    team_id TEXT NOT NULL REFERENCES teams(team_id),
    grid_position INTEGER NOT NULL,
    finish_position INTEGER,
    classification_order INTEGER NOT NULL,
    laps_completed INTEGER NOT NULL,
    elapsed_time_ms INTEGER,
    status TEXT NOT NULL,
    PRIMARY KEY (race_id, driver_id)
);

CREATE TABLE laps (
    race_id TEXT NOT NULL,
    driver_id TEXT NOT NULL,
    lap_number INTEGER NOT NULL,
    lap_time_ms INTEGER NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (race_id, driver_id, lap_number),
    FOREIGN KEY (race_id, driver_id) REFERENCES race_entries(race_id, driver_id)
);

CREATE TABLE pit_stops (
    race_id TEXT NOT NULL,
    driver_id TEXT NOT NULL,
    stop_number INTEGER NOT NULL,
    lap_number INTEGER NOT NULL,
    duration_ms INTEGER,
    PRIMARY KEY (race_id, driver_id, stop_number),
    FOREIGN KEY (race_id, driver_id) REFERENCES race_entries(race_id, driver_id)
);
"""


class SQLiteRaceDataWriter:
    """Persist a canonical race dataset atomically in SQLite."""

    def write(
        self, race_data: RaceData, destination: Path, *, overwrite: bool = False
    ) -> None:
        destination = destination.resolve()
        if destination.exists() and not overwrite:
            raise FileExistsError(f"output already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        os.close(file_descriptor)
        temporary = Path(temporary_name)
        try:
            with sqlite3.connect(temporary) as connection:
                connection.executescript(SCHEMA)
                self._insert(connection, race_data)
                violations = connection.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise sqlite3.IntegrityError(
                        f"foreign key violations after import: {violations}"
                    )
            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _insert(connection: sqlite3.Connection, data: RaceData) -> None:
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            (
                ("source_name", data.source_name),
                ("source_version", str(data.source_version)),
                ("source_sha256", data.source_sha256),
            ),
        )
        connection.executemany(
            """
            INSERT INTO source_ids(entity_type, source_name, external_id, canonical_id)
            VALUES (?, ?, ?, ?)
            """,
            (
                (
                    item.entity_type,
                    item.source_name,
                    item.external_id,
                    item.canonical_id,
                )
                for item in data.source_ids
            ),
        )
        circuit = data.circuit
        connection.execute(
            "INSERT INTO circuits VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                circuit.circuit_id,
                circuit.name,
                circuit.location,
                circuit.country,
                circuit.latitude_deg,
                circuit.longitude_deg,
                circuit.altitude_m,
            ),
        )
        connection.executemany(
            "INSERT INTO drivers VALUES (?, ?, ?, ?)",
            (
                (driver.driver_id, driver.code, driver.given_name, driver.family_name)
                for driver in data.drivers
            ),
        )
        connection.executemany(
            "INSERT INTO teams VALUES (?, ?)",
            ((team.team_id, team.name) for team in data.teams),
        )
        race = data.race
        connection.execute(
            "INSERT INTO races VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                race.race_id,
                race.circuit_id,
                race.season,
                race.round_number,
                race.name,
                race.race_date.isoformat(),
                race.start_time_utc.isoformat() if race.start_time_utc else None,
            ),
        )
        connection.executemany(
            "INSERT INTO race_entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    entry.race_id,
                    entry.driver_id,
                    entry.team_id,
                    entry.grid_position,
                    entry.finish_position,
                    entry.classification_order,
                    entry.laps_completed,
                    entry.elapsed_time_ms,
                    entry.status,
                )
                for entry in data.entries
            ),
        )
        connection.executemany(
            "INSERT INTO laps VALUES (?, ?, ?, ?, ?)",
            (
                (
                    lap.race_id,
                    lap.driver_id,
                    lap.lap_number,
                    lap.lap_time_ms,
                    lap.position,
                )
                for lap in data.laps
            ),
        )
        connection.executemany(
            "INSERT INTO pit_stops VALUES (?, ?, ?, ?, ?)",
            (
                (
                    stop.race_id,
                    stop.driver_id,
                    stop.stop_number,
                    stop.lap_number,
                    stop.duration_ms,
                )
                for stop in data.pit_stops
            ),
        )
