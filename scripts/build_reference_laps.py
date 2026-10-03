"""Gere ``data/parameters/reference-laps-v1.json`` a partir do historico.

Uso, a partir da raiz do repositorio::

    python scripts/build_reference_laps.py \\
        --database data/curated/history.sqlite \\
        --seasons 2022 2023 2024

Os circuitos sao os do catalogo de geometria (``data/sources/
fastf1-tracks-2025.json``), que e o conjunto que o backend oferece. O banco e
aberto apenas para leitura. Ver ``application/reference_laps.py`` para o metodo.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from f1_simulator.adapters.persistence.sqlite_history import (  # noqa: E402
    SQLiteHistoryRepository,
)
from f1_simulator.adapters.reference_laps_json import (  # noqa: E402
    write_reference_laps,
)
from f1_simulator.application.reference_laps import (  # noqa: E402
    build_reference_laps,
)

DEFAULT_MANIFEST = ROOT / "data" / "sources" / "fastf1-tracks-2025.json"
DEFAULT_OUTPUT = ROOT / "data" / "parameters" / "reference-laps-v1.json"


def catalog_circuit_ids(manifest: Path) -> list[str]:
    """IDs canonicos dos circuitos do catalogo de geometria."""

    events = json.loads(manifest.read_text(encoding="utf-8"))["source"]["events"]
    return [f"circuit:{event['circuit_id']}" for event in events]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--seasons", type=int, nargs="+", required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    circuit_ids = catalog_circuit_ids(args.manifest)
    laps = build_reference_laps(
        SQLiteHistoryRepository(args.database),
        circuit_ids=circuit_ids,
        seasons=args.seasons,
    )
    missing = sorted(set(circuit_ids) - {lap.circuit_id for lap in laps})
    write_reference_laps(
        laps,
        args.output,
        seasons=args.seasons,
        source="jtrotman/formula-1-race-data v128 (race_results.fastest_lap_time_ms)",
    )
    for lap in laps:
        print(
            f"{lap.circuit_id:12s} {lap.reference_lap_time_ms / 1000:7.2f} s "
            f"({lap.races} corridas, {list(lap.seasons)})"
        )
    if missing:
        print(f"sem dados no intervalo: {missing}", file=sys.stderr)
    print(f"gravado em {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
