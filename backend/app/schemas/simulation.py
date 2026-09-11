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
