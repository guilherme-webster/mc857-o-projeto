"""Atributos ficticios e versionados que modulam o comportamento dos pilotos."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Literal

Archetype = Literal["aggressive", "balanced", "conservative"]
FieldSource = Literal["generated", "preset", "manual"]

PARAMETER_VERSION = "assumed-driver-attributes-v2"

_RATIONALE = (
    "Atributos assumidos e nao calibrados. A versao v2 acrescenta agressividade "
    "e firmeza sob pressao para modular disputas; as faixas e os valores sao "
    "heuristicos e ficticios, nunca medicoes de pessoas reais."
)

_ARCHETYPE_RATIONALE = (
    "Faixas heuristicamente escolhidas para produzir estilos ficticios distintos; "
    "1.0 e neutro nos fatores multiplicativos."
)

ATTRIBUTE_FIELDS = (
    "pace_offset_pct",
    "consistency_factor",
    "tyre_management_factor",
    "aggression",
    "composure",
)


@dataclass(frozen=True, slots=True)
class ArchetypeProfile:
    """Faixas versionadas usadas para sortear um perfil ficticio.

    ``aggression`` multiplica a pressao e o risco de contato do atacante;
    ``composure`` multiplica a resistencia do defensor. Ambos sao fatores
    adimensionais estritamente positivos e usam 1.0 como valor neutro.
    """

    name: Archetype
    pace_offset_pct: tuple[float, float]
    consistency_factor: tuple[float, float]
    tyre_management_factor: tuple[float, float]
    aggression: tuple[float, float]
    composure: tuple[float, float]
    source_kind: Literal["heuristic"] = "heuristic"
    parameter_version: str = PARAMETER_VERSION
    rationale: str = _ARCHETYPE_RATIONALE

    def __post_init__(self) -> None:
        for field in ATTRIBUTE_FIELDS:
            low, high = getattr(self, field)
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                for value in (low, high)
            ):
                raise ValueError(f"{field} range must be finite numbers")
            if low > high:
                raise ValueError(f"{field} range low must not exceed high")
        for field in (
            "consistency_factor",
            "tyre_management_factor",
            "aggression",
            "composure",
        ):
            low, _ = getattr(self, field)
            if low <= 0:
                raise ValueError(f"{field} must stay positive")
        if self.source_kind != "heuristic":
            raise ValueError("source_kind deve ser 'heuristic'")
        if (
            not isinstance(self.parameter_version, str)
            or not self.parameter_version.strip()
        ):
            raise ValueError("parameter_version deve ser texto nao vazio")
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ValueError("rationale deve ser texto nao vazio")


@dataclass(frozen=True, slots=True)
class DriverAttributes:
    """Atributos assumidos de um piloto, com origem auditavel por campo.

    Os valores nao descrevem pessoas reais. ``sources`` distingue sorteio,
    preset ficticio nomeado e edicao manual, nesta ordem de precedencia.
    """

    driver_id: str
    archetype: Archetype
    pace_offset_pct: float
    consistency_factor: float
    tyre_management_factor: float
    aggression: float
    composure: float
    sources: Mapping[str, FieldSource]
    source_kind: Literal["assumed"] = "assumed"
    parameter_version: str = PARAMETER_VERSION
    rationale: str = _RATIONALE

    def __post_init__(self) -> None:
        if not self.driver_id:
            raise ValueError("driver_id is required")
        for field in ATTRIBUTE_FIELDS:
            value = getattr(self, field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"{field} must be a finite number")
        if any(
            getattr(self, field) <= 0
            for field in (
                "consistency_factor",
                "tyre_management_factor",
                "aggression",
                "composure",
            )
        ):
            raise ValueError("factors must be strictly positive")
        if set(self.sources) != set(ATTRIBUTE_FIELDS):
            raise ValueError("sources must cover every attribute field")
        if any(
            origin not in ("generated", "preset", "manual")
            for origin in self.sources.values()
        ):
            raise ValueError("source deve ser 'generated', 'preset' ou 'manual'")
        if self.source_kind != "assumed":
            raise ValueError("source_kind deve ser 'assumed'")
        if (
            not isinstance(self.parameter_version, str)
            or not self.parameter_version.strip()
        ):
            raise ValueError("parameter_version deve ser texto nao vazio")
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ValueError("rationale deve ser texto nao vazio")


ASSUMED_ARCHETYPES: tuple[ArchetypeProfile, ...] = (
    ArchetypeProfile(
        name="aggressive",
        pace_offset_pct=(-0.60, -0.20),
        consistency_factor=(1.10, 1.40),
        tyre_management_factor=(1.15, 1.45),
        aggression=(1.20, 1.50),
        composure=(0.85, 1.05),
    ),
    ArchetypeProfile(
        name="balanced",
        pace_offset_pct=(-0.15, 0.15),
        consistency_factor=(0.90, 1.10),
        tyre_management_factor=(0.90, 1.10),
        aggression=(0.90, 1.10),
        composure=(0.90, 1.10),
    ),
    ArchetypeProfile(
        name="conservative",
        pace_offset_pct=(0.10, 0.40),
        consistency_factor=(0.70, 0.95),
        tyre_management_factor=(0.65, 0.90),
        aggression=(0.60, 0.85),
        composure=(1.05, 1.30),
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
