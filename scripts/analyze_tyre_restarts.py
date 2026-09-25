#!/usr/bin/env python3
"""Publish sensitivity of tyre trends to post-resumption lap windows."""

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
    """Publish new files atomically, preserving baseline reports and raw data."""
    root = root.resolve()
    if root.is_relative_to(ROOT / "data/raw"):
        raise ValueError("reports cannot be written in data/raw")
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".restarts-", dir=root) as temp:
        directory = Path(temp)
        (directory / "analysis.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        for name, records in [
            ("anchors", result["anchors"]),
            ("changes", result["changes"]),
        ]:
            with (directory / f"{name}.csv").open(
                "w", newline="", encoding="utf-8"
            ) as stream:
                if records:
                    writer = csv.DictWriter(stream, fieldnames=list(records[0]))
                    writer.writeheader()
                    writer.writerows(
                        {
                            k: json.dumps(v) if isinstance(v, dict) else v
                            for k, v in r.items()
                        }
                        for r in records
                    )
        if plots:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 2, figsize=(13, 5))
            windows = [r["window"] for r in result["summaries"]]
            axes[0].plot(
                windows, [r["eligible_laps"] for r in result["summaries"]], marker="o"
            )
            for r in result["summaries"]:
                axes[0].annotate(
                    f"{r['eligible_laps']} voltas\n{r['fitted_stints']} ajustes",
                    (r["window"], r["eligible_laps"]),
                    xytext=(0, 8),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8,
                )
            axes[0].margins(y=0.25)
            axes[0].set(
                xlabel="Janela após retomada (voltas)",
                ylabel="Voltas aprovadas, todos os compostos",
                title="Custo de cobertura · 18 eventos",
            )
            for c in ("SOFT", "MEDIUM", "HARD"):
                axes[1].plot(
                    windows,
                    [
                        next(
                            s["median_slope"] for s in r["slopes"] if s["compound"] == c
                        )
                        for r in result["summaries"]
                    ],
                    marker="o",
                    label=c,
                )
            axes[1].set(
                xlabel="Janela após retomada (voltas)",
                ylabel="Mediana entre stints (ms/volta de idade)",
                title="Tendência líquida, não desgaste causal",
            )
            axes[1].legend()
            fig.tight_layout()
            fig.savefig(directory / "sensibilidade.png", dpi=150)
            plt.close(fig)
            examples = [
                ("session:1124:R", "driver:842", 2),
                ("session:1124:R", "driver:839", 2),
                ("session:1128:R", "driver:822", 2),
            ]
            fig, axes = plt.subplots(1, 3, figsize=(16, 5))
            for ax, (sid, driver, stint) in zip(axes, examples):
                s = next(
                    (
                        s
                        for s in result["marked_stints"]
                        if (s["session_id"], s["driver_id"], s["stint"])
                        == (sid, driver, stint)
                    ),
                    None,
                )
                if s is None:
                    ax.set_visible(False)
                    continue
                good = [r for r in s["rows"] if r["eligible"]]
                ax.scatter(
                    [r["tyre_life_laps"] for r in good],
                    [r["lap_time_ms"] / 1000 for r in good],
                    s=15,
                    color="#555555",
                    label="Voltas aprovadas no original",
                )
                removed = [
                    r
                    for r in good
                    if r.get("restart_offset", 999) <= 2 or r.get("spans_resumes")
                ]
                ax.scatter(
                    [r["tyre_life_laps"] for r in removed],
                    [r["lap_time_ms"] / 1000 for r in removed],
                    s=70,
                    facecolors="none",
                    edgecolors="red",
                    label="Retiradas pela janela 2",
                )
                for k in (0, 2, 3, 5):
                    fit = next(
                        r["fit"]
                        for r in result["changes"]
                        if (r["window"], r["session_id"], r["driver_id"], r["stint"])
                        == (k, sid, driver, stint)
                    )
                    if fit:
                        x = [fit["age_min"], fit["age_max"]]
                        ax.plot(
                            x,
                            [
                                (fit["intercept_ms"] + fit["slope_ms_per_age_lap"] * a)
                                / 1000
                                for a in x
                            ],
                            label=f"Janela {k}: {fit['slope_ms_per_age_lap']:+.0f} ms/volta",
                        )
                ax.set(
                    title=f"{result['baseline']['driver_names'][driver]} · S{stint}\n{result['baseline']['events'][sid]}",
                    xlabel="Idade observada (voltas)",
                    ylabel="Tempo (s)",
                )
                ax.legend(fontsize=7)
            fig.tight_layout()
            fig.savefig(directory / "casos-relargada.png", dpi=150)
            plt.close(fig)
        target = root / ("restarts-" + uuid4().hex)
        os.rename(directory, target)
    return target


def main(argv=None) -> int:
    """Use only the plan's development partition, offline."""
    from scripts.evaluate_profiles import load_plan
    from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryRepository
    from f1_simulator.application.analyze_tyre_restarts import analyze_restarts

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "data/curated/tyre-restarts"
    )
    parser.add_argument("--without-plots", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = load_plan(args.plan)
        result = analyze_restarts(
            SQLiteHistoryRepository(args.database),
            session_ids=plan.development_sessions,
            config=plan.config,
        )
        print(publish(result, args.output_root, plots=not args.without_plots))
    except (ValueError, OSError, sqlite3.Error, ImportError) as exc:
        print(f"relargadas: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
