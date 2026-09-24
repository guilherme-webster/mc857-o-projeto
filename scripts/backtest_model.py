#!/usr/bin/env python3
"""Valide o modelo contra corridas reais nao usadas na calibracao.

Executa, para cada corrida de validacao, tres cenarios sobre o mesmo grid:

``grid``      -- linha de base: chega na ordem em que largou;
``constant``  -- linha de base: o modelo antigo, ritmo constante por carro;
``model``     -- o modelo calibrado, com combustivel, pneu, trafego, paradas,
                 largada, abandono e ruido.

Um modelo so se justifica se vencer as duas linhas de base. Exemplo::

    python scripts/backtest_model.py \\
        --database data/curated/history.sqlite \\
        --parameters data/parameters/model-v1.json \\
        --seasons 2024 --seed 20260922

Como a corrida tem componente aleatorio, ``--repeats`` roda cada evento varias
vezes com sementes derivadas e reporta a media; um unico sorteio nao caracteriza
o comportamento do modelo.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest do modelo contra corridas historicas."
    )
    parser.add_argument(
        "--database", type=Path, default=ROOT / "data" / "curated" / "history.sqlite"
    )
    parser.add_argument(
        "--parameters",
        type=Path,
        default=ROOT / "data" / "parameters" / "model-v1.json",
    )
    parser.add_argument("--seasons", type=int, nargs="+", required=True)
    parser.add_argument("--seed", type=int, default=20260922)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--stops", type=int, default=2, help="paradas planejadas")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--reliability-factor",
        type=float,
        default=1.0,
        help=(
            "multiplica o risco de abandono. 0 desliga o abandono e isola "
            "o efeito das parcelas deterministicas do modelo"
        ),
    )
    parser.add_argument(
        "--no-disputes",
        action="store_true",
        help=(
            "desliga bloqueio, exclusao fisica e contato. Serve para medir "
            "quanto o modelo de disputa custa em precisao e quanto compra "
            "em realismo de movimentacao"
        ),
    )
    parser.add_argument(
        "--pace-source",
        choices=("weekend", "profile", "qualifying", "combined"),
        default="weekend",
        help=(
            "weekend: ritmo do proprio fim de semana (isola o modelo de "
            "corrida). profile: ritmo relativo de corridas anteriores, pelo "
            "metodo da issue #40. qualifying: melhor volta da classificacao "
            "convertida em ritmo de corrida -- medida antes da largada, "
            "portanto sem vazamento e especifica daquele fim de semana. "
            "combined: media geometrica das duas anteriores -- a "
            "classificacao da o nivel do fim de semana, o perfil da a forma "
            "de corrida que uma volta unica nao mede"
        ),
    )
    parser.add_argument(
        "--profile-races",
        type=int,
        default=12,
        help="quantas corridas anteriores alimentam o perfil",
    )
    parser.add_argument(
        "--json-out", type=Path, default=None, help="grava as metricas agregadas"
    )
    parser.add_argument(
        "--allow-calibrated-seasons",
        action="store_true",
        help="permite validar sobre a mesma era usada na calibracao",
    )
    return parser.parse_args()


def main() -> int:
    from f1_simulator.adapters.model_parameters_json import read_parameters
    from f1_simulator.adapters.persistence.sqlite_race_scenario import (
        list_races,
        load_observed_race,
    )
    from f1_simulator.application.backtest_model import (
        aggregate,
        evaluate,
        grid_baseline_classification,
    )
    from f1_simulator.domain.race_simulation import (
        Competitor,
        Entrant,
        simulate_detailed_race,
        simulate_race,
    )
    from f1_simulator.adapters.persistence.sqlite_trotman_profiles import (
        assess_trotman_races,
        races_before,
    )
    from f1_simulator.application.pace_profiles import (
        build_pace_profiles,
        reference_times_from_profiles,
    )
    from f1_simulator.domain.random_source import SeededRandomSource
    from f1_simulator.domain.strategy import PlannedStopStrategy

    args = parse_args()
    seasons = tuple(sorted(set(args.seasons)))

    try:
        parameters = read_parameters(args.parameters)
    except (FileNotFoundError, ValueError, KeyError) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1

    overlap = set(seasons) & set(parameters.provenance.seasons)
    if overlap and not args.allow_calibrated_seasons:
        print(
            f"erro: temporadas {sorted(overlap)} foram usadas para calibrar "
            f"{parameters.version}. Validar nelas mede memorizacao, nao "
            "generalizacao. Use --allow-calibrated-seasons para forcar.",
            file=sys.stderr,
        )
        return 2

    race_ids = list_races(args.database, seasons)
    if args.limit:
        race_ids = race_ids[: args.limit]
    if not race_ids:
        print(f"erro: nenhuma corrida em {seasons}", file=sys.stderr)
        return 1

    from f1_simulator.application.pace_profiles import TROTMAN_PROFILE_CONFIG

    compounds = ("MEDIUM", "HARD", "MEDIUM", "HARD")
    collected: dict[str, list] = {"grid": [], "constant": [], "model": []}
    skipped: list[str] = []
    profiled_total = fallback_total = 0

    for race_id in race_ids:
        try:
            observed = load_observed_race(args.database, race_id)
        except ValueError as error:
            skipped.append(f"{race_id}: {error}")
            continue

        track = parameters.track(observed.circuit_id)

        # Ritmo de referencia de cada participante. Em "profile", ele vem de
        # corridas ANTERIORES: a corrida validada nao contribui para estimar o
        # ritmo de seus proprios pilotos.
        references = {
            e.driver_id: e.reference_lap_time_ms for e in observed.entries
        }
        if args.pace_source == "combined":
            # Media geometrica das duas fontes. Cada uma mede algo que a outra
            # nao ve: a classificacao mede a velocidade daquele fim de semana em
            # uma volta unica, o perfil mede a forma sustentada em corrida.
            # A media geometrica e a natural para grandezas multiplicativas --
            # um piloto 2% mais lento em uma e 0% na outra fica 1% mais lento.
            prior = races_before(
                args.database, race_id, max_races=args.profile_races
            )
            assessments, drivers = assess_trotman_races(
                args.database, prior, TROTMAN_PROFILE_CONFIG
            )
            profiles, _ = build_pace_profiles(assessments, drivers)
            profiled_refs, coverage = reference_times_from_profiles(
                references, profiles
            )
            blended = {}
            for entry in observed.entries:
                profile_ref = profiled_refs[entry.driver_id]
                if entry.qualifying_ms:
                    quali_ref = (
                        entry.qualifying_ms * parameters.qualifying_to_race_ratio
                    )
                    blended[entry.driver_id] = (quali_ref * profile_ref) ** 0.5
                    profiled_total += 1
                else:
                    blended[entry.driver_id] = profile_ref
                    fallback_total += 1
            references = blended
        elif args.pace_source == "qualifying":
            # A classificacao mede a velocidade daquele fim de semana antes de
            # a corrida comecar. Quem nao tem volta registrada mantem o ritmo
            # de fim de semana, e isso e contado.
            converted = {}
            for entry in observed.entries:
                if entry.qualifying_ms:
                    converted[entry.driver_id] = (
                        entry.qualifying_ms * parameters.qualifying_to_race_ratio
                    )
                    profiled_total += 1
                else:
                    converted[entry.driver_id] = entry.reference_lap_time_ms
                    fallback_total += 1
            references = converted
        elif args.pace_source == "profile":
            prior = races_before(
                args.database, race_id, max_races=args.profile_races
            )
            assessments, drivers = assess_trotman_races(
                args.database, prior, TROTMAN_PROFILE_CONFIG
            )
            profiles, _ = build_pace_profiles(assessments, drivers)
            references, coverage = reference_times_from_profiles(
                references, profiles
            )
            profiled_total += coverage.profiled
            fallback_total += coverage.fell_back

        collected["grid"].append(
            evaluate(
                label="grid",
                observed=observed,
                simulated_classification=grid_baseline_classification(observed),
            )
        )

        constant = simulate_race(
            [
                Competitor(e.driver_id, e.name, references[e.driver_id])
                for e in observed.entries
            ],
            observed.total_laps,
        )
        collected["constant"].append(
            evaluate(
                label="constant",
                observed=observed,
                simulated_classification=constant["classification"],
                simulated_history=constant["history"],
            )
        )

        for repeat in range(args.repeats):
            # Uma unica fonte aleatoria por execucao: ela sorteia primeiro o
            # escalonamento das paradas (uma decisao de cenario, tomada antes da
            # largada) e depois conduz a corrida. Manter a ordem fixa e o que
            # torna a semente reproduzivel.
            rng = SeededRandomSource(args.seed + repeat)
            entrants = [
                Entrant(
                    driver_id=e.driver_id,
                    name=e.name,
                    reference_lap_time_ms=references[e.driver_id],
                    grid_position=e.grid_position,
                    strategy=PlannedStopStrategy(
                        args.stops,
                        compounds,
                        offset_laps=round(
                            rng.standard_normal()
                            * parameters.pit_window_spread_laps
                        ),
                    ),
                    team_id=e.team_id,
                    starting_compound="MEDIUM",
                    # Risco base da era x fator da equipe: com um risco unico
                    # o motor acerta quantos carros quebram mas nunca quais.
                    reliability_factor=args.reliability_factor
                    * parameters.reliability_factor(e.team_id),
                )
                for e in sorted(observed.entries, key=lambda x: x.driver_id)
            ]
            result = simulate_detailed_race(
                entrants,
                total_laps=observed.total_laps,
                parameters=parameters,
                track=track,
                rng=rng,
                resolve_position_disputes=not args.no_disputes,
            )
            collected["model"].append(
                evaluate(
                    label="model",
                    observed=observed,
                    simulated_classification=result["classification"],
                    simulated_history=result["history"],
                )
            )

    print(f"parametros      : {parameters.version}")
    print(f"calibrado em    : {parameters.provenance.seasons}")
    print(f"validando em    : {seasons}  ({len(race_ids)} corridas)")
    print(f"repeticoes      : {args.repeats} sementes por corrida")
    print(f"fator de risco  : {args.reliability_factor}")
    print(f"disputas        : {'desligadas' if args.no_disputes else 'ligadas'}")
    print(f"fonte do ritmo  : {args.pace_source}", end="")
    if args.pace_source != "weekend":
        total = profiled_total + fallback_total
        share = 100 * profiled_total / total if total else 0
        print(f"  ({profiled_total} de {total} participantes, {share:.0f}%; "
              f"o resto manteve o ritmo do fim de semana)")
    else:
        print()
    if skipped:
        print(f"ignoradas       : {len(skipped)}")
    print()

    header = (
        f"{'cenario':10s} {'pos MAE':>8s} {'pos RMSE':>9s} {'spearman':>9s} "
        f"{'vencedor':>9s} {'podio/3':>8s} {'DNF sim':>8s} {'DNF real':>9s} "
        f"{'par sim':>8s} {'par real':>9s} {'troca/v':>8s} {'real':>6s}"
    )
    print(header)
    print("-" * len(header))

    summary = {}
    for label in ("grid", "constant", "model"):
        metrics = aggregate(label, collected[label])
        summary[label] = asdict(metrics)
        print(
            f"{label:10s} {metrics.position_mae:8.3f} {metrics.position_rmse:9.3f} "
            f"{metrics.spearman:9.4f} {metrics.winner_accuracy:8.1%} "
            f"{metrics.mean_podium_overlap:8.2f} "
            f"{metrics.mean_retirements_simulated:8.2f} "
            f"{metrics.mean_retirements_observed:9.2f} "
            f"{metrics.mean_stops_simulated:8.2f} "
            f"{metrics.mean_stops_observed:9.2f} "
            f"{metrics.changes_per_lap_simulated:8.2f} "
            f"{metrics.changes_per_lap_observed:6.2f}"
        )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(
                {
                    "parameters_version": parameters.version,
                    "calibration_seasons": list(parameters.provenance.seasons),
                    "validation_seasons": list(seasons),
                    "races": len(race_ids),
                    "repeats": args.repeats,
                    "seed": args.seed,
                    "results": summary,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nmetricas gravadas em {args.json_out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
