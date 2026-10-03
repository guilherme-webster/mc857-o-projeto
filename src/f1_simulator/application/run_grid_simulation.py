from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from f1_simulator.application.build_grid import GridEntry
from f1_simulator.domain.driver_attributes import DriverAttributes
from f1_simulator.domain.race_simulation import (
    ASSUMED_LAP_VARIABILITY,
    Competitor,
    simulate_race,
)
from f1_simulator.domain.random_source import RandomSource


@dataclass(frozen=True, slots=True)
class RaceSetup:
    total_laps: int
    track_id: str | None = None
    weather: str | None = None

    def __post_init__(self) -> None:
        if type(self.total_laps) is not int or self.total_laps <= 0:
            raise ValueError("total_laps must be a positive integer")


def run_grid_simulation(
    grid: Sequence[GridEntry],
    attributes: dict[str, DriverAttributes],
    setup: RaceSetup,
    rng: RandomSource | None = None,
) -> dict:
    competitors = tuple(
        Competitor(
            driver_id=entry.driver_id,
            name=entry.driver_name,
            attributes=attributes[entry.driver_id],
        )
        for entry in grid
    )
    result = simulate_race(
        competitors,
        setup.total_laps,
        variability=ASSUMED_LAP_VARIABILITY if rng is not None else None,
        rng=rng,
    )
    result["setup"] = {
        "total_laps": setup.total_laps,
        "track_id": setup.track_id,
        "weather": setup.weather,
    }
    return result
