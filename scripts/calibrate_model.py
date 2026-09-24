#!/usr/bin/env python3
"""Estime os parametros do modelo a partir do historico canonico.

Previsto na arvore de diretorios do plano (secao 9). Le o SQLite produzido por
``scripts/ingest_trotman.py --all-tables`` e grava um JSON pequeno e versionado
em ``data/parameters/``.

Exemplo::

    python scripts/calibrate_model.py \\
        --database data/curated/history.sqlite \\
        --seasons 2022 2023 \\
        --output data/parameters/model-v1.json

As temporadas de calibracao devem ser **separadas** das usadas na validacao
(plano, secao 7.3). O backtest recusa rodar sobre uma temporada calibrada, a
menos que isso seja pedido explicitamente.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calibra os parametros do modelo de tempo de volta."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=ROOT / "data" / "curated" / "history.sqlite",
        help="SQLite do historico completo (--all-tables)",
    )
    parser.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        required=True,
        help="temporadas de calibracao; use uma era regulatoria coerente",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "parameters" / "model-v1.json",
    )
    parser.add_argument("--version", default=None, help="rotulo da versao gerada")
    parser.add_argument(
        "--min-stops-per-circuit",
        type=int,
        default=20,
        help="paradas minimas para calibrar a perda de boxes de um circuito",
    )
    return parser.parse_args()


def main() -> int:
    from f1_simulator.adapters.model_parameters_json import write_parameters
    from f1_simulator.adapters.persistence.sqlite_calibration import (
        load_calibration_input,
    )
    from f1_simulator.application.calibrate_model import calibrate

    args = parse_args()
    seasons = tuple(sorted(set(args.seasons)))
    version = args.version or f"trotman-v128-{'-'.join(str(s) for s in seasons)}"

    try:
        data, excluded = load_calibration_input(args.database, seasons=seasons)
        parameters, diagnostics = calibrate(
            data,
            version=version,
            minimum_stops_per_circuit=args.min_stops_per_circuit,
        )
    except (FileNotFoundError, ValueError) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1

    write_parameters(parameters, args.output)

    print(f"temporadas de calibracao : {seasons}")
    print(f"corridas                 : {diagnostics.races}")
    print(f"voltas limpas usadas     : {diagnostics.clean_laps:,}")
    print("voltas excluidas por filtro:")
    for reason, count in sorted(excluded.items(), key=lambda kv: -kv[1]):
        print(f"    {reason:28s} {count:>8,}")
    print()
    print("coeficientes identificados:")
    print(
        f"    combustivel  {diagnostics.fuel_ms_per_lap:+8.2f} ms por volta de corrida"
    )
    print(
        f"    pneu         {diagnostics.tyre_ms_per_lap:+8.2f} ms por volta de stint"
    )
    print(
        f"    colinearidade(volta, idade) = {diagnostics.collinearity:.4f}"
        "   (precisa ser < 1 para separar os dois)"
    )
    print()
    print(f"penalidade de largada   : {parameters.grid_penalty_ms_per_position:.1f} ms/posicao")
    print(f"ruido por volta         : sigma {parameters.lap_noise_ms:.0f} ms, "
          f"assimetria {parameters.lap_noise_skew:.3f}")
    print(f"risco de abandono       : {parameters.dnf_hazard_per_lap:.5f} por volta")
    print(f"circuitos calibrados    : {diagnostics.circuits_calibrated}"
          f"  ({diagnostics.circuits_with_severity} com severidade de pneu propria)")
    severities = [t.tyre_severity for t in parameters.tracks]
    difficulties = [t.overtaking_difficulty for t in parameters.tracks]
    if severities:
        print(f"severidade de pneu      : {min(severities):.2f}x a "
              f"{max(severities):.2f}x entre circuitos")
        print(f"dificuldade de ultrap.  : {min(difficulties):.2f} a "
              f"{max(difficulties):.2f}")
    if parameters.team_reliability:
        factors = sorted(parameters.team_reliability, key=lambda t: t.hazard_factor)
        print(f"equipes calibradas      : {diagnostics.teams_calibrated}  "
              f"({factors[0].name} {factors[0].hazard_factor:.2f}x .. "
              f"{factors[-1].name} {factors[-1].hazard_factor:.2f}x)")
    print(f"perda de boxes (fallback): {parameters.fallback_track.pit_loss_ms/1000:.2f} s")
    print()
    print(f"parametros gravados em {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
