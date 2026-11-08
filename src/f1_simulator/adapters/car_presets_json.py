"""Adaptador JSON para perfis ficticios de carro por equipe.

Borda de configuracao versionada, no mesmo molde de
:mod:`f1_simulator.adapters.driver_presets_json`. Concentra I/O, validacao
estrutural e traducao para :class:`CarPreset`; a aplicacao recebe objetos
canonicos e nao conhece chaves JSON nem caminhos de arquivo.

O ritmo de cada equipe e heuristico (negativo = mais rapido, zero = carro de
referencia) e o adaptador rejeita campos desconhecidos e magnitudes absurdas
para que erros de digitacao nao virem configuracao ignorada.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from json import JSONDecodeError
from math import isfinite
from pathlib import Path
from typing import Any

from f1_simulator.application.car_presets import CarPreset

#: Magnitude maxima admissivel para ``pace_offset_pct`` de carro. ~5% ja e um
#: gap de carro muito maior do que o spread real de uma temporada (1-3%); o
#: limite existe para barrar erros de digitacao, nao para descrever F1 real.
MAX_CAR_PACE_OFFSET_PCT = 5.0


class CarPresetError(ValueError):
    """Indica configuracao de presets de carro ilegivel, ambigua ou fora do contrato."""


def load_car_presets(path: str | Path) -> dict[str, CarPreset]:
    """Leia e valide ``path``, devolvendo presets indexados por ``team_id``.

    Veja :func:`load_car_preset_file` para obter tambem o aviso de que os
    perfis sao ficticios.
    """

    return load_car_preset_file(path)[0]


def load_car_preset_file(
    path: str | Path,
) -> tuple[dict[str, CarPreset], str]:
    """Leia e valide ``path``: presets por ``team_id`` e o ``disclaimer``.

    Descarta o mapa de overrides por piloto; use
    :func:`load_car_preset_file_with_overrides` quando precisar dele.
    """

    presets, disclaimer, _ = load_car_preset_file_with_overrides(path)
    return presets, disclaimer


def load_car_preset_file_with_overrides(
    path: str | Path,
) -> tuple[dict[str, CarPreset], str, dict[str, float]]:
    """Leia ``path``: presets por equipe, ``disclaimer`` e overrides por piloto.

    O aviso acompanha os perfis porque quem os exibe precisa dizer, junto do
    nome real da equipe, que a caracterizacao e ficticia.

    Cada equipe pode trazer um campo opcional ``driver_overrides``, um mapa de
    ``driver_id`` canonico para pontos percentuais somados ao ritmo da equipe
    (negativo = o carro daquele piloto e mais rapido que o do companheiro).
    Ausente, os dois carros da equipe sao identicos. O mapa de retorno junta
    os overrides de todas as equipes, indexado por ``driver_id``.

    Raises:
        CarPresetError: se o arquivo nao puder ser lido, o JSON for invalido
            ou qualquer metadado, equipe ou valor violar o contrato.
    """

    source_path = Path(path)
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise CarPresetError(
            f"nao foi possivel ler presets de carros em {source_path}: {error}"
        ) from error
    except JSONDecodeError as error:
        raise CarPresetError(
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
            "teams",
        },
        "raiz",
    )
    if root["source_kind"] != "heuristic":
        raise CarPresetError("raiz.source_kind deve ser 'heuristic'")
    parameter_version = _nonempty_text(
        root["parameter_version"], "raiz.parameter_version"
    )
    rationale = _nonempty_text(root["rationale"], "raiz.rationale")
    if root["fictional_profiles"] is not True:
        raise CarPresetError("raiz.fictional_profiles deve ser true")
    disclaimer = _nonempty_text(root["disclaimer"], "raiz.disclaimer")

    teams = root["teams"]
    if not isinstance(teams, list) or not teams:
        raise CarPresetError("raiz.teams deve ser uma lista nao vazia")

    result: dict[str, CarPreset] = {}
    overrides: dict[str, float] = {}
    for index, raw_team in enumerate(teams):
        location = f"raiz.teams[{index}]"
        team = _mapping(raw_team, location)
        _keys_with_optional(
            team,
            required={"team_id", "team_name", "pace_offset_pct", "characterization"},
            optional={"driver_overrides"},
            location=location,
        )
        team_id = _canonical_team_id(team["team_id"], f"{location}.team_id")
        if team_id in result:
            raise CarPresetError(f"team_id duplicado em {location}: {team_id}")
        team_name = _nonempty_text(team["team_name"], f"{location}.team_name")
        pace = _pace_offset_pct(team["pace_offset_pct"], f"{location}.pace_offset_pct")
        characterization = _nonempty_text(
            team["characterization"], f"{location}.characterization"
        )
        if "driver_overrides" in team:
            _collect_driver_overrides(
                team["driver_overrides"],
                overrides,
                f"{location}.driver_overrides",
            )
        try:
            result[team_id] = CarPreset(
                team_id=team_id,
                team_name=team_name,
                pace_offset_pct=pace,
                characterization=characterization,
                source_kind="heuristic",
                parameter_version=parameter_version,
                rationale=rationale,
            )
        except ValueError as error:
            raise CarPresetError(f"preset invalido em {location}: {error}") from error
    return result, disclaimer, overrides


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CarPresetError(f"{location} deve ser um objeto JSON")
    if any(not isinstance(key, str) for key in value):
        raise CarPresetError(f"{location} deve usar somente chaves textuais")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], location: str) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise CarPresetError(f"{location} sem campos obrigatorios: {missing}")
    if unknown:
        raise CarPresetError(f"{location} tem campos desconhecidos: {unknown}")


def _keys_with_optional(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str],
    location: str,
) -> None:
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    if missing:
        raise CarPresetError(f"{location} sem campos obrigatorios: {missing}")
    if unknown:
        raise CarPresetError(f"{location} tem campos desconhecidos: {unknown}")


def _collect_driver_overrides(
    value: Any,
    into: dict[str, float],
    location: str,
) -> None:
    """Some overrides por piloto deste time ao mapa compartilhado.

    Um ``driver_id`` so pode aparecer uma vez em todo o arquivo (um piloto nao
    corre por duas equipes no mesmo grid); a repeticao e erro de configuracao.
    """

    overrides = _mapping(value, location)
    if not overrides:
        raise CarPresetError(f"{location} nao pode ser objeto vazio")
    for raw_id, raw_pace in overrides.items():
        driver_location = f"{location}.{raw_id}"
        driver_id = _canonical_driver_id(raw_id, driver_location)
        if driver_id in into:
            raise CarPresetError(
                f"{driver_location}: driver_id repetido entre equipes"
            )
        into[driver_id] = _pace_offset_pct(raw_pace, driver_location)


def _canonical_driver_id(value: Any, location: str) -> str:
    driver_id = _nonempty_text(value, location)
    prefix, separator, external_id = driver_id.partition(":")
    if prefix != "driver" or separator != ":" or not external_id.isdigit():
        raise CarPresetError(
            f"{location} deve usar o identificador canonico driver:<numero>"
        )
    return driver_id


def _nonempty_text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CarPresetError(f"{location} deve ser texto nao vazio")
    return value.strip()


def _canonical_team_id(value: Any, location: str) -> str:
    team_id = _nonempty_text(value, location)
    prefix, separator, external_id = team_id.partition(":")
    if prefix != "team" or separator != ":" or not external_id.isdigit():
        raise CarPresetError(
            f"{location} deve usar o identificador canonico team:<numero>"
        )
    return team_id


def _pace_offset_pct(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CarPresetError(f"{location} deve ser numero")
    value_as_float = float(value)
    if not isfinite(value_as_float):
        raise CarPresetError(f"{location} deve ser finito")
    if abs(value_as_float) > MAX_CAR_PACE_OFFSET_PCT:
        raise CarPresetError(
            f"{location}={value_as_float} fora do limite +/-{MAX_CAR_PACE_OFFSET_PCT}"
        )
    return value_as_float
