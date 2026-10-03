"""Grava e le a tabela versionada de voltas de referencia por circuito.

O artefato fica em ``data/parameters/`` ao lado do ``model-v1.json`` e e
versionado no Git, como os demais parametros do modelo: e pequeno, derivado de
forma reproduzivel por ``scripts/build_reference_laps.py`` e necessario para o
backend rodar sem o banco historico completo.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from f1_simulator.application.reference_laps import METHOD_VERSION, ReferenceLap

SCHEMA_VERSION = 1


class ReferenceLapsError(ValueError):
    """Artefato ausente de campos obrigatorios ou com valores invalidos."""


def write_reference_laps(
    laps: Sequence[ReferenceLap],
    destination: Path,
    *,
    seasons: Sequence[int],
    source: str,
) -> None:
    """Grave a tabela de forma atomica (arquivo temporario + ``os.replace``)."""

    payload = {
        "schema_version": SCHEMA_VERSION,
        "method_version": METHOD_VERSION,
        "origin": "historical-median",
        "source": source,
        "seasons": sorted(set(seasons)),
        "rationale": (
            "Por corrida, mediana das voltas mais rapidas de cada piloto; por "
            "circuito, mediana entre as corridas. Usada como volta de "
            "referencia ideal do motor detalhado; nao descreve pilotos."
        ),
        "circuits": [
            {
                "circuit_id": lap.circuit_id,
                "reference_lap_time_ms": lap.reference_lap_time_ms,
                "races": lap.races,
                "seasons": list(lap.seasons),
            }
            for lap in sorted(laps, key=lambda item: item.circuit_id)
        ],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        os.replace(temporary, destination)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def read_reference_laps(source: Path) -> dict[str, ReferenceLap]:
    """Leia e valide a tabela, devolvendo ``circuit_id -> ReferenceLap``.

    ``FileNotFoundError`` sobe intacto, para o chamador distinguir "tabela nao
    gerada" de "tabela corrompida" (``ReferenceLapsError``).
    """

    try:
        payload = json.loads(Path(source).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ReferenceLapsError(f"JSON invalido em {source}: {error}") from error
    if not isinstance(payload, dict):
        raise ReferenceLapsError("o artefato deve ser um objeto JSON")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ReferenceLapsError(
            f"schema_version {payload.get('schema_version')!r} nao suportado"
        )
    if payload.get("method_version") != METHOD_VERSION:
        raise ReferenceLapsError(
            f"method_version {payload.get('method_version')!r} nao suportado"
        )
    circuits = payload.get("circuits")
    if not isinstance(circuits, list):
        raise ReferenceLapsError("circuits deve ser uma lista")

    table: dict[str, ReferenceLap] = {}
    for row in circuits:
        try:
            lap = ReferenceLap(
                circuit_id=row["circuit_id"],
                reference_lap_time_ms=row["reference_lap_time_ms"],
                races=row["races"],
                seasons=tuple(row["seasons"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ReferenceLapsError(f"linha invalida {row!r}: {error}") from error
        if lap.circuit_id in table:
            raise ReferenceLapsError(f"circuito duplicado: {lap.circuit_id}")
        table[lap.circuit_id] = lap
    return table
