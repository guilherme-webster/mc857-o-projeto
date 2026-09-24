"""Order descriptive pace estimates without implying statistical superiority."""

from dataclasses import dataclass
from math import isfinite

from f1_simulator.application.profile_drivers import ProfileRun
from f1_simulator.domain.profile_reliability import (
    BootstrapConfig,
    ProfileSupport,
    profile_support,
)


@dataclass(frozen=True)
class RankedDriver:
    """Competition rank (1, 1, 3); unavailable drivers have no position or pace."""

    position: int | None
    driver_id: str
    name: str
    pace_delta_pct: float | None
    support: ProfileSupport


def rank_drivers(
    run: ProfileRun, bootstrap: BootstrapConfig = BootstrapConfig()
) -> tuple[RankedDriver, ...]:
    """Smaller aggregate pace is faster; exact ties share rank, IDs order display.

    Rank uses full precision, never rounded labels, MAD or confidence bounds.
    Marginal intervals do not test whether adjacent drivers differ. Input is one
    common profiling run; its selection/configuration must accompany publication.
    """
    if len({p.driver_id for p in run.profiles}) != len(run.profiles):
        raise ValueError("duplicate driver profiles")
    names = dict(run.driver_names)
    for p in run.profiles:
        if not p.unavailable_reason and (
            p.pace_delta_pct is None
            or not isfinite(p.pace_delta_pct)
            or p.pace_delta_pct <= -100
        ):
            raise ValueError("available profile requires finite pace greater than -100")
    ordered = sorted(
        run.profiles,
        key=lambda p: (
            bool(p.unavailable_reason),
            p.pace_delta_pct if not p.unavailable_reason else 0,
            p.driver_id,
        ),
    )
    rows = []
    previous, position = None, None
    for i, p in enumerate(ordered, 1):
        pace = None if p.unavailable_reason else p.pace_delta_pct
        if pace is not None and pace != previous:
            position = i
        rows.append(
            RankedDriver(
                position if pace is not None else None,
                p.driver_id,
                names.get(p.driver_id, p.driver_id),
                pace,
                profile_support(p, "selected_sample", bootstrap),
            )
        )
        previous = pace
    return tuple(rows)
