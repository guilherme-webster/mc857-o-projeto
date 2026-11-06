#!/usr/bin/env python3
"""Meça a sensibilidade do resultado ao fator heuristico da largada.

O experimento roda o motor detalhado diretamente, sem janela nem servidor. Usa
o mesmo conjunto de sementes para todos os fatores (comparacao pareada), tres
circuitos com perfis distintos de ultrapassagem e um grid sintetico fixo de 20
carros e tres relacoes entre classificacao e ritmo. Uma delas torna o carro de
P8 exatamente 500 ms/volta mais rapido que a pole; as outras representam uma
ordem de classificacao perfeita e um top 5 de ritmo misturado.

Os resultados sao uma analise de sensibilidade de uma hipotese de produto, nao
calibracao nem estimativa historica. Exemplo a partir da raiz::

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
      scripts/analyze_grid_start_sensitivity.py --races-per-track 40
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

DEFAULT_FACTORS = (
    1.0,
    0.75,
    0.5,
    0.35,
    0.25,
    0.15,
    0.1,
    0.075,
    0.05,
    0.025,
    0.015,
    0.0,
)
DEFAULT_TRACKS = (
    ("circuit:13", 44),  # Spa: facilidade calibrada alta de ultrapassagem.
    ("circuit:18", 71),  # Interlagos: caso intermediario.
    ("circuit:6", 78),  # Monaco: dificuldade calibrada maxima.
)
POLE_ID = "driver:sensitivity:01"
FAST_P8_ID = "driver:sensitivity:08"
GRID_SCENARIOS = ("qualifying_order", "mixed_top_five", "fast_p8")


def _analysis_grid(
    reference_lap_time_ms: float, scenario: str
) -> tuple[tuple, dict]:
    """Monte um dos tres grids fixos usados na comparacao pareada."""

    from f1_simulator.domain.driver_attributes import ATTRIBUTE_FIELDS, DriverAttributes
    from f1_simulator.domain.race_simulation import Entrant
    from f1_simulator.domain.strategy import NoStopStrategy

    entrants = []
    attributes = {}
    for position in range(1, 21):
        driver_id = f"driver:sensitivity:{position:02d}"
        if scenario == "qualifying_order":
            pace_rank = position
            pace_ms = reference_lap_time_ms + 75.0 * (pace_rank - 1)
        elif scenario == "mixed_top_five":
            top_offsets = {1: 0.0, 2: -300.0, 3: 150.0, 4: -500.0, 5: -100.0}
            pace_ms = reference_lap_time_ms + top_offsets.get(
                position, 75.0 * (position - 1)
            )
        elif scenario == "fast_p8":
            top_offsets = {
                1: 0.0,
                2: -400.0,
                3: -300.0,
                4: -200.0,
                5: -100.0,
                8: -500.0,
            }
            pace_ms = reference_lap_time_ms + top_offsets.get(
                position, 75.0 * (position - 1)
            )
        else:
            raise ValueError(f"cenario de grid desconhecido: {scenario}")
        entrants.append(
            Entrant(
                driver_id=driver_id,
                name=f"P{position:02d}",
                reference_lap_time_ms=pace_ms,
                grid_position=position,
                # Uma estrategia comum e sem sorteios isola o efeito do grid;
                # pneus, trafego, disputa, ruido e controle de prova continuam.
                strategy=NoStopStrategy(),
                starting_compound="MEDIUM",
            )
        )
        attributes[driver_id] = DriverAttributes(
            driver_id=driver_id,
            archetype="balanced",
            pace_offset_pct=0.0,
            consistency_factor=1.0,
            tyre_management_factor=1.0,
            aggression=1.0,
            composure=1.0,
            sources={field: "manual" for field in ATTRIBUTE_FIELDS},
        )
    return tuple(entrants), attributes


def _summarize_factor(
    factor: float, calibrated_ms_per_position: float, outcomes: list[dict]
) -> dict:
    """Agregue vitorias, P8 e distribuicao inteira de variacao de posicoes."""

    pole_wins = sum(item["winner"] == POLE_ID for item in outcomes)
    p8_positions = [
        item["final_positions"][FAST_P8_ID]
        for item in outcomes
        if item["grid_scenario"] == "fast_p8"
    ]
    deltas = Counter()
    for item in outcomes:
        for position in range(1, 21):
            driver_id = f"driver:sensitivity:{position:02d}"
            deltas[position - item["final_positions"][driver_id]] += 1
    total = sum(deltas.values())
    gained = sum(count for delta, count in deltas.items() if delta > 0)
    unchanged = deltas[0]
    lost = sum(count for delta, count in deltas.items() if delta < 0)
    return {
        "factor": factor,
        "effective_ms_per_position": calibrated_ms_per_position * factor,
        "races": len(outcomes),
        "pole_wins": pole_wins,
        "pole_win_rate": pole_wins / len(outcomes),
        "p8_races": len(p8_positions),
        "p8_mean_final_position": sum(p8_positions) / len(p8_positions),
        "p8_wins": sum(position == 1 for position in p8_positions),
        "position_change": {
            "gained_rate": gained / total,
            "unchanged_rate": unchanged / total,
            "lost_rate": lost / total,
            "histogram": {str(delta): deltas[delta] for delta in sorted(deltas)},
        },
    }


def run_sensitivity(
    *,
    factors: tuple[float, ...] = DEFAULT_FACTORS,
    races_per_track: int = 40,
    seed: int = 108_2026,
    parameters_path: Path = ROOT / "data" / "parameters" / "model-v1.json",
    reference_laps_path: Path = (
        ROOT / "data" / "parameters" / "reference-laps-v1.json"
    ),
    grid_start_path: Path = ROOT / "data" / "parameters" / "grid-start-v1.json",
    tracks: tuple[tuple[str, int], ...] = DEFAULT_TRACKS,
) -> dict:
    """Execute a matriz fator x pista x semente e devolva JSON auditavel."""

    if type(races_per_track) is not int or races_per_track <= 0:
        raise ValueError("races_per_track deve ser um inteiro positivo")
    if type(seed) is not int:
        raise ValueError("seed deve ser um inteiro verdadeiro")
    if not factors:
        raise ValueError("informe ao menos um fator")

    from f1_simulator.adapters.grid_start_parameters_json import (
        read_grid_start_parameters,
    )
    from f1_simulator.adapters.model_parameters_json import read_parameters
    from f1_simulator.adapters.reference_laps_json import read_reference_laps
    from f1_simulator.domain.grid_start import GridStartParameters
    from f1_simulator.domain.race_control import HEURISTIC_RACE_CONTROL
    from f1_simulator.domain.race_simulation import simulate_detailed_race
    from f1_simulator.domain.random_source import SeededRandomSource

    model = read_parameters(parameters_path)
    references = read_reference_laps(reference_laps_path)
    configured = read_grid_start_parameters(grid_start_path)
    track_rows = []
    for circuit_id, laps in tracks:
        if type(laps) is not int or laps <= 0:
            raise ValueError(f"voltas invalidas para {circuit_id}: {laps!r}")
        track_rows.append((model.track(circuit_id), references[circuit_id], laps))

    results = []
    for factor in factors:
        grid_start = GridStartParameters(
            penalty_factor=factor,
            origin="heuristic",
            parameter_version="grid-start-sensitivity-v1",
            rationale="Valor candidato da analise pareada da issue #108.",
        )
        outcomes = []
        for track_index, (track, reference, total_laps) in enumerate(track_rows):
            for scenario_index, scenario in enumerate(GRID_SCENARIOS):
                entrants, attributes = _analysis_grid(
                    reference.reference_lap_time_ms, scenario
                )
                for race_index in range(races_per_track):
                    race_seed = (
                        seed
                        + track_index * 100_000
                        + scenario_index * 10_000
                        + race_index
                    )
                    result = simulate_detailed_race(
                        entrants,
                        total_laps=total_laps,
                        parameters=model,
                        track=track,
                        rng=SeededRandomSource(race_seed),
                        attributes=attributes,
                        dispute_model="pressure",
                        race_control=HEURISTIC_RACE_CONTROL,
                        grid_start=grid_start,
                    )
                    final_positions = {
                        car["driver_id"]: car["position"]
                        for car in result["classification"]
                    }
                    outcomes.append(
                        {
                            "grid_scenario": scenario,
                            "winner": result["classification"][0]["driver_id"],
                            "final_positions": final_positions,
                        }
                    )
        results.append(
            _summarize_factor(
                factor, model.grid_penalty_ms_per_position, outcomes
            )
        )

    return {
        "method_version": "grid-start-sensitivity-v1",
        "model_parameters_version": model.version,
        "calibrated_grid_penalty_ms_per_position": (
            model.grid_penalty_ms_per_position
        ),
        "configured_factor": configured.penalty_factor,
        "seed": seed,
        "races_per_track": races_per_track,
        "tracks": [
            {
                "circuit_id": track.circuit_id,
                "name": track.name,
                "laps": laps,
                "overtaking_difficulty": track.overtaking_difficulty,
            }
            for track, _reference, laps in track_rows
        ],
        "grid": {
            "cars": 20,
            "scenarios": list(GRID_SCENARIOS),
            "fast_car_grid_position": 8,
            "fast_car_advantage_ms_per_lap_over_pole": 500.0,
            "other_pace_step_ms_per_lap": 75.0,
        },
        "results": results,
    }


def _track_argument(value: str) -> tuple[str, int]:
    """Converta ``circuit:13=44`` para o contrato interno da CLI."""

    try:
        circuit_id, raw_laps = value.rsplit("=", 1)
        laps = int(raw_laps)
    except ValueError as error:
        raise argparse.ArgumentTypeError("use CIRCUIT_ID=VOLTAS") from error
    if not circuit_id or laps <= 0:
        raise argparse.ArgumentTypeError("use CIRCUIT_ID=VOLTAS positivas")
    return circuit_id, laps


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factors", type=float, nargs="+", default=DEFAULT_FACTORS)
    parser.add_argument("--races-per-track", type=int, default=40)
    parser.add_argument("--seed", type=int, default=108_2026)
    parser.add_argument(
        "--parameters",
        type=Path,
        default=ROOT / "data" / "parameters" / "model-v1.json",
    )
    parser.add_argument(
        "--reference-laps",
        type=Path,
        default=ROOT / "data" / "parameters" / "reference-laps-v1.json",
    )
    parser.add_argument(
        "--grid-start-parameters",
        type=Path,
        default=ROOT / "data" / "parameters" / "grid-start-v1.json",
    )
    parser.add_argument(
        "--track",
        action="append",
        type=_track_argument,
        dest="tracks",
        help="pista e voltas; repetivel, por exemplo circuit:13=44",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = run_sensitivity(
            factors=tuple(args.factors),
            races_per_track=args.races_per_track,
            seed=args.seed,
            parameters_path=args.parameters,
            reference_laps_path=args.reference_laps,
            grid_start_path=args.grid_start_parameters,
            tracks=tuple(args.tracks) if args.tracks else DEFAULT_TRACKS,
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
