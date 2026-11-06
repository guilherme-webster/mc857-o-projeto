"""Leia e grave o artefato versionado do carro de referencia (ADR 0014).

O artefato separa o que foi estimado (``grip_mu``, ``downforce_cla_m2``) do
que e hipotese de ordem de grandeza, e guarda o erro por circuito para que a
qualidade do ajuste fique auditavel sem rodar a calibracao de novo.

``DEFAULT_CAR_PHYSICS`` no dominio espelha este artefato; um teste garante que
os dois nao divergem. O motor usa a constante para nao exigir arquivo em cada
chamada (testes, desenho da pista, 2D), e o artefato registra de onde ela veio.
"""

from __future__ import annotations

import json
from pathlib import Path

from f1_simulator.application.calibrate_car_physics import (
    CarPhysicsFit,
    ratio_summary,
)
from f1_simulator.domain.speed_dynamics import CarPhysics

SCHEMA_VERSION = 1
ESTIMATED_FIELDS = ("grip_mu", "downforce_cla_m2")
ASSUMED_FIELDS = (
    "v_max_straight_kmh",
    "drag_cda_m2",
    "mass_kg",
    "power_kw",
    "traction_share",
)
_FIELDS = {
    "schema_version",
    "origin",
    "parameter_version",
    "method_version",
    "rationale",
    "sources",
    "estimated",
    "assumed",
    "fit",
    "circuits",
}


class CarPhysicsParametersError(ValueError):
    """Artefato com campos ausentes, extras ou valores invalidos."""


def write_car_physics(
    destination: Path,
    fit: CarPhysicsFit,
    *,
    parameter_version: str,
    rationale: str,
    sources: dict[str, str],
) -> None:
    """Grave o ajuste com proveniencia e o erro de cada circuito."""

    physics = fit.physics
    payload = {
        "schema_version": SCHEMA_VERSION,
        "origin": "estimated",
        "parameter_version": parameter_version,
        "method_version": fit.method_version,
        "rationale": rationale,
        "sources": sources,
        "estimated": {name: getattr(physics, name) for name in ESTIMATED_FIELDS},
        "assumed": {name: getattr(physics, name) for name in ASSUMED_FIELDS},
        "fit": ratio_summary(fit),
        "circuits": [
            {
                "circuit_id": row.circuit_id,
                "reference_lap_ms": round(row.reference_lap_ms, 1),
                "physical_lap_ms": round(row.physical_lap_ms, 1),
                "ratio": round(row.ratio, 4),
            }
            for row in sorted(fit.circuits, key=lambda row: row.ratio)
        ],
    }
    Path(destination).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def read_car_physics(source: Path) -> CarPhysics:
    """Leia o carro de referencia, preservando ``FileNotFoundError``."""

    try:
        payload = json.loads(Path(source).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CarPhysicsParametersError(f"JSON invalido em {source}: {error}") from error
    if not isinstance(payload, dict) or set(payload) != _FIELDS:
        raise CarPhysicsParametersError(f"campos inesperados em {source}")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise CarPhysicsParametersError("schema_version nao suportada")
    estimated = payload["estimated"]
    assumed = payload["assumed"]
    if set(estimated) != set(ESTIMATED_FIELDS) or set(assumed) != set(ASSUMED_FIELDS):
        raise CarPhysicsParametersError("blocos estimated/assumed incompletos")
    try:
        return CarPhysics(**estimated, **assumed)
    except (TypeError, ValueError) as error:
        raise CarPhysicsParametersError(str(error)) from error
