#!/usr/bin/env python3
"""Write a lightweight race catalog from the Trotman source.

This is the sanctioned reader of the raw dataset for cataloging purposes. It
extracts only ``{race_id, name, year}`` per race and writes them to a curated
JSON index, so the backend can list every race without ever touching the raw
archive itself. The heavy per-race ingestion stays in ``ingest_trotman.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


DEFAULT_SOURCE = ROOT / "data" / "raw" / "formula-1-race-data-v128.zip"
DEFAULT_OUTPUT = ROOT / "data" / "curated" / "races-index.json"


def parse_args() -> argparse.Namespace:
    """Parse the source archive and output catalog paths."""

    parser = argparse.ArgumentParser(
        description="Gera o catalogo de corridas (race_id, name, year) da Base Trotman."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _write_catalog(races: list[dict[str, object]], destination: Path) -> None:
    """Publish the catalog atomically through a same-directory rename."""

    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            json.dump(races, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    """Read the source with the Trotman adapter and write the race catalog."""

    from f1_simulator.adapters.datasets.trotman import (
        TrotmanDatasetAdapter,
        TrotmanDatasetError,
    )

    args = parse_args()
    try:
        adapter = TrotmanDatasetAdapter(args.source)
        races = adapter.list_races()
        _write_catalog(races, args.output)
    except (TrotmanDatasetError, OSError) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1
    print(f"corridas catalogadas: {len(races)}")
    print(f"indice: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
