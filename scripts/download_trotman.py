#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


DEFAULT_DESTINATION = ROOT / "data" / "raw" / "formula-1-race-data-v128.zip"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Baixa e verifica a versao 128 do dataset Formula 1 Race Data."
    )
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument(
        "--overwrite", action="store_true", help="substitui um arquivo existente"
    )
    return parser.parse_args()


def main() -> int:
    from f1_simulator.adapters.datasets.acquisition import (
        AcquisitionError,
        download_verified,
    )
    from f1_simulator.adapters.datasets.trotman_source import (
        TROTMAN_ARCHIVE_SHA256,
        TROTMAN_DOWNLOAD_URL,
    )

    args = parse_args()
    try:
        downloaded = download_verified(
            TROTMAN_DOWNLOAD_URL,
            args.destination,
            TROTMAN_ARCHIVE_SHA256,
            overwrite=args.overwrite,
        )
    except (AcquisitionError, OSError) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1
    action = "baixado e verificado" if downloaded else "ja estava verificado"
    print(f"{action}: {args.destination.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
