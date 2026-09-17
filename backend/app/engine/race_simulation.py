from __future__ import annotations

from dataclasses import dataclass, field

from app.engine.models import CarState, DriverParameters


@dataclass
class RaceSimulation:

    parameters: list[DriverParameters]
    total_laps: int
    pit_laps: set[int] = field(default_factory=set)
    _cars: list[CarState] = field(default_factory=list, init=False)
    _params_by_id: dict[str, DriverParameters] = field(
        default_factory=dict, init=False
    )

    def __post_init__(self) -> None:
        if self.total_laps <= 0:
            raise ValueError("total_laps must be positive")
        runnable = [p for p in self.parameters if p.base_lap_time_ms is not None]
        self._params_by_id = {p.driver_id: p for p in runnable}
        self._cars = [CarState.from_parameters(p) for p in runnable]

    def run(self) -> dict:
        """Simulate every lap and return the full history ready for the API."""

        snapshots = [self.step() for _ in range(self.total_laps)]
        return {
            "total_laps": self.total_laps,
            "history": snapshots,
            "classification": self._classification(),
        }

    def step(self) -> dict:
        """Advance the simulation by exactly one lap and snapshot the field."""

        lap = self._cars[0].current_lap + 1 if self._cars else 1
        for car in self._cars:
            if car.retired:
                continue
            self._advance_car(car, lap)
        self._recompute_positions()
        return self._snapshot(lap)

    def _advance_car(self, car: CarState, lap: int) -> None:
        """Apply one lap of pace, degradation and optional pit loss to a car."""

        params = self._params_by_id[car.driver_id]
        car.current_lap = lap
        car.tire_age += 1
        lap_time = params.base_lap_time_ms + params.degradation_ms_per_lap * car.tire_age

        car.pitting_this_lap = lap in self.pit_laps
        if car.pitting_this_lap:
            lap_time += params.pit_loss_ms
            car.tire_age = 0

        car.last_lap_time_ms = lap_time
        car.total_time_ms += lap_time
        car.laps_completed = lap

    def _recompute_positions(self) -> None:
        """Order running cars by elapsed time; retired cars sink to the back."""

        running = sorted(
            (car for car in self._cars if not car.retired),
            key=lambda car: car.total_time_ms,
        )
        for index, car in enumerate(running, start=1):
            car.position = index
        offset = len(running)
        retired = sorted(
            (car for car in self._cars if car.retired),
            key=lambda car: (car.retired_on_lap or 0),
            reverse=True,
        )
        for index, car in enumerate(retired, start=1):
            car.position = offset + index

    def _snapshot(self, lap: int) -> dict:
        """Serialize the current field into a plain dict for one lap."""

        cars = sorted(self._cars, key=lambda car: car.position)
        return {
            "lap": lap,
            "cars": [
                {
                    "position": car.position,
                    "driver_id": car.driver_id,
                    "name": car.name,
                    "lap_time_ms": round(car.last_lap_time_ms, 1),
                    "total_time_ms": round(car.total_time_ms, 1),
                    "tire_age": car.tire_age,
                    "pitting": car.pitting_this_lap,
                    "retired": car.retired,
                }
                for car in cars
            ],
        }

    def _classification(self) -> list[dict]:
        """Return the final order once all laps have been simulated."""

        cars = sorted(self._cars, key=lambda car: car.position)
        return [
            {
                "position": car.position,
                "driver_id": car.driver_id,
                "name": car.name,
                "total_time_ms": round(car.total_time_ms, 1),
                "laps_completed": car.laps_completed,
                "retired": car.retired,
            }
            for car in cars
        ]
