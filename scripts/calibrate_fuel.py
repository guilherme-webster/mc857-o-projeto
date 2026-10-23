#!/usr/bin/env python3
"""Calibre e valide o modelo de massa de combustivel contra o historico.

Le o SQLite produzido por ``scripts/ingest_trotman.py --all-tables`` e grava
``data/parameters/fuel-v1.json``. As temporadas de validacao precisam ser
diferentes das de calibracao: o relatorio compara, corrida a corrida, o modelo
de massa com o combustivel linear legado de ``model-v1.json``.

Exemplo::

    python scripts/calibrate_fuel.py \\
        --database data/curated/history.sqlite \\
        --seasons 2022 2023 \\
        --validate-seasons 2024 2025

A extensao das pistas vem do catalogo de geometria FastF1
(``data/sources/fastf1-tracks-2025.json``); corridas em circuitos fora dele
(Paul Ricard, por exemplo) sao listadas como ignoradas.

O mesmo artefato leva o tempo de parada por equipe usado no reabastecimento,
medido nas paradas reais de ``--stop-seasons`` e validado em
``--stop-validate-seasons``. A persistencia entre temporadas e estimada so
com janelas que terminam antes da validacao.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from f1_simulator.adapters.fuel_parameters_json import (  # noqa: E402
    write_fuel_parameters,
)
from f1_simulator.adapters.model_parameters_json import read_parameters  # noqa: E402
from f1_simulator.adapters.persistence.sqlite_calibration import (  # noqa: E402
    load_calibration_input,
)
from f1_simulator.adapters.persistence.sqlite_history import (  # noqa: E402
    SQLiteHistoryRepository,
)
from f1_simulator.application.calibrate_fuel import (  # noqa: E402
    FuelRaceContext,
    PitStopObservation,
    calibrate_fuel,
    calibrate_refuel_stops,
    validate_fuel,
    validate_refuel_stops,
)

DEFAULT_MANIFEST = ROOT / "data" / "sources" / "fastf1-tracks-2025.json"
DEFAULT_MODEL = ROOT / "data" / "parameters" / "model-v1.json"
DEFAULT_OUTPUT = ROOT / "data" / "parameters" / "fuel-v1.json"
SOURCE_NAME = "jtrotman/formula-1-race-data"
SOURCE_VERSION = 128


def lap_lengths_km(manifest: Path) -> dict[str, float]:
    """Extensao de cada circuito do catalogo de geometria, em km."""

    events = json.loads(manifest.read_text(encoding="utf-8"))["source"]["events"]
    return {
        f"circuit:{event['circuit_id']}": float(event["lap_length_m"]) / 1000.0
        for event in events
    }


def race_contexts(
    repository: SQLiteHistoryRepository,
    seasons: tuple[int, ...],
    lengths: dict[str, float],
) -> dict[str, FuelRaceContext]:
    """Referencia (mediana das voltas mais rapidas) e extensao de cada corrida."""

    contexts: dict[str, FuelRaceContext] = {}
    for season in seasons:
        for race in repository.records("races", season=season):
            length = lengths.get(race["circuit_id"])
            if length is None:
                continue
            fastest = [
                result["fastest_lap_time_ms"]
                for result in repository.records(
                    "race_results", race_id=race["race_id"]
                )
                if result["fastest_lap_time_ms"] is not None
            ]
            if not fastest:
                continue
            contexts[race["race_id"]] = FuelRaceContext(
                race_id=race["race_id"],
                name=race["name"],
                season=season,
                circuit_id=race["circuit_id"],
                reference_lap_ms=float(statistics.median(fastest)),
                lap_length_km=length,
            )
    return contexts


def pit_stops(
    repository: SQLiteHistoryRepository, seasons: tuple[int, ...]
) -> list[PitStopObservation]:
    """Paradas reais com a equipe de cada carro (via ``race_results``)."""

    teams = {record["team_id"]: record["name"] for record in repository.records("teams")}
    observations: list[PitStopObservation] = []
    for season in seasons:
        for race in repository.records("races", season=season):
            race_id = race["race_id"]
            team_of = {
                result["driver_id"]: result["team_id"]
                for result in repository.records("race_results", race_id=race_id)
            }
            for stop in repository.records("pit_stops", race_id=race_id):
                team_id = team_of.get(stop["driver_id"])
                if team_id is None or stop["duration_ms"] is None:
                    continue
                observations.append(
                    PitStopObservation(
                        race_id=race_id,
                        season=season,
                        team_id=team_id,
                        team_name=teams.get(team_id, team_id),
                        duration_ms=int(stop["duration_ms"]),
                    )
                )
    return observations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--database", type=Path, default=ROOT / "data" / "curated" / "history.sqlite"
    )
    parser.add_argument("--seasons", type=int, nargs="+", required=True)
    parser.add_argument("--validate-seasons", type=int, nargs="+", default=())
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--version", default=None)
    parser.add_argument("--stop-seasons", type=int, nargs="+", default=(2023, 2024))
    parser.add_argument(
        "--stop-validate-seasons", type=int, nargs="+", default=(2025,)
    )
    parser.add_argument(
        "--persistence-from",
        type=int,
        default=2021,
        help="primeira temporada das janelas usadas para medir a persistencia",
    )
    parser.add_argument(
        "--no-refuelling",
        action="store_true",
        help="grava o cenario com a regra 2010+ (sem reabastecimento)",
    )
    args = parser.parse_args(argv)

    seasons = tuple(sorted(set(args.seasons)))
    holdout = tuple(sorted(set(args.validate_seasons)))
    if set(seasons) & set(holdout):
        print("erro: validacao precisa usar temporadas fora da calibracao",
              file=sys.stderr)
        return 1
    version = args.version or f"fuel-trotman-v128-{'-'.join(map(str, seasons))}"
    stop_seasons = tuple(sorted(set(args.stop_seasons)))
    stop_holdout = tuple(sorted(set(args.stop_validate_seasons)))
    if stop_holdout and min(stop_holdout) <= max(stop_seasons):
        print("erro: a validacao das paradas precisa vir depois das temporadas "
              "de calibracao", file=sys.stderr)
        return 1
    # Janelas de duas temporadas -> temporada seguinte, todas dentro de
    # ``stop_seasons`` ou antes: nenhuma ve a validacao.
    windows = [
        ((year - 2, year - 1), year)
        for year in range(args.persistence_from + 2, max(stop_seasons) + 1)
    ]

    lengths = lap_lengths_km(args.manifest)
    repository = SQLiteHistoryRepository(args.database)
    try:
        data, _ = load_calibration_input(args.database, seasons=seasons)
        contexts = race_contexts(repository, seasons, lengths)
        parameters, diagnostics = calibrate_fuel(
            data.laps,
            contexts,
            version=version,
            seasons=seasons,
            source_name=SOURCE_NAME,
            source_version=SOURCE_VERSION,
        )
        history_stops = pit_stops(
            repository,
            tuple(range(args.persistence_from, max(stop_seasons) + 1)),
        )
        refuel_stops = calibrate_refuel_stops(
            history_stops,
            seasons=stop_seasons,
            persistence_windows=windows,
            source_name=SOURCE_NAME,
            source_version=SOURCE_VERSION,
        )
        parameters = replace(
            parameters,
            refuel_stops=refuel_stops,
            refuelling_allowed=not args.no_refuelling,
        )
        refuel_validation = None
        if stop_holdout:
            refuel_validation = validate_refuel_stops(
                pit_stops(repository, stop_holdout),
                refuel_stops,
                seasons=stop_holdout,
            )
        validation = None
        if holdout:
            holdout_data, _ = load_calibration_input(args.database, seasons=holdout)
            validation = validate_fuel(
                holdout_data.laps,
                race_contexts(repository, holdout, lengths),
                parameters,
                linear_ms_per_lap=read_parameters(
                    args.model
                ).fuel_penalty_ms_per_remaining_lap,
                seasons=holdout,
            )
    except (FileNotFoundError, ValueError) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1

    write_fuel_parameters(
        parameters,
        args.output,
        diagnostics=diagnostics,
        validation=validation,
        refuel_validation=refuel_validation,
    )

    print(f"temporadas de calibracao : {seasons}")
    print(f"corridas / voltas limpas : {diagnostics.races} / {diagnostics.clean_laps:,}")
    if diagnostics.skipped_races:
        print(f"corridas sem contexto    : {len(diagnostics.skipped_races)}")
    print(f"fracao por km de comb.   : {parameters.lap_time_fraction_per_fuel_km:.4e}")
    print(f"colinearidade            : {diagnostics.collinearity:.4f}")
    print(f"pneu (mesma regressao)   : {diagnostics.tyre_ms_per_lap:+.2f} ms/volta")
    print(f"equivale a               : {diagnostics.implied_ms_per_kg_at_90s:.1f} ms/kg"
          f" numa volta de 90 s ({parameters.burn_kg_per_km} kg/km assumido)")
    if validation is not None:
        print()
        print(f"validacao fora da amostra {validation.seasons}: "
              f"{len(validation.races)} corridas")
        print("    erro da inclinacao por corrida (ms/volta)   massa   linear")
        print(f"    media ponderada pelas voltas              "
              f"{validation.mass_weighted_mae_ms:6.1f}  "
              f"{validation.linear_weighted_mae_ms:6.1f}")
        print(f"    mediana                                   "
              f"{validation.mass_median_ae_ms:6.1f}  "
              f"{validation.linear_median_ae_ms:6.1f}")
    print()
    print(f"reabastecimento permitido: {parameters.refuelling_allowed}")
    print(f"tempo de parada por equipe: {len(refuel_stops.team_offsets)} equipes "
          f"de {stop_seasons}, persistencia {refuel_stops.persistence:.3f} "
          f"(janelas {windows})")
    print(f"variacao por parada       : sigma {refuel_stops.stop_sigma_ms:.0f} ms, "
          f"assimetria {refuel_stops.stop_skew:.3f}")
    for item in sorted(refuel_stops.team_offsets, key=lambda t: t.offset_ms):
        print(f"    {item.name[:22]:22s} {item.offset_ms:+7.1f} ms medido -> "
              f"{refuel_stops.offset_ms(item.team_id):+7.1f} ms previsto "
              f"({item.stops} paradas)")
    if refuel_validation is not None:
        print(f"validacao das paradas {refuel_validation.seasons}: "
              f"{len(refuel_validation.teams)} equipes, {refuel_validation.stops} paradas")
        print(f"    erro medio do deslocamento por equipe: modelo "
              f"{refuel_validation.model_mae_ms:.0f} ms | cru "
              f"{refuel_validation.raw_offset_mae_ms:.0f} ms | zero "
              f"{refuel_validation.zero_offset_mae_ms:.0f} ms")
        print(f"    paradas dentro do p10-p90 modelado: "
              f"{refuel_validation.p10_p90_coverage:.1%} (ideal 80%)")
    print(f"gravado em {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
