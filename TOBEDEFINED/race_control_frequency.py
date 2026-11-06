#!/usr/bin/env python3
"""Meça frequencias plausíveis do controle de prova em corridas heuristicas.

O experimento nao calibra ``model-v1.json`` nem apresenta suas taxas como
observacoes reais. Ele exercita varios circuitos ja presentes nesse arquivo,
vinte perfis ficticios gerados por semente, estrategia heuristica com janela
individual e o motor de pressao. O objetivo e somente verificar os alvos do PRD
4.4.2: aproximadamente 0,6 SC/VSC por corrida e uma vermelha a cada seis.

Exemplo, a partir da raiz do repositorio::

    PYTHONDONTWRITEBYTECODE=1 TMPDIR=$PWD/tmp \
      .venv/bin/python scripts/race_control_frequency.py --races 200
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def _count_overtakes(history: list[dict], grid: tuple[str, ...]) -> int:
    """Conte ganhos de posicao em pista, excluindo volta com parada do carro.

    O motor ainda nao publica um evento proprio de ultrapassagem. Esta metrica
    de sanidade conta posicoes ganhas entre retratos por carros que permaneceram
    em pista e nao aumentaram ``stops_made`` na volta. Assim, uma passagem pelo
    pit lane nao e apresentada como ultrapassagem, embora abandonos simultaneos
    possam tornar o numero uma aproximacao. Isso basta para comparar cenarios;
    nao e uma estatistica oficial de corrida.
    """

    previous_positions = {driver_id: index for index, driver_id in enumerate(grid)}
    previous_stops = {driver_id: 0 for driver_id in grid}
    total = 0
    for snapshot in history:
        running = [car for car in snapshot["cars"] if car["status"] == "RUNNING"]
        positions = {
            car["driver_id"]: index for index, car in enumerate(running)
        }
        for car in running:
            driver_id = car["driver_id"]
            if driver_id not in previous_positions:
                continue
            if car["stops_made"] != previous_stops.get(driver_id, 0):
                continue
            total += max(0, previous_positions[driver_id] - positions[driver_id])
        previous_positions = positions
        previous_stops = {
            car["driver_id"]: car["stops_made"] for car in running
        }
    return total


def run_frequency_sample(
    races: int,
    *,
    seed: int = 67_2026,
    total_laps: int = 58,
    parameters_path: Path = ROOT / "data" / "parameters" / "model-v1.json",
) -> dict[str, object]:
    """Simule uma amostra fixa e devolva contagens e taxas agregadas.

    ``seed + indice_da_corrida`` identifica cada execucao. Circuitos percorrem
    o catalogo calibrado em ordem e voltam ao inicio quando ``races`` o excede.
    Os offsets de parada sao sorteados no intervalo declarado pela propria
    ``HeuristicPitParameters``; nenhum limiar fica escondido neste script.
    """

    if type(races) is not int or races <= 0:
        raise ValueError("races deve ser um inteiro positivo")
    if type(seed) is not int:
        raise ValueError("seed deve ser um inteiro verdadeiro")
    if type(total_laps) is not int or total_laps <= 0:
        raise ValueError("total_laps deve ser um inteiro positivo")

    from f1_simulator.adapters.model_parameters_json import read_parameters
    from f1_simulator.application.generate_attributes import generate_attributes
    from f1_simulator.domain.race_control import HEURISTIC_RACE_CONTROL
    from f1_simulator.domain.race_simulation import Entrant, simulate_detailed_race
    from f1_simulator.domain.random_source import SeededRandomSource, uniform_index
    from f1_simulator.domain.strategy import (
        DEFAULT_HEURISTIC_PIT_PARAMETERS,
        HeuristicPitStrategy,
    )

    parameters = read_parameters(parameters_path)
    tracks = tuple(sorted(parameters.tracks, key=lambda item: item.circuit_id))
    if not tracks:
        raise ValueError("o arquivo de parametros nao contem circuitos")

    driver_ids = tuple(f"driver:frequency:{index:02d}" for index in range(20))
    neutralizations = 0
    red_flags = 0
    overtakes = 0
    pit_stops = 0
    retirements = {"MECHANICAL": 0, "CONTACT": 0, "CRASH": 0}

    for race_index in range(races):
        rng = SeededRandomSource(seed + race_index)
        track = tracks[race_index % len(tracks)]
        generated = generate_attributes(
            driver_ids, rng.spawn("driver-attributes")
        )
        attributes = {item.driver_id: item for item in generated}
        offset_source = rng.spawn("pit-offsets")
        amplitude = (
            DEFAULT_HEURISTIC_PIT_PARAMETERS.driver_variation_amplitude_laps
        )
        entrants = []
        for grid_index, driver_id in enumerate(driver_ids, start=1):
            driver_attributes = attributes[driver_id]
            offset_laps = (
                uniform_index(
                    offset_source,
                    f"pit-offset:{driver_id}",
                    2 * amplitude + 1,
                )
                - amplitude
            )
            entrants.append(
                Entrant(
                    driver_id=driver_id,
                    name=f"Piloto {grid_index:02d}",
                    reference_lap_time_ms=90_000.0 + 75.0 * (grid_index - 1),
                    grid_position=grid_index,
                    strategy=HeuristicPitStrategy(
                        parameters,
                        track,
                        tyre_management_factor=(
                            driver_attributes.tyre_management_factor
                        ),
                        offset_laps=offset_laps,
                    ),
                    starting_compound="MEDIUM",
                )
            )

        result = simulate_detailed_race(
            entrants,
            total_laps=total_laps,
            parameters=parameters,
            track=track,
            rng=rng,
            attributes=attributes,
            dispute_model="pressure",
            race_control=HEURISTIC_RACE_CONTROL,
        )
        for event in result["race_control_events"]:
            if event["type"] not in (
                "race_control_started",
                "race_control_escalated",
            ):
                continue
            if event["status"] in ("SC", "VSC"):
                neutralizations += 1
            elif event["status"] == "RED":
                red_flags += 1
        overtakes += _count_overtakes(result["history"], driver_ids)
        for car in result["classification"]:
            pit_stops += car["stops_made"]
            cause = car["retirement_cause"]
            if cause is not None:
                retirements[cause] += 1

    completed_laps = races * total_laps
    car_starts = races * len(driver_ids)
    return {
        "races": races,
        "total_laps_per_race": total_laps,
        "seed": seed,
        "race_control_parameter_version": (
            HEURISTIC_RACE_CONTROL.parameter_version
        ),
        "neutralizations": neutralizations,
        "neutralizations_per_race": neutralizations / races,
        "red_flags": red_flags,
        "red_flags_per_race": red_flags / races,
        "overtakes": overtakes,
        "overtakes_per_lap": overtakes / completed_laps,
        "pit_stops": pit_stops,
        "pit_stops_per_car": pit_stops / car_starts,
        "retirements": retirements,
        "retirements_per_race_by_cause": {
            cause: count / races for cause, count in retirements.items()
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--races", type=int, default=200)
    parser.add_argument("--seed", type=int, default=67_2026)
    parser.add_argument("--laps", type=int, default=58)
    parser.add_argument(
        "--parameters",
        type=Path,
        default=ROOT / "data" / "parameters" / "model-v1.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        metrics = run_frequency_sample(
            args.races,
            seed=args.seed,
            total_laps=args.laps,
            parameters_path=args.parameters,
        )
    except (FileNotFoundError, KeyError, ValueError) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
