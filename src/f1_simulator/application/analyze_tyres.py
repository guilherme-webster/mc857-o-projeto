"""Descriptive stint exploration; no causal tyre coefficients or motor parameters.

Age is preserved exactly as supplied by the canonical ETL. Within-stint trends
mix tyre condition, race progression, fuel and traffic. Early-lap contrasts are
operational proxies, not measurements of tyre temperature or warm-up duration.
"""

from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
from math import isclose
from statistics import median

from f1_simulator.application.ports.history import HistoryRepository
from f1_simulator.application.profile_drivers import profile_drivers
from f1_simulator.domain.driver_profile import ProfileConfig

DRY = ("SOFT", "MEDIUM", "HARD")
COMPARISON_GATES = {"insufficient_context_laps", "insufficient_comparison_drivers"}


def fit_trend(rows: list[dict]) -> dict | None:
    """OLS and median pairwise slopes on >=5 laps spanning >=4 age laps.

    MAEs are in-sample diagnostics, not forecasts. The constant uses a median
    (MAE-optimal); OLS minimizes squared error, so need not improve MAE.
    Pairwise slopes omit duplicate ages. Negative slopes are never truncated.
    """
    if len(rows) < 5:
        return None
    x = [r["tyre_life_laps"] for r in rows]
    y = [r["lap_time_ms"] for r in rows]
    if max(x) - min(x) < 4:
        return None
    mx, my = sum(x) / len(x), sum(y) / len(y)
    slope = sum((a - mx) * (b - my) for a, b in zip(x, y)) / sum(
        (a - mx) ** 2 for a in x
    )
    intercept = my - slope * mx
    robust = median(
        (y[j] - y[i]) / (x[j] - x[i])
        for i in range(len(x))
        for j in range(i + 1, len(x))
        if x[j] != x[i]
    )
    center = median(y)
    return dict(
        laps=len(rows),
        age_min=min(x),
        age_max=max(x),
        slope_ms_per_age_lap=slope,
        robust_slope_ms_per_age_lap=robust,
        intercept_ms=intercept,
        constant_mae_ms=sum(abs(v - center) for v in y) / len(y),
        linear_mae_ms=sum(abs(b - (intercept + slope * a)) for a, b in zip(x, y))
        / len(y),
    )


def describe_stint(rows: list[dict]) -> dict:
    """Audit the original sequence before fitting quality-approved dry laps.

    Sequence positions are race-lap offsets from the first recorded stint lap,
    not ranks among surviving observations. Unknown starts cannot support an
    early-lap contrast. A pit-out timestamp or race lap 1 establishes the start.
    """
    rows = sorted(rows, key=lambda r: r["lap_number"])
    first = rows[0]
    compounds = {r["compound"] for r in rows}
    flags = {r["fresh_tyre"] for r in rows}
    issues = []
    if len(compounds) != 1 or None in compounds:
        issues.append("ambiguous_compound")
    if len(flags) != 1 or None in flags:
        issues.append("ambiguous_fresh_flag")
    if any(r["tyre_life_laps"] is None for r in rows):
        issues.append("missing_age")
    else:
        if any(
            not isclose(
                b["tyre_life_laps"] - a["tyre_life_laps"],
                b["lap_number"] - a["lap_number"],
                abs_tol=1e-6,
            )
            for a, b in zip(rows, rows[1:])
        ):
            issues.append("age_progression_mismatch")
    if len({r["lap_number"] for r in rows}) != len(rows):
        issues.append("duplicate_lap")
    start_known = first["lap_number"] == 1 or first["pit_out_ms"] is not None
    for r in rows:
        r["stint_lap_offset"] = r["lap_number"] - first["lap_number"] + 1
    selected = [r for r in rows if r["eligible"]]
    dry = first["compound"] in DRY
    usable = selected if dry and not issues else []
    fit = fit_trend(usable)
    cuts = {
        str(cut): fit_trend([r for r in usable if r["stint_lap_offset"] > cut])
        if start_known
        else None
        for cut in (3, 5)
    }
    early = [r["lap_time_ms"] for r in usable if 2 <= r["stint_lap_offset"] <= 3]
    later = [r["lap_time_ms"] for r in usable if 5 <= r["stint_lap_offset"] <= 8]
    # Post-pit and new/used are kept separate; the first stint contains start effects.
    contrast = (
        median(early) - median(later)
        if start_known and len(early) == 2 and len(later) >= 3
        else None
    )
    return dict(
        session_id=first["session_id"],
        driver_id=first["driver_id"],
        stint=first["stint"],
        compound=first["compound"],
        fresh_tyre=first["fresh_tyre"],
        input_laps=len(rows),
        eligible_laps=len(selected),
        first_race_lap=first["lap_number"],
        last_race_lap=rows[-1]["lap_number"],
        start_known=start_known,
        start_kind="race_start"
        if first["lap_number"] == 1
        else "post_pit"
        if start_known
        else "unknown",
        issues=issues,
        fit=fit,
        sensitivity=cuts,
        early_minus_later_ms=contrast,
        early_laps=len(early),
        later_laps=len(later),
        rows=rows,
    )


def analyze_tyres(
    repository: HistoryRepository,
    *,
    session_ids: tuple[str, ...],
    config: ProfileConfig,
) -> dict:
    """Explore explicitly selected race sessions via canonical Python records."""
    events = {}
    seen = set()
    for sid in sorted(session_ids):
        sessions = tuple(repository.records("sessions", session_id=sid))
        if len(sessions) != 1 or sessions[0]["kind"] != "R":
            raise ValueError("select race sessions")
        race = sessions[0]["race_id"]
        if race in seen:
            raise ValueError("duplicate race aliases")
        seen.add(race)
        records = tuple(repository.records("races", race_id=race))
        if len(records) != 1:
            raise ValueError("missing canonical race")
        events[sid] = records[0]["name"]
    run = profile_drivers(repository, session_ids=session_ids, config=config)
    audits = {(lap.session_id, lap.driver_id, lap.lap_number): lap for lap in run.laps}
    groups, ungrouped = defaultdict(list), []
    for sid in sorted(session_ids):
        for record in repository.records("lap_observations", session_id=sid):
            r = record.as_dict()
            audit = audits[sid, r["driver_id"], r["lap_number"]]
            reasons = sorted(set(audit.exclusions) - COMPARISON_GATES)
            if r["compound"] in DRY and (
                audit.context is None or audit.context.rainfall is not False
            ):
                reasons.append("dry_compound_rain_or_unknown")
            if r["stint"] is None:
                reasons.append("missing_stint")
            if r["tyre_life_laps"] is None:
                reasons.append("missing_age")
            r.update(exclusions=reasons, eligible=not reasons)
            if r["stint"] is None:
                ungrouped.append(r)
            else:
                groups[sid, r["driver_id"], r["stint"]].append(r)
    stints = [describe_stint(groups[k]) for k in sorted(groups)]
    coverage = []
    for sid in sorted(events):
        for compound in sorted(
            {s["compound"] for s in stints if s["session_id"] == sid}, key=str
        ):
            subset = [
                s
                for s in stints
                if s["session_id"] == sid and s["compound"] == compound
            ]
            fits = [s["fit"] for s in subset if s["fit"]]
            coverage.append(
                dict(
                    session_id=sid,
                    event=events[sid],
                    compound=compound,
                    input_laps=sum(s["input_laps"] for s in subset),
                    eligible_laps=sum(s["eligible_laps"] for s in subset),
                    stints=len(subset),
                    fitted_stints=len(fits),
                    median_slope_ms_per_age_lap=median(
                        f["slope_ms_per_age_lap"] for f in fits
                    )
                    if fits
                    else None,
                )
            )
    settings = dict(
        method="tyre-stint-exploration-v1",
        session_ids=run.session_ids,
        profile_config=asdict(config),
        min_laps=5,
        min_age_span=4,
        early_offsets=[2, 3],
        later_offsets=[5, 6, 7, 8],
        min_later_laps=3,
        cuts=[3, 5],
        dry_requires_rainfall_false=True,
    )
    return dict(
        settings=settings,
        events=events,
        driver_names=dict(run.driver_names),
        source_reports_json=run.source_reports_json,
        settings_sha256=hashlib.sha256(
            json.dumps(settings, sort_keys=True).encode()
        ).hexdigest(),
        stints=stints,
        ungrouped=ungrouped,
        coverage=coverage,
        exclusion_counts=dict(
            Counter(e for s in stints for r in s["rows"] for e in r["exclusions"])
        ),
    )
