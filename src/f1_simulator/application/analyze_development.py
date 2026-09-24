"""Explore only development sessions; the reserved sample is never profiled."""

from collections import defaultdict
from dataclasses import asdict, replace
import hashlib
import json
from statistics import median

from f1_simulator.application.ports.history import HistoryRepository
from f1_simulator.application.profile_drivers import profile_drivers
from f1_simulator.domain.context_sensitivity import ContextVariant, separate_stints
from f1_simulator.domain.driver_profile import estimate_profiles
from f1_simulator.domain.profile_evaluation import EvaluationPlan
from f1_simulator.domain.profile_reliability import BootstrapConfig, profile_support


def analyze_development(
    repository: HistoryRepository,
    plan: EvaluationPlan,
    *,
    bootstrap: BootstrapConfig = BootstrapConfig(),
    narrow_window: int = 5,
) -> dict:
    """Measure grouping sensitivity and leave-one-event-out influence offline.

    Holdout IDs are retained as protocol metadata only. No records for their
    sessions are requested. Dropping an event recomputes the median of event
    medians exactly: references within other events cannot depend on it.
    Influence is descriptive, not prediction error or another bootstrap interval.
    """
    if type(narrow_window) is not int or not 0 < narrow_window < plan.config.lap_window:
        raise ValueError("narrow_window must be smaller than the baseline lap window")
    variants = (
        ContextVariant(),
        ContextVariant("stints", split_stints=True),
        ContextVariant("narrow", narrow_window),
        ContextVariant("narrow-stints", narrow_window, True),
    )
    settings = dict(
        version="development-exploration-v1",
        plan=asdict(plan),
        bootstrap=asdict(bootstrap),
        variants=[asdict(v) for v in variants],
    )
    digest = hashlib.sha256(
        json.dumps(
            settings, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    results = []
    baseline = {}
    for variant in variants:
        config = replace(
            plan.config, lap_window=variant.lap_window or plan.config.lap_window
        )
        run = profile_drivers(
            repository, session_ids=plan.development_sessions, config=config
        )
        if variant.split_stints:
            profiles, audit = estimate_profiles(
                separate_stints(run.laps),
                tuple(p.driver_id for p in run.profiles),
                config,
            )
            run = replace(
                run,
                profiles=profiles,
                laps=audit,
                method_version="contextual-pace-stint-v1",
            )
        names = dict(run.driver_names)
        rows, influences = [], []
        for profile in run.profiles:
            support = profile_support(profile, "development", bootstrap)
            events = defaultdict(list)
            for context in profile.contexts:
                events[context.context.race_id].append(context)
            event_values = {
                key: (
                    median(c.pace_delta_pct for c in cs),
                    median(c.consistency_mad_pct for c in cs),
                )
                for key, cs in sorted(events.items())
            }
            shifts = []
            for omitted in event_values:
                remaining = [v for key, v in event_values.items() if key != omitted]
                available = (
                    len(remaining) >= config.min_events
                    and profile.pace_delta_pct is not None
                )
                pace = median(v[0] for v in remaining) if available else None
                mad = median(v[1] for v in remaining) if available else None
                shift = pace - profile.pace_delta_pct if available else None
                if shift is not None:
                    shifts.append(abs(shift))
                influences.append(
                    dict(
                        driver_id=profile.driver_id,
                        omitted_race_id=omitted,
                        remaining_events=len(remaining),
                        pace_pct=pace,
                        mad_pct=mad,
                        pace_shift_pp=shift,
                        mad_shift_pp=mad - profile.consistency_mad_pct
                        if available
                        else None,
                        unavailable_reason=None
                        if available
                        else "insufficient_remaining_events",
                    )
                )
            row = asdict(support) | dict(
                driver_name=names.get(profile.driver_id, profile.driver_id),
                pace_pct=profile.pace_delta_pct,
                mad_pct=profile.consistency_mad_pct,
                unavailable_reason=profile.unavailable_reason,
                max_leave_one_event_out_pace_shift_pp=max(shifts) if shifts else None,
            )
            if variant.name == "baseline":
                baseline[profile.driver_id] = row
            base = baseline[profile.driver_id]
            for metric in ("pace", "mad"):
                a, b = base[f"{metric}_pct"], row[f"{metric}_pct"]
                row[f"{metric}_shift_from_baseline_pp"] = (
                    b - a if a is not None and b is not None else None
                )
            rows.append(row)
        count = sum(p.compared_laps for p in run.profiles)
        results.append(
            dict(
                variant=asdict(variant),
                run=asdict(run),
                drivers=rows,
                event_influence=influences,
                summary=dict(
                    input_laps=len(run.laps),
                    compared_laps=count,
                    coverage_pct=100 * count / len(run.laps) if run.laps else None,
                    supported_drivers=sum(
                        p.unavailable_reason is None for p in run.profiles
                    ),
                    total_drivers=len(run.profiles),
                    mixed_stint_contexts=sum(
                        c.stints > 1 for p in run.profiles for c in p.contexts
                    ),
                ),
            )
        )
    return dict(
        settings=settings,
        analysis_sha256=digest,
        reserved_metrics_computed=False,
        results=results,
    )
