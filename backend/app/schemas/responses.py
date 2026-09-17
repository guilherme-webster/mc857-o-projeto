from __future__ import annotations

from pydantic import BaseModel


class DriverParametersResponse(BaseModel):

    driver_id: str
    name: str
    team_id: str | None
    grid_position: int
    base_lap_time_ms: float | None
    degradation_ms_per_lap: float
    pit_loss_ms: float
    retirement_per_lap: float


class LoadedDriversResponse(BaseModel):

    race_id: int
    count: int
    drivers: list[DriverParametersResponse]


class RaceCatalogEntry(BaseModel):

    race_id: int
    name: str
    year: int
    round: int
    date: str


class RaceCatalogResponse(BaseModel):

    count: int
    races: list[RaceCatalogEntry]


class RaceSourceInfo(BaseModel):

    name: str | None
    version: str | None
    sha256: str | None


class RaceInfo(BaseModel):

    race_id: str
    name: str
    season: int
    round_number: int
    race_date: str
    start_time_utc: str | None


class CircuitInfo(BaseModel):

    circuit_id: str
    name: str
    location: str
    country: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: int | None


class RaceCounts(BaseModel):

    drivers: int
    teams: int
    race_entries: int
    laps: int
    pit_stops: int


class RaceDetailsResponse(BaseModel):

    source: RaceSourceInfo
    race: RaceInfo
    circuit: CircuitInfo
    counts: RaceCounts


class LoadRaceRequest(BaseModel):

    race_id: int


class RaceLoadErrorResponse(BaseModel):

    reason: str
    message: str
    race_id: int
    detail: str | None = None
