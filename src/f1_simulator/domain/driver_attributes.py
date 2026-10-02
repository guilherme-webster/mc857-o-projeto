from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Literal

Archetype = Literal["aggressive", "balanced", "conservative"]
FieldSource = Literal["generated", "manual"]

PARAMETER_VERSION = "assumed-driver-attributes-v1"

_RATIONALE = (
    "Assumed, non-calibrated driver attributes. No dataset supports real driver "
    "skill, so values are drawn from fictional archetype ranges and must never "
    "be read as measurements."
)

ATTRIBUTE_FIELDS = ("pace_offset_pct", "consistency_factor", "tyre_management_factor")


@dataclass(frozen=True, slots=True)
class ArchetypeProfile:
    name: Archetype
    pace_offset_pct: tuple[float, float]
    consistency_factor: tuple[float, float]
    tyre_management_factor: tuple[float, float]

    def __post_init__(self) -> None:
        for field in ATTRIBUTE_FIELDS:
            low, high = getattr(self, field)
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in (low, high)):
                raise ValueError(f"{field} range must be finite numbers")
            if low > high:
                raise ValueError(f"{field} range low must not exceed high")
        for field in ("consistency_factor", "tyre_management_factor"):
            low, _ = getattr(self, field)
            if low <= 0:
                raise ValueError(f"{field} must stay positive")


@dataclass(frozen=True, slots=True)
class DriverAttributes:
    driver_id: str
    archetype: Archetype
    pace_offset_pct: float
    consistency_factor: float
    tyre_management_factor: float
    sources: Mapping[str, FieldSource]
    source_kind: Literal["assumed"] = "assumed"
    parameter_version: str = PARAMETER_VERSION
    rationale: str = _RATIONALE

    def __post_init__(self) -> None:
        if not self.driver_id:
            raise ValueError("driver_id is required")
        for field in ATTRIBUTE_FIELDS:
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                raise ValueError(f"{field} must be a finite number")
        if self.consistency_factor <= 0 or self.tyre_management_factor <= 0:
            raise ValueError("factors must be strictly positive")
        if set(self.sources) != set(ATTRIBUTE_FIELDS):
            raise ValueError("sources must cover every attribute field")
        if any(origin not in ("generated", "manual") for origin in self.sources.values()):
            raise ValueError("source must be 'generated' or 'manual'")


ASSUMED_ARCHETYPES: tuple[ArchetypeProfile, ...] = (
    ArchetypeProfile(
        name="aggressive",
        pace_offset_pct=(-0.60, -0.20),
        consistency_factor=(1.10, 1.40),
        tyre_management_factor=(1.15, 1.45),
    ),
    ArchetypeProfile(
        name="balanced",
        pace_offset_pct=(-0.15, 0.15),
        consistency_factor=(0.90, 1.10),
        tyre_management_factor=(0.90, 1.10),
    ),
    ArchetypeProfile(
        name="conservative",
        pace_offset_pct=(0.10, 0.40),
        consistency_factor=(0.70, 0.95),
        tyre_management_factor=(0.65, 0.90),
    ),
)


def archetype_profile(
    name: Archetype,
    catalogue: tuple[ArchetypeProfile, ...] = ASSUMED_ARCHETYPES,
) -> ArchetypeProfile:
    for profile in catalogue:
        if profile.name == name:
            return profile
    raise ValueError(f"unknown archetype: {name}")
