"""Canonical tabular facts for historical analysis, independent of dataframes.

Unlike ``RaceData``, a history can include cancelled events, practice sessions
and multiple results for a driver in early shared-car races. Those facts must
not be forced through the smaller, executable single-race aggregate. Explicit
schemas below are the public contract; CSV names and vendor fields belong only
to adapters. Dates/times use ISO text, durations milliseconds, speeds km/h.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

Scalar: TypeAlias = str | int | float | bool | None


@dataclass(frozen=True)
class Column:
    """One canonical field, including nullability and numerical bounds."""

    name: str
    kind: str = "text"
    nullable: bool = True
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True)
class Table:
    """Record shape and relational invariants shared by validation and storage."""

    name: str
    columns: tuple[Column, ...]
    key: tuple[str, ...]
    references: tuple[tuple[str, str, str], ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        """Return field order; it is stable in records and persistence."""
        return tuple(c.name for c in self.columns)


@dataclass(frozen=True)
class HistoricalRecord:
    """Validated immutable facts; consumers address canonical fields by name."""

    table: str
    fields: tuple[tuple[str, Scalar], ...]

    def __getitem__(self, name: str) -> Scalar:
        """Read a canonical field, raising KeyError for an unknown field."""
        for key, value in self.fields:
            if key == name:
                return value
        raise KeyError(name)

    def as_dict(self) -> dict[str, Scalar]:
        """Return a detached copy, so callers cannot mutate a stored record."""
        return dict(self.fields)


def _id(name: str) -> Column:
    return Column(name, nullable=False)


def _int(name: str, *, required: bool = False, minimum: int = 0) -> Column:
    return Column(name, "int", not required, minimum)


_RACE_REF = ("race_id", "races", "race_id")
_DRIVER_REF = ("driver_id", "drivers", "driver_id")
_TEAM_REF = ("team_id", "teams", "team_id")
_STATUS_REF = ("status_id", "statuses", "status_id")

_RESULT_COLUMNS = (
    _id("result_id"),
    _id("race_id"),
    _id("driver_id"),
    _id("team_id"),
    _int("car_number"),
    _int("grid_position"),
    _int("finish_position", minimum=1),
    Column("position_text", nullable=False),
    _int("classification_order", required=True, minimum=1),
    Column("points", "float", False),
    _int("laps_completed", required=True),
    Column("result_time_text"),
    _int("elapsed_time_ms"),
    _int("fastest_lap"),
    _int("fastest_lap_rank"),
    _int("fastest_lap_time_ms"),
    Column("status_id"),
)

HISTORY_TABLES = (
    Table(
        "seasons",
        (_int("season", required=True, minimum=1), Column("url")),
        ("season",),
    ),
    Table(
        "circuits",
        (
            _id("circuit_id"),
            _id("circuit_ref"),
            _id("name"),
            _id("location"),
            _id("country"),
            Column("latitude_deg", "float", False, -90, 90),
            Column("longitude_deg", "float", False, -180, 180),
            Column("altitude_m", "int"),
            Column("url"),
        ),
        ("circuit_id",),
    ),
    Table(
        "drivers",
        (
            _id("driver_id"),
            _id("driver_ref"),
            _int("car_number"),
            Column("code"),
            _id("given_name"),
            _id("family_name"),
            Column("birth_date", "date"),
            Column("nationality"),
            Column("url"),
        ),
        ("driver_id",),
    ),
    Table(
        "teams",
        (
            _id("team_id"),
            _id("team_ref"),
            _id("name"),
            Column("nationality"),
            Column("url"),
        ),
        ("team_id",),
    ),
    Table("statuses", (_id("status_id"), _id("description")), ("status_id",)),
    Table(
        "races",
        (
            _id("race_id"),
            _int("season", required=True, minimum=1),
            _int("round_number", required=True, minimum=1),
            _id("circuit_id"),
            _id("name"),
            Column("race_date", "date", False),
            Column("start_time_utc", "time"),
            Column("url"),
            *(
                Column(f"{session}_{unit}", "date" if unit == "date" else "time")
                for session in ("fp1", "fp2", "fp3", "qualifying", "sprint")
                for unit in ("date", "time_utc")
            ),
        ),
        ("race_id",),
        (("season", "seasons", "season"), ("circuit_id", "circuits", "circuit_id")),
    ),
    # Results are keyed by source result, not (race, driver): the latter loses
    # genuine shared-car / multiple-entry history in the full Trotman archive.
    Table(
        "race_results",
        _RESULT_COLUMNS + (Column("fastest_lap_speed_kmh", "float", True, 0),),
        ("result_id",),
        (_RACE_REF, _DRIVER_REF, _TEAM_REF, _STATUS_REF),
    ),
    Table(
        "sprint_results",
        _RESULT_COLUMNS,
        ("result_id",),
        (_RACE_REF, _DRIVER_REF, _TEAM_REF, _STATUS_REF),
    ),
    Table(
        "laps",
        (
            _int("record_number", required=True, minimum=1),
            _id("race_id"),
            _id("driver_id"),
            _int("lap_number", required=True, minimum=1),
            _int("position", required=True, minimum=1),
            _int("lap_time_ms", required=True, minimum=1),
            Column("lap_time_text"),
        ),
        ("record_number",),
        (_RACE_REF, _DRIVER_REF),
    ),
    Table(
        "pit_stops",
        (
            _id("race_id"),
            _id("driver_id"),
            _int("stop_number", required=True, minimum=1),
            _int("lap_number", required=True, minimum=1),
            Column("source_clock_time", "time"),
            Column("duration_text"),
            _int("duration_ms"),
        ),
        ("race_id", "driver_id", "stop_number"),
        (_RACE_REF, _DRIVER_REF),
    ),
    Table(
        "qualifying",
        (
            _id("qualifying_id"),
            _id("race_id"),
            _id("driver_id"),
            _id("team_id"),
            _int("car_number"),
            _int("position", required=True, minimum=1),
            _int("q1_ms"),
            _int("q2_ms"),
            _int("q3_ms"),
        ),
        ("qualifying_id",),
        (_RACE_REF, _DRIVER_REF, _TEAM_REF),
    ),
    Table(
        "constructor_results",
        (
            _id("constructor_result_id"),
            _id("race_id"),
            _id("team_id"),
            Column("points", "float", False),
            Column("status_text"),
        ),
        ("constructor_result_id",),
        (_RACE_REF, _TEAM_REF),
    ),
    Table(
        "driver_standings",
        (
            _id("standing_id"),
            _id("race_id"),
            _id("driver_id"),
            Column("points", "float", False),
            _int("position", minimum=1),
            _id("position_text"),
            _int("wins", required=True),
        ),
        ("standing_id",),
        (_RACE_REF, _DRIVER_REF),
    ),
    Table(
        "constructor_standings",
        (
            _id("standing_id"),
            _id("race_id"),
            _id("team_id"),
            Column("points", "float", False),
            _int("position", minimum=1),
            _id("position_text"),
            _int("wins", required=True),
        ),
        ("standing_id",),
        (_RACE_REF, _TEAM_REF),
    ),
)

HISTORY_SCHEMA = {table.name: table for table in HISTORY_TABLES}
