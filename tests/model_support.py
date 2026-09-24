"""Fabricas de parametros para os testes do modelo de corrida.

Os valores sao redondos e arbitrarios de proposito: os testes verificam
regras e invariantes, nao os coeficientes calibrados. Amarrar um teste aos
numeros de ``data/parameters`` faria a suite quebrar a cada recalibracao, que e
uma mudanca legitima e esperada.
"""

from __future__ import annotations

from f1_simulator.domain.model_parameters import (
    CalibrationProvenance,
    CompoundParameters,
    ModelParameters,
    TeamReliability,
    TrackParameters,
)


def provenance(**overrides) -> CalibrationProvenance:
    defaults = dict(
        source_name="teste",
        source_version=1,
        seasons=(2022, 2023),
        races=10,
        clean_laps=1000,
        calibrated_at="2026-09-22",
    )
    defaults.update(overrides)
    return CalibrationProvenance(**defaults)


def track(**overrides) -> TrackParameters:
    defaults = dict(
        circuit_id="circuit:1",
        name="Circuito de teste",
        pit_loss_ms=20_000.0,
        tyre_severity=1.0,
        overtaking_difficulty=0.5,
        origin="calibrated",
        observed_stops=50,
    )
    defaults.update(overrides)
    return TrackParameters(**defaults)


def team(**overrides) -> TeamReliability:
    defaults = dict(
        team_id="team:1",
        name="Equipe de teste",
        hazard_factor=1.0,
        observed_entries=80,
        retirements=10,
        origin="calibrated",
    )
    defaults.update(overrides)
    return TeamReliability(**defaults)


def parameters(**overrides) -> ModelParameters:
    defaults = dict(
        version="teste-v1",
        provenance=provenance(),
        fuel_penalty_ms_per_remaining_lap=25.0,
        grid_penalty_ms_per_position=800.0,
        reference_compound="MEDIUM",
        compounds=(
            CompoundParameters("SOFT", -450.0, 64.0, 0.0, 14),
            CompoundParameters("MEDIUM", 0.0, 40.0, 0.0, 22),
            CompoundParameters("HARD", 450.0, 24.0, 0.0, 37),
        ),
        tracks=(track(),),
        fallback_track=track(
            circuit_id="__fallback__", name="mediana", origin="assumed"
        ),
        team_reliability=(
            team(team_id="team:frail", name="Fragil", hazard_factor=1.6),
            team(team_id="team:solid", name="Solida", hazard_factor=0.5),
        ),
        lap_noise_ms=250.0,
        lap_noise_skew=0.0,
        dnf_hazard_per_lap=0.0025,
        traffic_penalty_ms=600.0,
        traffic_threshold_ms=2500.0,
        pit_window_spread_laps=6.0,
        qualifying_to_race_ratio=1.05,
        overtake_advantage_scale_ms=900.0,
        minimum_gap_ms=700.0,
        collision_probability_per_dispute=0.004,
        contact_dnf_share=0.41,
    )
    defaults.update(overrides)
    return ModelParameters(**defaults)
