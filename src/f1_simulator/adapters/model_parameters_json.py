"""Serializacao dos parametros do modelo em JSON versionado.

O plano (secao 7.1) pede "JSON ou TOML versionado para parametros calibrados".
Este adaptador e a unica fronteira entre ``ModelParameters`` e o disco: o
dominio nunca le nem escreve arquivo.

O arquivo gerado e pequeno, legivel e deve ser versionado no Git -- ao
contrario do banco curado, que fica fora do controle de versao. E ele que torna
uma simulacao reproduzivel meses depois: junto com a semente e a versao do
dataset, define completamente o resultado.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from f1_simulator.domain.model_parameters import (
    CalibrationProvenance,
    CompoundParameters,
    ModelParameters,
    TeamReliability,
    TrackParameters,
)


def to_dict(parameters: ModelParameters) -> dict:
    """Converta para um dicionario JSON-serializavel, sem perder campo algum."""

    payload = asdict(parameters)
    payload["provenance"]["seasons"] = list(parameters.provenance.seasons)
    payload["compounds"] = [asdict(c) for c in parameters.compounds]
    payload["tracks"] = [asdict(t) for t in parameters.tracks]
    payload["fallback_track"] = asdict(parameters.fallback_track)
    payload["team_reliability"] = [asdict(t) for t in parameters.team_reliability]
    return payload


def from_dict(payload: dict) -> ModelParameters:
    """Reconstrua os parametros validando pelas invariantes do dominio.

    A validacao acontece nos ``__post_init__`` das dataclasses: um arquivo
    corrompido ou editado a mao falha aqui, antes de a corrida comecar, em vez
    de produzir tempos silenciosamente errados.
    """

    provenance = CalibrationProvenance(
        source_name=payload["provenance"]["source_name"],
        source_version=int(payload["provenance"]["source_version"]),
        seasons=tuple(payload["provenance"]["seasons"]),
        races=int(payload["provenance"]["races"]),
        clean_laps=int(payload["provenance"]["clean_laps"]),
        calibrated_at=payload["provenance"]["calibrated_at"],
    )
    return ModelParameters(
        version=payload["version"],
        provenance=provenance,
        fuel_penalty_ms_per_remaining_lap=float(
            payload["fuel_penalty_ms_per_remaining_lap"]
        ),
        grid_penalty_ms_per_position=float(payload["grid_penalty_ms_per_position"]),
        reference_compound=payload["reference_compound"],
        compounds=tuple(CompoundParameters(**c) for c in payload["compounds"]),
        tracks=tuple(TrackParameters(**t) for t in payload["tracks"]),
        fallback_track=TrackParameters(**payload["fallback_track"]),
        team_reliability=tuple(
            TeamReliability(**t) for t in payload.get("team_reliability", ())
        ),
        lap_noise_ms=float(payload["lap_noise_ms"]),
        lap_noise_skew=float(payload["lap_noise_skew"]),
        dnf_hazard_per_lap=float(payload["dnf_hazard_per_lap"]),
        traffic_penalty_ms=float(payload["traffic_penalty_ms"]),
        traffic_threshold_ms=float(payload["traffic_threshold_ms"]),
        pit_window_spread_laps=float(payload["pit_window_spread_laps"]),
        qualifying_to_race_ratio=float(payload["qualifying_to_race_ratio"]),
        overtake_advantage_scale_ms=float(payload["overtake_advantage_scale_ms"]),
        minimum_gap_ms=float(payload["minimum_gap_ms"]),
        collision_probability_per_dispute=float(
            payload["collision_probability_per_dispute"]
        ),
        contact_dnf_share=float(payload["contact_dnf_share"]),
    )


def write_parameters(parameters: ModelParameters, destination: Path) -> None:
    """Grave os parametros de forma legivel e estavel para o diff do Git."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(to_dict(parameters), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_parameters(source: Path) -> ModelParameters:
    """Leia e valide um arquivo de parametros calibrados."""

    if not source.exists():
        raise FileNotFoundError(
            f"parametros do modelo nao encontrados: {source}. "
            "Rode scripts/calibrate_model.py para gera-los."
        )
    return from_dict(json.loads(source.read_text(encoding="utf-8")))
