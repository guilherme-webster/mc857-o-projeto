"""Casos de uso para gerar, predefinir e editar atributos ficticios."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from math import isfinite
from types import MappingProxyType
from typing import Literal

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


@dataclass(frozen=True, slots=True)
class DriverPreset:
    """Preset ficticio validado, independente do formato JSON de origem.

    ``values`` pode fixar qualquer subconjunto dos atributos. Os demais campos
    ainda sao sorteados dentro do arquétipo do preset, preservando a variedade
    e a reproducibilidade. A metainformacao explicita que esses numeros sao
    heuristicas narrativas, nao observacoes sobre a pessoa nomeada.
    """

    driver_id: str
    driver_name: str
    archetype: Archetype
    values: Mapping[str, float]
    characterization: str
    source_kind: Literal["heuristic"]
    parameter_version: str
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.driver_id, str) or not self.driver_id.strip():
            raise ValueError("driver_id deve ser texto nao vazio")
        if not isinstance(self.driver_name, str) or not self.driver_name.strip():
            raise ValueError("driver_name deve ser texto nao vazio")
        if (
            not isinstance(self.characterization, str)
            or not self.characterization.strip()
        ):
            raise ValueError("characterization deve ser texto nao vazio")
        if self.source_kind != "heuristic":
            raise ValueError("source_kind deve ser 'heuristic'")
        if (
            not isinstance(self.parameter_version, str)
            or not self.parameter_version.strip()
        ):
            raise ValueError("parameter_version deve ser texto nao vazio")
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ValueError("rationale deve ser texto nao vazio")
        if not self.values:
            raise ValueError("values do preset nao pode ser vazio")

        unknown_fields = [field for field in self.values if field not in ATTRIBUTE_FIELDS]
        if unknown_fields:
            raise ValueError(f"atributos desconhecidos no preset: {unknown_fields}")
        for field, value in self.values.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"valor de {field} no preset deve ser finito")
            if field != "pace_offset_pct" and value <= 0:
                raise ValueError(f"valor de {field} no preset deve ser positivo")

        # Uma dataclass frozen nao basta se mantiver a referencia ao dict do
        # adaptador. A copia somente leitura impede mutacao posterior do preset.
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


def generate_attributes(
    driver_ids: Sequence[str],
    rng: RandomSource,
    *,
    forced_archetypes: Mapping[str, Archetype] | None = None,
    catalogue: tuple[ArchetypeProfile, ...] = ASSUMED_ARCHETYPES,
) -> tuple[DriverAttributes, ...]:
    """Sorteie atributos por piloto usando fluxos e rotulos estaveis.

    Cada piloto recebe um filho de ``rng`` e cada campo usa seu proprio nome
    como rotulo. Campos novos sao acrescentados ao fim de ``ATTRIBUTE_FIELDS``
    para que os valores historicos dos campos v1 nao mudem para a mesma semente.
    """

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
                aggression=values["aggression"],
                composure=values["composure"],
                sources={field: "generated" for field in ATTRIBUTE_FIELDS},
            )
        )
    return tuple(result)


def apply_presets(
    attributes: Sequence[DriverAttributes],
    presets: Mapping[str, DriverPreset],
    rng: RandomSource,
    *,
    catalogue: tuple[ArchetypeProfile, ...] = ASSUMED_ARCHETYPES,
) -> tuple[DriverAttributes, ...]:
    """Aplique presets aos pilotos presentes sem afetar os demais.

    O arquétipo do preset substitui o sorteado originalmente. Por esse motivo,
    todos os campos do piloto sao re-sorteados no mesmo fluxo deterministico,
    agora dentro das faixas corretas, antes de os valores fixados receberem
    origem ``preset``. Presets de pilotos fora do grid sao ignorados de forma
    intencional; o arquivo representa o catalogo de 2024, enquanto cada grid
    normalmente contem apenas um subconjunto dele.
    """

    by_id = {item.driver_id: item for item in attributes}
    if len(by_id) != len(attributes):
        raise ValueError("attributes contem driver_id duplicado")
    for driver_id, preset in presets.items():
        if driver_id != preset.driver_id:
            raise ValueError(
                f"chave {driver_id!r} nao corresponde ao preset {preset.driver_id!r}"
            )

    updated = dict(by_id)
    for item in attributes:
        preset = presets.get(item.driver_id)
        if preset is None:
            continue
        profile = archetype_profile(preset.archetype, catalogue)
        field_source = rng.spawn(f"attributes:{item.driver_id}")
        values = {
            field: uniform_float(field_source, field, *getattr(profile, field))
            for field in ATTRIBUTE_FIELDS
        }
        sources = {field: "generated" for field in ATTRIBUTE_FIELDS}
        for field, value in preset.values.items():
            values[field] = value
            sources[field] = "preset"
        updated[item.driver_id] = replace(
            item,
            archetype=preset.archetype,
            sources=sources,
            **values,
        )

    return tuple(updated[item.driver_id] for item in attributes)


def apply_overrides(
    attributes: Sequence[DriverAttributes],
    overrides: Mapping[str, Mapping[str, float]],
) -> tuple[DriverAttributes, ...]:
    """Aplique edicoes manuais como ultima camada de precedencia.

    Campos omitidos preservam valor e origem; campos informados passam a ter
    origem ``manual``, inclusive quando antes vieram de um preset.
    """

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
