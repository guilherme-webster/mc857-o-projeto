"""Grava e le o artefato versionado do modelo de combustivel.

O arquivo fica em ``data/parameters/fuel-v1.json``, ao lado de ``model-v1.json``
e ``reference-laps-v1.json``. E gerado por ``scripts/calibrate_fuel.py`` e
carrega, junto dos parametros, a evidencia que os sustenta: diagnostico da
regressao e a validacao por corrida em temporadas fora da calibracao.

Os parametros sao agrupados por origem (calibrado, regulamento, hipotese,
regra do cenario) para que ninguem leia uma hipotese como medida -- exigencia
do ADR 0008. O bloco ``refuel_stops`` traz o tempo de parada por equipe medido
nas paradas reais e sua validacao fora da amostra.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, fields
from pathlib import Path

from f1_simulator.application.calibrate_fuel import (
    METHOD_VERSION,
    FuelCalibrationDiagnostics,
    FuelValidationReport,
    RefuelStopValidation,
)
from f1_simulator.domain.fuel import (
    FuelModelParameters,
    RefuelStopParameters,
    TeamPitOffset,
)
from f1_simulator.domain.model_parameters import CalibrationProvenance

SCHEMA_VERSION = 1

_ASSUMED_FIELDS = (
    "burn_kg_per_km",
    "finish_reserve_kg",
    "vsc_burn_factor",
    "sc_burn_factor",
    "red_flag_burn_factor",
    "lift_coast_max_saving_fraction",
    "lift_coast_ms_per_kg_saved",
    "refuel_rate_kg_per_s",
    "tyre_change_ms",
)

#: Hipoteses acrescentadas depois da primeira versao do artefato. Um arquivo
#: gerado antes delas continua valido e recebe o valor padrao do dominio, em
#: vez de exigir uma recalibracao so para declarar uma hipotese nova.
_ASSUMED_DEFAULTS = {
    item.name: item.default
    for item in fields(FuelModelParameters)
    if item.name in ("refuel_rate_kg_per_s", "tyre_change_ms")
}


class FuelParametersError(ValueError):
    """Artefato sem campos obrigatorios ou com valores invalidos."""


def write_fuel_parameters(
    parameters: FuelModelParameters,
    destination: Path,
    *,
    diagnostics: FuelCalibrationDiagnostics | None = None,
    validation: FuelValidationReport | None = None,
    refuel_validation: RefuelStopValidation | None = None,
) -> None:
    """Grave de forma atomica (arquivo temporario + ``os.replace``)."""

    provenance = asdict(parameters.provenance)
    provenance["seasons"] = list(parameters.provenance.seasons)
    payload: dict = {
        "schema_version": SCHEMA_VERSION,
        "method_version": METHOD_VERSION,
        "version": parameters.version,
        "provenance": provenance,
        "calibrated": {
            "origin": parameters.origin,
            "lap_time_fraction_per_fuel_km": parameters.lap_time_fraction_per_fuel_km,
            "rationale": (
                "Fracao do tempo de volta perdida por carregar o combustivel de "
                "1 km; regressao de dois relogios com regressor volta*T*L."
            ),
        },
        "regulation": {
            "origin": "regulation",
            "max_fuel_kg": parameters.max_fuel_kg,
            "rationale": (
                "Regulamento tecnico 2022-2025: no maximo 110 kg por corrida. "
                "O regulamento proibe reabastecer desde 2010; ver 'scenario'."
            ),
        },
        "scenario": {
            "origin": "assumed",
            "refuelling_allowed": parameters.refuelling_allowed,
            "rationale": (
                "Decisao do grupo (logica 1994-2009): toda parada troca pneus "
                "e reabastece; cada piloto decide quando parar e quanto "
                "colocar pesando desgaste, peso e custo da parada, e so e "
                "obrigado a parar se nao chegaria a proxima entrada dos boxes. "
                "Desligado, vale a regra 2010+ (economia e pane)."
            ),
        },
        "assumed": {
            "origin": "assumed",
            **{name: getattr(parameters, name) for name in _ASSUMED_FIELDS},
            "rationale": (
                "Nao observavel no Trotman. Consumo de 105 kg em 305 km; reserva "
                "para a amostra de 1 L da FIA; queima reduzida sob SC/VSC; "
                "lift-and-coast limitado e caro."
            ),
        },
    }
    if parameters.refuel_stops is not None:
        payload["refuel_stops"] = _refuel_stops_payload(parameters.refuel_stops)
    if refuel_validation is not None:
        payload["refuel_stops_validation"] = {
            **asdict(refuel_validation),
            "seasons": list(refuel_validation.seasons),
        }
    if diagnostics is not None:
        payload["diagnostics"] = {
            **asdict(diagnostics),
            "skipped_races": list(diagnostics.skipped_races),
        }
    if validation is not None:
        payload["validation"] = {
            "seasons": list(validation.seasons),
            "mass_weighted_mae_ms": validation.mass_weighted_mae_ms,
            "linear_weighted_mae_ms": validation.linear_weighted_mae_ms,
            "mass_median_ae_ms": validation.mass_median_ae_ms,
            "linear_median_ae_ms": validation.linear_median_ae_ms,
            "races": [asdict(check) for check in validation.races],
        }

    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        os.replace(temporary, destination)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def read_fuel_parameters(source: Path) -> FuelModelParameters:
    """Leia e valide o artefato pelas invariantes do dominio.

    ``FileNotFoundError`` sobe intacto, para o chamador distinguir "artefato
    nao gerado" de "artefato corrompido" (``FuelParametersError``).
    """

    try:
        payload = json.loads(Path(source).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise FuelParametersError(f"JSON invalido em {source}: {error}") from error
    try:
        if payload["schema_version"] != SCHEMA_VERSION:
            raise FuelParametersError(
                f"schema_version {payload['schema_version']!r} nao suportada"
            )
        provenance = payload["provenance"]
        assumed = payload["assumed"]
        return FuelModelParameters(
            version=payload["version"],
            provenance=CalibrationProvenance(
                source_name=provenance["source_name"],
                source_version=int(provenance["source_version"]),
                seasons=tuple(int(s) for s in provenance["seasons"]),
                races=int(provenance["races"]),
                clean_laps=int(provenance["clean_laps"]),
                calibrated_at=provenance["calibrated_at"],
            ),
            lap_time_fraction_per_fuel_km=float(
                payload["calibrated"]["lap_time_fraction_per_fuel_km"]
            ),
            origin=payload["calibrated"]["origin"],
            max_fuel_kg=float(payload["regulation"]["max_fuel_kg"]),
            refuelling_allowed=_bool(
                payload.get("scenario", {}).get("refuelling_allowed", True)
            ),
            refuel_stops=(
                _refuel_stops_from(payload["refuel_stops"])
                if payload.get("refuel_stops") is not None
                else None
            ),
            **{
                name: float(
                    assumed[name] if name in assumed else _ASSUMED_DEFAULTS[name]
                )
                for name in _ASSUMED_FIELDS
            },
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, FuelParametersError):
            raise
        raise FuelParametersError(f"artefato de combustivel invalido: {error}") from error


def _bool(value: object) -> bool:
    if type(value) is not bool:
        raise FuelParametersError("refuelling_allowed deve ser booleano")
    return value


def _refuel_stops_payload(stops: RefuelStopParameters) -> dict:
    provenance = asdict(stops.provenance)
    provenance["seasons"] = list(stops.provenance.seasons)
    return {
        "origin": stops.origin,
        "provenance": provenance,
        "persistence": stops.persistence,
        "stop_sigma_ms": stops.stop_sigma_ms,
        "stop_skew": stops.stop_skew,
        "rationale": (
            "Perda media do carro = pit_loss_ms do circuito + offset_ms da "
            "equipe x persistence. offset_ms e a mediana de (duracao no pit "
            "lane - mediana da corrida) nas paradas reais; persistence e a "
            "fracao desse desvio que se repete na temporada seguinte."
        ),
        "team_offsets": [asdict(item) for item in stops.team_offsets],
    }


def _refuel_stops_from(payload: dict) -> RefuelStopParameters:
    provenance = payload["provenance"]
    return RefuelStopParameters(
        provenance=CalibrationProvenance(
            source_name=provenance["source_name"],
            source_version=int(provenance["source_version"]),
            seasons=tuple(int(s) for s in provenance["seasons"]),
            races=int(provenance["races"]),
            clean_laps=int(provenance["clean_laps"]),
            calibrated_at=provenance["calibrated_at"],
        ),
        team_offsets=tuple(
            TeamPitOffset(
                team_id=item["team_id"],
                name=item["name"],
                offset_ms=float(item["offset_ms"]),
                stops=int(item["stops"]),
            )
            for item in payload["team_offsets"]
        ),
        persistence=float(payload["persistence"]),
        stop_sigma_ms=float(payload["stop_sigma_ms"]),
        stop_skew=float(payload["stop_skew"]),
        origin=payload["origin"],
    )
