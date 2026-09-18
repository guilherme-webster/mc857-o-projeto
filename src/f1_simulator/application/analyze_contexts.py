"""Compare declared context variants on the same already observed events."""

from dataclasses import dataclass

from f1_simulator.application.evaluate_profiles import (
    ProfileEvaluation,
    evaluate_profiles,
)
from f1_simulator.application.ports.history import HistoryRepository
from f1_simulator.domain.context_sensitivity import ContextVariant
from f1_simulator.domain.profile_evaluation import EvaluationPlan
from f1_simulator.domain.profile_reliability import BootstrapConfig


@dataclass(frozen=True)
class ContextChange:
    """Paired driver/event changes; counts expose changing support, not causality."""

    variant: str
    partition: str
    session_id: str
    driver_id: str
    input_laps: int
    baseline_laps: int
    compared_laps: int
    common_laps: int
    contexts: int
    mixed_stint_contexts: int
    pace_shift_pp: float | None
    mad_shift_pp: float | None


def analyze_contexts(
    repository: HistoryRepository,
    plan: EvaluationPlan,
    *,
    narrow_window: int = 5,
    bootstrap: BootstrapConfig = BootstrapConfig(),
) -> tuple[tuple[ProfileEvaluation, ...], tuple[ContextChange, ...]]:
    """Run a fixed 2x2 exploration, without selecting an optimal variant.

    These events have already been inspected. Old partition labels are retained
    for traceability, not to claim new confirmatory validation. Narrower lap
    windows only proxy track evolution; rain intensity remains unobserved.
    """
    if type(narrow_window) is not int or not 0 < narrow_window < plan.config.lap_window:
        raise ValueError("narrow_window must be positive and smaller than baseline")
    variants = (
        ContextVariant(),
        ContextVariant("stints", split_stints=True),
        ContextVariant("narrow", narrow_window),
        ContextVariant("narrow-stints", narrow_window, True),
    )
    results = tuple(
        evaluate_profiles(repository, plan, variant=v, bootstrap=bootstrap)
        for v in variants
    )
    baseline = {(r.session_id, r.driver_id): r for r in results[0].event_estimates}

    def supported_laps(result):
        return {
            (lap.session_id, lap.driver_id, lap.lap_number)
            for run in (result.development, result.validation)
            for lap in run.laps
            if not lap.exclusions
        }

    original = supported_laps(results[0])
    rows = []
    for result in results:
        common = original & supported_laps(result)
        for row in result.event_estimates:
            base = baseline[row.session_id, row.driver_id]
            rows.append(
                ContextChange(
                    result.variant.name,
                    row.partition,
                    row.session_id,
                    row.driver_id,
                    row.input_laps,
                    base.compared_laps,
                    row.compared_laps,
                    sum(
                        s == row.session_id and d == row.driver_id for s, d, _ in common
                    ),
                    row.contexts,
                    row.mixed_stint_contexts,
                    row.pace_delta_pct - base.pace_delta_pct
                    if row.pace_delta_pct is not None
                    and base.pace_delta_pct is not None
                    else None,
                    row.consistency_mad_pct - base.consistency_mad_pct
                    if row.consistency_mad_pct is not None
                    and base.consistency_mad_pct is not None
                    else None,
                )
            )
    return results, tuple(rows)
