"""Estime a aderencia e o downforce do carro de referencia (ADR 0014).

Uso, a partir da raiz do repositorio::

    python scripts/calibrate_car_physics.py

Le a geometria versionada das pistas (a mesma que o backend monta em
``/data/geometry``) e as voltas de referencia historicas, ajusta ``grip_mu`` e
``downforce_cla_m2`` e grava ``data/parameters/car-physics-v1.json``. Depois de
gravar, atualize ``DEFAULT_CAR_PHYSICS`` em ``domain/speed_dynamics.py``: um
teste falha enquanto os dois divergirem. Ver
``application/calibrate_car_physics.py`` para o metodo.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from f1_simulator.adapters.car_physics_json import write_car_physics  # noqa: E402
from f1_simulator.adapters.datasets.mock_track_geometry import (  # noqa: E402
    MockTrackDatasetAdapter,
    MockTrackDatasetError,
)
from f1_simulator.adapters.reference_laps_json import (  # noqa: E402
    read_reference_laps,
)
from f1_simulator.application.calibrate_car_physics import (  # noqa: E402
    fit_car_physics,
    ratio_summary,
)
from f1_simulator.factories.track_geometry_factory import (  # noqa: E402
    TrackGeometryFactory,
    TrackGeometryValidationError,
)

GEOMETRY = ROOT / "tests" / "fixtures" / "trotman_v128_tracks_2025"
SOURCES = ROOT / "data" / "sources"
DEFAULT_REFERENCE = ROOT / "data" / "parameters" / "reference-laps-v1.json"
DEFAULT_OUTPUT = ROOT / "data" / "parameters" / "car-physics-v1.json"

RATIONALE = (
    "grip_mu e downforce_cla_m2 escolhidos por grade para que o piloto neutro "
    "reproduza a volta de referencia historica de cada circuito (raiz do erro "
    "quadratico medio de log(fisica/referencia)). O modelo anterior do ADR 0010 "
    "errava 0,169 nessa mesma medida (Monaco 37% rapido). Os campos 'assumed' "
    "sao ordem de grandeza de um F1 recente, nao medidos. Residuos maiores: "
    "curvas inclinadas (Zandvoort), altitude (Mexico) e chicanes curtas que a "
    "polilinha de 240 pontos nao resolve (Monza)."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--geometry", type=Path, default=GEOMETRY)
    parser.add_argument("--sources", type=Path, default=SOURCES)
    parser.add_argument("--reference-laps", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    adapter = MockTrackDatasetAdapter(
        args.geometry / "track_points.csv",
        args.sources / "fastf1-tracks-2025.json",
        args.geometry / "pit_lane_points.csv",
        args.sources / "fastf1-pit-lanes-2025.json",
    )
    references = read_reference_laps(args.reference_laps)
    tracks = {}
    for circuit_id, reference in references.items():
        try:
            geometry = TrackGeometryFactory.build(adapter.load_geometry(circuit_id))
        except (MockTrackDatasetError, TrackGeometryValidationError) as error:
            # Circuito com volta de referencia mas sem geometria: fica fora.
            print(f"sem geometria para {circuit_id}: {error}", file=sys.stderr)
            continue
        tracks[circuit_id] = (geometry, reference.reference_lap_time_ms)

    fit = fit_car_physics(tracks)
    write_car_physics(
        args.output,
        fit,
        parameter_version="car-physics-v1",
        rationale=RATIONALE,
        sources={
            "geometry": "FastF1 3.8.3, 24 pistas de 2025, 240 pontos "
            "(data/sources/fastf1-tracks-2025.json)",
            "reference_laps": f"{args.reference_laps.name} "
            "(historical-median-fastest-laps-v1)",
        },
    )
    summary = ratio_summary(fit)
    print(
        f"{len(tracks)} circuitos: grip_mu={fit.physics.grip_mu} "
        f"downforce_cla_m2={fit.physics.downforce_cla_m2} | {summary}"
    )
    print(f"gravado em {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
