#!/usr/bin/env python3
"""Run the generic race ETL with the Trotman and SQLite adapters."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


DEFAULT_SOURCE = ROOT / "data" / "raw" / "formula-1-race-data-v128.zip"


def parse_args() -> argparse.Namespace:
    """Parse source, race and output paths supplied to the ETL command."""

    parser = argparse.ArgumentParser(
        description="Normaliza uma corrida da Base Trotman v128 em SQLite."
    )
    parser.add_argument("--race-id", type=int, required=True, help="raceId externo")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--overwrite", action="store_true", help="substitui saidas existentes"
    )
    return parser.parse_args()


def main() -> int:
    """Compose concrete adapters and report expected ingestion errors to the CLI."""

    from f1_simulator.adapters.datasets.trotman import (
        TrotmanDatasetAdapter,
        TrotmanDatasetError,
    )
    from f1_simulator.adapters.persistence.sqlite_race_data import SQLiteRaceDataWriter
    from f1_simulator.application.etl import run_race_etl
    from f1_simulator.factories.race_data_factory import RaceDataValidationError

    args = parse_args()
    try:
        # This CLI is the composition root: it chooses concrete adapters while
        # the application service remains independent of Trotman and SQLite.
        dataset = TrotmanDatasetAdapter(args.source)
        writer = SQLiteRaceDataWriter()
        report = run_race_etl(
            dataset,
            writer,
            args.race_id,
            args.output,
            args.report,
            overwrite=args.overwrite,
        )
    except (
        TrotmanDatasetError,
        RaceDataValidationError,
        OSError,
        sqlite3.Error,
    ) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report["row_counts"], sort_keys=True))
    print(f"sqlite: {args.output.resolve()}")
    print(f"relatorio: {args.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
