#!/usr/bin/env python3
"""Enrich a complete historical catalog with selected offline FastF1 sessions."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Select an explicit event/year scope before making network requests."""
    from f1_simulator.adapters.datasets.fastf1_sessions import SESSION_KINDS

    parser = argparse.ArgumentParser(
        description="Enriquece um historico Trotman completo com sessoes FastF1."
    )
    parser.add_argument(
        "--base",
        required=True,
        type=Path,
        help="SQLite criado por ingest_trotman.py --all-tables",
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--race-id", type=int, help="raceId Trotman de um evento")
    scope.add_argument(
        "--season", type=int, help="todos os eventos da temporada presentes na base"
    )
    parser.add_argument(
        "--rounds", nargs="+", type=int, help="limita as etapas de --season"
    )
    parser.add_argument(
        "--sessions", nargs="+", choices=SESSION_KINDS, default=["R", "Q"]
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="cache persistente opcional; padrao temporario e removido",
    )
    parser.add_argument(
        "--without-telemetry",
        action="store_true",
        help="nao solicita amostras de carro/posicao; registra exclusao no relatorio",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="falha se um feed solicitado estiver indisponivel ou sem pilotos esperados",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.rounds and args.season is None:
        parser.error("--rounds exige --season")
    if len(set(args.sessions)) != len(args.sessions):
        parser.error("--sessions nao pode conter repeticoes")
    return args


def ingest(args: argparse.Namespace, *, loader=None) -> list[dict[str, object]]:
    """Publish all selected sessions together, keeping old artifacts on failure.

    A staging catalog accumulates per-session transactions. Only after every
    requested session succeeds is the final destination replaced. The injected
    loader lets tests exercise failure recovery without performing any HTTP.
    """
    from f1_simulator.adapters.datasets.fastf1_sessions import (
        FastF1SessionAdapter,
        load_session,
    )
    from f1_simulator.adapters.persistence.sqlite_history import (
        SQLiteHistoryRepository,
        SQLiteHistoryWriter,
    )
    from f1_simulator.application.history_etl import run_history_etl

    destination = args.output.resolve()
    if destination.exists() and not args.overwrite:
        raise FileExistsError(f"output already exists: {destination}")
    if destination.is_relative_to(ROOT / "data" / "raw"):
        raise ValueError("curated output must not be written into data/raw")
    repository = SQLiteHistoryRepository(args.base)
    filters = (
        {"race_id": f"race:{args.race_id}"}
        if args.race_id is not None
        else {"season": args.season}
    )
    races = [r.as_dict() for r in repository.records("races", **filters)]
    if args.rounds:
        missing = set(args.rounds) - {r["round_number"] for r in races}
        if missing:
            raise ValueError(f"rounds absent from catalog: {sorted(missing)}")
        races = [r for r in races if r["round_number"] in args.rounds]
    races.sort(key=lambda row: (row["season"], row["round_number"]))
    if not races or any(r["season"] < 2018 for r in races):
        raise ValueError("select existing catalog events from 2018 onwards")
    driver_refs = {
        r["driver_ref"]: r["driver_id"] for r in repository.records("drivers")
    }
    historical_source = next(
        r["source"]
        for r in repository.reports()
        if r["source"].get("scope") == "complete_snapshot"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    reports = []
    with ExitStack() as stack:
        staging = (
            Path(
                stack.enter_context(
                    tempfile.TemporaryDirectory(
                        prefix=".fastf1-import-", dir=destination.parent
                    )
                )
            )
            / "history.sqlite"
        )
        cache = args.cache_dir or Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="fastf1-cache-"))
        )
        base = args.base
        for race in races:
            for kind in args.sessions:
                session = (loader or load_session)(
                    race["season"],
                    race["round_number"],
                    kind,
                    cache,
                    telemetry=not args.without_telemetry,
                )
                dataset = FastF1SessionAdapter(
                    session,
                    race,
                    driver_refs,
                    kind,
                    telemetry=not args.without_telemetry,
                    strict=args.strict,
                )
                dataset.manifest["historical_source"] = historical_source
                report = run_history_etl(
                    dataset,
                    SQLiteHistoryWriter(),
                    staging,
                    base=base,
                    overwrite=staging.exists(),
                )
                reports.append(report)
                base = staging
                print(
                    f"validada: {race['season']} etapa {race['round_number']} {kind}",
                    file=sys.stderr,
                )
        if args.overwrite:
            os.replace(staging, destination)
        else:
            os.link(staging, destination)
            staging.unlink()
    return reports


def main() -> int:
    """Print concise import counts; complete reports remain in SQLite.imports."""
    args = parse_args()
    try:
        reports = ingest(args)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {r["source"]["session_id"]: r["row_counts"] for r in reports},
            sort_keys=True,
        )
    )
    print(f"sqlite e relatorios internos: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
