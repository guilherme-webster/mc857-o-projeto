"""Sensitivity to operational Aborted→Started windows, not calibrated exclusions."""

from collections import defaultdict
from copy import deepcopy
from statistics import median

from f1_simulator.application.analyze_tyres import analyze_tyres, describe_stint, DRY


def restart_times(statuses: list[dict]) -> tuple[int, ...]:
    """Detect resumed sessions, excluding initial starts and repeated Started rows.

    Missing clocks or conflicting simultaneous statuses fail explicitly. This
    does not detect SC/VSC restarts while the session remains Started.
    """
    by_time = defaultdict(set)
    for row in statuses:
        if row["session_time_ms"] is None:
            raise ValueError("session status clock missing")
        by_time[row["session_time_ms"]].add(row["status"])
    # Finished/Finalised/Ends may legitimately share a timestamp. Only conflicts
    # involving the states used to infer a restart are ambiguous here.
    pending = False
    resumed = []
    for time, values in sorted(by_time.items()):
        if len(values) > 1 and values & {"Aborted", "Started"}:
            raise ValueError("ambiguous restart status")
        if "Aborted" in values:
            pending = True
        elif "Started" in values:
            if pending:
                resumed.append(time)
            pending = False
        elif values & {"Finished", "Finalised", "Ends"}:
            pending = False
    return tuple(resumed)


def mark_windows(rows: list[dict], resumes: tuple[int, ...]) -> list[dict]:
    """Mark offsets from each driver's first recorded lap starting after resume.

    Anchor before quality filtering, preserve lap-number gaps and never reset at
    a tyre change. The latest restart supersedes the previous window. A lap
    spanning the timestamp is recorded separately, never counted as first full
    post-resume lap. No recorded candidate yields no invented anchor.
    """
    groups = defaultdict(list)
    for row in rows:
        groups[row["driver_id"]].append(row)
    marks = []
    for driver, laps in sorted(groups.items()):
        for i, time in enumerate(resumes):
            end = resumes[i + 1] if i + 1 < len(resumes) else float("inf")
            candidates = [
                r
                for r in laps
                if r["lap_start_ms"] is not None and time <= r["lap_start_ms"] < end
            ]
            anchor = (
                min(candidates, key=lambda r: (r["lap_start_ms"], r["lap_number"]))
                if candidates
                else None
            )
            marks.append(
                dict(
                    driver_id=driver,
                    resume_ms=time,
                    anchor_lap=anchor["lap_number"] if anchor else None,
                )
            )
            for row in laps:
                start, finish = row["lap_start_ms"], row["session_time_ms"]
                if start is not None and finish is not None and start < time < finish:
                    row.setdefault("spans_resumes", []).append(time)
                if anchor and start is not None and time <= start < end:
                    row["restart_offset"] = row["lap_number"] - anchor["lap_number"] + 1
                    row["resume_ms"] = time
    return marks


def _median(values):
    values = list(values)
    return median(values) if values else None


def summarize(stints: list[dict], baseline: list[dict], window: int) -> dict:
    """Summaries preserve both surviving coverage and paired changes in estimates."""
    slopes = []
    for compound in DRY:
        current = [s for s in stints if s["compound"] == compound and s["fit"]]
        paired = [
            (b, s)
            for b, s in zip(baseline, stints)
            if b["compound"] == compound and b["fit"] and s["fit"]
        ]
        slopes.append(
            dict(
                compound=compound,
                fitted_stints=len(current),
                paired_stints=len(paired),
                negative=sum(s["fit"]["slope_ms_per_age_lap"] < 0 for s in current),
                median_slope=_median(s["fit"]["slope_ms_per_age_lap"] for s in current),
                paired_median_change=_median(
                    s["fit"]["slope_ms_per_age_lap"] - b["fit"]["slope_ms_per_age_lap"]
                    for b, s in paired
                ),
                sign_changes=sum(
                    (s["fit"]["slope_ms_per_age_lap"] < 0)
                    != (b["fit"]["slope_ms_per_age_lap"] < 0)
                    for b, s in paired
                ),
            )
        )
    early = []
    for compound in DRY:
        for fresh in (True, False):
            events = defaultdict(list)
            for s in stints:
                if (
                    s["compound"] == compound
                    and s["fresh_tyre"] == fresh
                    and s["start_kind"] == "post_pit"
                    and s["early_minus_later_ms"] is not None
                ):
                    events[s["session_id"]].append(s["early_minus_later_ms"])
            early.append(
                dict(
                    compound=compound,
                    fresh=fresh,
                    stints=sum(map(len, events.values())),
                    events=len(events),
                    event_median_ms=_median(median(v) for v in events.values()),
                )
            )
    return dict(
        window=window,
        eligible_laps=sum(s["eligible_laps"] for s in stints),
        fitted_stints=sum(s["fit"] is not None for s in stints),
        slopes=slopes,
        early=early,
    )


def analyze_restarts(repository, *, session_ids, config) -> dict:
    """Keep the original analysis intact; vary only restart-window exclusions.

    Windows 0/1/2/3/5 are exploratory sensitivity choices, not a learned rule.
    Clockless laps retain existing quality exclusions rather than imputation.
    """
    baseline = analyze_tyres(repository, session_ids=session_ids, config=config)
    resumes, marks = {}, []
    stints = deepcopy(baseline["stints"])
    for sid in baseline["events"]:
        times = restart_times(
            [
                r.as_dict()
                for r in repository.records("session_status_events", session_id=sid)
            ]
        )
        resumes[sid] = times
        rows = [r for s in stints if s["session_id"] == sid for r in s["rows"]]
        marks.extend(dict(session_id=sid, **m) for m in mark_windows(rows, times))
    variants = []
    changes = []
    for window in (0, 1, 2, 3, 5):
        current = []
        for original in stints:
            rows = deepcopy(original["rows"])
            for row in rows:
                offset = row.get("restart_offset")
                if window and (
                    row.get("spans_resumes")
                    or (offset is not None and 1 <= offset <= window)
                ):
                    row["eligible"] = False
                    row["exclusions"].append(f"restart_window_{window}")
            updated = describe_stint(rows)
            current.append(updated)
            if resumes[original["session_id"]]:
                changes.append(
                    dict(
                        window=window,
                        session_id=updated["session_id"],
                        driver_id=updated["driver_id"],
                        stint=updated["stint"],
                        compound=updated["compound"],
                        eligible_laps=updated["eligible_laps"],
                        fit=updated["fit"],
                        early_minus_later_ms=updated["early_minus_later_ms"],
                    )
                )
        variants.append(summarize(current, stints, window))
    return dict(
        method="tyre-restart-sensitivity-v1",
        baseline=baseline,
        marked_stints=stints,
        resumes=resumes,
        anchors=marks,
        summaries=variants,
        changes=changes,
    )
