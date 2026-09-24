"""Descriptive driver/team pace, conditional on observed race context.

This experimental method estimates neither innate skill nor a predictive lap
model. Each context compares equally weighted driver medians. Event-level
aggregation prevents long races from dominating a multi-event profile. No
randomness, database, dataframe or transport is involved.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from math import isfinite
from statistics import median

from f1_simulator.domain.history import HistoricalRecord

METHOD_VERSION = "contextual-pace-v1"


@dataclass(frozen=True)
class ProfileConfig:
    """Explicit exploratory choices, not calibrated defaults.

    Windows partition race lap number and tyre age; neither controls traffic,
    fuel or setup completely. Minimum counts are availability gates, not
    statistical confidence. Weather must cover the entire lap without a stale
    sample or a change in the observed rainfall boolean.
    """

    lap_window: int
    tyre_age_window: int
    weather_max_age_ms: int
    min_laps_per_context: int
    min_drivers_per_context: int
    min_events: int

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.min_drivers_per_context < 2 or self.min_laps_per_context < 2:
            raise ValueError("comparison requires at least two drivers and two laps")


@dataclass(frozen=True, order=True)
class PaceContext:
    """Scope in which milliseconds can be compared; rainfall is not track grip."""

    session_id: str
    race_id: str
    season: int
    circuit_id: str
    compound: str
    rainfall: bool
    lap_window_start: int
    tyre_age_window_start: int


@dataclass(frozen=True)
class LapAssessment:
    """Audit of every input lap; all applicable exclusion reasons are retained."""

    session_id: str
    driver_id: str
    team_id: str | None
    lap_number: int
    stint: int | None
    lap_time_ms: int | None
    context: PaceContext | None
    exclusions: tuple[str, ...]
    reference_ms: float | None = None
    residual_pct: float | None = None


@dataclass(frozen=True)
class ContextEstimate:
    """Median pace and raw MAD of residuals, without a Gaussian conversion."""

    context: PaceContext
    team_id: str
    laps: int
    stints: int
    comparison_drivers: int
    reference_ms: float
    observed_median_ms: float
    pace_delta_pct: float
    consistency_mad_pct: float


@dataclass(frozen=True)
class DriverProfile:
    """Immutable observational profile; unavailable estimates are None, never zero."""

    driver_id: str
    input_laps: int
    compared_laps: int
    events: int
    exclusions: tuple[tuple[str, int], ...]
    contexts: tuple[ContextEstimate, ...]
    pace_delta_pct: float | None
    consistency_mad_pct: float | None
    unavailable_reason: str | None


def _interval_values(
    rows: tuple[HistoricalRecord, ...],
    start: int,
    end: int,
    field: str,
    max_age_ms: int | None = None,
) -> tuple[object, ...]:
    """Backward as-of at start plus events through end, never a future fill.

    Simultaneous conflicting observations make coverage unknown. State events
    persist until changed; sampled weather additionally expires by tolerance.
    End is included conservatively to exclude a transition at the lap boundary.
    """
    by_time: dict[int, set] = defaultdict(set)
    for row in rows:
        if row["session_time_ms"] is not None:
            by_time[row["session_time_ms"]].add(row[field])
    times = sorted(by_time)
    index = bisect_right(times, start) - 1
    if index < 0:
        return ()
    selected = times[index : bisect_right(times, end)]
    values = []
    for i, time in enumerate(selected):
        until = selected[i + 1] if i + 1 < len(selected) else end
        if max_age_ms is not None and until - time > max_age_ms:
            return ()
        value = by_time[time]
        if len(value) != 1 or None in value:
            return ()
        values.append(next(iter(value)))
    return tuple(values)


def assess_session(
    *,
    session_id: str,
    race_id: str,
    season: int,
    circuit_id: str,
    laps: tuple[HistoricalRecord, ...],
    weather: tuple[HistoricalRecord, ...],
    session_status: tuple[HistoricalRecord, ...],
    teams: dict[str, str],
    config: ProfileConfig,
    lap_schema_complete: bool = True,
) -> tuple[LapAssessment, ...]:
    """Select canonical race observations without mutating or filtering ETL facts.

    Clear track status and accuracy flags do not prove free air. Unknown
    quality is excluded conservatively. A missing/ambiguous event team prevents
    attributing a profile to a team; car numbers are never used as identities.
    """
    counts = Counter((r["driver_id"], r["lap_number"]) for r in laps)
    assessed = []
    for lap in sorted(laps, key=lambda r: (r["driver_id"], r["lap_number"])):
        reasons = []
        if not lap_schema_complete:
            reasons.append("lap_schema_incomplete_or_unknown")
        driver = lap["driver_id"]
        time = lap["lap_time_ms"]
        start, end = lap["lap_start_ms"], lap["session_time_ms"]
        if lap["session_id"] != session_id:
            raise ValueError("lap does not belong to selected session")
        if counts[driver, lap["lap_number"]] != 1:
            reasons.append("duplicate_lap")
        if driver not in teams:
            reasons.append("missing_or_ambiguous_team")
        if time is None or not isfinite(time) or time <= 0:
            reasons.append("invalid_lap_time")
        if lap["lap_number"] == 1:
            reasons.append("first_lap")
        if lap["pit_in_ms"] is not None or lap["pit_out_ms"] is not None:
            reasons.append("pit_lap")
        for field, expected in (
            ("accurate", True),
            ("deleted", False),
            ("generated", False),
        ):
            if lap[field] is not expected:
                reasons.append(
                    f"{field}_unknown" if lap[field] is None else f"{field}_rejected"
                )
        if lap["track_status"] != "1":
            reasons.append("track_not_clear_or_unknown")
        compound, age, stint = lap["compound"], lap["tyre_life_laps"], lap["stint"]
        if compound not in {"SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"}:
            reasons.append("compound_unknown")
        if age is None or not isfinite(age) or age < 0 or stint is None:
            reasons.append("tyre_context_unknown")
        rainfall = None
        if start is None or end is None or end <= start:
            reasons.append("lap_clock_unknown")
        else:
            states = _interval_values(session_status, start, end, "status")
            if not states or any(s != "Started" for s in states):
                reasons.append("session_not_running_or_unknown")
            rain = _interval_values(
                weather, start, end, "rainfall", config.weather_max_age_ms
            )
            if not rain or any(type(r) is not bool for r in rain):
                reasons.append("weather_missing_or_stale")
            elif len(set(rain)) != 1:
                reasons.append("weather_transition")
            else:
                rainfall = rain[0]
        context = None
        if not reasons:
            context = PaceContext(
                session_id,
                race_id,
                season,
                circuit_id,
                compound,
                rainfall,
                ((lap["lap_number"] - 1) // config.lap_window) * config.lap_window + 1,
                int(age // config.tyre_age_window) * config.tyre_age_window,
            )
        assessed.append(
            LapAssessment(
                session_id,
                driver,
                teams.get(driver),
                lap["lap_number"],
                stint,
                time,
                context,
                tuple(reasons),
            )
        )
    return tuple(assessed)


def estimate_profiles(
    assessments: tuple[LapAssessment, ...],
    driver_ids: tuple[str, ...],
    config: ProfileConfig,
) -> tuple[tuple[DriverProfile, ...], tuple[LapAssessment, ...]]:
    """Compare equal-weight driver medians within each eligible context.

    Positive delta means slower than the contextual field reference (which
    includes the driver). MAD measures observed dispersion after context
    centering, not an identified psychological or intrinsic consistency trait.
    Events receive equal weight; no cross-circuit millisecond average is made.
    """
    groups = defaultdict(lambda: defaultdict(list))
    for i, lap in enumerate(assessments):
        if not lap.exclusions:
            groups[lap.context][lap.driver_id].append(i)
    audit = list(assessments)
    estimates = defaultdict(list)
    for context, drivers in sorted(groups.items()):
        supported = {
            d: ids
            for d, ids in drivers.items()
            if len(ids) >= config.min_laps_per_context
        }
        for driver, indices in drivers.items():
            reason = None
            if driver not in supported:
                reason = "insufficient_context_laps"
            elif len(supported) < config.min_drivers_per_context:
                reason = "insufficient_comparison_drivers"
            if reason:
                for i in indices:
                    audit[i] = replace(audit[i], exclusions=(reason,))
        if len(supported) < config.min_drivers_per_context:
            continue
        reference = float(
            median(
                median(audit[i].lap_time_ms for i in ids) for ids in supported.values()
            )
        )
        for driver, indices in supported.items():
            residuals = [100 * (audit[i].lap_time_ms / reference - 1) for i in indices]
            center = median(residuals)
            for i, residual in zip(indices, residuals):
                audit[i] = replace(
                    audit[i], reference_ms=reference, residual_pct=residual
                )
            estimates[driver].append(
                ContextEstimate(
                    context,
                    audit[indices[0]].team_id,
                    len(indices),
                    len({audit[i].stint for i in indices}),
                    len(supported),
                    reference,
                    float(median(audit[i].lap_time_ms for i in indices)),
                    center,
                    median(abs(r - center) for r in residuals),
                )
            )
    profiles = []
    for driver in sorted(set(driver_ids)):
        laps = [lap for lap in audit if lap.driver_id == driver]
        contexts = tuple(estimates[driver])
        events = defaultdict(list)
        for estimate in contexts:
            events[estimate.context.race_id].append(estimate)
        reason = None
        if not laps:
            reason = "no_lap_observations"
        elif not contexts:
            reason = "no_comparable_contexts"
        elif len(events) < config.min_events:
            reason = "insufficient_events"
        pace = consistency = None
        if reason is None:
            pace = median(
                median(c.pace_delta_pct for c in cs) for cs in events.values()
            )
            consistency = median(
                median(c.consistency_mad_pct for c in cs) for cs in events.values()
            )
        profiles.append(
            DriverProfile(
                driver,
                len(laps),
                sum(not lap.exclusions for lap in laps),
                len(events),
                tuple(
                    sorted(Counter(r for lap in laps for r in lap.exclusions).items())
                ),
                contexts,
                pace,
                consistency,
                reason,
            )
        )
    return tuple(profiles), tuple(audit)
