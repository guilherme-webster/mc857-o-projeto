"""Explicit exploratory regrouping of canonical lap assessments, not ETL edits."""

from dataclasses import dataclass, replace

from f1_simulator.domain.driver_profile import LapAssessment, PaceContext


@dataclass(frozen=True)
class ContextVariant:
    """Stint ordinal is a sensitivity probe, not equivalent strategy across cars."""

    name: str = "baseline"
    lap_window: int | None = None
    split_stints: bool = False

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("variant name must be nonempty")
        if self.lap_window is not None and (
            type(self.lap_window) is not int or self.lap_window < 1
        ):
            raise ValueError("lap_window must be a positive integer")
        if type(self.split_stints) is not bool:
            raise ValueError("split_stints must be boolean")


@dataclass(frozen=True, order=True)
class StintContext(PaceContext):
    """Experimental context extension; the original v1 contract stays intact."""

    comparison_stint: int


def separate_stints(laps: tuple[LapAssessment, ...]) -> tuple[LapAssessment, ...]:
    """Split BEFORE support gates, retaining all quality exclusions.

    Previous support exclusions are removed because comparison groups change;
    eligibility/quality exclusions must never be relaxed. Reference and residual
    are invalidated, so the normal estimator recomputes them for the new field.
    """
    support_reasons = {"insufficient_context_laps", "insufficient_comparison_drivers"}
    result = []
    for lap in laps:
        context = lap.context
        if context is not None:
            if lap.stint is None:
                raise ValueError("eligible context requires a known stint")
            context = StintContext(
                context.session_id,
                context.race_id,
                context.season,
                context.circuit_id,
                context.compound,
                context.rainfall,
                context.lap_window_start,
                context.tyre_age_window_start,
                lap.stint,
            )
        result.append(
            replace(
                lap,
                context=context,
                exclusions=tuple(r for r in lap.exclusions if r not in support_reasons),
                reference_ms=None,
                residual_pct=None,
            )
        )
    return tuple(result)
