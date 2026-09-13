#!/usr/bin/env python3
"""Generate development-only context sensitivity and event-influence reports."""

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
    """Publish complete unique artifacts, preserving previous outputs on failure."""
    root = root.resolve()
    if root.is_relative_to(ROOT / "data/raw"):
        raise ValueError("reports cannot be written in data/raw")
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".development-", dir=root) as temporary:
        directory = Path(temporary)
        (directory / "analysis.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        )
        lines = [
            "# Exploração exclusiva do desenvolvimento",
            "",
            f"SHA-256: `{result['analysis_sha256']}`.",
            "Eventos reservados não foram perfilados. Influência não é erro de previsão.",
            "",
            "| Variante | Voltas comparáveis | Cobertura (%) | Pilotos com perfil | Mistura de stints |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for variant in result["results"]:
            name = variant["variant"]["name"]
            summary = variant["summary"]
            lines.append(
                f"| {name} | {summary['compared_laps']}/{summary['input_laps']} | {summary['coverage_pct']} | {summary['supported_drivers']}/{summary['total_drivers']} | {summary['mixed_stint_contexts']} |"
            )
            for key in ("drivers", "event_influence"):
                rows = variant[key]
                with (directory / f"{name}-{key}.csv").open(
                    "w", newline="", encoding="utf-8"
                ) as stream:
                    if rows:
                        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                        writer.writeheader()
                        for row in rows:
                            writer.writerow(
                                {
                                    k: json.dumps(v, ensure_ascii=False)
                                    if isinstance(v, (tuple, list))
                                    else v
                                    for k, v in row.items()
                                }
                            )
            if plots:
                import matplotlib

                matplotlib.use("Agg")
                import matplotlib.pyplot as plt

                rows = sorted(variant["drivers"], key=lambda r: r["driver_name"])
                fig, axes = plt.subplots(
                    1, 3, figsize=(19, max(6, len(rows) * 0.48)), sharey=True
                )
                for i, row in enumerate(rows):
                    for ax, metric, interval in (
                        (axes[0], "pace", "pace_interval_pct"),
                        (axes[1], "mad", "consistency_interval_pct"),
                    ):
                        value = row[f"{metric}_pct"]
                        if value is not None:
                            if row[interval] is not None:
                                ax.plot(
                                    row[interval], [i, i], color="#2469a0", alpha=0.6
                                )
                            ax.scatter(
                                value,
                                i,
                                edgecolors="#2469a0",
                                facecolors="none" if row["warnings"] else "#2469a0",
                            )
                        else:
                            ax.text(
                                0.02,
                                i,
                                "insuficiente",
                                transform=ax.get_yaxis_transform(),
                                fontsize=8,
                            )
                    value = row["max_leave_one_event_out_pace_shift_pp"]
                    if value is not None:
                        axes[2].scatter(value, i, color="#c45b17")
                    else:
                        axes[2].text(
                            0.02,
                            i,
                            "insuficiente",
                            transform=axes[2].get_yaxis_transform(),
                            fontsize=8,
                        )
                axes[0].set_yticks(
                    range(len(rows)),
                    [
                        f"{r['driver_name']}\n{r['compared_laps']}v/{r['contexts']}c/{r['events']}e"
                        for r in rows
                    ],
                    fontsize=8,
                )
                axes[0].invert_yaxis()
                axes[0].set(xlabel="Ritmo relativo (%)")
                axes[1].set(xlabel="MAD (pp do tempo relativo)")
                axes[2].set(xlabel="Máxima mudança de ritmo (pp)\nao retirar um evento")
                fig.suptitle(
                    f"Desenvolvimento · {name} · intervalos bootstrap {result['settings']['bootstrap']['confidence']:.0%}\nv: voltas; c: contextos; e: eventos. Marcador vazio: aviso de suporte. Não é ranking de habilidade."
                )
                fig.tight_layout()
                for extension in ("png", "svg"):
                    fig.savefig(directory / f"{name}.{extension}", dpi=140)
                plt.close(fig)
        lines += [
            "",
            "CSVs detalham suporte, intervalos, diferenças entre variantes e influência de cada evento.",
            "A remoção de um evento recalcula a mediana dos eventos restantes e respeita o mínimo de eventos.",
            "Perfis e referências dependem de piloto/equipe/contexto. Escolhas exigem registro antes da avaliação reservada.",
        ]
        (directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        target = root / ("development-" + uuid4().hex)
        if target.exists():
            raise FileExistsError(target)
        os.rename(directory, target)
    return target


def main(argv: list[str] | None = None) -> int:
    """Load the frozen plan but pass only development IDs to the profiler."""
    from scripts.evaluate_profiles import load_plan
    from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryRepository
    from f1_simulator.application.analyze_development import analyze_development

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "data/curated/development-studies"
    )
    parser.add_argument("--without-plots", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = analyze_development(
            SQLiteHistoryRepository(args.database), load_plan(args.plan)
        )
        output = publish(result, args.output_root, plots=not args.without_plots)
    except (ValueError, OSError, sqlite3.Error, ImportError) as exc:
        print(f"desenvolvimento: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
