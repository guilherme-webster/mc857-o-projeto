from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from collections.abc import Callable
from datetime import date, time
from pathlib import Path

from f1_simulator.adapters.datasets.trotman_source import (
    TROTMAN_ARCHIVE_SHA256,
    TROTMAN_DATASET_REF,
    TROTMAN_DATASET_VERSION,
)
from f1_simulator.application.race_data_dto import NormalizedRaceData, NormalizedRow


class TrotmanDatasetError(ValueError):
    """Raised when the Trotman source is missing or malformed."""


class TrotmanDatasetAdapter:
    """Normalize one race from version 128 of the Trotman dataset."""

    REQUIRED_COLUMNS = {
        "circuits.csv": {
            "circuitId",
            "name",
            "location",
            "country",
            "lat",
            "lng",
            "alt",
        },
        "drivers.csv": {"driverId", "code", "forename", "surname"},
        "constructors.csv": {"constructorId", "name"},
        "races.csv": {
            "raceId",
            "year",
            "round",
            "circuitId",
            "name",
            "date",
            "time",
        },
        "results.csv": {
            "raceId",
            "driverId",
            "constructorId",
            "grid",
            "position",
            "positionOrder",
            "laps",
            "milliseconds",
            "statusId",
        },
        "lap_times.csv": {
            "raceId",
            "driverId",
            "lap",
            "position",
            "milliseconds",
        },
        "pit_stops.csv": {
            "raceId",
            "driverId",
            "stop",
            "lap",
            "milliseconds",
        },
        "status.csv": {"statusId", "status"},
    }

    def __init__(self, source: Path) -> None:
        self.source = source.resolve()
        if not self.source.exists():
            raise TrotmanDatasetError(f"dataset source does not exist: {self.source}")
        if not self.source.is_dir() and not zipfile.is_zipfile(self.source):
            raise TrotmanDatasetError(
                "dataset source must be a directory or ZIP archive"
            )
        self.source_sha256 = self._source_sha256()
        if (
            self.source_sha256 is not None
            and self.source_sha256 != TROTMAN_ARCHIVE_SHA256
        ):
            raise TrotmanDatasetError(
                "archive checksum does not match Trotman dataset version 128"
            )

    def load_race(self, race_external_id: int) -> NormalizedRaceData:
        race_key = str(race_external_id)
        race_rows = self._read_rows("races.csv", lambda row: row["raceId"] == race_key)
        race_row = self._exactly_one(race_rows, f"raceId={race_key}")
        circuit_key = self._required_text(race_row, "circuitId", "races.csv")
        circuit_row = self._exactly_one(
            self._read_rows(
                "circuits.csv", lambda row: row["circuitId"] == circuit_key
            ),
            f"circuitId={circuit_key}",
        )

        result_rows = self._read_rows(
            "results.csv", lambda row: row["raceId"] == race_key
        )
        if not result_rows:
            raise TrotmanDatasetError(f"raceId={race_key} has no results")
        driver_keys = {row["driverId"] for row in result_rows}
        team_keys = {row["constructorId"] for row in result_rows}
        status_keys = {row["statusId"] for row in result_rows}

        driver_rows = self._read_rows(
            "drivers.csv", lambda row: row["driverId"] in driver_keys
        )
        team_rows = self._read_rows(
            "constructors.csv", lambda row: row["constructorId"] in team_keys
        )
        status_rows = self._read_rows(
            "status.csv", lambda row: row["statusId"] in status_keys
        )
        self._require_ids("driver", driver_keys, driver_rows, "driverId")
        self._require_ids("team", team_keys, team_rows, "constructorId")
        self._require_ids("status", status_keys, status_rows, "statusId")
        statuses = {row["statusId"]: row["status"] for row in status_rows}

        lap_rows = self._read_rows(
            "lap_times.csv", lambda row: row["raceId"] == race_key
        )
        pit_rows = self._read_rows(
            "pit_stops.csv", lambda row: row["raceId"] == race_key
        )

        return NormalizedRaceData(
            source_name=TROTMAN_DATASET_REF,
            source_version=TROTMAN_DATASET_VERSION,
            source_sha256=self.source_sha256,
            circuit=self._normalize_circuit(circuit_row),
            race=self._normalize_race(race_row),
            drivers=tuple(
                self._normalize_driver(row)
                for row in sorted(driver_rows, key=lambda item: int(item["driverId"]))
            ),
            teams=tuple(
                self._normalize_team(row)
                for row in sorted(
                    team_rows, key=lambda item: int(item["constructorId"])
                )
            ),
            entries=tuple(
                self._normalize_entry(row, statuses)
                for row in sorted(
                    result_rows, key=lambda item: int(item["positionOrder"])
                )
            ),
            laps=tuple(
                self._normalize_lap(row)
                for row in sorted(
                    lap_rows, key=lambda item: (int(item["driverId"]), int(item["lap"]))
                )
            ),
            pit_stops=tuple(
                self._normalize_pit_stop(row)
                for row in sorted(
                    pit_rows,
                    key=lambda item: (int(item["driverId"]), int(item["stop"])),
                )
            ),
        )

    def _read_rows(
        self, filename: str, predicate: Callable[[dict[str, str]], bool]
    ) -> list[dict[str, str]]:
        required = self.REQUIRED_COLUMNS[filename]
        try:
            if self.source.is_dir():
                path = self.source / filename
                with path.open(newline="", encoding="utf-8-sig") as stream:
                    return self._collect_rows(stream, filename, required, predicate)
            with zipfile.ZipFile(self.source) as archive:
                with archive.open(filename) as raw_stream:
                    stream = io.TextIOWrapper(
                        raw_stream, encoding="utf-8-sig", newline=""
                    )
                    return self._collect_rows(stream, filename, required, predicate)
        except (FileNotFoundError, KeyError) as error:
            raise TrotmanDatasetError(
                f"required file is missing: {filename}"
            ) from error
        except (csv.Error, UnicodeError, zipfile.BadZipFile) as error:
            raise TrotmanDatasetError(f"cannot read {filename}: {error}") from error

    @staticmethod
    def _collect_rows(
        stream: io.TextIOBase,
        filename: str,
        required: set[str],
        predicate: Callable[[dict[str, str]], bool],
    ) -> list[dict[str, str]]:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or ())
        missing = sorted(required - columns)
        if missing:
            raise TrotmanDatasetError(
                f"{filename} is missing required columns: {', '.join(missing)}"
            )
        return [row for row in reader if predicate(row)]

    def _source_sha256(self) -> str | None:
        if self.source.is_dir():
            return None
        digest = hashlib.sha256()
        with self.source.open("rb") as archive:
            for chunk in iter(lambda: archive.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _normalize_circuit(cls, row: dict[str, str]) -> NormalizedRow:
        return {
            "external_id": cls._required_text(row, "circuitId", "circuits.csv"),
            "name": cls._required_text(row, "name", "circuits.csv"),
            "location": cls._required_text(row, "location", "circuits.csv"),
            "country": cls._required_text(row, "country", "circuits.csv"),
            "latitude_deg": cls._required_float(row, "lat", "circuits.csv"),
            "longitude_deg": cls._required_float(row, "lng", "circuits.csv"),
            "altitude_m": cls._optional_int(row, "alt", "circuits.csv"),
        }

    @classmethod
    def _normalize_race(cls, row: dict[str, str]) -> NormalizedRow:
        return {
            "external_id": cls._required_text(row, "raceId", "races.csv"),
            "circuit_external_id": cls._required_text(row, "circuitId", "races.csv"),
            "season": cls._required_int(row, "year", "races.csv"),
            "round_number": cls._required_int(row, "round", "races.csv"),
            "name": cls._required_text(row, "name", "races.csv"),
            "race_date": cls._required_date(row, "date", "races.csv"),
            "start_time_utc": cls._optional_time(row, "time", "races.csv"),
        }

    @classmethod
    def _normalize_driver(cls, row: dict[str, str]) -> NormalizedRow:
        return {
            "external_id": cls._required_text(row, "driverId", "drivers.csv"),
            "code": cls._optional_text(row, "code"),
            "given_name": cls._required_text(row, "forename", "drivers.csv"),
            "family_name": cls._required_text(row, "surname", "drivers.csv"),
        }

    @classmethod
    def _normalize_team(cls, row: dict[str, str]) -> NormalizedRow:
        return {
            "external_id": cls._required_text(row, "constructorId", "constructors.csv"),
            "name": cls._required_text(row, "name", "constructors.csv"),
        }

    @classmethod
    def _normalize_entry(
        cls, row: dict[str, str], statuses: dict[str, str]
    ) -> NormalizedRow:
        status_id = cls._required_text(row, "statusId", "results.csv")
        return {
            "driver_external_id": cls._required_text(row, "driverId", "results.csv"),
            "team_external_id": cls._required_text(row, "constructorId", "results.csv"),
            "grid_position": cls._required_int(row, "grid", "results.csv"),
            "finish_position": cls._optional_int(row, "position", "results.csv"),
            "classification_order": cls._required_int(
                row, "positionOrder", "results.csv"
            ),
            "laps_completed": cls._required_int(row, "laps", "results.csv"),
            "elapsed_time_ms": cls._optional_int(row, "milliseconds", "results.csv"),
            "status": statuses[status_id],
        }

    @classmethod
    def _normalize_lap(cls, row: dict[str, str]) -> NormalizedRow:
        return {
            "driver_external_id": cls._required_text(row, "driverId", "lap_times.csv"),
            "lap_number": cls._required_int(row, "lap", "lap_times.csv"),
            "lap_time_ms": cls._required_int(row, "milliseconds", "lap_times.csv"),
            "position": cls._required_int(row, "position", "lap_times.csv"),
        }

    @classmethod
    def _normalize_pit_stop(cls, row: dict[str, str]) -> NormalizedRow:
        return {
            "driver_external_id": cls._required_text(row, "driverId", "pit_stops.csv"),
            "stop_number": cls._required_int(row, "stop", "pit_stops.csv"),
            "lap_number": cls._required_int(row, "lap", "pit_stops.csv"),
            "duration_ms": cls._optional_int(row, "milliseconds", "pit_stops.csv"),
        }

    @staticmethod
    def _exactly_one(rows: list[dict[str, str]], description: str) -> dict[str, str]:
        if not rows:
            raise TrotmanDatasetError(f"not found: {description}")
        if len(rows) > 1:
            raise TrotmanDatasetError(f"duplicate rows found for {description}")
        return rows[0]

    @staticmethod
    def _require_ids(
        entity: str,
        expected: set[str],
        rows: list[dict[str, str]],
        key: str,
    ) -> None:
        actual = {row[key] for row in rows}
        missing = sorted(expected - actual)
        if missing:
            raise TrotmanDatasetError(
                f"missing {entity} references: {', '.join(missing)}"
            )
        if len(actual) != len(rows):
            raise TrotmanDatasetError(f"duplicate {entity} identifiers")

    @staticmethod
    def _is_null(value: str | None) -> bool:
        return value is None or value.strip() in {"", r"\N"}

    @classmethod
    def _required_text(cls, row: dict[str, str], key: str, filename: str) -> str:
        value = row.get(key)
        if cls._is_null(value):
            raise TrotmanDatasetError(f"{filename}.{key} cannot be null")
        return str(value).strip()

    @classmethod
    def _optional_text(cls, row: dict[str, str], key: str) -> str | None:
        value = row.get(key)
        return None if cls._is_null(value) else str(value).strip()

    @classmethod
    def _required_int(cls, row: dict[str, str], key: str, filename: str) -> int:
        value = cls._required_text(row, key, filename)
        try:
            return int(value)
        except ValueError as error:
            raise TrotmanDatasetError(f"{filename}.{key} must be an integer") from error

    @classmethod
    def _optional_int(cls, row: dict[str, str], key: str, filename: str) -> int | None:
        value = row.get(key)
        if cls._is_null(value):
            return None
        try:
            return int(str(value))
        except ValueError as error:
            raise TrotmanDatasetError(f"{filename}.{key} must be an integer") from error

    @classmethod
    def _required_float(cls, row: dict[str, str], key: str, filename: str) -> float:
        value = cls._required_text(row, key, filename)
        try:
            return float(value)
        except ValueError as error:
            raise TrotmanDatasetError(f"{filename}.{key} must be numeric") from error

    @classmethod
    def _required_date(cls, row: dict[str, str], key: str, filename: str) -> date:
        value = cls._required_text(row, key, filename)
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise TrotmanDatasetError(f"{filename}.{key} must use ISO date") from error

    @classmethod
    def _optional_time(
        cls, row: dict[str, str], key: str, filename: str
    ) -> time | None:
        value = row.get(key)
        if cls._is_null(value):
            return None
        try:
            return time.fromisoformat(str(value))
        except ValueError as error:
            raise TrotmanDatasetError(f"{filename}.{key} must use ISO time") from error
