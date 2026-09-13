"""Descriptive stability between disjoint event samples, not prediction error."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from f1_simulator.domain.driver_profile import (
    METHOD_VERSION,
    DriverProfile,
    ProfileConfig,
)

EVALUATION_VERSION = "profile-stability-v1"


@dataclass(frozen=True)
class EvaluationPlan:
    """Freeze the selection and thresholds before inspecting validation metrics.

    Both partitions use the same config. Session disjointness is checked here;
    the application additionally resolves event identities to prevent aliases
    or multiple sessions of a race crossing the partition boundary.
    """

    evaluation_id: str
    development_sessions: tuple[str, ...]
    validation_sessions: tuple[str, ...]
    config: ProfileConfig
    evaluation_version: str = EVALUATION_VERSION
    profile_method_version: str = METHOD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.evaluation_id, str) or not self.evaluation_id.strip():
            raise ValueError("evaluation_id must be nonempty")
        if not isinstance(self.config, ProfileConfig):
            raise ValueError("config must be a ProfileConfig")
        if (
            self.evaluation_version != EVALUATION_VERSION
            or self.profile_method_version != METHOD_VERSION
        ):
            raise ValueError(
                "evaluation/profile version does not match implemented methods"
            )
        for field in ("development_sessions", "validation_sessions"):
            sessions = getattr(self, field)
            if not isinstance(sessions, tuple) or not sessions:
                raise ValueError(f"{field} must be a nonempty tuple")
            if any(not isinstance(s, str) or not s.strip() for s in sessions):
                raise ValueError(f"{field} contains an invalid session ID")
            if len(set(sessions)) != len(sessions):
                raise ValueError(f"{field} contains repeated sessions")
            object.__setattr__(self, field, tuple(sorted(sessions)))
        if set(self.development_sessions) & set(self.validation_sessions):
            raise ValueError("development and validation sessions must be disjoint")


@dataclass(frozen=True)
class DriverStability:
    """Validation minus development, in percentage points (pp).

    These are shifts of independently estimated descriptive profiles. Contexts
    and comparison fields can differ, so shifts do not isolate intrinsic skill.
    Missing/insufficient support is retained rather than assigned a zero shift.
    """

    driver_id: str
    development_pace_pct: float | None
    validation_pace_pct: float | None
    pace_shift_pp: float | None
    development_consistency_pct: float | None
    validation_consistency_pct: float | None
    consistency_shift_pp: float | None
    development_events: int
    validation_events: int
    development_teams: tuple[str, ...]
    validation_teams: tuple[str, ...]
    development_compounds: tuple[str, ...]
    validation_compounds: tuple[str, ...]
    unavailable_reasons: tuple[str, ...]


@dataclass(frozen=True)
class StabilitySummary:
    """Equal weight per supported driver; no accuracy or confidence claim."""

    total_drivers: int
    paired_drivers: int
    median_absolute_pace_shift_pp: float | None
    median_absolute_consistency_shift_pp: float | None


def compare_profiles(
    development: tuple[DriverProfile, ...],
    validation: tuple[DriverProfile, ...],
) -> tuple[tuple[DriverStability, ...], StabilitySummary]:
    """Compare only available pairs, retaining the union of both driver catalogs."""
    left = {p.driver_id: p for p in development}
    right = {p.driver_id: p for p in validation}
    if len(left) != len(development) or len(right) != len(validation):
        raise ValueError("duplicate driver profiles in a partition")
    rows = []
    for driver in sorted(left.keys() | right.keys()):
        a, b = left.get(driver), right.get(driver)
        reasons = []
        for role, profile in (("development", a), ("validation", b)):
            reason = "driver_absent" if profile is None else profile.unavailable_reason
            if reason is None and (
                profile.pace_delta_pct is None or profile.consistency_mad_pct is None
            ):
                reason = "metrics_unavailable"
            if reason:
                reasons.append(f"{role}:{reason}")
        rows.append(
            DriverStability(
                driver,
                a.pace_delta_pct if a else None,
                b.pace_delta_pct if b else None,
                b.pace_delta_pct - a.pace_delta_pct if not reasons else None,
                a.consistency_mad_pct if a else None,
                b.consistency_mad_pct if b else None,
                b.consistency_mad_pct - a.consistency_mad_pct if not reasons else None,
                a.events if a else 0,
                b.events if b else 0,
                tuple(sorted({c.team_id for c in a.contexts})) if a else (),
                tuple(sorted({c.team_id for c in b.contexts})) if b else (),
                tuple(sorted({c.context.compound for c in a.contexts})) if a else (),
                tuple(sorted({c.context.compound for c in b.contexts})) if b else (),
                tuple(reasons),
            )
        )
    paired = [r for r in rows if not r.unavailable_reasons]
    return tuple(rows), StabilitySummary(
        len(rows),
        len(paired),
        median(abs(r.pace_shift_pp) for r in paired) if paired else None,
        median(abs(r.consistency_shift_pp) for r in paired) if paired else None,
    )
