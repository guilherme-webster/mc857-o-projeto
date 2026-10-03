from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
        if self.mode == "random" and self.pair_ids:
            raise ValueError("pair_ids are not accepted in random mode")
        return self


class DriverAttributesResponse(BaseModel):

    archetype: Literal["aggressive", "balanced", "conservative"]
    pace_offset_pct: float
    consistency_factor: float
    tyre_management_factor: float
    aggression: float
    composure: float
    sources: dict[str, Literal["generated", "preset", "manual"]]


class GridEntryResponse(BaseModel):

    driver_id: str
    driver_name: str
    team_id: str
    team_name: str
    attributes: DriverAttributesResponse


class BuildGridResponse(BaseModel):

    size: int
    seed: int
    grid: list[GridEntryResponse]


class AttributeOverride(BaseModel):

    driver_id: str
    pace_offset_pct: float | None = None
    consistency_factor: float | None = Field(default=None, gt=0)
    tyre_management_factor: float | None = Field(default=None, gt=0)
    aggression: float | None = Field(default=None, gt=0)
    composure: float | None = Field(default=None, gt=0)


class EditGridAttributesRequest(BaseModel):

    overrides: list[AttributeOverride] = Field(min_length=1, max_length=40)


class RaceSetupRequest(BaseModel):

    total_laps: int = Field(ge=1, le=200)
    track_id: str | None = None
    weather: str | None = None


class RunGridRequest(BaseModel):

    setup: RaceSetupRequest


class HistoryRaceResponse(BaseModel):

    race_id: str
    name: str
    season: int
    round_number: int
    circuit_id: str
    race_date: str
    start_time_utc: str | None


class HistoryRacesResponse(BaseModel):

    count: int
    races: list[HistoryRaceResponse]


class HistoryBuildResponse(BaseModel):

    schema_version: int
    row_counts: dict[str, int]
    canonical_sha256: str


class HistoryBuildErrorResponse(BaseModel):

    reason: str
    message: str
    detail: str | None = None
