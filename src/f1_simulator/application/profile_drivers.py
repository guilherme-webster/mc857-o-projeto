"""Build observational profiles through the existing canonical Python port."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

from f1_simulator.application.ports.history import HistoryRepository
from f1_simulator.domain.driver_profile import (
    METHOD_VERSION,
    DriverProfile,
    LapAssessment,
    ProfileConfig,
    assess_session,
    estimate_profiles,
)


@dataclass(frozen=True)
class ProfileRun:
    """Reproducible result with complete selection, settings and source manifests.

    Source reports are canonical JSON strings so callers cannot mutate nested
    provenance in an otherwise frozen result. They contain acquisition dates,
    transforms and canonical checksums; no wall-clock run time affects equality.
    """

    method_version: str
    config: ProfileConfig
    session_ids: tuple[str, ...]
    source_reports_json: tuple[str, ...]
    profiles: tuple[DriverProfile, ...]
    laps: tuple[LapAssessment, ...]
    uncertainty: str = "not_estimated; sample counts are not confidence intervals"
    interpretation: str = (
        "descriptive driver/team performance; not isolated skill or prediction"
    )
    driver_names: tuple[tuple[str, str], ...] = ()


def profile_drivers(
    repository: HistoryRepository,
    *,
    session_ids: tuple[str, ...],
    config: ProfileConfig,
) -> ProfileRun:
    """Profile all participants in explicitly selected race sessions, offline.

    Qualifying is rejected instead of mixing incomparable Q1/Q2/Q3 and race
    laps. Team identity comes from the event's canonical race results; missing
    or multiple entries stay unavailable rather than choosing an arbitrary car.
    A full historical database without enrichment gets a clear input error.
    """
    if not session_ids or len(set(session_ids)) != len(session_ids):
        raise ValueError("select a nonempty set of distinct race session IDs")
    selected = tuple(sorted(session_ids))
    reports = repository.reports()
    session_sources = {r["source"].get("session_id"): r["source"] for r in reports}
    available = set(session_sources)
    if not set(selected) <= available:
        raise ValueError(
            "selected sessions lack ETL provenance; enrich the history first"
        )
    laps = []
    drivers = set()
    for session_id in selected:
        sessions = tuple(repository.records("sessions", session_id=session_id))
        if len(sessions) != 1 or sessions[0]["kind"] != "R":
            raise ValueError(f"{session_id}: initial profiling supports race (R) only")
        race_id = sessions[0]["race_id"]
        races = tuple(repository.records("races", race_id=race_id))
        if len(races) != 1:
            raise ValueError(f"{session_id}: missing or ambiguous canonical race")
        race = races[0]
        participants = tuple(
            repository.records("session_drivers", session_id=session_id)
        )
        session_drivers = {r["driver_id"] for r in participants}
        drivers.update(session_drivers)
        entries = defaultdict(list)
        for entry in repository.records("race_results", race_id=race_id):
            entries[entry["driver_id"]].append(entry["team_id"])
        teams = {d: ts[0] for d, ts in entries.items() if len(ts) == 1}
        observations = tuple(
            repository.records("lap_observations", session_id=session_id)
        )
        if any(r["driver_id"] not in session_drivers for r in observations):
            raise ValueError("lap references a driver absent from the session")
        laps.extend(
            assess_session(
                session_id=session_id,
                race_id=race_id,
                season=race["season"],
                circuit_id=race["circuit_id"],
                laps=observations,
                weather=tuple(
                    repository.records("weather_observations", session_id=session_id)
                ),
                session_status=tuple(
                    repository.records("session_status_events", session_id=session_id)
                ),
                teams=teams,
                config=config,
                lap_schema_complete=(
                    session_sources[session_id]
                    .get("missing_columns", {})
                    .get("lap_observations")
                    == []
                ),
            )
        )
    profiles, audit = estimate_profiles(tuple(laps), tuple(drivers), config)
    # Names are display metadata from the canonical catalog, never join keys.
    # Missing names retain the ID as a diagnostic fallback for older datasets.
    names = {}
    for driver in repository.records("drivers"):
        if driver["driver_id"] in drivers:
            name = " ".join(
                str(driver[field] or "").strip()
                for field in ("given_name", "family_name")
            ).strip()
            if name:
                names[driver["driver_id"]] = name
    relevant = [
        r
        for r in reports
        if r["source"].get("session_id") in selected
        or r["source"].get("scope") == "complete_snapshot"
    ]
    return ProfileRun(
        METHOD_VERSION,
        config,
        selected,
        tuple(
            sorted(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in relevant)
        ),
        profiles,
        audit,
        driver_names=tuple(sorted(names.items())),
    )
