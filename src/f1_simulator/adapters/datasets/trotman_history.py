"""Stream every column of all fourteen Trotman v128 CSVs into canonical facts."""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from f1_simulator.adapters.datasets.trotman import (
    TrotmanDatasetAdapter,
    TrotmanDatasetError,
)
from f1_simulator.adapters.datasets.trotman_source import TROTMAN_DATASET_REF
from f1_simulator.domain.history import HISTORY_TABLES, Scalar


# Explicit mappings make coverage reviewable: even original display strings
# with different semantics (e.g. '+1 lap' versus elapsed milliseconds) survive.
_RESULT = {
    "resultId": "result_id",
    "raceId": "race_id",
    "driverId": "driver_id",
    "constructorId": "team_id",
    "number": "car_number",
    "grid": "grid_position",
    "position": "finish_position",
    "positionText": "position_text",
    "positionOrder": "classification_order",
    "points": "points",
    "laps": "laps_completed",
    "time": "result_time_text",
    "milliseconds": "elapsed_time_ms",
    "fastestLap": "fastest_lap",
    "rank": "fastest_lap_rank",
    "fastestLapTime": "fastest_lap_time_ms",
    "statusId": "status_id",
}
_STANDING = {
    "raceId": "race_id",
    "points": "points",
    "position": "position",
    "positionText": "position_text",
    "wins": "wins",
}
MAPPINGS = {
    "seasons": ("seasons.csv", {"year": "season", "url": "url"}),
    "circuits": (
        "circuits.csv",
        {
            "circuitId": "circuit_id",
            "circuitRef": "circuit_ref",
            "name": "name",
            "location": "location",
            "country": "country",
            "lat": "latitude_deg",
            "lng": "longitude_deg",
            "alt": "altitude_m",
            "url": "url",
        },
    ),
    "drivers": (
        "drivers.csv",
        {
            "driverId": "driver_id",
            "driverRef": "driver_ref",
            "number": "car_number",
            "code": "code",
            "forename": "given_name",
            "surname": "family_name",
            "dob": "birth_date",
            "nationality": "nationality",
            "url": "url",
        },
    ),
    "teams": (
        "constructors.csv",
        {
            "constructorId": "team_id",
            "constructorRef": "team_ref",
            "name": "name",
            "nationality": "nationality",
            "url": "url",
        },
    ),
    "statuses": ("status.csv", {"statusId": "status_id", "status": "description"}),
    "races": (
        "races.csv",
        {
            "raceId": "race_id",
            "year": "season",
            "round": "round_number",
            "circuitId": "circuit_id",
            "name": "name",
            "date": "race_date",
            "time": "start_time_utc",
            "url": "url",
            **{
                f"{src}_{unit}": f"{dst}_{'time_utc' if unit == 'time' else unit}"
                for src, dst in (
                    ("fp1", "fp1"),
                    ("fp2", "fp2"),
                    ("fp3", "fp3"),
                    ("quali", "qualifying"),
                    ("sprint", "sprint"),
                )
                for unit in ("date", "time")
            },
        },
    ),
    "race_results": (
        "results.csv",
        {**_RESULT, "fastestLapSpeed": "fastest_lap_speed_kmh"},
    ),
    "sprint_results": ("sprint_results.csv", _RESULT),
    "laps": (
        "lap_times.csv",
        {
            "raceId": "race_id",
            "driverId": "driver_id",
            "lap": "lap_number",
            "position": "position",
            "time": "lap_time_text",
            "milliseconds": "lap_time_ms",
        },
    ),
    "pit_stops": (
        "pit_stops.csv",
        {
            "raceId": "race_id",
            "driverId": "driver_id",
            "stop": "stop_number",
            "lap": "lap_number",
            "time": "source_clock_time",
            "duration": "duration_text",
            "milliseconds": "duration_ms",
        },
    ),
    "qualifying": (
        "qualifying.csv",
        {
            "qualifyId": "qualifying_id",
            "raceId": "race_id",
            "driverId": "driver_id",
            "constructorId": "team_id",
            "number": "car_number",
            "position": "position",
            "q1": "q1_ms",
            "q2": "q2_ms",
            "q3": "q3_ms",
        },
    ),
    "constructor_results": (
        "constructor_results.csv",
        {
            "constructorResultsId": "constructor_result_id",
            "raceId": "race_id",
            "constructorId": "team_id",
            "points": "points",
            "status": "status_text",
        },
    ),
    "driver_standings": (
        "driver_standings.csv",
        {"driverStandingsId": "standing_id", "driverId": "driver_id", **_STANDING},
    ),
    "constructor_standings": (
        "constructor_standings.csv",
        {
            "constructorStandingsId": "standing_id",
            "constructorId": "team_id",
            **_STANDING,
        },
    ),
}


def duration_ms(value: str) -> int:
    """Parse seconds or M:SS/H:MM:SS without binary floating-point truncation."""
    parts = value.split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"invalid duration: {value}")
    seconds = Decimal(0)
    for part in parts:
        number = Decimal(part)
        if not number.is_finite() or number < 0:
            raise ValueError(f"invalid duration: {value}")
        seconds = seconds * 60 + number
    return int((seconds * 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP))


class TrotmanHistoryAdapter:
    """Import the complete snapshot, preserving early history and all columns.

    The existing adapter verifies ZIP identity. Directory input is explicitly
    unverified against that ZIP (useful for small fixtures); each input file
    still receives its own checksum. No implicit season/race filter is applied.
    """

    tables = HISTORY_TABLES

    def __init__(self, source: Path) -> None:
        checked = TrotmanDatasetAdapter(source)
        self.source = checked.source
        self.manifest = {
            "source_name": TROTMAN_DATASET_REF,
            "source_version": 128,
            "source_sha256": checked.source_sha256,
            "schema_version": 1,
            "transform_version": "trotman-history-1",
            "license": "CC0-1.0",
            "url": "https://www.kaggle.com/datasets/jtrotman/formula-1-race-data",
            "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
            "archive_verified": checked.source_sha256 is not None,
            "scope": "complete_snapshot",
            "files": {},
        }

    @contextmanager
    def _open(self, filename: str):
        if self.source.is_dir():
            with (self.source / filename).open("rb") as stream:
                yield stream
        else:
            with (
                zipfile.ZipFile(self.source) as archive,
                archive.open(filename) as stream,
            ):
                yield stream

    def rows(self, table: str) -> Iterator[dict[str, Scalar]]:
        """Normalize one CSV incrementally and reject unhandled schema changes."""
        spec = next(t for t in self.tables if t.name == table)
        filename, mapping = MAPPINGS[table]
        try:
            digest = hashlib.sha256()
            with self._open(filename) as raw:
                for chunk in iter(lambda: raw.read(1024 * 1024), b""):
                    digest.update(chunk)
            self.manifest["files"][filename] = {"sha256": digest.hexdigest()}
            with self._open(filename) as raw:
                reader = csv.DictReader(
                    io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                )
                if set(reader.fieldnames or ()) != set(mapping) or len(
                    reader.fieldnames or ()
                ) != len(mapping):
                    raise TrotmanDatasetError(
                        f"{filename}: expected columns {sorted(mapping)}, got {reader.fieldnames}"
                    )
                for number, row in enumerate(reader, 2):
                    if None in row or any(value is None for value in row.values()):
                        raise TrotmanDatasetError(
                            f"{filename}:{number}: malformed CSV row"
                        )
                    translated = {
                        mapping[name]: (
                            None if value.strip() in ("", "\\N") else value.strip()
                        )
                        for name, value in row.items()
                    }
                    # The snapshot contains duplicate lap keys, including
                    # conflicting measurements. Preserve every observation by
                    # its ordinal within this checksummed source, not by taking
                    # whichever row happens to occur first or last.
                    if table == "laps":
                        translated["record_number"] = str(number - 1)
                    try:
                        yield {
                            column.name: self._convert(
                                table, column, translated[column.name]
                            )
                            for column in spec.columns
                        }
                    except (ValueError, InvalidOperation) as error:
                        raise TrotmanDatasetError(
                            f"{filename}:{number}: {error}"
                        ) from error
        except (
            OSError,
            KeyError,
            zipfile.BadZipFile,
            UnicodeError,
            csv.Error,
        ) as error:
            raise TrotmanDatasetError(f"cannot read {filename}: {error}") from error

    @staticmethod
    def _convert(table, column, value):
        if value is None:
            return None
        if column.name.endswith("_id"):
            prefix = column.name.removesuffix("_id")
            if column.name == "result_id" and table == "sprint_results":
                prefix = "sprint_result"
            if column.name == "standing_id":
                prefix = table.removesuffix("s")
            return f"{prefix}:{value}"
        if column.name in ("q1_ms", "q2_ms", "q3_ms", "fastest_lap_time_ms"):
            return duration_ms(value)
        if column.kind == "int":
            return int(value)
        if column.kind == "float":
            return float(value)
        return value
