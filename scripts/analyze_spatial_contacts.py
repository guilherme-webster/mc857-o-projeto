"""Avalie contatos no motor 2D, offline e sem gravar resultados.

Exemplo: PYTHONPATH=src python scripts/analyze_spatial_contacts.py --preset smoke
Matriz: --circuits circuit:6,circuit:9 --seeds 1,2 --grids 10,20
--laps 3,10 --dts 0.1,0.2. A saída JSON vai para stdout.

Cenário controlado: seco, sem pneus/combustível/paradas/falhas mecânicas;
controle de prova padrão ativo. O ritmo varia com o atributo assumido do piloto.
Contagens SAT são pares por amostra, não incidentes físicos únicos. A análise
ignora carros retirados, terminados e nos boxes. Passagem persistente exige
inversão da ordem longitudinal absoluta mantida por N segundos; não confundir
com a manobra interna nem com ultrapassagem de retardatário. Frenagem anormal
é queda de velocidade entre amostras superior ao limiar configurado, não uma
medida de telemetria. O relógio mede execução e diagnóstico e não é determinístico.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import time
from pathlib import Path
from unittest.mock import patch

from f1_simulator.adapters.car_physics_json import read_car_physics
from f1_simulator.adapters.datasets.mock_track_geometry import MockTrackDatasetAdapter
from f1_simulator.domain import race_simulation_2d
from f1_simulator.domain.driver_attributes import ATTRIBUTE_FIELDS, DriverAttributes
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.track_space import (
    _projected_rectangle,
    _rectangles_overlap,
    integrate_field,
)
from f1_simulator.factories.track_geometry_factory import TrackGeometryFactory

ROOT = Path(__file__).resolve().parents[1]
PRESETS = {
    "smoke-v1": dict(circuits=["circuit:6"], seeds=[1], grids=[4], laps=[1], dts=[0.2]),
    "comparison-v1": dict(circuits=["circuit:6", "circuit:9", "circuit:14"],
                          seeds=[1, 2, 3], grids=[20], laps=[10], dts=[0.2]),
}


def geometry_for(circuit_id: str):
    """Carregue geometria reduzida e sua proveniência versionada localmente."""
    fixture = ROOT / "tests/fixtures/trotman_v128_tracks_2025"
    sources = ROOT / "data/sources"
    adapter = MockTrackDatasetAdapter(
        fixture / "track_points.csv", sources / "fastf1-tracks-2025.json",
        fixture / "pit_lane_points.csv", sources / "fastf1-pit-lanes-2025.json",
    )
    return TrackGeometryFactory.build(adapter.load_geometry(circuit_id))


def analyze_samples(samples, track, total_laps, persistence_s, braking_ms2):
    """Meça estados por passo; preserve pares distintos e contagens por amostra."""
    previous = {}
    stable = {}
    candidate = {}
    passes = []
    parallel = {}
    longest_parallel_s = 0.0
    longest_parallel_pair = None
    overlaps = 0
    overlap_pairs = set()
    braking = 0
    worst_braking = 0.0
    backwards = 0
    max_backwards = 0.0
    race_distance = total_laps * track.lap_length_m
    for sample in samples:
        active = {c.driver_id: c for c in sample.cars
                  if not c.retired and c.pit_state is None and c.distance_m < race_distance}
        for did, car in active.items():
            if did in previous:
                old_time, old_distance, old_speed = previous[did]
                dt = sample.time_s - old_time
                delta = car.distance_m - old_distance
                if delta < -1e-7:
                    backwards += 1
                    max_backwards = max(max_backwards, -delta)
                if dt > 0:
                    decel = (old_speed - car.speed_ms) / dt
                    worst_braking = max(worst_braking, decel)
                    braking += decel > braking_ms2
            previous[did] = (sample.time_s, car.distance_m, car.speed_ms)
        # Invalidar amostras de carros ausentes evita comparar através de boxes.
        previous = {did: state for did, state in previous.items() if did in active}
        poses = {did: _projected_rectangle(track, c, c.distance_m)
                 for did, c in active.items()}
        active_pairs = set()
        for a, b in itertools.combinations(sorted(active), 2):
            pair = (a, b)
            active_pairs.add(pair)
            ca, cb = active[a], active[b]
            if (abs(ca.distance_m-cb.distance_m) <= (ca.length_m+cb.length_m)/2
                    and abs(ca.lateral_m-cb.lateral_m) >= (ca.width_m+cb.width_m)/2):
                parallel.setdefault(pair, sample.time_s)
                duration = sample.time_s-parallel[pair]
                if duration > longest_parallel_s:
                    longest_parallel_s, longest_parallel_pair = duration, pair
            else:
                parallel.pop(pair, None)
            if _rectangles_overlap(ca, poses[a], cb, poses[b]):
                overlaps += 1
                overlap_pairs.add(pair)
            delta = ca.distance_m - cb.distance_m
            if abs(delta) < 1e-7:
                continue
            leader = a if delta > 0 else b
            if pair not in stable:
                stable[pair] = leader
            elif leader == stable[pair]:
                candidate.pop(pair, None)
            else:
                if pair not in candidate or candidate[pair][0] != leader:
                    candidate[pair] = (leader, sample.time_s)
                if sample.time_s - candidate[pair][1] + 1e-9 >= persistence_s:
                    passes.append({"ahead": leader, "behind": b if leader == a else a,
                                   "confirmed_at_s": round(sample.time_s, 6)})
                    stable[pair] = leader
                    del candidate[pair]
        stable = {p: leader for p, leader in stable.items() if p in active_pairs}
        candidate = {p: value for p, value in candidate.items() if p in active_pairs}
        parallel = {p: value for p, value in parallel.items() if p in active_pairs}
    unfinished = sorted(c.driver_id for c in samples[-1].cars
                        if not c.retired and c.distance_m < race_distance)
    return {
        "samples": len(samples),
        "simulated_time_s": round(samples[-1].time_s, 6),
        "unfinished_drivers": unfinished,
        "sat_overlap_pair_samples": overlaps,
        "sat_distinct_pairs": len(overlap_pairs),
        "sat_pairs": [list(p) for p in sorted(overlap_pairs)],
        "persistent_overtakes": passes,
        "persistent_overtake_count": len(passes),
        "longest_parallel_s": round(longest_parallel_s, 6),
        "longest_parallel_pair": list(longest_parallel_pair) if longest_parallel_pair else None,
        "abnormal_braking_samples": braking,
        "max_deceleration_ms2": round(worst_braking, 6),
        "backward_distance_samples": backwards,
        "max_backward_distance_m": round(max_backwards, 6),
    }


def run_case(circuit, seed, grid, laps, dt, persistence_s, braking_ms2):
    """Execute um cenário isolado e resuma a classificação e as amostras."""
    geometry = geometry_for(circuit)
    physics = read_car_physics(ROOT / "data/parameters/car-physics-v1.json")
    entrants = []
    for i in range(grid):
        did = f"driver:{i + 1:02d}"
        # Ordem invertida do ritmo cria oportunidades reproduzíveis de disputa.
        attrs = DriverAttributes(
            driver_id=did, archetype="balanced",
            sources={key: "generated" for key in ATTRIBUTE_FIELDS},
            pace_offset_pct=1.0 - 2.0 * i / max(1, grid - 1),
            consistency_factor=1.0, tyre_management_factor=1.0,
            aggression=1.0, composure=1.0,
        )
        entrants.append(dict(driver_id=did, name=did, grid_position=i + 1,
                             attributes=attrs, aggression=1.0))
    captured = {}

    def capture(cars, track, physics_by_id, **kwargs):
        # Limite de diagnostico, nao regra de corrida: um bloqueio nao deve
        # consumir dez milhoes de passos sem aparecer no relatorio.
        kwargs["max_steps"] = math.ceil(laps * 600 / dt)
        samples = integrate_field(cars, track, physics_by_id, **kwargs)
        captured["metrics"] = analyze_samples(samples, track, laps, persistence_s, braking_ms2)
        return samples

    started = time.perf_counter()
    with patch.object(race_simulation_2d, "integrate_field", side_effect=capture):
        result = race_simulation_2d.simulate_2d_race(
            entrants, geometry, total_laps=laps, rng=SeededRandomSource(seed),
            base_physics=physics, dt_s=dt,
        )
    elapsed = time.perf_counter() - started
    retired = sorted(row["driver_id"] for row in result["classification"]
                     if row["retirement_cause"] == "CONTACT")
    events = result.get("contact_events_2d", ())
    return dict(circuit=circuit, seed=seed, grid=grid, laps=laps, dt_s=dt,
                contact_events=len(events) if "contact_events_2d" in result else None,
                touches=sum(e["kind"] == "touch" for e in events),
                damaging_contacts=sum(e["kind"] == "damage" for e in events),
                max_closing_speed_ms=max((e["closing_speed_ms"] for e in events), default=0.0),
                contact_retirements=len(retired), contact_retired_drivers=retired,
                runtime_s=round(elapsed, 3), **captured["metrics"])


def main():
    """Interprete a matriz, valide entradas e escreva somente JSON em stdout."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preset", choices=PRESETS, default="smoke-v1")
    for option in ("circuits", "seeds", "grids", "laps", "dts"):
        parser.add_argument("--" + option, help="lista separada por vírgulas")
    parser.add_argument("--persistence-s", type=float, default=2.0)
    parser.add_argument("--braking-ms2", type=float, default=50.0)
    args = parser.parse_args()
    config = dict(PRESETS[args.preset])
    try:
        for name, convert in (("circuits", str), ("seeds", int), ("grids", int),
                              ("laps", int), ("dts", float)):
            value = getattr(args, name)
            if value is not None:
                config[name] = [convert(item.strip()) for item in value.split(",")]
        if (any(not c.startswith("circuit:") or not c[8:].isdigit() for c in config["circuits"])
                or any(n < 1 or n > 40 for n in config["grids"])
                or any(n < 1 for n in config["laps"])
                or any(not math.isfinite(n) or n <= 0 for n in config["dts"])
                or not math.isfinite(args.persistence_s) or args.persistence_s <= 0
                or not math.isfinite(args.braking_ms2) or args.braking_ms2 <= 0):
            raise ValueError("valores fora da faixa")
    except ValueError as error:
        parser.error(str(error))
    cases = [run_case(*row, args.persistence_s, args.braking_ms2) for row in
             itertools.product(config["circuits"], config["seeds"], config["grids"],
                               config["laps"], config["dts"])]
    inputs = [ROOT / "data/parameters/car-physics-v1.json",
              ROOT / "tests/fixtures/trotman_v128_tracks_2025/track_points.csv",
              ROOT / "tests/fixtures/trotman_v128_tracks_2025/pit_lane_points.csv",
              ROOT / "data/sources/fastf1-tracks-2025.json",
              ROOT / "data/sources/fastf1-pit-lanes-2025.json"]
    hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in inputs}
    print(json.dumps({"input_sha256": hashes, "schema_version": "spatial-contact-analysis-v1", "preset": args.preset,
                      "matrix": config, "persistence_s": args.persistence_s,
                      "braking_threshold_ms2": args.braking_ms2,
                      "scenario": "dry-no-tyre-fuel-pit-mechanical-v1",
                      "physics": "data/parameters/car-physics-v1.json",
                      "geometry": "tests/fixtures/trotman_v128_tracks_2025",
                      "cases": cases}, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
