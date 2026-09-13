"""Evaluate fixed descriptive profiles through canonical Python repositories."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from statistics import median

from f1_simulator.application.ports.history import HistoryRepository
from f1_simulator.application.profile_drivers import ProfileRun, profile_drivers
from f1_simulator.domain.profile_evaluation import (
    DriverStability,
    EvaluationPlan,
    StabilitySummary,
    compare_profiles,
)


@dataclass(frozen=True)
class EventCoverage:
    """Event-level denominator and all exclusion reasons, which may overlap."""

    partition: str
    session_id: str
    race_id: str
    race_name: str
    season: int
    race_date: str
    participants: int
    input_laps: int
    compared_laps: int
    coverage_pct: float | None
    compared_drivers: int
    exclusions: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class DriverEventEstimate:
    """One event's descriptive medians for visualization, regardless of min_events.

    Cross-event availability gates still apply to the partition-level profile.
    An absent participant creates no point; an entrant without comparable laps
    has an explicit None. No missing point is interpolated across events.
    """

    partition: str
    session_id: str
    driver_id: str
    team_ids: tuple[str, ...]
    input_laps: int
    compared_laps: int
    pace_delta_pct: float | None
    consistency_mad_pct: float | None


@dataclass(frozen=True)
class ProfileEvaluation:
    """Auditable evaluation, including independent runs and fixed plan digest."""

    plan: EvaluationPlan
    plan_sha256: str
    development: ProfileRun
    validation: ProfileRun
    coverage: tuple[EventCoverage, ...]
    event_estimates: tuple[DriverEventEstimate, ...]
    comparisons: tuple[DriverStability, ...]
    summary: StabilitySummary
    validation_after_development: bool
    warnings: tuple[str, ...]


def evaluate_profiles(
    repository: HistoryRepository, plan: EvaluationPlan
) -> ProfileEvaluation:
    """Evaluate disjoint races with identical, predeclared modeling parameters.

    Metadata and event separation are validated before any lap is read. Each
    partition is passed separately to the existing profiler; validation never
    changes development references or config. No parameter fitting, baseline
    prediction or HTTP is introduced. Chronology is reported from catalog dates.
    """
    available = {r["source"].get("session_id") for r in repository.reports()}
    selected = plan.development_sessions + plan.validation_sessions
    if not set(selected) <= available:
        raise ValueError("evaluation sessions lack ETL provenance; ingest them first")
    metadata = {}
    participants = {}
    seen_races = set()
    for session_id in selected:
        sessions = tuple(repository.records("sessions", session_id=session_id))
        if len(sessions) != 1 or sessions[0]["kind"] != "R":
            raise ValueError(f"{session_id}: evaluation requires a unique race session")
        race_id = sessions[0]["race_id"]
        if race_id in seen_races:
            raise ValueError("each race must occur exactly once across the evaluation")
        seen_races.add(race_id)
        races = tuple(repository.records("races", race_id=race_id))
        if len(races) != 1:
            raise ValueError(f"{session_id}: missing or ambiguous race metadata")
        metadata[session_id] = races[0]
        participants[session_id] = tuple(
            sorted(
                r["driver_id"]
                for r in repository.records("session_drivers", session_id=session_id)
            )
        )
    development = profile_drivers(
        repository, session_ids=plan.development_sessions, config=plan.config
    )
    validation = profile_drivers(
        repository, session_ids=plan.validation_sessions, config=plan.config
    )
    comparisons, summary = compare_profiles(development.profiles, validation.profiles)
    coverage, event_estimates = [], []
    for partition, run in (("development", development), ("validation", validation)):
        by_driver = {p.driver_id: p for p in run.profiles}
        for session_id in run.session_ids:
            race = metadata[session_id]
            laps = [lap for lap in run.laps if lap.session_id == session_id]
            compared = [lap for lap in laps if not lap.exclusions]
            coverage.append(
                EventCoverage(
                    partition,
                    session_id,
                    race["race_id"],
                    race["name"],
                    race["season"],
                    race["race_date"],
                    len(participants[session_id]),
                    len(laps),
                    len(compared),
                    100 * len(compared) / len(laps) if laps else None,
                    len({lap.driver_id for lap in compared}),
                    tuple(
                        sorted(
                            Counter(
                                reason for lap in laps for reason in lap.exclusions
                            ).items()
                        )
                    ),
                )
            )
            for driver in participants[session_id]:
                contexts = [
                    c
                    for c in by_driver[driver].contexts
                    if c.context.session_id == session_id
                ]
                event_estimates.append(
                    DriverEventEstimate(
                        partition,
                        session_id,
                        driver,
                        tuple(sorted({c.team_id for c in contexts})),
                        sum(lap.driver_id == driver for lap in laps),
                        sum(lap.driver_id == driver for lap in compared),
                        # This is the same within-event reduction specified by the
                        # profiler; no lap timing or eligibility rule is duplicated.
                        median(c.pace_delta_pct for c in contexts)
                        if contexts
                        else None,
                        median(c.consistency_mad_pct for c in contexts)
                        if contexts
                        else None,
                    )
                )
    chronological = min(
        metadata[s]["race_date"] for s in plan.validation_sessions
    ) > max(metadata[s]["race_date"] for s in plan.development_sessions)
    warnings = [
        "descriptive_stability_not_prediction_error",
        "context_distributions_may_differ",
        "uncertainty_not_estimated",
        "no_automatic_robustness_threshold",
    ]
    if not chronological:
        warnings.append("validation_not_strictly_after_development")
    if not summary.paired_drivers:
        warnings.append("no_supported_driver_pairs")
    canonical_plan = json.dumps(
        asdict(plan), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return ProfileEvaluation(
        plan,
        hashlib.sha256(canonical_plan.encode()).hexdigest(),
        development,
        validation,
        tuple(coverage),
        tuple(event_estimates),
        comparisons,
        summary,
        chronological,
        tuple(warnings),
    )
