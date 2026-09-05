"""Read canonical race aggregates from SQLite without leaking SQL upstream."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, time
from pathlib import Path

from f1_simulator.application.ports.race_data import (
    RaceDataNotFoundError,
    RaceDataRepositoryError,
)
from f1_simulator.domain.race_data import (
    Circuit,
    Driver,
    Lap,
    PitStop,
    Race,
    RaceData,
    RaceEntry,
    SourceId,
    Team,
)


class SQLiteRaceDataRepository:
    """Reconstruct complete ``RaceData`` aggregates from the curated database.

    The connection uses SQLite's read-only mode, so a missing path cannot be
    mistaken for a new empty database. SQL errors and inconsistent persisted
    data are translated to application-level repository errors, keeping SQLite
    types and exceptions outside callers.
    """

    def __init__(self, source: Path) -> None:
        """Configure the curated SQLite file used by subsequent queries."""

        self._source = source.resolve()

    def get_race(self, race_id: str) -> RaceData:
        """Load one race by canonical ID and reject incomplete persistence.

        ``race_id`` must be a non-empty canonical identifier. A missing race
        raises ``RaceDataNotFoundError``; missing files, invalid schemas,
        malformed values and broken foreign keys raise
        ``RaceDataRepositoryError``.
        """

        if not isinstance(race_id, str) or not race_id.strip():
            raise ValueError("race_id must be non-empty text")
        if not self._source.is_file():
            raise RaceDataRepositoryError(
                f"canonical race database does not exist: {self._source}"
            )

        # URI read-only mode is important here: sqlite3.connect(path) would
        # silently create an empty file if the source disappeared between the
        # existence check and connection.
        database_uri = f"{self._source.as_uri()}?mode=ro"
        try:
            with closing(sqlite3.connect(database_uri, uri=True)) as connection:
                connection.row_factory = sqlite3.Row
                return self._load_race(connection, race_id.strip())
        except RaceDataRepositoryError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as error:
            raise RaceDataRepositoryError(
                f"cannot read canonical race database {self._source}: {error}"
            ) from error

    def _load_race(self, connection: sqlite3.Connection, race_id: str) -> RaceData:
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RaceDataRepositoryError(
                "canonical race database contains foreign-key violations"
            )

        metadata = {
            self._text(row, "key"): row["value"]
            for row in connection.execute("SELECT key, value FROM metadata")
        }
        source_name = self._metadata_text(metadata, "source_name")
        source_version = self._metadata_positive_int(metadata, "source_version")
        source_sha256 = self._metadata_sha256(metadata)

        race_row = connection.execute(
            """
            SELECT race_id, circuit_id, season, round_number, name,
                   race_date, start_time_utc
            FROM races
            WHERE race_id = ?
            """,
            (race_id,),
        ).fetchone()
        if race_row is None:
            raise RaceDataNotFoundError(f"canonical race not found: {race_id}")

        race = Race(
            race_id=self._text(race_row, "race_id"),
            circuit_id=self._text(race_row, "circuit_id"),
            season=self._positive_int(race_row, "season"),
            round_number=self._positive_int(race_row, "round_number"),
            name=self._text(race_row, "name"),
            race_date=self._date(race_row, "race_date"),
            start_time_utc=self._optional_time(race_row, "start_time_utc"),
        )
        circuit = self._load_circuit(connection, race.circuit_id)
        entries = self._load_entries(connection, race.race_id)
        if not entries:
            raise RaceDataRepositoryError(
                f"canonical race has no entries: {race.race_id}"
            )

        # Participant order follows the classification. This gives callers a
        # stable ordering without relying on SQLite's unspecified row order.
        drivers = self._load_drivers(connection, race.race_id)
        teams = self._load_teams(connection, race.race_id)
        laps = self._load_laps(connection, race.race_id)
        pit_stops = self._load_pit_stops(connection, race.race_id)
        source_ids = self._load_source_ids(
            connection,
            source_name,
            circuit,
            race,
            drivers,
            teams,
        )

        return RaceData(
            source_name=source_name,
            source_version=source_version,
            source_sha256=source_sha256,
            circuit=circuit,
            race=race,
            drivers=drivers,
            teams=teams,
            entries=entries,
            laps=laps,
            pit_stops=pit_stops,
            source_ids=source_ids,
        )

    def _load_circuit(self, connection: sqlite3.Connection, circuit_id: str) -> Circuit:
        row = connection.execute(
            """
            SELECT circuit_id, name, location, country, latitude_deg,
                   longitude_deg, altitude_m
            FROM circuits
            WHERE circuit_id = ?
            """,
            (circuit_id,),
        ).fetchone()
        if row is None:
            raise RaceDataRepositoryError(f"canonical circuit not found: {circuit_id}")
        return Circuit(
            circuit_id=self._text(row, "circuit_id"),
            name=self._text(row, "name"),
            location=self._text(row, "location"),
            country=self._text(row, "country"),
            latitude_deg=self._float(row, "latitude_deg"),
            longitude_deg=self._float(row, "longitude_deg"),
            altitude_m=self._optional_int(row, "altitude_m"),
        )

    def _load_drivers(
        self, connection: sqlite3.Connection, race_id: str
    ) -> tuple[Driver, ...]:
        rows = connection.execute(
            """
            SELECT d.driver_id, d.code, d.given_name, d.family_name
            FROM drivers AS d
            JOIN race_entries AS e ON e.driver_id = d.driver_id
            WHERE e.race_id = ?
            ORDER BY e.classification_order
            """,
            (race_id,),
        )
        return tuple(
            Driver(
                driver_id=self._text(row, "driver_id"),
                code=self._optional_text(row, "code"),
                given_name=self._text(row, "given_name"),
                family_name=self._text(row, "family_name"),
            )
            for row in rows
        )

    def _load_teams(
        self, connection: sqlite3.Connection, race_id: str
    ) -> tuple[Team, ...]:
        rows = connection.execute(
            """
            SELECT t.team_id, t.name
            FROM teams AS t
            JOIN race_entries AS e ON e.team_id = t.team_id
            WHERE e.race_id = ?
            GROUP BY t.team_id, t.name
            ORDER BY MIN(e.classification_order)
            """,
            (race_id,),
        )
        return tuple(
            Team(
                team_id=self._text(row, "team_id"),
                name=self._text(row, "name"),
            )
            for row in rows
        )

    def _load_entries(
        self, connection: sqlite3.Connection, race_id: str
    ) -> tuple[RaceEntry, ...]:
        rows = connection.execute(
            """
            SELECT race_id, driver_id, team_id, grid_position, finish_position,
                   classification_order, laps_completed, elapsed_time_ms, status
            FROM race_entries
            WHERE race_id = ?
            ORDER BY classification_order
            """,
            (race_id,),
        )
        return tuple(
            RaceEntry(
                race_id=self._text(row, "race_id"),
                driver_id=self._text(row, "driver_id"),
                team_id=self._text(row, "team_id"),
                grid_position=self._non_negative_int(row, "grid_position"),
                finish_position=self._optional_positive_int(row, "finish_position"),
                classification_order=self._positive_int(row, "classification_order"),
                laps_completed=self._non_negative_int(row, "laps_completed"),
                elapsed_time_ms=self._optional_positive_int(row, "elapsed_time_ms"),
                status=self._text(row, "status"),
            )
            for row in rows
        )

    def _load_laps(
        self, connection: sqlite3.Connection, race_id: str
    ) -> tuple[Lap, ...]:
        rows = connection.execute(
            """
            SELECT l.race_id, l.driver_id, l.lap_number, l.lap_time_ms, l.position
            FROM laps AS l
            JOIN race_entries AS e
              ON e.race_id = l.race_id AND e.driver_id = l.driver_id
            WHERE l.race_id = ?
            ORDER BY e.classification_order, l.lap_number
            """,
            (race_id,),
        )
        return tuple(
            Lap(
                race_id=self._text(row, "race_id"),
                driver_id=self._text(row, "driver_id"),
                lap_number=self._positive_int(row, "lap_number"),
                lap_time_ms=self._positive_int(row, "lap_time_ms"),
                position=self._positive_int(row, "position"),
            )
            for row in rows
        )

    def _load_pit_stops(
        self, connection: sqlite3.Connection, race_id: str
    ) -> tuple[PitStop, ...]:
        rows = connection.execute(
            """
            SELECT p.race_id, p.driver_id, p.stop_number, p.lap_number,
                   p.duration_ms
            FROM pit_stops AS p
            JOIN race_entries AS e
              ON e.race_id = p.race_id AND e.driver_id = p.driver_id
            WHERE p.race_id = ?
            ORDER BY e.classification_order, p.stop_number
            """,
            (race_id,),
        )
        return tuple(
            PitStop(
                race_id=self._text(row, "race_id"),
                driver_id=self._text(row, "driver_id"),
                stop_number=self._positive_int(row, "stop_number"),
                lap_number=self._positive_int(row, "lap_number"),
                duration_ms=self._optional_positive_int(row, "duration_ms"),
            )
            for row in rows
        )

    def _load_source_ids(
        self,
        connection: sqlite3.Connection,
        source_name: str,
        circuit: Circuit,
        race: Race,
        drivers: tuple[Driver, ...],
        teams: tuple[Team, ...],
    ) -> tuple[SourceId, ...]:
        expected = (
            (("circuit", circuit.circuit_id),)
            + (("race", race.race_id),)
            + tuple(("driver", driver.driver_id) for driver in drivers)
            + tuple(("team", team.team_id) for team in teams)
        )
        return tuple(
            self._load_source_id(connection, source_name, entity_type, canonical_id)
            for entity_type, canonical_id in expected
        )

    def _load_source_id(
        self,
        connection: sqlite3.Connection,
        source_name: str,
        entity_type: str,
        canonical_id: str,
    ) -> SourceId:
        rows = connection.execute(
            """
            SELECT entity_type, source_name, external_id, canonical_id
            FROM source_ids
            WHERE entity_type = ? AND source_name = ? AND canonical_id = ?
            """,
            (entity_type, source_name, canonical_id),
        ).fetchall()
        if len(rows) != 1:
            raise RaceDataRepositoryError(
                "canonical entity must have exactly one source identifier: "
                f"{entity_type} {canonical_id}"
            )
        row = rows[0]
        return SourceId(
            entity_type=self._text(row, "entity_type"),
            source_name=self._text(row, "source_name"),
            external_id=self._text(row, "external_id"),
            canonical_id=self._text(row, "canonical_id"),
        )

    @staticmethod
    def _text(row: sqlite3.Row, key: str) -> str:
        value = row[key]
        if not isinstance(value, str) or not value.strip():
            raise RaceDataRepositoryError(f"{key} must be non-empty text")
        return value.strip()

    @staticmethod
    def _optional_text(row: sqlite3.Row, key: str) -> str | None:
        value = row[key]
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise RaceDataRepositoryError(f"{key} must be text or null")
        return value.strip()

    @staticmethod
    def _int(row: sqlite3.Row, key: str) -> int:
        value = row[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise RaceDataRepositoryError(f"{key} must be an integer")
        return value

    @classmethod
    def _positive_int(cls, row: sqlite3.Row, key: str) -> int:
        value = cls._int(row, key)
        if value <= 0:
            raise RaceDataRepositoryError(f"{key} must be positive")
        return value

    @classmethod
    def _non_negative_int(cls, row: sqlite3.Row, key: str) -> int:
        value = cls._int(row, key)
        if value < 0:
            raise RaceDataRepositoryError(f"{key} must be non-negative")
        return value

    @classmethod
    def _optional_int(cls, row: sqlite3.Row, key: str) -> int | None:
        return None if row[key] is None else cls._int(row, key)

    @classmethod
    def _optional_positive_int(cls, row: sqlite3.Row, key: str) -> int | None:
        return None if row[key] is None else cls._positive_int(row, key)

    @staticmethod
    def _float(row: sqlite3.Row, key: str) -> float:
        value = row[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RaceDataRepositoryError(f"{key} must be numeric")
        return float(value)

    @classmethod
    def _date(cls, row: sqlite3.Row, key: str) -> date:
        value = cls._text(row, key)
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise RaceDataRepositoryError(f"{key} must use ISO date") from error

    @classmethod
    def _optional_time(cls, row: sqlite3.Row, key: str) -> time | None:
        value = cls._optional_text(row, key)
        if value is None:
            return None
        try:
            return time.fromisoformat(value)
        except ValueError as error:
            raise RaceDataRepositoryError(f"{key} must use ISO time") from error

    @staticmethod
    def _metadata_text(metadata: dict[str, object], key: str) -> str:
        value = metadata.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RaceDataRepositoryError(f"metadata.{key} must be non-empty text")
        return value.strip()

    @staticmethod
    def _metadata_optional_text(metadata: dict[str, object], key: str) -> str | None:
        value = metadata.get(key)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise RaceDataRepositoryError(f"metadata.{key} must be text or null")
        return value.strip()

    @staticmethod
    def _metadata_positive_int(metadata: dict[str, object], key: str) -> int:
        raw_value = metadata.get(key)
        if isinstance(raw_value, bool) or not isinstance(raw_value, (str, int)):
            raise RaceDataRepositoryError(f"metadata.{key} must be a positive integer")
        try:
            value = int(raw_value)
        except ValueError as error:
            raise RaceDataRepositoryError(
                f"metadata.{key} must be a positive integer"
            ) from error
        if value <= 0:
            raise RaceDataRepositoryError(f"metadata.{key} must be a positive integer")
        return value

    @classmethod
    def _metadata_sha256(cls, metadata: dict[str, object]) -> str | None:
        value = cls._metadata_optional_text(metadata, "source_sha256")
        if value is None:
            return None
        normalized = value.lower()
        hexadecimal = set("0123456789abcdef")
        if len(normalized) != 64 or any(char not in hexadecimal for char in normalized):
            raise RaceDataRepositoryError(
                "metadata.source_sha256 must be a hexadecimal SHA-256 or null"
            )
        return normalized
