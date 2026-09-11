"""Fictional, backend-free race state used to prototype the race screen.

This is deliberately not the simulation engine described in ADR 0002: it
has no telemetry, no events, and no connection to the Django contract. It
exists only so the Arcade race screen can be built and reviewed before the
real snapshot format is agreed with the backend. Replacing it with real
snapshots later should only require swapping what feeds ``RaceState``, not
the drawing code in ``race_view.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RaceCar:
    """One fictional car moving around the track at a constant speed.

    ``speed`` is expressed in laps per second, so ``distance`` (in laps)
    grows linearly with time. Keeping speed constant is a simplification
    the team chose on purpose for this first prototype; a real car's speed
    would instead come from simulated lap times.
    """

    name: str
    color: tuple[int, int, int]
    speed: float
    distance: float = 0.0

    def __post_init__(self) -> None:
        """Reject a car that could never move, which would break the demo."""

        if self.speed <= 0:
            raise ValueError("speed must be positive")
        if self.distance < 0:
            raise ValueError("distance must start at zero or later")

    def advance(self, delta_time: float) -> None:
        """Move the car forward by ``delta_time`` seconds at constant speed."""

        self.distance += self.speed * delta_time

    @property
    def laps_completed(self) -> int:
        """Return the number of full laps this car has already finished."""

        return int(self.distance)

    @property
    def lap_fraction(self) -> float:
        """Return progress through the current lap, in the range [0, 1)."""

        return self.distance % 1.0


@dataclass(slots=True)
class RaceState:
    """A minimal, in-memory race made of a fixed list of fictional cars."""

    cars: list[RaceCar] = field(default_factory=list)

    def advance(self, delta_time: float) -> None:
        """Advance every car by ``delta_time`` seconds."""

        for car in self.cars:
            car.advance(delta_time)

    def standings(self) -> list[RaceCar]:
        """Return the cars ordered from race leader to last place.

        Ranking by total distance travelled (not just current-lap fraction)
        is what correctly keeps a car that has completed more laps ahead of
        one that is merely further along in the same lap.
        """

        return sorted(self.cars, key=lambda car: car.distance, reverse=True)
