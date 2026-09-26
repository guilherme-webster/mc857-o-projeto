"""SC/VSC window sensitivity and event-separated descriptive trend benchmarks."""

from collections import defaultdict
from copy import deepcopy
from random import Random
from statistics import median

from f1_simulator.application.analyze_tyres import (
    analyze_tyres,
    describe_stint,
    fit_trend,
    DRY,
)
from f1_simulator.application.analyze_tyre_restarts import (
    restart_times,
    mark_windows,
    summarize,
)


def neutralizations(rows: list[dict]) -> dict:
    """Detect 4/6/7 episodes ending at 1; 5 cancels, 2 preserves pending state.

    Sequence preserves the canonical feed ordering at equal timestamps. Missing
    clocks and unknown statuses fail rather than implying an all-clear period.
    """
    if not rows:
        raise ValueError("track status feed missing")
    active = set()
    start = None
    releases, cancelled, simultaneous = [], [], []
    ordered = sorted(
        rows,
        key=lambda r: (
            r["session_time_ms"] if r["session_time_ms"] is not None else -1,
            r["sequence"],
        ),
    )
    if any(
        r["session_time_ms"] is None
        or r["status"] not in {"1", "2", "4", "5", "6", "7"}
        for r in ordered
    ):
        raise ValueError("unknown track status or clock")
    if len({r["sequence"] for r in ordered}) != len(ordered):
        raise ValueError("duplicate track status sequence")
    for i, row in enumerate(ordered):
        t, status = row["session_time_ms"], row["status"]
        if i and t == ordered[i - 1]["session_time_ms"]:
            simultaneous.append(t)
        if status in {"4", "6", "7"}:
            if not active:
                start = t
            active.add("SC" if status == "4" else "VSC")
        elif status == "5":
            if active:
                cancelled.append(dict(start_ms=start, red_ms=t, kinds=sorted(active)))
            active, start = set(), None
        elif status == "1" and active:
            releases.append(dict(start_ms=start, clear_ms=t, kinds=sorted(active)))
            active, start = set(), None
    return dict(
        releases=releases,
        cancelled=cancelled,
        open_episode=sorted(active),
        simultaneous_times=sorted(set(simultaneous)),
    )


def apply_windows(
    stints: list[dict], red: dict, clear: dict, window: int
) -> list[dict]:
    """Union independent event windows; red resumes always use two laps."""
    current = deepcopy(stints)
    for sid in red:
        allrows = [r for s in current if s["session_id"] == sid for r in s["rows"]]
        excluded = set()
        for time, width in [(t, 2) for t in red[sid]] + [
            (t, window) for t in clear[sid] if window
        ]:
            marked = deepcopy(allrows)
            mark_windows(marked, (time,))
            excluded.update(
                (r["driver_id"], r["lap_number"])
                for r in marked
                if r.get("spans_resumes")
                or 1 <= r.get("restart_offset", 999999) <= width
            )
        for row in allrows:
            if (row["driver_id"], row["lap_number"]) in excluded:
                row["eligible"] = False
                row["exclusions"].append(f"context_window_red2_sc{window}")
    return [describe_stint(s["rows"]) for s in current]


def influence(rows: list[dict]) -> dict | None:
    """Largest absolute slope change after removing one lap, for paired estimators."""
    full = fit_trend(rows)
    if not full:
        return None
    reduced = [fit_trend(rows[:i] + rows[i + 1 :]) for i in range(len(rows))]
    if any(f is None for f in reduced):
        return None
    return {
        name: max(abs(f[key] - full[key]) for f in reduced)
        for name, key in (
            ("ols", "slope_ms_per_age_lap"),
            ("robust", "robust_slope_ms_per_age_lap"),
        )
    }


def transfer_benchmark(stints: list[dict]) -> list[dict]:
    """Leave one event out; target first five laps anchor only its intercept.

    Training slopes use other events exclusively. All three predictions share
    target laps and support. No clipping, no recalibration on future target laps.
    """
    results = []
    for target in sorted({s["session_id"] for s in stints}):
        for compound in DRY:
            train = [
                s
                for s in stints
                if s["session_id"] != target and s["compound"] == compound and s["fit"]
            ]
            groups = defaultdict(list)
            for s in train:
                groups[s["session_id"]].append(s["fit"])
            if len(groups) < 2:
                continue
            slopes = {
                name: median(median(f[key] for f in group) for group in groups.values())
                for name, key in (
                    ("ols", "slope_ms_per_age_lap"),
                    ("robust", "robust_slope_ms_per_age_lap"),
                )
            }
            slopes["constant"] = 0.0
            for s in stints:
                if (
                    s["session_id"] != target
                    or s["compound"] != compound
                    or not s["fit"]
                ):
                    continue
                rows = sorted(
                    (r for r in s["rows"] if r["eligible"]),
                    key=lambda r: r["lap_number"],
                )
                if len(rows) < 8 or fit_trend(rows[:5]) is None:
                    continue
                anchor, future = rows[:5], rows[5:]
                maes = {}
                for name, slope in slopes.items():
                    intercept = median(
                        r["lap_time_ms"] - slope * r["tyre_life_laps"] for r in anchor
                    )
                    maes[name] = sum(
                        abs(
                            r["lap_time_ms"] - (intercept + slope * r["tyre_life_laps"])
                        )
                        for r in future
                    ) / len(future)
                results.append(
                    dict(
                        session_id=target,
                        driver_id=s["driver_id"],
                        stint=s["stint"],
                        compound=compound,
                        training_sessions=sorted(groups),
                        anchor_laps=[r["lap_number"] for r in anchor],
                        test_laps=[r["lap_number"] for r in future],
                        slopes=slopes,
                        mae_ms=maes,
                    )
                )
    return results


def event_errors(rows: list[dict]) -> list[dict]:
    """One median error per event on a common set of target stints."""
    groups = defaultdict(list)
    for row in rows:
        groups[row["session_id"]].append(row)
    return [
        dict(
            session_id=sid,
            stints=len(group),
            test_laps=sum(len(r["test_laps"]) for r in group),
            **{
                name: median(r["mae_ms"][name] for r in group)
                for name in ("constant", "ols", "robust")
            },
        )
        for sid, group in sorted(groups.items())
    ]


def interval(values: list[float]) -> list[float] | None:
    """Fixed exploratory event bootstrap; never treat laps as independent."""
    if len(values) < 2:
        return None
    rng = Random(42)
    draws = sorted(median(rng.choices(values, k=len(values))) for _ in range(2000))

    def percentile(p):
        x = p * (len(draws) - 1)
        lo = int(x)
        return draws[lo] + (draws[min(lo + 1, len(draws) - 1)] - draws[lo]) * (x - lo)

    return [percentile(0.025), percentile(0.975)]


def compare_estimators(repository, *, session_ids, config) -> dict:
    """Follow the predeclared protocol; sensitivity cannot auto-select the primary."""
    baseline = analyze_tyres(repository, session_ids=session_ids, config=config)
    red, clear, audit, messages = {}, {}, {}, {}
    for sid in baseline["events"]:
        red[sid] = restart_times(
            [
                r.as_dict()
                for r in repository.records("session_status_events", session_id=sid)
            ]
        )
        audit[sid] = neutralizations(
            [
                r.as_dict()
                for r in repository.records("track_status_events", session_id=sid)
            ]
        )
        clear[sid] = [x["clear_ms"] for x in audit[sid]["releases"]]
        messages[sid] = [
            r.as_dict()
            for r in repository.records("race_control_messages", session_id=sid)
            if "SAFETY CAR" in (r["message"] or "").upper()
        ]
    reference = apply_windows(baseline["stints"], red, clear, 0)
    summaries = []
    for window in (0, 1, 2, 3, 5):
        current = apply_windows(baseline["stints"], red, clear, window)
        summaries.append(summarize(current, reference, window))
        if window == 2:
            primary = current
    diagnostics = []
    for s in primary:
        if not s["fit"]:
            continue
        value = influence([r for r in s["rows"] if r["eligible"]])
        diagnostics.append(
            dict(
                session_id=s["session_id"],
                driver_id=s["driver_id"],
                stint=s["stint"],
                compound=s["compound"],
                ols=s["fit"]["slope_ms_per_age_lap"],
                robust=s["fit"]["robust_slope_ms_per_age_lap"],
                influence=value,
            )
        )
    tests = transfer_benchmark(primary)
    errors = event_errors(tests)
    contrasts = {}
    for a, b in (("ols", "constant"), ("robust", "constant"), ("robust", "ols")):
        values = [e[a] - e[b] for e in errors]
        contrasts[f"{a}_minus_{b}"] = dict(
            median_ms=median(values) if values else None,
            interval_ms=interval(values),
            events_better=sum(v < 0 for v in values),
            events=len(values),
        )
    return dict(
        method="tyre-sc-estimator-study-v1",
        primary_window=2,
        baseline=baseline,
        red_resumes=red,
        track_audit=audit,
        messages=messages,
        summaries=summaries,
        primary_stints=primary,
        diagnostics=diagnostics,
        test_predictions=tests,
        event_errors=errors,
        contrasts=contrasts,
    )
