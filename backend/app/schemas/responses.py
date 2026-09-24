from __future__ import annotations

from pydantic import BaseModel, Field


class SeriesTrackRequest(BaseModel):
    """Uma pista da sequência, identificada pelo catálogo de geometria."""

    circuit_id: str = Field(min_length=1)
    total_laps: int = Field(ge=1, le=200)


class SeriesCompetitorRequest(BaseModel):
    """Participante livre; ritmo-base explícito em milissegundos por km."""

    driver_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    pace_ms_per_km: float = Field(gt=0, allow_inf_nan=False)


class SeriesSimulationRequest(BaseModel):
    """Sequência ordenada e pilotos informados pelo usuário, sem race_id."""

    tracks: list[SeriesTrackRequest] = Field(min_length=1, max_length=24)
    competitors: list[SeriesCompetitorRequest] = Field(min_length=1, max_length=40)


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


class HistoryBuildResponse(BaseModel):

    schema_version: int
    row_counts: dict[str, int]
    canonical_sha256: str


class HistoryBuildErrorResponse(BaseModel):

    reason: str
    message: str
    detail: str | None = None
