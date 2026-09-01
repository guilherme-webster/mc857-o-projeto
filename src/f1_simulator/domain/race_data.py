"""Source-independent entities that form one validated race-data aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time


@dataclass(frozen=True, slots=True)
class Circuit:
    """Canonical circuit identity and geographic coordinates."""

    circuit_id: str
    name: str
    location: str
    country: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: int | None


@dataclass(frozen=True, slots=True)
class Driver:
    """Canonical driver identity independent of a dataset's identifier."""

    driver_id: str
    code: str | None
    given_name: str
    family_name: str


@dataclass(frozen=True, slots=True)
class Team:
    """Canonical constructor or team participating in a race."""

    team_id: str
    name: str


@dataclass(frozen=True, slots=True)
class Race:
    """One scheduled race linked to its canonical circuit."""

    race_id: str
    circuit_id: str
    season: int
    round_number: int
    name: str
    race_date: date
    start_time_utc: time | None


@dataclass(frozen=True, slots=True)
class RaceEntry:
    """A driver's classification and team assignment for one race."""

    race_id: str
    driver_id: str
    team_id: str
    grid_position: int
    finish_position: int | None
    classification_order: int
    laps_completed: int
    elapsed_time_ms: int | None
    status: str


@dataclass(frozen=True, slots=True)
class Lap:
    """One driver's completed lap; duration is expressed in milliseconds."""

    race_id: str
    driver_id: str
    lap_number: int
    lap_time_ms: int
    position: int


@dataclass(frozen=True, slots=True)
class PitStop:
    """One recorded stop; duration is milliseconds when supplied by the source."""

    race_id: str
    driver_id: str
    stop_number: int
    lap_number: int
    duration_ms: int | None


@dataclass(frozen=True, slots=True)
class SourceId:
    """Trace an external entity identifier to the corresponding canonical ID."""

    entity_type: str
    source_name: str
    external_id: str
    canonical_id: str


@dataclass(frozen=True, slots=True)
class RaceData:
    """Validated aggregate exchanged by ingestion, persistence and consumers."""

    source_name: str
    source_version: int
    source_sha256: str | None
    circuit: Circuit
    race: Race
    drivers: tuple[Driver, ...]
    teams: tuple[Team, ...]
    entries: tuple[RaceEntry, ...]
    laps: tuple[Lap, ...]
    pit_stops: tuple[PitStop, ...]
    source_ids: tuple[SourceId, ...]
