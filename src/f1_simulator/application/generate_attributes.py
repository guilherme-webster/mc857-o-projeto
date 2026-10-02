from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from f1_simulator.domain.driver_attributes import (
    ASSUMED_ARCHETYPES,
    ATTRIBUTE_FIELDS,
    Archetype,
    ArchetypeProfile,
    DriverAttributes,
    archetype_profile,
)
from f1_simulator.domain.random_source import (
    RandomSource,
    uniform_float,
    uniform_index,
)


def generate_attributes(
    driver_ids: Sequence[str],
    rng: RandomSource,
    *,
    forced_archetypes: Mapping[str, Archetype] | None = None,
    catalogue: tuple[ArchetypeProfile, ...] = ASSUMED_ARCHETYPES,
) -> tuple[DriverAttributes, ...]:
    unique = list(dict.fromkeys(driver_ids))
    if len(unique) != len(driver_ids):
        raise ValueError("driver_ids must be unique")
    forced = dict(forced_archetypes or {})
    unknown = [driver_id for driver_id in forced if driver_id not in unique]
    if unknown:
        raise ValueError(f"forced archetype for unknown driver: {unknown}")

    names = tuple(profile.name for profile in catalogue)
    archetype_source = rng.spawn("attributes:archetype")

    result = []
    for driver_id in sorted(unique):
        if driver_id in forced:
            name = forced[driver_id]
        else:
            name = names[uniform_index(archetype_source, f"archetype:{driver_id}", len(names))]
        profile = archetype_profile(name, catalogue)
        field_source = rng.spawn(f"attributes:{driver_id}")
        values = {
            field: uniform_float(field_source, field, *getattr(profile, field))
            for field in ATTRIBUTE_FIELDS
        }
        result.append(
            DriverAttributes(
                driver_id=driver_id,
                archetype=name,
                pace_offset_pct=values["pace_offset_pct"],
                consistency_factor=values["consistency_factor"],
                tyre_management_factor=values["tyre_management_factor"],
                sources={field: "generated" for field in ATTRIBUTE_FIELDS},
            )
        )
    return tuple(result)


def apply_overrides(
    attributes: Sequence[DriverAttributes],
    overrides: Mapping[str, Mapping[str, float]],
) -> tuple[DriverAttributes, ...]:
    by_id = {item.driver_id: item for item in attributes}
    if len(by_id) != len(attributes):
        raise ValueError("attributes contain duplicate driver_id")
    unknown = [driver_id for driver_id in overrides if driver_id not in by_id]
    if unknown:
        raise ValueError(f"override for unknown driver: {unknown}")

    updated = dict(by_id)
    for driver_id, patch in overrides.items():
        unknown_fields = [field for field in patch if field not in ATTRIBUTE_FIELDS]
        if unknown_fields:
            raise ValueError(f"unknown attribute fields: {unknown_fields}")
        current = updated[driver_id]
        sources = dict(current.sources)
        changes = {}
        for field, value in patch.items():
            changes[field] = value
            sources[field] = "manual"
        updated[driver_id] = replace(current, sources=sources, **changes)

    return tuple(updated[item.driver_id] for item in attributes)
