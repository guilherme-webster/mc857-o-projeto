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
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--race-id", type=int, help="raceId externo")
    scope.add_argument(
        "--all-tables",
        action="store_true",
        help="importa todos os campos dos 14 CSVs, sem filtro de temporada",
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--report",
        type=Path,
        help="JSON externo (obrigatorio no modo --race-id); historico completo guarda relatorio no SQLite",
    )
    parser.add_argument(
        "--geometry-dir",
        type=Path,
        help="diretorio dos CSVs track_points.csv e pit_lane_points.csv da issue 51",
    )
    parser.add_argument(
        "--geometry-manifests-dir",
        type=Path,
        default=ROOT / "data" / "sources",
        help="diretorio dos manifestos fastf1-tracks-2025.json e fastf1-pit-lanes-2025.json",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="substitui saidas existentes"
    )
    args = parser.parse_args()
    if args.all_tables and (args.geometry_dir or args.report):
        parser.error(
            "--all-tables guarda relatorio interno e nao aceita --geometry-dir/--report"
        )
    if not args.all_tables and args.report is None:
        parser.error("--race-id exige --report")
    return args


def main() -> int:
    """Compose concrete adapters and report expected ingestion errors to the CLI."""

    from f1_simulator.adapters.datasets.trotman import (
        TrotmanDatasetAdapter,
        TrotmanDatasetError,
    )
    from f1_simulator.adapters.persistence.sqlite_race_data import SQLiteRaceDataWriter
    from f1_simulator.application.etl import run_race_etl
    from f1_simulator.factories.race_data_factory import RaceDataValidationError
    from f1_simulator.adapters.datasets.mock_track_geometry import (
        MockTrackDatasetAdapter,
        MockTrackDatasetError,
    )
    from f1_simulator.factories.track_geometry_factory import (
        TrackGeometryValidationError,
    )

    args = parse_args()
    try:
        if args.all_tables:
            from f1_simulator.adapters.datasets.trotman_history import (
                TrotmanHistoryAdapter,
            )
            from f1_simulator.adapters.persistence.sqlite_history import (
                SQLiteHistoryWriter,
            )
            from f1_simulator.application.history_etl import run_history_etl

            source = args.source.resolve()
            output = args.output.resolve()
            if output == source or source.is_dir() and output.is_relative_to(source):
                raise ValueError(
                    "a saida nao pode substituir ou ficar dentro da fonte bruta"
                )
            report = run_history_etl(
                TrotmanHistoryAdapter(source),
                SQLiteHistoryWriter(),
                output,
                overwrite=args.overwrite,
            )
            print(json.dumps(report["row_counts"], sort_keys=True))
            print(f"sqlite e relatorio interno: {output}")
            return 0
        # This CLI is the composition root: it chooses concrete adapters while
        # the application service remains independent of Trotman and SQLite.
        dataset = TrotmanDatasetAdapter(args.source)
        writer = SQLiteRaceDataWriter()
        geometry_dataset = None
        if args.geometry_dir is not None:
            geometry_dataset = MockTrackDatasetAdapter(
                args.geometry_dir / "track_points.csv",
                args.geometry_manifests_dir / "fastf1-tracks-2025.json",
                args.geometry_dir / "pit_lane_points.csv",
                args.geometry_manifests_dir / "fastf1-pit-lanes-2025.json",
            )
        report = run_race_etl(
            dataset,
            writer,
            args.race_id,
            args.output,
            args.report,
            overwrite=args.overwrite,
            geometry_dataset=geometry_dataset,
        )
    except (
        TrotmanDatasetError,
        RaceDataValidationError,
        MockTrackDatasetError,
        TrackGeometryValidationError,
        OSError,
        sqlite3.Error,
        ValueError,
    ) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report["row_counts"], sort_keys=True))
    print(f"sqlite: {args.output.resolve()}")
    print(f"relatorio: {args.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
