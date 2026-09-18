from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DriverParameters:

    driver_id: str
    name: str
    team_id: str | None
    grid_position: int
    base_lap_time_ms: float | None
    degradation_ms_per_lap: float # TODO
    pit_loss_ms: float # TODO
    retirement_per_lap: float = 0.0 # TODO
