#!/usr/bin/env python3
"""Publish matched teammate comparisons and exact-context time references."""

from __future__ import annotations

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
    """Publish new complete artifacts atomically; never overwrite existing results."""
    root = root.resolve()
    if root.is_relative_to(ROOT / "data/raw"):
        raise ValueError("reports cannot be written in data/raw")
    root.mkdir(parents=True, exist_ok=True)
    names = dict(result["run"]["driver_names"])
    teams = dict(result["team_names"])
    with tempfile.TemporaryDirectory(prefix=".teammates-", dir=root) as temporary:
        directory = Path(temporary)
        (directory / "analysis.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        )
        rows = []
        for pair in result["pairs"]:
            rows.append(
                {k: v for k, v in pair.items() if k not in ("events", "contexts")}
                | {
                    "team_name": teams.get(pair["team_id"], pair["team_id"]),
                    "driver_a_name": names.get(pair["driver_a"], pair["driver_a"]),
                    "driver_b_name": names.get(pair["driver_b"], pair["driver_b"]),
                }
            )
        for filename, records in (
            ("pairs.csv", rows),
            ("references.csv", result["context_references"]),
        ):
            with (directory / filename).open(
                "w", newline="", encoding="utf-8"
            ) as stream:
                if records:
                    writer = csv.DictWriter(stream, fieldnames=list(records[0]))
                    writer.writeheader()
                    for row in records:
                        writer.writerow(
                            {
                                k: json.dumps(v, ensure_ascii=False)
                                if isinstance(v, (tuple, list, dict))
                                else v
                                for k, v in row.items()
                            }
                        )
        lines = [
            "# Companheiros em contextos compartilhados",
            "",
            f"Método: shared-teammate-context-v1; hash: `{result['analysis_sha256']}`.",
            "Gap simétrico: negativo indica A mais rápido. Não é ranking de habilidade.",
            "Intervalos reamostram eventos pareados inteiros; poucos eventos limitam a interpretação.",
            "",
            "| Piloto A | Piloto B | Equipe | Eventos compartilhados/candidatos | Contextos compartilhados/união | Gap (%) |",
            "| --- | --- | --- | ---: | ---: | ---: |",
        ]
        for row in rows:
            gap = "indisponível" if row["gap_pct"] is None else f"{row['gap_pct']:+.4f}"
            lines.append(
                f"| {row['driver_a_name']} | {row['driver_b_name']} | {row['team_name']} | {row['shared_events']}/{row['candidate_events']} | {row['shared_contexts']}/{row['union_contexts']} | {gap} |"
            )
        (directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if plots:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(15, max(5, len(rows) * 0.65)))
            for i, row in enumerate(rows):
                if row["gap_pct"] is None:
                    ax.text(0.02, i, "insuficiente", transform=ax.get_yaxis_transform())
                else:
                    if row["interval_pct"] is not None:
                        ax.plot(row["interval_pct"], [i, i], color="#2469a0")
                    ax.scatter(
                        row["gap_pct"],
                        i,
                        edgecolors="#2469a0",
                        facecolors="none" if row["warnings"] else "#2469a0",
                    )
            ax.set_yticks(
                range(len(rows)),
                [
                    f"{r['driver_a_name']} − {r['driver_b_name']} ({r['team_name']})\n{r['shared_events']}/{r['candidate_events']} eventos · {r['shared_contexts']}/{r['union_contexts']} contextos · {r['driver_a_shared_laps']}/{r['driver_b_shared_laps']} voltas A/B"
                    for r in rows
                ],
                fontsize=8,
            )
            ax.axvline(0, color="gray", linewidth=0.8)
            ax.invert_yaxis()
            ax.set(
                xlabel="100 × (mediana A − mediana B) / média das duas medianas (%)",
                title=f"Companheiros · contextos compartilhados · bootstrap {result['settings']['bootstrap']['confidence']:.0%}\nNegativo: A mais rápido; marcador vazio: suporte limitado. Sem ranking causal.",
            )
            fig.tight_layout()
            for extension in ("png", "svg"):
                fig.savefig(directory / f"teammates.{extension}", dpi=140)
            plt.close(fig)
        target = root / ("teammates-" + uuid4().hex)
        if target.exists():
            raise FileExistsError(target)
        os.rename(directory, target)
    return target


def main(argv: list[str] | None = None) -> int:
    """Analyze development IDs from the plan, never silently include its reserve."""
    from scripts.evaluate_profiles import load_plan
    from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryRepository
    from f1_simulator.application.analyze_teammates import analyze_teammates

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "data/curated/teammate-studies"
    )
    parser.add_argument("--without-plots", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = load_plan(args.plan)
        result = analyze_teammates(
            SQLiteHistoryRepository(args.database),
            session_ids=plan.development_sessions,
            config=plan.config,
        )
        output = publish(result, args.output_root, plots=not args.without_plots)
    except (OSError, ValueError, sqlite3.Error, ImportError) as exc:
        print(f"companheiros: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
