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


@dataclass(slots=True)
class CarState:

    driver_id: str
    name: str
    position: int
    current_lap: int = 0
    laps_completed: int = 0
    tire_age: int = 0
    total_time_ms: float = 0.0
    last_lap_time_ms: float = 0.0
    pitting_this_lap: bool = False
    retired: bool = False
    retired_on_lap: int | None = None

    @classmethod
    def from_parameters(cls, params: DriverParameters) -> "CarState":
        """Create the starting state for a car from its tuned parameters."""

        return cls(
            driver_id=params.driver_id,
            name=params.name,
            position=params.grid_position,
        )
