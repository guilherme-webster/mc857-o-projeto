"""Immutable input and deterministic time rule for the simulation core.

No profiler, persistence, transport or random source is needed to consume this
contract. The exact observed context limits this first experiment to one lap.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite

from f1_simulator.domain.driver_profile import PaceContext


@dataclass(frozen=True)
class DriverPaceParameters:
    """Observed driver/team effect, valid only for the declared frozen context.

    Reference already contains car/tyre/weather effects. MAD and bootstrap are
    deliberately absent from the time rule: neither is calibrated lap noise.
    Provenance fingerprints identify the full source run retained by the caller.
    """

    driver_id: str
    team_id: str
    context: PaceContext
    reference_lap_time_ms: float
    pace_offset_pct: float
    profile_method_version: str
    source_sessions: tuple[str, ...]
    source_manifest_hashes: tuple[str, ...]
    profile_run_sha256: str
    events: int
    contexts: int
    compared_laps: int
    context_laps: int
    warnings: tuple[str, ...]
    parameter_version: str = "observed-context-pace-v1"
    variability_mode: str = "disabled"

    def __post_init__(self) -> None:
        if not self.driver_id or not self.team_id:
            raise ValueError("driver and team are required")
        for value in (self.reference_lap_time_ms, self.pace_offset_pct):
            if isinstance(value, bool) or not isfinite(value):
                raise ValueError("time and offset must be finite numbers")
        if self.reference_lap_time_ms <= 0 or self.pace_offset_pct <= -100:
            raise ValueError("reference and modeled time must be positive")
        if self.variability_mode != "disabled":
            raise ValueError("lap variability has not been calibrated")
        if self.parameter_version != "observed-context-pace-v1":
            raise ValueError("unsupported parameter version")
        if (
            self.context.session_id not in self.source_sessions
            or len(set(self.source_sessions)) != len(self.source_sessions)
            or not self.source_manifest_hashes
            or not self.profile_run_sha256
            or not self.profile_method_version
        ):
            raise ValueError("parameters require matching source scope and provenance")
        if any(
            type(v) is not int or v < 1
            for v in (self.events, self.contexts, self.compared_laps, self.context_laps)
        ):
            raise ValueError("parameters require positive support counts")


@dataclass(frozen=True)
class LapTime:
    """Decomposed milliseconds, rounded once at the integer clock boundary."""

    reference_ms: Decimal
    pace_effect_ms: Decimal
    modeled_ms: Decimal
    clock_ms: int


def deterministic_lap_time(parameters: DriverPaceParameters) -> LapTime:
    """Apply the context effect once; preserve fractional ms until final rounding."""
    reference = Decimal(str(parameters.reference_lap_time_ms))
    effect = reference * Decimal(str(parameters.pace_offset_pct)) / Decimal(100)
    modeled = reference + effect
    clock = int(modeled.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if clock <= 0:
        raise ValueError("modeled time is below integer clock resolution")
    return LapTime(reference, effect, modeled, clock)
