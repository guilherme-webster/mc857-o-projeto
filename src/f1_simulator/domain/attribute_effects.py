from __future__ import annotations

from f1_simulator.domain.driver_attributes import DriverAttributes


def adjusted_reference_ms(base_reference_ms: float, attributes: DriverAttributes | None) -> float:
    if attributes is None:
        return base_reference_ms
    return base_reference_ms * (1.0 + attributes.pace_offset_pct / 100.0)


def adjusted_tyre_effect_ms(
    tyre_effect_ms: float | None, attributes: DriverAttributes | None
) -> float | None:
    if tyre_effect_ms is None or attributes is None:
        return tyre_effect_ms
    return tyre_effect_ms * attributes.tyre_management_factor


def consistency_scale(attributes: DriverAttributes | None) -> float:
    if attributes is None:
        return 1.0
    return attributes.consistency_factor


def attributes_assumption(attributes: DriverAttributes) -> dict:
    """Exponha valores e proveniencia sem reinterpretar ausencia como zero."""

    return {
        "kind": "driver_attributes",
        "driver_id": attributes.driver_id,
        "archetype": attributes.archetype,
        "source_kind": attributes.source_kind,
        "parameter_version": attributes.parameter_version,
        "rationale": attributes.rationale,
        "pace_offset_pct": attributes.pace_offset_pct,
        "consistency_factor": attributes.consistency_factor,
        "tyre_management_factor": attributes.tyre_management_factor,
        "aggression": attributes.aggression,
        "composure": attributes.composure,
        "sources": dict(attributes.sources),
    }
