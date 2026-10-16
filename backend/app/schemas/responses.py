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
    """``race`` monta o grid com a largada de ``race_id`` no historico; o
    tamanho vem da propria corrida."""

    size: int | None = Field(default=None, ge=1, le=40)
    mode: Literal["manual", "random", "race"]
    pair_ids: list[str] = Field(default_factory=list)
    race_id: str | None = None
    seed: int | None = Field(default=None, ge=0, le=2**53 - 1)

    @model_validator(mode="after")
    def _validate_scenario(self) -> BuildGridRequest:
        if self.mode in ("random", "race") and self.pair_ids:
            raise ValueError(f"pair_ids are not accepted in {self.mode} mode")
        if self.mode == "race":
            if not self.race_id:
                raise ValueError("race mode requires race_id")
            if self.size is not None:
                raise ValueError("size comes from the race in race mode")
        else:
            if self.race_id is not None:
                raise ValueError("race_id is only accepted in race mode")
            if self.size is None:
                raise ValueError(f"size is required in {self.mode} mode")
        return self


class DriverAttributesResponse(BaseModel):
    archetype: Literal["aggressive", "balanced", "conservative"]
    pace_offset_pct: float
    consistency_factor: float
    tyre_management_factor: float
    aggression: float
    composure: float
    sources: dict[str, Literal["generated", "preset", "manual"]]


class DriverProfileResponse(BaseModel):
    """Perfil ficticio nomeado aplicado ao piloto (origem ``preset``)."""

    characterization: str
    parameter_version: str


class GridEntryResponse(BaseModel):
    driver_id: str
    driver_name: str
    team_id: str
    team_name: str
    attributes: DriverAttributesResponse
    profile: DriverProfileResponse | None = None


class BuildGridResponse(BaseModel):
    size: int
    seed: int
    grid: list[GridEntryResponse]
    # Presente quando algum piloto do grid tem perfil ficticio nomeado.
    profiles_disclaimer: str | None = None


class AttributeOverride(BaseModel):
    driver_id: str
    pace_offset_pct: float | None = None
    consistency_factor: float | None = Field(default=None, gt=0)
    tyre_management_factor: float | None = Field(default=None, gt=0)
    aggression: float | None = Field(default=None, gt=0)
    composure: float | None = Field(default=None, gt=0)


class EditGridAttributesRequest(BaseModel):
    overrides: list[AttributeOverride] = Field(min_length=1, max_length=40)


class WeatherSegmentRequest(BaseModel):
    from_lap: int = Field(ge=1, le=200)
    to_lap: int = Field(ge=1, le=200)
    rain: Literal["dry", "light_rain", "heavy_rain"]


class RaceSetupRequest(BaseModel):
    total_laps: int = Field(ge=1, le=200)
    track_id: str | None = None
    weather: list[WeatherSegmentRequest] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_weather(self) -> RaceSetupRequest:
        for segment in self.weather:
            if segment.to_lap < segment.from_lap:
                raise ValueError("weather segment: to_lap must be >= from_lap")
            if segment.to_lap > self.total_laps:
                raise ValueError("weather segment exceeds total_laps")
        return self


class RunGridRequest(BaseModel):
    setup: RaceSetupRequest


class SaveRaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class SavedRaceMeta(BaseModel):
    id: str
    name: str
    saved_at: str
    seed: int | None = None
    track_id: str | None = None
    total_laps: int | None = None
    car_count: int


class SavedRacesResponse(BaseModel):
    count: int
    saved: list[SavedRaceMeta]


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


class ChampionshipStageEntry(BaseModel):
    driver_id: str = Field(min_length=1)
    position: int = Field(ge=1)
    retired: bool = False


class ChampionshipRequest(BaseModel):
    scoring: Literal["f1", "none"] = "f1"
    tiebreak: Literal["best_average", "most_wins"] = "best_average"
    stages: list[list[ChampionshipStageEntry]] = Field(min_length=1, max_length=24)


class ChampionshipRowResponse(BaseModel):
    position: int
    driver_id: str
    points: int
    wins: int
    podiums: int
    average_position: float
    stage_positions: list[int | None]
    stage_retired: list[bool]


class ChampionshipResponse(BaseModel):
    scoring: Literal["f1", "none"]
    tiebreak: Literal["best_average", "most_wins"]
    rows: list[ChampionshipRowResponse]
