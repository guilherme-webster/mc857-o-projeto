#!/usr/bin/env python3
"""Rode uma corrida simulada e explique o resultado, sem frontend nem servidor.

Usa apenas a biblioteca padrao do Python: nenhuma instalacao, nenhum ambiente
virtual, nenhum container. Le o historico canonico e os parametros calibrados,
executa o motor e imprime um relatorio legivel. Com ``--html`` grava tambem um
visualizador autocontido que abre no navegador.

Exemplos::

    # lista as corridas disponiveis de uma temporada
    python scripts/race_report.py --season 2024

    # relatorio completo de uma corrida
    python scripts/race_report.py --race-id 1141

    # visualizador no navegador, com a geometria real do circuito
    python scripts/race_report.py --race-id 1141 --html data/reports/corrida.html

Este script e um consumidor do nucleo, nao parte dele: ele nao define regra
alguma de corrida. Tudo o que imprime vem de ``simulate_detailed_race`` e da
comparacao com o resultado historico.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# O console do Windows usa cp1252 por padrao e quebraria nomes como
# "Autodromo Jose Carlos Pace". Forcar UTF-8 na saida evita mojibake sem exigir
# que o usuario configure o terminal.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_COMPOUNDS = ("MEDIUM", "HARD", "MEDIUM", "HARD")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Relatorio de uma corrida simulada, sem frontend."
    )
    parser.add_argument(
        "--database", type=Path, default=ROOT / "data" / "curated" / "history.sqlite"
    )
    parser.add_argument(
        "--parameters",
        type=Path,
        default=ROOT / "data" / "parameters" / "model-v1.json",
    )
    parser.add_argument("--race-id", help="id da corrida no historico canonico")
    parser.add_argument(
        "--season", type=int, help="lista as corridas desta temporada e encerra"
    )
    parser.add_argument("--seed", type=int, default=20260922)
    parser.add_argument("--stops", type=int, default=2)
    parser.add_argument(
        "--driver",
        help="parte do nome do piloto cuja decomposicao de tempo sera detalhada",
    )
    parser.add_argument(
        "--geometry",
        type=Path,
        default=ROOT
        / "tests"
        / "fixtures"
        / "trotman_v128_tracks_2025"
        / "track_points.csv",
        help="CSV de pontos de pista usado pelo visualizador HTML",
    )
    parser.add_argument("--html", type=Path, help="grava o visualizador autocontido")
    return parser.parse_args()


def list_season(database: Path, season: int) -> int:
    """Imprima as corridas de uma temporada para o usuario escolher um id."""

    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT race_id, round_number, name, race_date, circuit_id "
            "FROM races WHERE season = ? ORDER BY round_number",
            (season,),
        ).fetchall()
    finally:
        connection.close()
    if not rows:
        print(f"nenhuma corrida encontrada em {season}", file=sys.stderr)
        return 1
    print(f"Corridas de {season}:\n")
    print(f"  {'race_id':>8s}  {'rd':>3s}  {'data':10s}  corrida")
    for race_id, rnd, name, date, _circuit in rows:
        print(f"  {race_id:>8s}  {rnd:>3}  {date:10s}  {name}")
    print(f"\nUse: python scripts/race_report.py --race-id {rows[0][0]}")
    return 0


def load_geometry(path: Path, circuit_id: str) -> dict | None:
    """Leia a polilinha de um circuito do CSV de geometria da issue #51.

    ``circuit_id`` canonico tem a forma ``circuit:18``; o CSV guarda apenas o
    numero externo. A conversao acontece aqui, na borda, e nao no dominio.
    """

    if not path.exists():
        return None
    external = circuit_id.split(":")[-1]
    points: list[tuple[int, float, float, float]] = []
    import csv

    with path.open(encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["circuitId"] == external:
                points.append(
                    (
                        int(row["sequence"]),
                        float(row["x"]),
                        float(row["y"]),
                        float(row["cumulativeDistanceMeters"]),
                    )
                )
    if not points:
        return None
    points.sort()
    return {
        "x": [p[1] for p in points],
        "y": [p[2] for p in points],
        "cumulative_m": [p[3] for p in points],
        "lap_length_m": points[-1][3],
    }


def _bar(value: float, peak: float, width: int = 28) -> str:
    """Barra ASCII simples; o terminal do Windows nao garante blocos Unicode."""

    if peak <= 0:
        return ""
    filled = int(round(width * min(1.0, value / peak)))
    return "#" * filled


def main() -> int:
    from f1_simulator.adapters.model_parameters_json import read_parameters
    from f1_simulator.adapters.persistence.sqlite_race_scenario import (
        load_observed_race,
    )
    from f1_simulator.domain.race_simulation import (
        Entrant,
        simulate_detailed_race,
    )
    from f1_simulator.domain.random_source import SeededRandomSource
    from f1_simulator.domain.strategy import PlannedStopStrategy

    args = parse_args()

    if not args.database.exists():
        print(
            f"erro: historico nao encontrado em {args.database}.\n"
            "Rode antes:\n"
            "  python scripts/download_trotman.py\n"
            "  python scripts/ingest_trotman.py --all-tables "
            "--output data/curated/history.sqlite",
            file=sys.stderr,
        )
        return 1

    if args.season:
        return list_season(args.database, args.season)
    if not args.race_id:
        print(
            "erro: informe --race-id, ou --season para listar as corridas.",
            file=sys.stderr,
        )
        return 1

    # O historico usa identificadores canonicos ("race:1141"), mas o numero
    # cru e o que aparece no Kaggle e nos comandos de ETL. Aceitar as duas
    # formas evita que o usuario precise saber dessa convencao interna.
    race_id = args.race_id
    if not race_id.startswith("race:"):
        race_id = f"race:{race_id}"

    try:
        parameters = read_parameters(args.parameters)
        observed = load_observed_race(args.database, race_id)
    except (FileNotFoundError, ValueError, KeyError) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1

    track = parameters.track(observed.circuit_id)

    # Mesma ordem de consumo da fonte aleatoria usada pelo backend: primeiro o
    # escalonamento das paradas, depois a corrida. Isso mantem a semente
    # reproduzivel entre o relatorio e a API.
    rng = SeededRandomSource(args.seed)
    entrants = [
        Entrant(
            driver_id=entry.driver_id,
            name=entry.name,
            reference_lap_time_ms=entry.reference_lap_time_ms,
            grid_position=entry.grid_position,
            strategy=PlannedStopStrategy(
                args.stops,
                DEFAULT_COMPOUNDS,
                offset_laps=round(
                    rng.standard_normal() * parameters.pit_window_spread_laps
                ),
            ),
            team_id=entry.team_id,
            starting_compound="MEDIUM",
            reliability_factor=parameters.reliability_factor(entry.team_id),
        )
        for entry in sorted(observed.entries, key=lambda e: e.driver_id)
    ]

    result = simulate_detailed_race(
        entrants,
        total_laps=observed.total_laps,
        parameters=parameters,
        track=track,
        rng=rng,
        collect_breakdowns=True,
    )

    _print_report(observed, result, parameters, track, args)

    if args.html:
        geometry = load_geometry(args.geometry, observed.circuit_id)
        _write_html(args.html, observed, result, parameters, track, geometry, args)
        print(f"\nVisualizador gravado em {args.html.resolve()}")
        print("Abra o arquivo no navegador (duplo clique). Nao precisa de servidor.")
    return 0


def _print_report(observed, result, parameters, track, args) -> None:
    grid = {e.driver_id: e.grid_position for e in observed.entries}
    real = {e.driver_id: e for e in observed.entries}
    final = result["classification"]
    leader_ms = final[0]["total_time_ms"]

    print("=" * 78)
    print(f" {observed.name} ({observed.season})")
    print("=" * 78)
    print(f" circuito    : {track.name}  [{track.origin}]")
    print(f" voltas      : {observed.total_laps}")
    print(f" parametros  : {parameters.version}")
    print(f"               calibrados em {parameters.provenance.seasons}, "
          f"{parameters.provenance.clean_laps:,} voltas limpas")
    print(f" semente     : {args.seed}   (mesma semente = mesma corrida)")
    print(f" estrategia  : {args.stops} paradas planejadas, escalonadas com "
          f"desvio de {parameters.pit_window_spread_laps:.1f} voltas")
    print(f" perda boxes : {track.pit_loss_ms / 1000:.2f} s por parada")

    print("\n" + "-" * 78)
    print(" CLASSIFICACAO SIMULADA  (comparada com o resultado real)")
    print("-" * 78)
    print(f" {'P':>2} {'piloto':22s} {'grid':>4} {'intervalo':>11} {'par':>3} "
          f"{'pneu':>5} {'estado':>8} {'real':>5} {'erro':>5}")
    errors = []
    for car in final:
        entry = real.get(car["driver_id"])
        # Um carro que abandonou acumulou MENOS tempo que o lider, porque parou
        # antes. Mostrar esse intervalo como numero negativo sugeriria que ele
        # esta na frente; o que importa dele e em que volta saiu.
        if car["status"] == "RETIRED":
            gap_text = f"DNF L{car['laps_completed']}"
        elif car["position"] == 1:
            gap_text = "lider"
        else:
            gap_text = f"+{(car['total_time_ms'] - leader_ms) / 1000:8.2f}s"
        real_pos = entry.finish_position if entry else None
        error = abs(car["position"] - real_pos) if real_pos else None
        if error is not None:
            errors.append(error)
        print(
            f" {car['position']:>2} {car['name'][:22]:22s} "
            f"{grid.get(car['driver_id'], 0):>4} {gap_text:>11} "
            f"{car['stops_made']:>3} "
            f"{car['compound'][0] + str(car['tyre_age_laps']):>5} "
            f"{car['status'][:8]:>8} "
            f"{(real_pos if real_pos else '-'):>5} "
            f"{(error if error is not None else '-'):>5}"
        )
    if errors:
        print(f"\n erro medio de posicao: {statistics.fmean(errors):.2f} posicoes")
        print(" (a coluna 'real' e a posicao oficial; 'erro' e a diferenca)")

    # ---- evolucao da corrida -------------------------------------------------
    print("\n" + "-" * 78)
    print(" EVOLUCAO DAS POSICOES")
    print("-" * 78)
    checkpoints = sorted(
        {1, *[round(observed.total_laps * f / 5) for f in range(1, 6)]}
    )
    checkpoints = [c for c in checkpoints if 1 <= c <= observed.total_laps]
    by_lap = {h["lap"]: {c["driver_id"]: c["position"] for c in h["cars"]}
              for h in result["history"]}
    print(f" {'piloto':22s} " + " ".join(f"L{c:<3}" for c in checkpoints))
    for car in final[:12]:
        trace = " ".join(
            f"{by_lap[c].get(car['driver_id'], 0):<4}" for c in checkpoints
        )
        print(f" {car['name'][:22]:22s} {trace}")

    changes = 0
    previous = None
    for entry in result["history"]:
        order = [c["driver_id"] for c in entry["cars"]]
        if previous is not None and order != previous:
            changes += 1
        previous = order
    print(f"\n voltas em que a ordem mudou: {changes} de {observed.total_laps}")
    print(" (o modelo antigo, de ritmo constante, produzia sempre 0)")

    # ---- paradas -------------------------------------------------------------
    print("\n" + "-" * 78)
    print(" PARADAS NOS BOXES")
    print("-" * 78)
    pit_laps: dict[str, list[int]] = {}
    previous_stops: dict[str, int] = {}
    for entry in result["history"]:
        for car in entry["cars"]:
            was = previous_stops.get(car["driver_id"], 0)
            if car["stops_made"] > was:
                pit_laps.setdefault(car["driver_id"], []).append(entry["lap"])
            previous_stops[car["driver_id"]] = car["stops_made"]
    for car in final[:12]:
        simulated = pit_laps.get(car["driver_id"], [])
        entry = real.get(car["driver_id"])
        real_count = entry.stops_made if entry else "-"
        print(
            f" {car['name'][:22]:22s} voltas {str(simulated):18s} "
            f"| real: {real_count} paradas"
        )
    all_sim = [len(v) for v in pit_laps.values()]
    print(
        f"\n media simulada {statistics.fmean(all_sim) if all_sim else 0:.2f} "
        f"paradas  |  media real "
        f"{statistics.fmean([e.stops_made for e in observed.entries]):.2f}"
    )

    # ---- decomposicao --------------------------------------------------------
    target = final[0]
    if args.driver:
        match = [c for c in final if args.driver.lower() in c["name"].lower()]
        if match:
            target = match[0]
        else:
            print(f"\n aviso: nenhum piloto contem {args.driver!r}; usando o lider")
    rows = [b for b in result["breakdowns"] if b["driver_id"] == target["driver_id"]]

    print("\n" + "-" * 78)
    print(f" DE ONDE VEM O TEMPO -- {target['name']}")
    print("-" * 78)
    print(" Cada volta e a referencia (volta limpa, pneu novo, tanque leve)")
    print(" mais penalidades. Todas as parcelas sao somadas; nada e escondido.\n")
    print(f" {'volta':>5} {'referencia':>11} {'comb':>7} {'pneu':>7} {'traf':>6} "
          f"{'boxes':>8} {'ruido':>7} {'=  total':>11}")
    sample = [1, 2, 5]
    sample += [observed.total_laps // 3, observed.total_laps // 2]
    sample += [2 * observed.total_laps // 3, observed.total_laps - 1,
               observed.total_laps]
    for lap in sorted(set(x for x in sample if 1 <= x <= observed.total_laps)):
        row = next((r for r in rows if r["lap"] == lap), None)
        if row is None:
            continue
        mark = "  <- parada" if row["pit_ms"] > 0 else ""
        print(
            f" {row['lap']:>5} {row['reference_ms'] / 1000:>10.3f}s "
            f"{row['fuel_ms'] / 1000:>+6.3f} {row['tyre_ms'] / 1000:>+6.3f} "
            f"{row['traffic_ms'] / 1000:>+5.3f} {row['pit_ms'] / 1000:>+7.3f} "
            f"{row['noise_ms'] / 1000:>+6.3f} = {row['total_ms'] / 1000:>8.3f}s{mark}"
        )
    totals = {
        "combustivel": sum(r["fuel_ms"] for r in rows),
        "pneu": sum(r["tyre_ms"] for r in rows),
        "trafego": sum(r["traffic_ms"] for r in rows),
        "boxes": sum(r["pit_ms"] for r in rows),
        "ruido": sum(abs(r["noise_ms"]) for r in rows),
    }
    peak = max(totals.values()) or 1
    print("\n Peso de cada efeito na corrida inteira:")
    for name, value in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"   {name:12s} {value / 1000:>8.1f}s  {_bar(value, peak)}")
    print("\n (ruido usa o valor absoluto: ele soma e subtrai ao longo da prova)")


def _write_html(path, observed, result, parameters, track, geometry, args) -> None:
    """Grave um visualizador autocontido, com os dados embutidos.

    Os dados vao embutidos no proprio arquivo de proposito: navegadores bloqueiam
    ``fetch`` de ``file://`` por CORS, entao um HTML que buscasse um JSON ao lado
    exigiria subir um servidor. Assim o arquivo abre com duplo clique.
    """

    real = {e.driver_id: e for e in observed.entries}
    final = {c["driver_id"]: c for c in result["classification"]}

    # Formato colunar por piloto: uma serie por grandeza, em vez de repetir
    # nome e identificador em cada uma das ~1.200 entradas de volta. O arquivo
    # embutido fica varias vezes menor sem perder nada.
    drivers = []
    for driver_id, car in sorted(final.items(), key=lambda kv: kv[1]["position"]):
        completed = car["laps_completed"]
        series = {"t": [], "pos": [], "stops": [], "comp": [], "age": []}
        for entry in result["history"][:completed]:
            state = next(c for c in entry["cars"] if c["driver_id"] == driver_id)
            series["t"].append(round(state["total_time_ms"]))
            series["pos"].append(state["position"])
            series["stops"].append(state["stops_made"])
            series["comp"].append(state["compound"][0])
            series["age"].append(state["tyre_age_laps"])
        entry_real = real.get(driver_id)
        family = car["name"].split()[-1] if car["name"] else driver_id
        drivers.append(
            {
                "id": driver_id,
                "name": car["name"],
                "tag": family[:3].upper(),
                "grid": entry_real.grid_position if entry_real else 0,
                "retired": car["status"] == "RETIRED",
                "retired_lap": completed if car["status"] == "RETIRED" else 0,
                "real_pos": entry_real.finish_position if entry_real else None,
                "real_stops": entry_real.stops_made if entry_real else None,
                **series,
            }
        )

    payload = {
        "race": {
            "race_id": observed.race_id.split(":")[-1],
            "name": observed.name,
            "season": observed.season,
            "circuit": track.name,
            "circuit_origin": track.origin,
            "total_laps": observed.total_laps,
            "seed": args.seed,
            "stops": args.stops,
            "parameters_version": parameters.version,
            "calibration_seasons": list(parameters.provenance.seasons),
            "pit_loss_s": round(track.pit_loss_ms / 1000, 2),
        },
        "geometry": geometry,
        "drivers": drivers,
    }

    body = (ROOT / "tools" / "race_viewer_template.html").read_text(encoding="utf-8")
    body = body.replace(
        "/*__RACE_DATA__*/null",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )
    # O template e escrito sem esqueleto para poder ser publicado tal e qual;
    # o arquivo local precisa do involucro completo para abrir via file://.
    page = (
        "<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'viewport-fit=cover">\n'
        "</head>\n<body>\n" + body + "\n</body>\n</html>\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
