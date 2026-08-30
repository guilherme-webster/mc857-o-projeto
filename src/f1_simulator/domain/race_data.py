from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time


@dataclass(frozen=True, slots=True)
class Circuit:
    circuit_id: str
    name: str
    location: str
    country: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: int | None


@dataclass(frozen=True, slots=True)
class Driver:
    driver_id: str
    code: str | None
    given_name: str
    family_name: str


@dataclass(frozen=True, slots=True)
class Team:
    team_id: str
    name: str


@dataclass(frozen=True, slots=True)
class Race:
    race_id: str
    circuit_id: str
    season: int
    round_number: int
    name: str
    race_date: date
    start_time_utc: time | None


@dataclass(frozen=True, slots=True)
class RaceEntry:
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
    race_id: str
    driver_id: str
    lap_number: int
    lap_time_ms: int
    position: int


@dataclass(frozen=True, slots=True)
class PitStop:
    race_id: str
    driver_id: str
    stop_number: int
    lap_number: int
    duration_ms: int | None


@dataclass(frozen=True, slots=True)
class SourceId:
    entity_type: str
    source_name: str
    external_id: str
    canonical_id: str


@dataclass(frozen=True, slots=True)
class RaceData:
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
