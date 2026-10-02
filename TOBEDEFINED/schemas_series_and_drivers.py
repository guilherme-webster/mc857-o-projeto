from __future__ import annotations

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
