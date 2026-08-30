from __future__ import annotations

from collections.abc import Iterable
from datetime import date, time

from f1_simulator.application.race_data_dto import NormalizedRaceData, NormalizedRow
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


class RaceDataValidationError(ValueError):
    """Raised when normalized data cannot form a consistent race dataset."""


class RaceDataFactory:
    """Build domain objects without reading files or knowing source schemas."""

    @classmethod
    def create(cls, normalized: NormalizedRaceData) -> RaceData:
        circuit_id = cls._canonical_id("circuit", normalized.circuit["external_id"])
        race_id = cls._canonical_id("race", normalized.race["external_id"])
        if str(normalized.race["circuit_external_id"]) != str(
            normalized.circuit["external_id"]
        ):
            raise RaceDataValidationError("race references a different circuit")

        latitude_deg = cls._float(normalized.circuit, "latitude_deg")
        longitude_deg = cls._float(normalized.circuit, "longitude_deg")
        if not -90 <= latitude_deg <= 90:
            raise RaceDataValidationError("latitude_deg must be between -90 and 90")
        if not -180 <= longitude_deg <= 180:
            raise RaceDataValidationError("longitude_deg must be between -180 and 180")

        circuit = Circuit(
            circuit_id=circuit_id,
            name=cls._text(normalized.circuit, "name"),
            location=cls._text(normalized.circuit, "location"),
            country=cls._text(normalized.circuit, "country"),
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            altitude_m=cls._optional_int(normalized.circuit, "altitude_m"),
        )
        race = Race(
            race_id=race_id,
            circuit_id=circuit_id,
            season=cls._positive_int(normalized.race, "season"),
            round_number=cls._positive_int(normalized.race, "round_number"),
            name=cls._text(normalized.race, "name"),
            race_date=cls._date(normalized.race, "race_date"),
            start_time_utc=cls._optional_time(normalized.race, "start_time_utc"),
        )

        driver_ids = cls._id_map("driver", normalized.drivers)
        team_ids = cls._id_map("team", normalized.teams)
        drivers = tuple(
            Driver(
                driver_id=driver_ids[str(row["external_id"])],
                code=cls._optional_text(row, "code"),
                given_name=cls._text(row, "given_name"),
                family_name=cls._text(row, "family_name"),
            )
            for row in normalized.drivers
        )
        teams = tuple(
            Team(
                team_id=team_ids[str(row["external_id"])],
                name=cls._text(row, "name"),
            )
            for row in normalized.teams
        )

        entries = tuple(
            cls._entry(row, race_id, driver_ids, team_ids) for row in normalized.entries
        )
        entry_driver_ids = {entry.driver_id for entry in entries}
        cls._require_unique(
            ((entry.race_id, entry.driver_id) for entry in entries), "race entries"
        )
        cls._require_unique(
            ((entry.race_id, entry.classification_order) for entry in entries),
            "classification order",
        )
        if entry_driver_ids != set(driver_ids.values()):
            raise RaceDataValidationError(
                "drivers and race entries must describe the same participants"
            )

        laps = tuple(cls._lap(row, race_id, driver_ids) for row in normalized.laps)
        pit_stops = tuple(
            cls._pit_stop(row, race_id, driver_ids) for row in normalized.pit_stops
        )
        cls._require_unique(
            ((lap.race_id, lap.driver_id, lap.lap_number) for lap in laps), "laps"
        )
        cls._require_unique(
            ((lap.race_id, lap.lap_number, lap.position) for lap in laps),
            "lap positions",
        )
        cls._require_unique(
            ((stop.race_id, stop.driver_id, stop.stop_number) for stop in pit_stops),
            "pit stops",
        )
        if any(lap.driver_id not in entry_driver_ids for lap in laps):
            raise RaceDataValidationError("lap references a driver outside the race")
        if any(stop.driver_id not in entry_driver_ids for stop in pit_stops):
            raise RaceDataValidationError(
                "pit stop references a driver outside the race"
            )

        source_ids = [
            SourceId(
                "circuit",
                normalized.source_name,
                str(normalized.circuit["external_id"]),
                circuit_id,
            ),
            SourceId(
                "race",
                normalized.source_name,
                str(normalized.race["external_id"]),
                race_id,
            ),
        ]
        source_ids.extend(
            SourceId("driver", normalized.source_name, external_id, canonical_id)
            for external_id, canonical_id in driver_ids.items()
        )
        source_ids.extend(
            SourceId("team", normalized.source_name, external_id, canonical_id)
            for external_id, canonical_id in team_ids.items()
        )

        return RaceData(
            source_name=normalized.source_name,
            source_version=normalized.source_version,
            source_sha256=normalized.source_sha256,
            circuit=circuit,
            race=race,
            drivers=drivers,
            teams=teams,
            entries=entries,
            laps=laps,
            pit_stops=pit_stops,
            source_ids=tuple(source_ids),
        )

    @classmethod
    def _entry(
        cls,
        row: NormalizedRow,
        race_id: str,
        driver_ids: dict[str, str],
        team_ids: dict[str, str],
    ) -> RaceEntry:
        driver_id = cls._related_id(row, "driver_external_id", driver_ids)
        team_id = cls._related_id(row, "team_external_id", team_ids)
        grid_position = cls._int(row, "grid_position")
        if grid_position < 0:
            raise RaceDataValidationError("grid_position must be non-negative")
        return RaceEntry(
            race_id=race_id,
            driver_id=driver_id,
            team_id=team_id,
            grid_position=grid_position,
            finish_position=cls._optional_positive_int(row, "finish_position"),
            classification_order=cls._positive_int(row, "classification_order"),
            laps_completed=cls._non_negative_int(row, "laps_completed"),
            elapsed_time_ms=cls._optional_positive_int(row, "elapsed_time_ms"),
            status=cls._text(row, "status"),
        )

    @classmethod
    def _lap(cls, row: NormalizedRow, race_id: str, driver_ids: dict[str, str]) -> Lap:
        return Lap(
            race_id=race_id,
            driver_id=cls._related_id(row, "driver_external_id", driver_ids),
            lap_number=cls._positive_int(row, "lap_number"),
            lap_time_ms=cls._positive_int(row, "lap_time_ms"),
            position=cls._positive_int(row, "position"),
        )

    @classmethod
    def _pit_stop(
        cls, row: NormalizedRow, race_id: str, driver_ids: dict[str, str]
    ) -> PitStop:
        return PitStop(
            race_id=race_id,
            driver_id=cls._related_id(row, "driver_external_id", driver_ids),
            stop_number=cls._positive_int(row, "stop_number"),
            lap_number=cls._positive_int(row, "lap_number"),
            duration_ms=cls._optional_positive_int(row, "duration_ms"),
        )

    @classmethod
    def _id_map(cls, entity: str, rows: tuple[NormalizedRow, ...]) -> dict[str, str]:
        result: dict[str, str] = {}
        for row in rows:
            external_id = str(row["external_id"])
            if external_id in result:
                raise RaceDataValidationError(
                    f"duplicate {entity} external_id: {external_id}"
                )
            result[external_id] = cls._canonical_id(entity, external_id)
        return result

    @staticmethod
    def _canonical_id(entity: str, external_id: object) -> str:
        value = str(external_id).strip()
        if not value:
            raise RaceDataValidationError(f"empty external id for {entity}")
        return f"{entity}:{value}"

    @staticmethod
    def _related_id(row: NormalizedRow, key: str, ids: dict[str, str]) -> str:
        external_id = str(row[key])
        try:
            return ids[external_id]
        except KeyError as error:
            raise RaceDataValidationError(
                f"orphan reference {key}={external_id}"
            ) from error

    @staticmethod
    def _require_unique(keys: Iterable[tuple[object, ...]], description: str) -> None:
        seen: set[tuple[object, ...]] = set()
        for key in keys:
            if key in seen:
                raise RaceDataValidationError(f"duplicate key in {description}: {key}")
            seen.add(key)

    @staticmethod
    def _text(row: NormalizedRow, key: str) -> str:
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RaceDataValidationError(f"{key} must be non-empty text")
        return value.strip()

    @staticmethod
    def _optional_text(row: NormalizedRow, key: str) -> str | None:
        value = row.get(key)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise RaceDataValidationError(f"{key} must be text or null")
        return value.strip()

    @staticmethod
    def _int(row: NormalizedRow, key: str) -> int:
        value = row.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise RaceDataValidationError(f"{key} must be an integer")
        return value

    @classmethod
    def _positive_int(cls, row: NormalizedRow, key: str) -> int:
        value = cls._int(row, key)
        if value <= 0:
            raise RaceDataValidationError(f"{key} must be positive")
        return value

    @classmethod
    def _non_negative_int(cls, row: NormalizedRow, key: str) -> int:
        value = cls._int(row, key)
        if value < 0:
            raise RaceDataValidationError(f"{key} must be non-negative")
        return value

    @classmethod
    def _optional_int(cls, row: NormalizedRow, key: str) -> int | None:
        if row.get(key) is None:
            return None
        return cls._int(row, key)

    @classmethod
    def _optional_positive_int(cls, row: NormalizedRow, key: str) -> int | None:
        if row.get(key) is None:
            return None
        return cls._positive_int(row, key)

    @staticmethod
    def _float(row: NormalizedRow, key: str) -> float:
        value = row.get(key)
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise RaceDataValidationError(f"{key} must be numeric")
        return float(value)

    @staticmethod
    def _date(row: NormalizedRow, key: str) -> date:
        value = row.get(key)
        if not isinstance(value, date):
            raise RaceDataValidationError(f"{key} must be a date")
        return value

    @staticmethod
    def _optional_time(row: NormalizedRow, key: str) -> time | None:
        value = row.get(key)
        if value is not None and not isinstance(value, time):
            raise RaceDataValidationError(f"{key} must be a time or null")
        return value
