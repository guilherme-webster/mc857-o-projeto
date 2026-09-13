#!/usr/bin/env python3
"""Run the local experimental driver profile and optionally export audit plots."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

if TYPE_CHECKING:
    from f1_simulator.application.profile_drivers import ProfileRun


def driver_labels(run: ProfileRun) -> dict[str, str]:
    """Use human names, disambiguating homonyms without changing canonical IDs."""
    names = dict(run.driver_names)
    labels = {p.driver_id: names.get(p.driver_id, p.driver_id) for p in run.profiles}
    counts = Counter(label.casefold() for label in labels.values())
    return {
        key: f"{label} ({key})" if counts[label.casefold()] > 1 else label
        for key, label in labels.items()
    }


def plot_audit(run: ProfileRun, destination: Path) -> None:
    """Export descriptive coverage, lap times and residuals, never validation error.

    Matplotlib is optional and confined to this CLI boundary. No profile formula
    is recalculated in the plots. Rejected laps remain visible in grey.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    destination.mkdir(parents=True, exist_ok=False)
    driver_ids = [p.driver_id for p in run.profiles]
    names = driver_labels(run)
    labels = [names[driver] for driver in driver_ids]
    fig, ax = plt.subplots(figsize=(11, max(4, len(labels) * 0.3)))
    counts = [p.compared_laps for p in run.profiles]
    ax.barh(labels, counts, label="Comparáveis")
    ax.barh(
        labels,
        [p.input_laps - p.compared_laps for p in run.profiles],
        left=counts,
        label="Excluídas",
        color="lightgray",
    )
    ax.set(
        xlabel="Voltas observadas (contagem)", title="Cobertura do perfil exploratório"
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(destination / "coverage.svg")
    fig.savefig(destination / "coverage.png", dpi=140)
    plt.close(fig)
    for number, session_id in enumerate(run.session_ids, 1):
        fig, axes = plt.subplots(2, 1, figsize=(12, 9))
        rows = [lap for lap in run.laps if lap.session_id == session_id]
        rejected = [
            lap for lap in rows if lap.exclusions and lap.lap_time_ms is not None
        ]
        axes[0].scatter(
            [lap.lap_number for lap in rejected],
            [lap.lap_time_ms / 1000 for lap in rejected],
            color="lightgray",
            s=9,
            label="Excluídas",
        )
        pits = [lap for lap in rejected if "pit_lap" in lap.exclusions]
        axes[0].scatter(
            [lap.lap_number for lap in pits],
            [lap.lap_time_ms / 1000 for lap in pits],
            color="firebrick",
            marker="x",
            s=25,
            label="Entrada/saída dos boxes",
        )
        for driver_index, driver in enumerate(driver_ids):
            palette = "tab20" if driver_index < 20 else "tab20b"
            color = plt.get_cmap(palette)(driver_index % 20)
            usable = [
                lap for lap in rows if lap.driver_id == driver and not lap.exclusions
            ]
            if not usable:
                continue
            axes[0].scatter(
                [lap.lap_number for lap in usable],
                [lap.lap_time_ms / 1000 for lap in usable],
                s=10,
                color=color,
                label=names[driver],
            )
            axes[1].scatter(
                [lap.lap_number for lap in usable],
                [lap.residual_pct for lap in usable],
                s=10,
                color=color,
            )
        axes[0].set(ylabel="Tempo observado (s)", title=session_id)
        axes[0].legend(
            fontsize=7, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.48)
        )
        fig.subplots_adjust(hspace=0.4)
        axes[1].axhline(0, color="black", linewidth=0.7)
        axes[1].set(
            xlabel="Número da volta",
            ylabel="Resíduo relativo ao contexto (%)",
            title="Positivo = mais lento; não é erro de previsão",
        )
        fig.tight_layout()
        fig.savefig(destination / f"session-{number}.svg")
        fig.savefig(destination / f"session-{number}.png", dpi=140)
        plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    """Print deterministic JSON; all uncalibrated thresholds must be explicit."""
    from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryRepository
    from f1_simulator.application.profile_drivers import profile_drivers
    from f1_simulator.domain.driver_profile import ProfileConfig

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--sessions", required=True, nargs="+")
    for name in (
        "lap-window",
        "tyre-age-window",
        "weather-max-age-ms",
        "min-laps-per-context",
        "min-drivers-per-context",
        "min-events",
    ):
        parser.add_argument(f"--{name}", required=True, type=int)
    parser.add_argument(
        "--plot-dir", type=Path, help="novo diretório para SVGs; requer matplotlib"
    )
    args = parser.parse_args(argv)
    try:
        config = ProfileConfig(
            **{name: getattr(args, name) for name in ProfileConfig.__dataclass_fields__}
        )
        run = profile_drivers(
            SQLiteHistoryRepository(args.database),
            session_ids=tuple(args.sessions),
            config=config,
        )
        if args.plot_dir:
            plot_audit(run, args.plot_dir)
        print(
            json.dumps(
                asdict(run),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
        )
    except (ValueError, OSError, sqlite3.Error, ImportError) as exc:
        print(f"perfilamento: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
