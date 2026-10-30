"""Leia o artefato versionado da heuristica de largada.

O adaptador e a fronteira entre JSON e o objeto validado do dominio. Ele exige
campos exatos para que erro de digitacao nao seja ignorado enquanto uma corrida
aparentemente plausivel usa outro valor.
"""

from __future__ import annotations

import json
from pathlib import Path

from f1_simulator.domain.grid_start import GridStartParameters

SCHEMA_VERSION = 1
_FIELDS = {
    "schema_version",
    "origin",
    "parameter_version",
    "rationale",
    "grid_start_penalty_factor",
}


class GridStartParametersError(ValueError):
    """Artefato ausente de campos, com campos extras ou valores invalidos."""


def read_grid_start_parameters(source: Path) -> GridStartParameters:
    """Leia e valide a heuristica, preservando ``FileNotFoundError``.

    A ausencia sobe intacta para a composition root decidir se a implantacao
    esta incompleta. JSON invalido e invariantes do dominio viram um erro unico
    e nomeado para a borda HTTP ou para scripts offline.
    """

    try:
        payload = json.loads(Path(source).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise GridStartParametersError(f"JSON invalido em {source}: {error}") from error
    if not isinstance(payload, dict):
        raise GridStartParametersError("o artefato deve ser um objeto JSON")
    fields = set(payload)
    if fields != _FIELDS:
        missing = sorted(_FIELDS - fields)
        extra = sorted(fields - _FIELDS)
        raise GridStartParametersError(
            f"campos invalidos: ausentes={missing}, extras={extra}"
        )
    if payload["schema_version"] != SCHEMA_VERSION:
        raise GridStartParametersError(
            f"schema_version {payload['schema_version']!r} nao suportado"
        )
    try:
        return GridStartParameters(
            penalty_factor=payload["grid_start_penalty_factor"],
            origin=payload["origin"],
            parameter_version=payload["parameter_version"],
            rationale=payload["rationale"],
        )
    except (TypeError, ValueError) as error:
        raise GridStartParametersError(str(error)) from error
