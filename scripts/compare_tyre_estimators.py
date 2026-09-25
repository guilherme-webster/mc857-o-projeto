#!/usr/bin/env python3
"""Publish SC/VSC sensitivity and event-held-out tyre trend comparison."""

import argparse
import csv
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def publish(result: dict, root: Path, *, plots: bool = True) -> Path:
    """Publish audited data and charts atomically without touching previous studies."""
    root = root.resolve()
    if root.is_relative_to(ROOT / "data/raw"):
        raise ValueError("reports cannot be written in data/raw")
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".estimators-", dir=root) as temporary:
        directory = Path(temporary)
        (directory / "analysis.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        for name, rows in [
            ("event-errors", result["event_errors"]),
            ("influence", result["diagnostics"]),
            ("predictions", result["test_predictions"]),
        ]:
            with (directory / f"{name}.csv").open(
                "w", newline="", encoding="utf-8"
            ) as stream:
                if rows:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(
                        {
                            k: json.dumps(v) if isinstance(v, (dict, list)) else v
                            for k, v in r.items()
                        }
                        for r in rows
                    )
        if plots:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 2, figsize=(13, 5))
            ss = result["summaries"]
            x = [s["window"] for s in ss]
            axes[0].plot(x, [s["eligible_laps"] for s in ss], marker="o")
            for s in ss:
                axes[0].annotate(
                    f"{s['eligible_laps']} voltas\n{s['fitted_stints']} ajustes",
                    (s["window"], s["eligible_laps"]),
                    xytext=(0, 8),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8,
                )
            axes[0].margins(y=0.25)
            axes[0].set(
                xlabel="Janela SC/VSC (voltas)",
                ylabel="Voltas aprovadas",
                title="Retomadas Aborted→Started: janela 2 fixa",
            )
            for c in ("SOFT", "MEDIUM", "HARD"):
                axes[1].plot(
                    x,
                    [
                        next(
                            d["median_slope"] for d in s["slopes"] if d["compound"] == c
                        )
                        for s in ss
                    ],
                    marker="o",
                    label=c,
                )
            axes[1].set(
                xlabel="Janela SC/VSC (voltas)",
                ylabel="Mediana dos slopes OLS (ms/volta)",
                title="Sensibilidade de tendência líquida",
            )
            axes[1].legend()
            fig.tight_layout()
            fig.savefig(directory / "sc-vsc-cobertura.png", dpi=150)
            plt.close(fig)
            fig, ax = plt.subplots(figsize=(8, 6))
            for c in ("SOFT", "MEDIUM", "HARD"):
                rows = [
                    r
                    for r in result["diagnostics"]
                    if r["compound"] == c and r["influence"]
                ]
                ax.scatter(
                    [r["influence"]["ols"] for r in rows],
                    [r["influence"]["robust"] for r in rows],
                    alpha=0.5,
                    s=15,
                    label=f"{c} ({len(rows)} stints)",
                )
            limit = max(ax.get_xlim()[1], ax.get_ylim()[1])
            ax.plot([0, limit], [0, limit], color="gray", linewidth=0.8)
            ax.set_xscale("symlog", linthresh=1)
            ax.set_yscale("symlog", linthresh=1)
            ax.set(
                xlabel="Maior alteração do slope OLS (ms/volta)",
                ylabel="Maior alteração do slope robusto (ms/volta)",
                title="Influência ao retirar uma volta · abaixo da diagonal favorece robusto",
            )
            ax.legend()
            fig.tight_layout()
            fig.savefig(directory / "influencia.png", dpi=150)
            plt.close(fig)
            rows = result["event_errors"]
            fig, ax = plt.subplots(figsize=(12, 8))
            for name, color in [("ols", "#ce7035"), ("robust", "#306daa")]:
                ax.scatter(
                    [r[name] - r["constant"] for r in rows],
                    range(len(rows)),
                    label=name,
                    color=color,
                )
            ax.set_yticks(
                range(len(rows)),
                [
                    f"{result['baseline']['events'][r['session_id']]} · {r['stints']} stints / {r['test_laps']} voltas"
                    for r in rows
                ],
                fontsize=8,
            )
            ax.axvline(0, color="gray")
            ax.invert_yaxis()
            ax.set(
                xlabel="MAE mediana do evento − MAE da constante (ms)",
                title="Transferência para evento deixado de fora\nNegativo: melhor que constante; âncora nas primeiras 5 voltas",
            )
            ax.legend()
            fig.tight_layout()
            fig.savefig(directory / "avaliacao-eventos.png", dpi=150)
            plt.close(fig)
        target = root / ("estimators-" + uuid4().hex)
        os.rename(directory, target)
    return target


def main(argv=None) -> int:
    """Run the predeclared development-only comparison."""
    from scripts.evaluate_profiles import load_plan
    from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryRepository
    from f1_simulator.application.compare_tyre_estimators import compare_estimators

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "data/curated/tyre-estimators"
    )
    parser.add_argument("--without-plots", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = load_plan(args.plan)
        result = compare_estimators(
            SQLiteHistoryRepository(args.database),
            session_ids=plan.development_sessions,
            config=plan.config,
        )
        print(publish(result, args.output_root, plots=not args.without_plots))
    except (ValueError, OSError, sqlite3.Error, ImportError) as exc:
        print(f"estimadores: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
