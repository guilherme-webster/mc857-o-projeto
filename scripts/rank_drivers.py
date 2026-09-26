#!/usr/bin/env python3
"""Publish an observational pace ranking from the development selection."""

import argparse
import csv
from dataclasses import asdict
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


def publish(run, root: Path, *, plots: bool = True) -> Path:
    """Publish names, counts and event intervals atomically in a new directory."""
    from f1_simulator.application.rank_drivers import rank_drivers
    from f1_simulator.domain.profile_reliability import BootstrapConfig

    root = root.resolve()
    if root.is_relative_to(ROOT / "data/raw"):
        raise ValueError("reports cannot be written in data/raw")
    rows = rank_drivers(run)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ranking-", dir=root) as temporary:
        directory = Path(temporary)
        (directory / "ranking.json").write_text(
            json.dumps(
                dict(
                    method="aggregate-pace-ranking-v1",
                    interpretation="observed driver/team pace; not isolated skill or statistical superiority",
                    bootstrap=asdict(BootstrapConfig()),
                    run=asdict(run),
                    ranking=[asdict(row) for row in rows],
                ),
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        with (directory / "ranking.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow(
                (
                    "position",
                    "driver_id",
                    "name",
                    "pace_pct",
                    "events",
                    "contexts",
                    "laps",
                    "interval_pct",
                    "warnings",
                )
            )
            for row in rows:
                s = row.support
                writer.writerow(
                    (
                        row.position,
                        row.driver_id,
                        row.name,
                        row.pace_delta_pct,
                        s.events,
                        s.contexts,
                        s.compared_laps,
                        s.pace_interval_pct,
                        ";".join(s.warnings),
                    )
                )
        lines = [
            "# Ranking descritivo por ritmo",
            "",
            "Menor percentual = ritmo observado mais rápido. Não isola piloto de equipe.",
            "Empates exatos compartilham posição; intervalos não certificam a ordem.",
            "",
            "| Posição | Piloto | Ritmo (%) | Eventos | Contextos | Voltas | Avisos |",
            "| ---: | --- | ---: | ---: | ---: | ---: | --- |",
        ]
        for row in rows:
            pace = (
                "indisponível"
                if row.pace_delta_pct is None
                else f"{row.pace_delta_pct:+.4f}"
            )
            s = row.support
            lines.append(
                f"| {row.position or '—'} | {row.name} | {pace} | {s.events} | {s.contexts} | {s.compared_laps} | {', '.join(s.warnings)} |"
            )
        (directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if plots:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(13, max(5, len(rows) * 0.43)))
            for i, row in enumerate(rows):
                if row.pace_delta_pct is None:
                    ax.text(0.02, i, "indisponível", transform=ax.get_yaxis_transform())
                else:
                    if row.support.pace_interval_pct is not None:
                        ax.plot(row.support.pace_interval_pct, [i, i], color="#2469a0")
                    ax.scatter(
                        row.pace_delta_pct,
                        i,
                        edgecolors="#2469a0",
                        facecolors="none" if row.support.warnings else "#2469a0",
                    )
            ax.set_yticks(
                range(len(rows)),
                [
                    f"{r.position or '—'}. {r.name} · {r.support.events} eventos / {r.support.contexts} contextos / {r.support.compared_laps} voltas"
                    for r in rows
                ],
                fontsize=8,
            )
            ax.invert_yaxis()
            ax.axvline(0, color="gray", linewidth=0.8)
            ax.set(
                xlabel="Ritmo relativo (%) · menor é mais rápido",
                title="Ranking descritivo piloto/equipe · 18 eventos de desenvolvimento"
                if len(run.session_ids) == 18
                else "Ranking descritivo piloto/equipe",
            )
            fig.text(
                0.5,
                0.01,
                "IC marginal 95% por eventos; não testa posições. Marcador vazio: avisos de suporte.",
                ha="center",
                fontsize=9,
            )
            fig.tight_layout(rect=(0, 0.035, 1, 1))
            for extension in ("png", "svg"):
                fig.savefig(directory / f"ranking.{extension}", dpi=140)
            plt.close(fig)
        target = root / ("ranking-" + uuid4().hex)
        os.rename(directory, target)
    return target


def main(argv: list[str] | None = None) -> int:
    """Use the explicit plan's development sessions; never silently merge reserve."""
    from scripts.evaluate_profiles import load_plan
    from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryRepository
    from f1_simulator.application.profile_drivers import profile_drivers

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "data/curated/driver-rankings"
    )
    parser.add_argument("--without-plots", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = load_plan(args.plan)
        run = profile_drivers(
            SQLiteHistoryRepository(args.database),
            session_ids=plan.development_sessions,
            config=plan.config,
        )
        print(publish(run, args.output_root, plots=not args.without_plots))
    except (ValueError, OSError, sqlite3.Error, ImportError) as exc:
        print(f"ranking: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
