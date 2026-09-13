#!/usr/bin/env python3
"""Evaluate disjoint event samples and publish a fresh, complete report folder."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict, fields as dataclass_fields
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import TYPE_CHECKING
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

if TYPE_CHECKING:
    from f1_simulator.application.evaluate_profiles import ProfileEvaluation
    from f1_simulator.domain.profile_evaluation import EvaluationPlan


def load_plan(path: Path) -> EvaluationPlan:
    """Translate strict JSON configuration at the boundary, with no inferred split."""
    from f1_simulator.domain.driver_profile import ProfileConfig
    from f1_simulator.domain.profile_evaluation import EvaluationPlan

    data = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "evaluation_id",
        "evaluation_version",
        "profile_method_version",
        "development_sessions",
        "validation_sessions",
        "config",
    }
    if not isinstance(data, dict) or set(data) != expected:
        raise ValueError(f"plan must contain exactly {sorted(expected)}")
    for name in ("development_sessions", "validation_sessions"):
        if not isinstance(data[name], list):
            raise ValueError(f"{name} must be a JSON list")
        data[name] = tuple(data[name])
    if not isinstance(data["config"], dict):
        raise ValueError("config must be an object")
    try:
        data["config"] = ProfileConfig(**data["config"])
        return EvaluationPlan(**data)
    except TypeError as exc:
        raise ValueError(f"invalid plan: {exc}") from exc


def _names(result: ProfileEvaluation) -> dict[str, str]:
    names = dict(result.development.driver_names) | dict(result.validation.driver_names)
    labels = {
        r.driver_id: names.get(r.driver_id, r.driver_id) for r in result.comparisons
    }
    counts = Counter(n.casefold() for n in labels.values())
    return {
        key: f"{name} ({key})" if counts[name.casefold()] > 1 else name
        for key, name in labels.items()
    }


def plot_evaluation(result: ProfileEvaluation, directory: Path) -> None:
    """Plot stored coverage and descriptive estimates, never recompute the model."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = _names(result)
    events = sorted(result.coverage, key=lambda e: (e.race_date, e.session_id))
    drivers = sorted(
        result.comparisons, key=lambda r: (names[r.driver_id], r.driver_id)
    )
    colors = {"development": "#2469a0", "validation": "#c45b17"}
    roles = {"development": "D", "validation": "V"}
    role_names = {"development": "Desenvolvimento", "validation": "Validação"}

    def save(fig, name):
        fig.tight_layout()
        for extension in ("png", "svg"):
            fig.savefig(directory / f"{name}.{extension}", dpi=140)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, max(4, len(events) * 0.5)))
    for i, event in enumerate(events):
        ax.barh(i, event.coverage_pct or 0, color=colors[event.partition])
        ax.text(
            (event.coverage_pct or 0) + 1,
            i,
            f"{event.compared_laps}/{event.input_laps}"
            if event.input_laps
            else "sem observações",
            va="center",
            fontsize=9,
        )
    ax.set_yticks(
        range(len(events)),
        [f"[{roles[e.partition]}] {e.race_name} {e.season}" for e in events],
    )
    ax.set(
        xlim=(0, 120),
        xlabel="Voltas comparáveis / observadas (%)",
        title="Cobertura por evento — D: desenvolvimento; V: validação",
    )
    save(fig, "coverage")

    fig, axes = plt.subplots(
        1, 2, figsize=(14, max(5, len(drivers) * 0.32)), sharey=True
    )
    for ax, field, title in zip(
        axes, ("pace", "consistency"), ("Ritmo relativo (%)", "Dispersão MAD (%)")
    ):
        for i, row in enumerate(drivers):
            a, b = (
                getattr(row, f"development_{field}_pct"),
                getattr(row, f"validation_{field}_pct"),
            )
            if a is not None and b is not None:
                ax.plot([a, b], [i, i], color="gray", linewidth=1)
            for value, role, marker in (
                (a, "development", "o"),
                (b, "validation", "s"),
            ):
                if value is not None:
                    ax.scatter(value, i, color=colors[role], marker=marker, s=24)
            if a is None and b is None:
                ax.text(
                    0.02,
                    i,
                    "indisponível",
                    transform=ax.get_yaxis_transform(),
                    fontsize=8,
                )
        for role, marker in (("development", "o"), ("validation", "s")):
            ax.scatter(
                [], [], color=colors[role], marker=marker, label=role_names[role]
            )
        ax.axvline(0, color="lightgray", linewidth=0.8)
        ax.set(xlabel=title, title="Estimativas independentes por grupo")
        ax.legend(fontsize=8)
    axes[0].set_yticks(range(len(drivers)), [names[r.driver_id] for r in drivers])
    axes[0].invert_yaxis()
    save(fig, "stability")

    estimates = {(r.driver_id, r.session_id): r for r in result.event_estimates}
    for field, filename, label, cmap in (
        ("pace_delta_pct", "pace-by-event", "Ritmo relativo (%)", "coolwarm"),
        ("consistency_mad_pct", "consistency-by-event", "Dispersão MAD (%)", "viridis"),
    ):
        matrix = []
        for driver in drivers:
            values = []
            for event in events:
                estimate = estimates.get((driver.driver_id, event.session_id))
                value = getattr(estimate, field) if estimate else None
                values.append(value if value is not None else float("nan"))
            matrix.append(values)
        fig, ax = plt.subplots(
            figsize=(max(9, len(events) * 1.4), max(5, len(drivers) * 0.3))
        )
        if matrix:
            finite = [value for row in matrix for value in row if value == value]
            scale = max((abs(value) for value in finite), default=1.0) or 1.0
            image = ax.imshow(
                matrix,
                aspect="auto",
                cmap=plt.get_cmap(cmap).with_extremes(bad="#454545"),
                vmin=-scale if field == "pace_delta_pct" else 0,
                vmax=scale,
            )
            fig.colorbar(image, ax=ax, label=label)
        else:
            ax.text(0.5, 0.5, "Sem participantes", ha="center", transform=ax.transAxes)
        ax.set_yticks(range(len(drivers)), [names[r.driver_id] for r in drivers])
        ax.set_xticks(
            range(len(events)),
            [f"[{roles[e.partition]}] {e.race_name}\n{e.race_date}" for e in events],
            rotation=25,
            ha="right",
        )
        ax.set_title(
            f"{label} por evento — cinza escuro: ausente/indisponível\nD: desenvolvimento; V: validação; pontos descritivos de um evento"
        )
        save(fig, filename)


def publish_report(
    result: ProfileEvaluation, root: Path, *, plots: bool = True
) -> Path:
    """Stage all artifacts and publish a unique directory only after success.

    Existing reports and input databases are never replaced. A plotting or
    serialization failure cleans only this execution's temporary directory.
    The folder name is unique; JSON content is deterministic for identical input.
    """
    from f1_simulator.domain.profile_evaluation import DriverStability

    root = root.resolve()
    if root.is_relative_to(ROOT / "data" / "raw"):
        raise ValueError("reports must not be written inside data/raw")
    root.mkdir(parents=True, exist_ok=True)
    names = _names(result)
    with tempfile.TemporaryDirectory(prefix=".evaluation-", dir=root) as temporary:
        directory = Path(temporary)
        (directory / "evaluation.json").write_text(
            json.dumps(
                asdict(result),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        for filename, records, fields in (
            (
                "coverage.csv",
                result.coverage,
                (
                    "partition",
                    "session_id",
                    "race_id",
                    "race_name",
                    "season",
                    "race_date",
                    "participants",
                    "input_laps",
                    "compared_laps",
                    "coverage_pct",
                    "compared_drivers",
                    "exclusions",
                ),
            ),
            (
                "stability.csv",
                result.comparisons,
                tuple(field.name for field in dataclass_fields(DriverStability)),
            ),
            (
                "driver-events.csv",
                result.event_estimates,
                (
                    "partition",
                    "session_id",
                    "driver_id",
                    "team_ids",
                    "input_laps",
                    "compared_laps",
                    "pace_delta_pct",
                    "consistency_mad_pct",
                ),
            ),
        ):
            headers = list(fields) + (["driver_name"] if "driver_id" in fields else [])
            with (directory / filename).open(
                "w", encoding="utf-8", newline=""
            ) as stream:
                writer = csv.DictWriter(stream, fieldnames=headers)
                writer.writeheader()
                for record in records:
                    row = asdict(record)
                    if "driver_id" in row:
                        row["driver_name"] = names[row["driver_id"]]
                    row = {
                        k: json.dumps(v, ensure_ascii=False)
                        if isinstance(v, tuple)
                        else v
                        for k, v in row.items()
                    }
                    writer.writerow(row)
        lines = [
            "# Avaliação descritiva entre eventos",
            "",
            f"Plano: `{result.plan.evaluation_id}`; SHA-256: `{result.plan_sha256}`.",
            "",
            "Mesmos parâmetros; grupos separados. Diferenças não são erro de previsão.",
            "",
            f"Pilotos com estimativas nos dois grupos: {result.summary.paired_drivers}/{result.summary.total_drivers}.",
            "",
            f"Mediana do módulo da mudança de ritmo (pp): {result.summary.median_absolute_pace_shift_pp}.",
            f"Mediana do módulo da mudança de MAD (pp): {result.summary.median_absolute_consistency_shift_pp}.",
            "",
            "Valores `None` indicam indisponibilidade, nunca efeito zero.",
            "",
            "| Grupo | Evento | Comparáveis / observadas |",
            "| --- | --- | --- |",
        ]
        lines.extend(
            f"| {e.partition} | {e.race_name} {e.season} | {e.compared_laps} / {e.input_laps} |"
            for e in result.coverage
        )
        lines += ["", "Avisos:", ""] + [f"- `{warning}`" for warning in result.warnings]
        lines += [
            "",
            "JSON contém proveniência e auditoria completa; CSVs resumem cobertura e estabilidade.",
            "Não há aprovação automática de robustez, intervalo de confiança ou calibração preditiva.",
        ]
        (directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if plots:
            plot_evaluation(result, directory)
        destination = root / ("evaluation-" + uuid4().hex)
        if destination.exists():
            raise FileExistsError(destination)
        os.rename(directory, destination)
    return destination


def main(argv: list[str] | None = None) -> int:
    """Run a saved plan locally; stdout prints the new report path, not raw JSON."""
    from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryRepository
    from f1_simulator.application.evaluate_profiles import evaluate_profiles

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "data" / "curated" / "evaluations"
    )
    parser.add_argument(
        "--without-plots",
        action="store_true",
        help="gera JSON/CSV/Markdown sem Matplotlib",
    )
    args = parser.parse_args(argv)
    try:
        result = evaluate_profiles(
            SQLiteHistoryRepository(args.database), load_plan(args.plan)
        )
        destination = publish_report(
            result, args.output_root, plots=not args.without_plots
        )
    except (ValueError, OSError, sqlite3.Error, ImportError) as exc:
        print(f"avaliação: {exc}", file=sys.stderr)
        return 1
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
