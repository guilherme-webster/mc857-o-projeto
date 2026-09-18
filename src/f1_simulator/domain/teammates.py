"""Matched teammate observations and context-specific deterministic references.

No attribution to innate skill is made. References are observational baselines
for a single circuit/session/tyre/weather window, never universal lap times.
"""

from collections import defaultdict
from dataclasses import asdict
from itertools import combinations
from math import isfinite
from random import Random
from statistics import median

from f1_simulator.domain.driver_profile import DriverProfile, PaceContext, ProfileConfig
from f1_simulator.domain.profile_reliability import BootstrapConfig


def context_reference(
    profiles: tuple[DriverProfile, ...], context: PaceContext
) -> dict:
    """Recover the equal-driver field reference from an exact supported context.

    Each driver contributes once. The reference already includes observed car,
    tyres and conditions; adding their effects again would double count them.
    An absent context fails explicitly instead of borrowing another circuit.
    """
    entries = [
        (p.driver_id, c) for p in profiles for c in p.contexts if c.context == context
    ]
    if not entries:
        raise ValueError("context has no supported observations")
    if len({d for d, _ in entries}) != len(entries):
        raise ValueError("duplicate driver in context")
    value = float(median(c.observed_median_ms for _, c in entries))
    if not isfinite(value) or value <= 0:
        raise ValueError("reference must be positive and finite")
    if any(
        c.reference_ms != value or c.comparison_drivers != len(entries)
        for _, c in entries
    ):
        raise ValueError("context estimates do not share a complete field reference")
    return dict(
        context=asdict(context),
        reference_lap_time_ms=value,
        drivers=len(entries),
        laps=sum(c.laps for _, c in entries),
        driver_ids=sorted(d for d, _ in entries),
        reference_kind="observed_context_field_median_v1",
        variability_mode="disabled",
        additional_team_tyre_weather_effects=False,
    )


def _interval(
    values: list[float], config: BootstrapConfig
) -> tuple[float, float] | None:
    # Events are whole paired observations; the two drivers are never resampled
    # independently and within-event laps are not treated as independent samples.
    if len(values) < 2:
        return None
    rng = Random(config.seed)
    samples = sorted(
        median(rng.choices(values, k=len(values))) for _ in range(config.replicates)
    )

    def quantile(q):
        position = q * (len(samples) - 1)
        lower = int(position)
        upper = min(lower + 1, len(samples) - 1)
        return samples[lower] + (samples[upper] - samples[lower]) * (position - lower)

    tail = (1 - config.confidence) / 2
    return quantile(tail), quantile(1 - tail)


def compare_teammates(
    profiles: tuple[DriverProfile, ...],
    memberships: tuple[tuple[str, str, str], ...],
    config: ProfileConfig,
    bootstrap: BootstrapConfig,
) -> tuple[dict, ...]:
    """Compare pairs within team and shared contexts, then give events equal weight.

    Membership triples are session/team/driver from the canonical race roster.
    Candidate pairs with no shared support remain explicit. Symmetric gap is
    100*(median_A-median_B)/mean(median_A, median_B); negative means A faster.
    Changing team creates a different pair. Pairwise results are not transitive
    rankings because the shared context sets may differ between pairs.
    """
    if len({p.driver_id for p in profiles}) != len(profiles):
        raise ValueError("duplicate driver profiles")
    if len(set(memberships)) != len(memberships):
        raise ValueError("duplicate membership")
    team_by_driver = {}
    groups = defaultdict(list)
    for session, team, driver in memberships:
        if (session, driver) in team_by_driver:
            raise ValueError("ambiguous team membership")
        team_by_driver[session, driver] = team
        groups[session, team].append(driver)
    contexts = {}
    for p in profiles:
        by_key = {}
        for c in p.contexts:
            if c.context in by_key:
                raise ValueError("duplicate driver context")
            if team_by_driver.get((c.context.session_id, p.driver_id)) != c.team_id:
                raise ValueError("context disagrees with canonical team membership")
            by_key[c.context] = c
        contexts[p.driver_id] = by_key
    candidates = defaultdict(list)
    for (session, team), drivers in sorted(groups.items()):
        for a, b in combinations(sorted(drivers), 2):
            candidates[team, a, b].append(session)
    result = []
    for (team, a, b), sessions in sorted(candidates.items()):
        left = {
            k: v
            for k, v in contexts.get(a, {}).items()
            if k.session_id in sessions and v.team_id == team
        }
        right = {
            k: v
            for k, v in contexts.get(b, {}).items()
            if k.session_id in sessions and v.team_id == team
        }
        rows, event_values = [], defaultdict(list)
        for key in sorted(left.keys() & right.keys()):
            x, y = left[key], right[key]
            if x.reference_ms != y.reference_ms:
                raise ValueError("paired context has inconsistent field reference")
            if any(
                not isfinite(v) or v <= 0
                for v in (x.observed_median_ms, y.observed_median_ms)
            ):
                raise ValueError("paired times must be positive")
            delta = (
                200
                * (x.observed_median_ms - y.observed_median_ms)
                / (x.observed_median_ms + y.observed_median_ms)
            )
            rows.append(
                dict(
                    context=asdict(key),
                    driver_a_laps=x.laps,
                    driver_b_laps=y.laps,
                    driver_a_median_ms=x.observed_median_ms,
                    driver_b_median_ms=y.observed_median_ms,
                    driver_a_stints=x.stints,
                    driver_b_stints=y.stints,
                    gap_pct=delta,
                )
            )
            event_values[key.race_id].append(delta)
        events = [
            dict(race_id=key, shared_contexts=len(v), gap_pct=median(v))
            for key, v in sorted(event_values.items())
        ]
        values = [e["gap_pct"] for e in events]
        reason = (
            "no_shared_contexts"
            if not values
            else "insufficient_shared_events"
            if len(values) < config.min_events
            else None
        )
        interval = _interval(values, bootstrap) if reason is None else None
        warnings = []
        if len(values) < bootstrap.warn_below_events:
            warnings.append("few_shared_events")
        if interval is not None and interval[0] == interval[1]:
            warnings.append("degenerate_interval_not_certainty")
        result.append(
            dict(
                team_id=team,
                driver_a=a,
                driver_b=b,
                candidate_events=len(sessions),
                shared_events=len(events),
                driver_a_contexts=len(left),
                driver_b_contexts=len(right),
                shared_contexts=len(rows),
                union_contexts=len(left.keys() | right.keys()),
                driver_a_shared_laps=sum(r["driver_a_laps"] for r in rows),
                driver_b_shared_laps=sum(r["driver_b_laps"] for r in rows),
                gap_pct=median(values) if reason is None else None,
                interval_pct=interval,
                unavailable_reason=reason,
                warnings=warnings,
                events=events,
                contexts=rows,
            )
        )
    return tuple(result)
