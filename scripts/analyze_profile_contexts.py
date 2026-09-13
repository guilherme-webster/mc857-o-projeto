#!/usr/bin/env python3
"""Publish context sensitivity, support and event-bootstrap plots offline."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, fields
import json
import os
from pathlib import Path
import sqlite3
from statistics import median
import sys
import tempfile
from uuid import uuid4
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

if TYPE_CHECKING:
    from f1_simulator.application.analyze_contexts import ContextChange
    from f1_simulator.application.evaluate_profiles import ProfileEvaluation


def publish_study(
    results: tuple[ProfileEvaluation, ...],
    changes: tuple[ContextChange, ...],
    root: Path,
    *,
    plots: bool = True,
) -> Path:
    """Publish all variants atomically; inputs and previous outputs stay untouched."""
    from scripts.evaluate_profiles import publish_report
    from f1_simulator.application.analyze_contexts import ContextChange

    root = root.resolve()
    if root.is_relative_to(ROOT / "data" / "raw"):
        raise ValueError("reports must not be written inside data/raw")
    root.mkdir(parents=True, exist_ok=True)
    names = dict(results[0].development.driver_names) | dict(
        results[0].validation.driver_names
    )
    with tempfile.TemporaryDirectory(prefix=".sensitivity-", dir=root) as temporary:
        directory = Path(temporary)
        lines = [
            "# Sensibilidade dos contextos de perfilamento",
            "",
            "Exploração de eventos já conhecidos; não é nova validação confirmatória.",
            "Número do stint não garante estratégia equivalente entre pilotos. Janela de voltas não mede aderência.",
            "Todas as variantes mantêm os mesmos filtros e mínimos de suporte; nenhuma é selecionada automaticamente.",
            "",
            "| Variante | Voltas comparáveis | Cobertura | Contextos com mistura de stints | Pares piloto/evento | Mediana abs(Δ ritmo) (pp) | Mediana abs(Δ MAD) (pp) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        summary = []
        for result in results:
            folder = publish_report(result, directory, plots=plots)
            folder.rename(directory / result.variant.name)
            rows = [r for r in changes if r.variant == result.variant.name]
            pace = [abs(r.pace_shift_pp) for r in rows if r.pace_shift_pp is not None]
            mad = [abs(r.mad_shift_pp) for r in rows if r.mad_shift_pp is not None]
            total = sum(r.input_laps for r in rows)
            count = sum(r.compared_laps for r in rows)
            entry = dict(
                variant=result.variant.name,
                input_laps=total,
                compared_laps=count,
                coverage_pct=100 * count / total if total else None,
                mixed_stint_contexts=sum(r.mixed_stint_contexts for r in rows),
                paired_driver_events=len(pace),
                changed_driver_events=sum(
                    r.pace_shift_pp is not None
                    and (abs(r.pace_shift_pp) > 1e-9 or abs(r.mad_shift_pp) > 1e-9)
                    for r in rows
                ),
                max_absolute_pace_shift_pp=max(pace) if pace else None,
                max_absolute_mad_shift_pp=max(mad) if mad else None,
                median_absolute_pace_shift_pp=median(pace) if pace else None,
                median_absolute_mad_shift_pp=median(mad) if mad else None,
            )
            summary.append(entry)

            def display(value):
                return "indisponível" if value is None else f"{value:.4f}"

            lines.append(
                f"| {result.variant.name} | {count}/{total} | {display(entry['coverage_pct'])}% | {entry['mixed_stint_contexts']} | {len(pace)} | {display(entry['median_absolute_pace_shift_pp'])} | {display(entry['median_absolute_mad_shift_pp'])} |"
            )
        lines += [
            "",
            "A mediana pode esconder mudanças concentradas em poucos pilotos/eventos:",
            "",
        ]
        for entry in summary:
            lines.append(
                f"- {entry['variant']}: {entry['changed_driver_events']}/{entry['paired_driver_events']} pares alterados; "
                f"máximo abs(Δ ritmo)={display(entry['max_absolute_pace_shift_pp'])} pp; "
                f"máximo abs(Δ MAD)={display(entry['max_absolute_mad_shift_pp'])} pp."
            )
        (directory / "summary.json").write_text(
            json.dumps(summary, indent=2, allow_nan=False) + "\n"
        )
        with (directory / "context-changes.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[f.name for f in fields(ContextChange)] + ["driver_name"],
            )
            writer.writeheader()
            for row in changes:
                writer.writerow(
                    asdict(row)
                    | {"driver_name": names.get(row.driver_id, row.driver_id)}
                )
        # Every contributing context can be traced back to its lap numbers/stints.
        with (directory / "context-audit.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            keys = [
                "variant",
                "partition",
                "driver_id",
                "driver_name",
                "session_id",
                "context_json",
                "lap_numbers",
                "stints",
                "lap_time_span_ms",
                "pace_pct",
                "mad_pct",
            ]
            writer = csv.DictWriter(stream, fieldnames=keys)
            writer.writeheader()
            for result in results:
                for role, run in (
                    ("development", result.development),
                    ("validation", result.validation),
                ):
                    for profile in run.profiles:
                        for context in profile.contexts:
                            laps = [
                                lap
                                for lap in run.laps
                                if not lap.exclusions
                                and lap.driver_id == profile.driver_id
                                and lap.context == context.context
                            ]
                            writer.writerow(
                                dict(
                                    variant=result.variant.name,
                                    partition=role,
                                    driver_id=profile.driver_id,
                                    driver_name=names.get(
                                        profile.driver_id, profile.driver_id
                                    ),
                                    session_id=context.context.session_id,
                                    context_json=json.dumps(
                                        asdict(context.context), sort_keys=True
                                    ),
                                    lap_numbers=json.dumps(
                                        [lap.lap_number for lap in laps]
                                    ),
                                    stints=json.dumps(
                                        sorted({lap.stint for lap in laps})
                                    ),
                                    lap_time_span_ms=max(
                                        lap.lap_time_ms for lap in laps
                                    )
                                    - min(lap.lap_time_ms for lap in laps),
                                    pace_pct=context.pace_delta_pct,
                                    mad_pct=context.consistency_mad_pct,
                                )
                            )
        lines += [
            "",
            "Mudanças usam somente pares piloto/evento disponíveis nas duas variantes; a composição de voltas e referências pode mudar.",
            "context-changes.csv inclui voltas comuns à referência; perder uma estimativa não equivale a corrigir seu valor.",
            "context-audit.csv permite investigar quais voltas e stints geraram cada estimativa.",
            "Cada subpasta contém gráficos, suporte, intervalos, proveniência e auditoria completos.",
            "Intervalos bootstrap marginais por evento são exploratórios, sobretudo com 2–3 eventos; não isolam habilidade nem classificam outliers.",
        ]
        (directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if plots:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 2, figsize=(12, 5))
            labels = [s["variant"] for s in summary]
            axes[0].bar(labels, [s["coverage_pct"] or 0 for s in summary])
            axes[0].set(
                ylabel="Voltas comparáveis / observadas (%)",
                title="Cobertura nos mesmos eventos",
            )
            for i, s in enumerate(summary):
                axes[0].text(
                    i,
                    (s["coverage_pct"] or 0) + 1,
                    f"{s['compared_laps']}v",
                    ha="center",
                )
            for i, s in enumerate(summary):
                if s["median_absolute_pace_shift_pp"] is not None:
                    axes[1].scatter(
                        i,
                        s["median_absolute_pace_shift_pp"],
                        marker="o",
                        color="#2469a0",
                    )
                    axes[1].scatter(
                        i,
                        s["median_absolute_mad_shift_pp"],
                        marker="s",
                        color="#c45b17",
                    )
                axes[1].annotate(
                    f"{s['paired_driver_events']} pares",
                    (i, 0),
                    xytext=(0, 5),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8,
                )
            axes[1].scatter([], [], marker="o", color="#2469a0", label="Ritmo")
            axes[1].scatter([], [], marker="s", color="#c45b17", label="MAD")
            axes[1].set_xticks(range(len(labels)), labels)
            axes[1].set(
                ylabel="Mediana do módulo da mudança (pp)",
                title="Mudança frente ao agrupamento original",
            )
            axes[1].legend()
            for ax in axes:
                ax.tick_params(axis="x", rotation=15)
            fig.suptitle(
                "Sensibilidade exploratória; diferenças incluem mudança de suporte e referência"
            )
            fig.tight_layout()
            for extension in ("png", "svg"):
                fig.savefig(directory / f"sensitivity.{extension}", dpi=140)
            plt.close(fig)
        destination = root / ("sensitivity-" + uuid4().hex)
        if destination.exists():
            raise FileExistsError(destination)
        os.rename(directory, destination)
    return destination


def main(argv: list[str] | None = None) -> int:
    """Generate a new self-contained analysis folder; no manual JSON dependency."""
    from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryRepository
    from f1_simulator.application.analyze_contexts import analyze_contexts
    from f1_simulator.domain.profile_reliability import BootstrapConfig
    from scripts.evaluate_profiles import load_plan

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "data/curated/context-studies"
    )
    parser.add_argument("--narrow-window", type=int, default=5)
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=42)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--warn-below-events", type=int, default=5)
    parser.add_argument("--without-plots", action="store_true")
    args = parser.parse_args(argv)
    try:
        bootstrap = BootstrapConfig(
            args.bootstrap_replicates,
            args.bootstrap_seed,
            args.confidence,
            args.warn_below_events,
        )
        results, changes = analyze_contexts(
            SQLiteHistoryRepository(args.database),
            load_plan(args.plan),
            narrow_window=args.narrow_window,
            bootstrap=bootstrap,
        )
        output = publish_study(
            results, changes, args.output_root, plots=not args.without_plots
        )
    except (ValueError, OSError, sqlite3.Error, ImportError) as exc:
        print(f"sensibilidade: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
