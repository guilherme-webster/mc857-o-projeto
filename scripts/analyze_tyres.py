#!/usr/bin/env python3
"""Publish development-only tyre stint audit, plots and descriptive diagnostics."""

import argparse
from collections import defaultdict
import csv
import json
import math
import os
from pathlib import Path
from statistics import median
import sqlite3
import sys
import tempfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def plot_study(result: dict, directory: Path) -> None:
    """Plot all driver/stint observations in event atlases plus summary diagnostics."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    stints, names = result["stints"], result["driver_names"]
    colors = {"SOFT": "#cc4444", "MEDIUM": "#b88a00", "HARD": "#3478ba"}
    links = []
    with PdfPages(directory / "pilotos-stints.pdf") as pdf:
        for sid, event in result["events"].items():
            groups = defaultdict(list)
            for stint in stints:
                if stint["session_id"] == sid:
                    groups[stint["driver_id"]].append(stint)
            drivers = sorted(groups, key=lambda d: names.get(d, d))
            fig, axes = plt.subplots(
                math.ceil(len(drivers) / 4), 4, figsize=(18, 15), squeeze=False
            )
            for ax, driver in zip(axes.flat, drivers):
                for i, stint in enumerate(groups[driver]):
                    color = plt.get_cmap("tab10")(i % 10)
                    rows = [
                        r
                        for r in stint["rows"]
                        if r["tyre_life_laps"] is not None
                        and r["lap_time_ms"] is not None
                    ]
                    for eligible in (False, True):
                        points = [r for r in rows if r["eligible"] == eligible]
                        ax.scatter(
                            [r["tyre_life_laps"] for r in points],
                            [r["lap_time_ms"] / 1000 for r in points],
                            s=9,
                            marker="o" if eligible else "x",
                            color=color if eligible else "#aaaaaa",
                            alpha=0.85 if eligible else 0.5,
                        )
                    fit = stint["fit"]
                    label = f"S{stint['stint']} {stint['compound']} {'novo' if stint['fresh_tyre'] else 'usado'} {stint['eligible_laps']}/{stint['input_laps']}"
                    if fit:
                        x = [fit["age_min"], fit["age_max"]]
                        ax.plot(
                            x,
                            [
                                (fit["intercept_ms"] + fit["slope_ms_per_age_lap"] * v)
                                / 1000
                                for v in x
                            ],
                            color=color,
                            linewidth=1,
                            linestyle="--",
                            label=label,
                        )
                    else:
                        ax.plot([], [], color=color, label=label + " sem ajuste")
                # No y-axis trimming: even very slow excluded pit/red-flag laps stay visible.
                ax.set_title(names.get(driver, driver), fontsize=10)
                ax.set_xlabel("Idade observada (voltas)", fontsize=8)
                ax.set_ylabel("Tempo (s)", fontsize=8)
                ax.tick_params(labelsize=7)
                ax.legend(fontsize=5.5, loc="best")
                ax.grid(alpha=0.15)
            for ax in list(axes.flat)[len(drivers) :]:
                ax.set_visible(False)
            fig.suptitle(
                f"{event} · {sid}\nPontos: aprovados; × cinza: excluídos; tracejado: tendência OLS, não desgaste causal. Legenda: voltas aprovadas/observadas.",
                fontsize=12,
            )
            fig.tight_layout(rect=(0, 0, 1, 0.95))
            filename = sid.replace(":", "-")
            fig.savefig(directory / f"{filename}.png", dpi=140)
            pdf.savefig(fig)
            for ax, driver in zip(axes.flat, drivers):
                approved = [
                    r["lap_time_ms"] / 1000
                    for stint in groups[driver]
                    for r in stint["rows"]
                    if r["eligible"] and r["lap_time_ms"] is not None
                ]
                if approved:
                    low, high = min(approved) - 1, max(approved) + 1
                    ax.set_ylim(low, high)
                    outside = sum(
                        r["lap_time_ms"] is not None
                        and not low <= r["lap_time_ms"] / 1000 <= high
                        for stint in groups[driver]
                        for r in stint["rows"]
                    )
                    ax.text(
                        0.02,
                        0.02,
                        f"{outside} excluídas fora do zoom",
                        transform=ax.transAxes,
                        fontsize=6,
                    )
                else:
                    ax.text(
                        0.5,
                        0.5,
                        "Sem voltas aprovadas",
                        transform=ax.transAxes,
                        ha="center",
                        fontsize=8,
                    )
            fig.suptitle(
                f"{event} · zoom em TODAS as voltas aprovadas\nExcluídas fora da escala estão contadas; consulte a página completa. Tracejado: tendência descritiva.",
                fontsize=12,
            )
            fig.savefig(directory / f"{filename}-zoom.png", dpi=140)
            pdf.savefig(fig)
            plt.close(fig)
            links.append(
                f"- {event}: [completo]({filename}.png) · [zoom]({filename}-zoom.png)"
            )
    (directory / "graficos.md").write_text(
        "# Atlas por evento, piloto e stint\n\n" + "\n".join(links) + "\n",
        encoding="utf-8",
    )

    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    events = list(result["events"])
    for j, compound in enumerate(colors):
        rows = [r for r in result["coverage"] if r["compound"] == compound]
        positions = [events.index(r["session_id"]) + (j - 1) * 0.22 for r in rows]
        axes[0].barh(
            positions,
            [100 * r["eligible_laps"] / r["input_laps"] for r in rows],
            height=0.2,
            color=colors[compound],
            label=compound,
        )
        for y, r in zip(positions, rows):
            if r["median_slope_ms_per_age_lap"] is not None:
                axes[1].scatter(
                    r["median_slope_ms_per_age_lap"], y, color=colors[compound], s=25
                )
    for ax in axes:
        ax.set_yticks(
            range(len(events)), [result["events"][s] for s in events], fontsize=8
        )
        ax.invert_yaxis()
        ax.grid(alpha=0.15)
    axes[0].set(
        xlabel="Voltas aprovadas / observadas (%)",
        xlim=(0, 105),
        title="Cobertura por evento e composto",
    )
    axes[0].legend()
    axes[1].set(
        xlabel="Mediana de inclinações dos stints (ms / volta de idade)",
        title="Evolução líquida observada · não coeficiente causal",
    )
    axes[1].axvline(0, color="gray", linewidth=0.8)
    fig.tight_layout()
    for extension in ("png", "svg"):
        fig.savefig(directory / f"cobertura-tendencias.{extension}", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for compound, color in colors.items():
        for fresh, marker in ((True, "o"), (False, "x")):
            grouped = defaultdict(list)
            for s in stints:
                if (
                    s["compound"] == compound
                    and s["fresh_tyre"] == fresh
                    and s["start_kind"] == "post_pit"
                    and s["early_minus_later_ms"] is not None
                ):
                    grouped[s["session_id"]].append(s["early_minus_later_ms"])
            x = list(range(len(grouped)))
            # Each point is an event median; x groups indicate compound/freshness.
            position = list(colors).index(compound) * 2 + (not fresh)
            offsets = [position + 0.3 * (i / max(1, len(x) - 1) - 0.5) for i in x]
            axes[0].scatter(
                offsets,
                [median(v) / 1000 for v in grouped.values()],
                color=color,
                marker=marker,
            )
            axes[0].text(
                position,
                0.98,
                f"{len(grouped)} eventos",
                transform=axes[0].get_xaxis_transform(),
                ha="center",
                va="top",
                fontsize=8,
            )
    axes[0].set_xticks(
        range(6), [f"{c}\n{f}" for c in colors for f in ("novo", "usado")], fontsize=8
    )
    axes[0].set(
        ylabel="Mediana por evento: tempo voltas 2–3 − 5–8 (s)",
        title="Após pit: positivo = início mais lento\nContraste descritivo, não temperatura",
    )
    axes[0].axhline(0, color="gray", linewidth=0.8)
    for compound, color in colors.items():
        pairs = [
            s
            for s in stints
            if s["compound"] == compound and s["fit"] and s["sensitivity"]["3"]
        ]
        axes[1].scatter(
            [s["fit"]["slope_ms_per_age_lap"] for s in pairs],
            [s["sensitivity"]["3"]["slope_ms_per_age_lap"] for s in pairs],
            color=color,
            alpha=0.4,
            s=12,
            label=f"{compound} ({len(pairs)} stints)",
        )
    lo = min(axes[1].get_xlim()[0], axes[1].get_ylim()[0])
    hi = max(axes[1].get_xlim()[1], axes[1].get_ylim()[1])
    axes[1].plot([lo, hi], [lo, hi], color="gray", linewidth=0.8)
    axes[1].set(
        xlabel="Inclinação com todas as voltas aprovadas (ms/volta)",
        ylabel="Inclinação retirando posições 1–3 (ms/volta)",
        title="Sensibilidade ao início do stint · mesmos stints",
    )
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    for extension in ("png", "svg"):
        fig.savefig(directory / f"inicio-sensibilidade.{extension}", dpi=150)
    plt.close(fig)


def publish(result: dict, root: Path, *, plots: bool = True) -> Path:
    """Atomically publish a new report; failures leave earlier artifacts untouched."""
    root = root.resolve()
    if root.is_relative_to(ROOT / "data/raw"):
        raise ValueError("reports cannot be written in data/raw")
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".tyres-", dir=root) as temporary:
        directory = Path(temporary)
        (directory / "analysis.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        rows = []
        for s in result["stints"]:
            row = {
                k: v for k, v in s.items() if k not in ("rows", "fit", "sensitivity")
            }
            row["driver_name"] = result["driver_names"].get(
                s["driver_id"], s["driver_id"]
            )
            row["event"] = result["events"][s["session_id"]]
            row.update({f"fit_{k}": v for k, v in (s["fit"] or {}).items()})
            for cut, fit in s["sensitivity"].items():
                row[f"cut_{cut}_slope"] = fit["slope_ms_per_age_lap"] if fit else None
            rows.append(row)
        for name, records in (
            ("stints.csv", rows),
            ("coverage.csv", result["coverage"]),
        ):
            with (directory / name).open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=sorted({k for r in records for k in r})
                )
                writer.writeheader()
                writer.writerows(records)
        if plots:
            plot_study(result, directory)
        target = root / ("tyres-" + uuid4().hex)
        os.rename(directory, target)
    return target


def main(argv: list[str] | None = None) -> int:
    """Study only development sessions in the supplied plan."""
    from scripts.evaluate_profiles import load_plan
    from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryRepository
    from f1_simulator.application.analyze_tyres import analyze_tyres

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "data/curated/tyre-studies"
    )
    parser.add_argument("--without-plots", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = load_plan(args.plan)
        result = analyze_tyres(
            SQLiteHistoryRepository(args.database),
            session_ids=plan.development_sessions,
            config=plan.config,
        )
        print(publish(result, args.output_root, plots=not args.without_plots))
    except (ValueError, OSError, sqlite3.Error, ImportError) as exc:
        print(f"pneus: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
