from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SeriesTrackRequest(BaseModel):

    circuit_id: str = Field(min_length=1)
    total_laps: int = Field(ge=1, le=200)


class SeriesCompetitorRequest(BaseModel):

    driver_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    pace_ms_per_km: float = Field(gt=0, allow_inf_nan=False)


class SeriesSimulationRequest(BaseModel):

    tracks: list[SeriesTrackRequest] = Field(min_length=1, max_length=24)
    competitors: list[SeriesCompetitorRequest] = Field(min_length=1, max_length=40)
    tyres: dict[str, str] | None = None
    variability: bool = False
    seed: int | None = Field(default=None, ge=0, le=2**53 - 1)

    @model_validator(mode="after")
    def _validate_scenario(self) -> "SeriesSimulationRequest":
        if self.seed is not None and not self.variability:
            raise ValueError(
                "seed may only be provided with variability=true: "
                "without noise it would be silently ignored"
            )
        if self.tyres is not None:
            driver_ids = {item.driver_id for item in self.competitors}
            planned = set(self.tyres)
            unknown = sorted(planned - driver_ids)
            missing = sorted(driver_ids - planned)
            if unknown:
                raise ValueError(f"tyres with unknown driver_id: {unknown}")
            if missing:
                raise ValueError(
                    f"tyres must cover all competitors; missing: {missing}"
                )
            if any(not compound.strip() for compound in self.tyres.values()):
                raise ValueError("tyres contains an empty compound")
        return self


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


class CatalogEntryResponse(BaseModel):

    driver_id: str
    driver_name: str
    driver_code: str | None
    team_id: str
    team_name: str


class CatalogResponse(BaseModel):

    count: int
    entries: list[CatalogEntryResponse]


class BuildGridRequest(BaseModel):

    size: int = Field(ge=1, le=40)
    mode: Literal["manual", "random"]
    pair_ids: list[str] = Field(default_factory=list)
    seed: int | None = Field(default=None, ge=0, le=2**53 - 1)

    @model_validator(mode="after")
    def _validate_scenario(self) -> "BuildGridRequest":
        is_random = self.mode == "random"
        if self.seed is not None and not is_random:
            raise ValueError("seed may only be provided in random mode")
        if is_random and self.pair_ids:
            raise ValueError("pair_ids are not accepted in random mode")
        return self


class GridEntryResponse(BaseModel):

    driver_id: str
    driver_name: str
    team_id: str
    team_name: str


class BuildGridResponse(BaseModel):

    size: int
    seed: int | None = None
    grid: list[GridEntryResponse]


class HistoryBuildResponse(BaseModel):

    schema_version: int
    row_counts: dict[str, int]
    canonical_sha256: str


class HistoryBuildErrorResponse(BaseModel):

    reason: str
    message: str
    detail: str | None = None
