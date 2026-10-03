"""Adaptador JSON para perfis ficticios nomeados de pilotos.

O arquivo e uma borda de configuracao versionada. Este modulo concentra I/O,
validacao estrutural e traducao para :class:`DriverPreset`; a aplicacao recebe
objetos canonicos e nao conhece chaves JSON nem caminhos de arquivo.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from f1_simulator.application.generate_attributes import DriverPreset
from f1_simulator.domain.driver_attributes import (
    ATTRIBUTE_FIELDS,
    Archetype,
    archetype_profile,
)


class DriverPresetError(ValueError):
    """Indica configuracao de presets ilegivel, ambigua ou fora do contrato."""


def load_driver_presets(path: str | Path) -> dict[str, DriverPreset]:
    """Leia e valide ``path``, devolvendo presets indexados por ``driver_id``.

    O adaptador rejeita campos desconhecidos para que erros de digitacao nao
    virem configuracao ignorada. Valores fixados devem pertencer a faixa do
    arquétipo declarado; edicoes fora dessas faixas continuam possiveis pelo
    override manual, cuja origem e explicitamente diferente.

    Raises:
        DriverPresetError: se o arquivo nao puder ser lido, o JSON for invalido
            ou qualquer metadado, piloto ou atributo violar o contrato.
    """

    source_path = Path(path)
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise DriverPresetError(
            f"nao foi possivel ler presets de pilotos em {source_path}: {error}"
        ) from error
    except JSONDecodeError as error:
        raise DriverPresetError(
            f"JSON invalido em {source_path}, linha {error.lineno}, "
            f"coluna {error.colno}: {error.msg}"
        ) from error

    root = _mapping(payload, "raiz")
    _exact_keys(
        root,
        {
            "source_kind",
            "parameter_version",
            "rationale",
            "fictional_profiles",
            "disclaimer",
            "drivers",
        },
        "raiz",
    )
    if root["source_kind"] != "heuristic":
        raise DriverPresetError("raiz.source_kind deve ser 'heuristic'")
    parameter_version = _nonempty_text(
        root["parameter_version"], "raiz.parameter_version"
    )
    rationale = _nonempty_text(root["rationale"], "raiz.rationale")
    if root["fictional_profiles"] is not True:
        raise DriverPresetError("raiz.fictional_profiles deve ser true")
    _nonempty_text(root["disclaimer"], "raiz.disclaimer")

    drivers = root["drivers"]
    if not isinstance(drivers, list) or not drivers:
        raise DriverPresetError("raiz.drivers deve ser uma lista nao vazia")

    result: dict[str, DriverPreset] = {}
    for index, raw_driver in enumerate(drivers):
        location = f"raiz.drivers[{index}]"
        driver = _mapping(raw_driver, location)
        _exact_keys(
            driver,
            {
                "driver_id",
                "driver_name",
                "archetype",
                "characterization",
                "attributes",
            },
            location,
        )
        driver_id = _canonical_driver_id(driver["driver_id"], f"{location}.driver_id")
        if driver_id in result:
            raise DriverPresetError(f"driver_id duplicado em {location}: {driver_id}")
        driver_name = _nonempty_text(
            driver["driver_name"], f"{location}.driver_name"
        )
        archetype = _archetype(driver["archetype"], f"{location}.archetype")
        characterization = _nonempty_text(
            driver["characterization"], f"{location}.characterization"
        )
        values = _attribute_values(
            driver["attributes"], archetype, f"{location}.attributes"
        )
        try:
            result[driver_id] = DriverPreset(
                driver_id=driver_id,
                driver_name=driver_name,
                archetype=archetype,
                values=values,
                characterization=characterization,
                source_kind="heuristic",
                parameter_version=parameter_version,
                rationale=rationale,
            )
        except ValueError as error:
            raise DriverPresetError(f"preset invalido em {location}: {error}") from error
    return result


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise DriverPresetError(f"{location} deve ser um objeto JSON")
    if any(not isinstance(key, str) for key in value):
        raise DriverPresetError(f"{location} deve usar somente chaves textuais")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], location: str) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise DriverPresetError(f"{location} sem campos obrigatorios: {missing}")
    if unknown:
        raise DriverPresetError(f"{location} tem campos desconhecidos: {unknown}")


def _nonempty_text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DriverPresetError(f"{location} deve ser texto nao vazio")
    return value.strip()


def _canonical_driver_id(value: Any, location: str) -> str:
    driver_id = _nonempty_text(value, location)
    prefix, separator, external_id = driver_id.partition(":")
    if prefix != "driver" or separator != ":" or not external_id.isdigit():
        raise DriverPresetError(
            f"{location} deve usar o identificador canonico driver:<numero>"
        )
    return driver_id


def _archetype(value: Any, location: str) -> Archetype:
    if value not in ("aggressive", "balanced", "conservative"):
        raise DriverPresetError(
            f"{location} deve ser 'aggressive', 'balanced' ou 'conservative'"
        )
    return value


def _attribute_values(
    value: Any,
    archetype: Archetype,
    location: str,
) -> dict[str, float]:
    attributes = _mapping(value, location)
    if not attributes:
        raise DriverPresetError(f"{location} deve fixar pelo menos um atributo")
    unknown = sorted(set(attributes) - set(ATTRIBUTE_FIELDS))
    if unknown:
        raise DriverPresetError(f"{location} tem atributos desconhecidos: {unknown}")

    profile = archetype_profile(archetype)
    result: dict[str, float] = {}
    for field, raw_value in attributes.items():
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise DriverPresetError(f"{location}.{field} deve ser numero")
        value_as_float = float(raw_value)
        low, high = getattr(profile, field)
        if not low <= value_as_float <= high:
            raise DriverPresetError(
                f"{location}.{field}={value_as_float} fora da faixa "
                f"[{low}, {high}] do arquétipo {archetype}"
            )
        result[field] = value_as_float
    return result
