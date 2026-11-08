"""Adaptador JSON para perfis ficticios de execucao de equipe.

Borda de configuracao versionada, no mesmo molde de
:mod:`f1_simulator.adapters.car_presets_json`. Concentra I/O, validacao
estrutural e traducao para :class:`TeamPreset`; a aplicacao recebe objetos
canonicos e nao conhece chaves JSON nem caminhos de arquivo.

``pit_execution_factor`` multiplica o tempo de pit stop da equipe (1.0 neutro).
O adaptador limita a magnitude para barrar erros de digitacao: um box duas
vezes mais lento ja e absurdo para F1.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from json import JSONDecodeError
from math import isfinite
from pathlib import Path
from typing import Any

from f1_simulator.application.team_presets import TeamPreset

#: Faixa admissivel do fator de execucao de pit. Um box bom perde ~2 s, um
#: ruim ~3,5 s; +/-50% cobre com folga a diferenca plausivel entre equipes e
#: ainda barra valores digitados por engano.
MIN_PIT_EXECUTION_FACTOR = 0.5
MAX_PIT_EXECUTION_FACTOR = 1.5


class TeamPresetError(ValueError):
    """Indica configuracao de presets de equipe ilegivel, ambigua ou fora do contrato."""


def load_team_presets(path: str | Path) -> dict[str, TeamPreset]:
    """Leia e valide ``path``, devolvendo presets indexados por ``team_id``.

    Veja :func:`load_team_preset_file` para obter tambem o aviso de que os
    perfis sao ficticios.
    """

    return load_team_preset_file(path)[0]


def load_team_preset_file(
    path: str | Path,
) -> tuple[dict[str, TeamPreset], str]:
    """Leia e valide ``path``: presets por ``team_id`` e o ``disclaimer``.

    Raises:
        TeamPresetError: se o arquivo nao puder ser lido, o JSON for invalido
            ou qualquer metadado, equipe ou valor violar o contrato.
    """

    source_path = Path(path)
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise TeamPresetError(
            f"nao foi possivel ler presets de equipes em {source_path}: {error}"
        ) from error
    except JSONDecodeError as error:
        raise TeamPresetError(
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
        raise TeamPresetError("raiz.source_kind deve ser 'heuristic'")
    parameter_version = _nonempty_text(
        root["parameter_version"], "raiz.parameter_version"
    )
    rationale = _nonempty_text(root["rationale"], "raiz.rationale")
    if root["fictional_profiles"] is not True:
        raise TeamPresetError("raiz.fictional_profiles deve ser true")
    disclaimer = _nonempty_text(root["disclaimer"], "raiz.disclaimer")

    teams = root["teams"]
    if not isinstance(teams, list) or not teams:
        raise TeamPresetError("raiz.teams deve ser uma lista nao vazia")

    result: dict[str, TeamPreset] = {}
    for index, raw_team in enumerate(teams):
        location = f"raiz.teams[{index}]"
        team = _mapping(raw_team, location)
        _exact_keys(
            team,
            {"team_id", "team_name", "pit_execution_factor", "characterization"},
            location,
        )
        team_id = _canonical_team_id(team["team_id"], f"{location}.team_id")
        if team_id in result:
            raise TeamPresetError(f"team_id duplicado em {location}: {team_id}")
        team_name = _nonempty_text(team["team_name"], f"{location}.team_name")
        factor = _pit_execution_factor(
            team["pit_execution_factor"], f"{location}.pit_execution_factor"
        )
        characterization = _nonempty_text(
            team["characterization"], f"{location}.characterization"
        )
        try:
            result[team_id] = TeamPreset(
                team_id=team_id,
                team_name=team_name,
                pit_execution_factor=factor,
                characterization=characterization,
                source_kind="heuristic",
                parameter_version=parameter_version,
                rationale=rationale,
            )
        except ValueError as error:
            raise TeamPresetError(f"preset invalido em {location}: {error}") from error
    return result, disclaimer


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise TeamPresetError(f"{location} deve ser um objeto JSON")
    if any(not isinstance(key, str) for key in value):
        raise TeamPresetError(f"{location} deve usar somente chaves textuais")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], location: str) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise TeamPresetError(f"{location} sem campos obrigatorios: {missing}")
    if unknown:
        raise TeamPresetError(f"{location} tem campos desconhecidos: {unknown}")


def _nonempty_text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TeamPresetError(f"{location} deve ser texto nao vazio")
    return value.strip()


def _canonical_team_id(value: Any, location: str) -> str:
    team_id = _nonempty_text(value, location)
    prefix, separator, external_id = team_id.partition(":")
    if prefix != "team" or separator != ":" or not external_id.isdigit():
        raise TeamPresetError(
            f"{location} deve usar o identificador canonico team:<numero>"
        )
    return team_id


def _pit_execution_factor(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TeamPresetError(f"{location} deve ser numero")
    value_as_float = float(value)
    if not isfinite(value_as_float):
        raise TeamPresetError(f"{location} deve ser finito")
    if not MIN_PIT_EXECUTION_FACTOR <= value_as_float <= MAX_PIT_EXECUTION_FACTOR:
        raise TeamPresetError(
            f"{location}={value_as_float} fora da faixa "
            f"[{MIN_PIT_EXECUTION_FACTOR}, {MAX_PIT_EXECUTION_FACTOR}]"
        )
    return value_as_float
