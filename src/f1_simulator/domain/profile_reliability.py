"""Conditional event-cluster bootstrap for descriptive profile medians.

Events, not laps, are the resampling units. Reducing each event first is exact
for this estimator (median of event medians) and keeps its internal dependence
and field reference fixed. These are marginal intervals, not ranking tests.
"""

from collections import defaultdict
from dataclasses import dataclass
from math import isfinite
from random import Random
from statistics import median

from f1_simulator.domain.driver_profile import DriverProfile


@dataclass(frozen=True)
class BootstrapConfig:
    """Reproducible percentile intervals; the small-sample warning is heuristic."""

    replicates: int = 2000
    seed: int = 42
    confidence: float = 0.95
    warn_below_events: int = 5

    def __post_init__(self):
        if type(self.replicates) is not int or self.replicates < 100:
            raise ValueError("replicates must be an integer >= 100")
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")
        if (
            isinstance(self.confidence, bool)
            or not isfinite(self.confidence)
            or not 0 < self.confidence < 1
        ):
            raise ValueError("confidence must lie between zero and one")
        if type(self.warn_below_events) is not int or self.warn_below_events < 2:
            raise ValueError("warn_below_events must be an integer >= 2")


@dataclass(frozen=True)
class ProfileSupport:
    """Counts and marginal interval endpoints in percent; None is not zero."""

    partition: str
    driver_id: str
    input_laps: int
    compared_laps: int
    contexts: int
    events: int
    mixed_stint_contexts: int
    pace_interval_pct: tuple[float, float] | None
    consistency_interval_pct: tuple[float, float] | None
    warnings: tuple[str, ...]


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def profile_support(
    profile: DriverProfile, partition: str, config: BootstrapConfig
) -> ProfileSupport:
    """Resample supported events equally; never bootstrap individual laps.

    Missing events are not imputed. This conditional empirical interval does
    not estimate uncertainty due to missingness, car effects or field changes.
    Even a zero-width interval cannot certify exactness. With fewer than two
    supported events, or an unavailable aggregate, no interval is reported.
    """
    events = defaultdict(list)
    for context in profile.contexts:
        events[context.context.race_id].append(context)
    values = [
        (
            median(c.pace_delta_pct for c in events[key]),
            median(c.consistency_mad_pct for c in events[key]),
        )
        for key in sorted(events)
    ]
    warnings = []
    pace_interval = consistency_interval = None
    if profile.unavailable_reason:
        warnings.append(profile.unavailable_reason)
    if len(values) < config.warn_below_events:
        warnings.append("few_events_exploratory_interval")
    if len(values) < 2:
        warnings.append("insufficient_events_for_interval")
    elif not profile.unavailable_reason:
        rng = Random(config.seed)
        pace, consistency = [], []
        for _ in range(config.replicates):
            sample = [values[rng.randrange(len(values))] for _ in values]
            pace.append(median(v[0] for v in sample))
            consistency.append(median(v[1] for v in sample))
        tail = (1 - config.confidence) / 2
        pace_interval = (_percentile(pace, tail), _percentile(pace, 1 - tail))
        consistency_interval = (
            _percentile(consistency, tail),
            _percentile(consistency, 1 - tail),
        )
        if any(a == b for a, b in (pace_interval, consistency_interval)):
            warnings.append("degenerate_interval_not_certainty")
    return ProfileSupport(
        partition,
        profile.driver_id,
        profile.input_laps,
        profile.compared_laps,
        len(profile.contexts),
        len(events),
        sum(c.stints > 1 for c in profile.contexts),
        pace_interval,
        consistency_interval,
        tuple(warnings),
    )
