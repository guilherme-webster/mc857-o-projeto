"""Build matched teammate evidence through canonical Python repositories."""

from dataclasses import asdict
import hashlib
import json

from f1_simulator.application.ports.history import HistoryRepository
from f1_simulator.application.profile_drivers import profile_drivers
from f1_simulator.domain.driver_profile import ProfileConfig
from f1_simulator.domain.profile_reliability import BootstrapConfig
from f1_simulator.domain.teammates import compare_teammates, context_reference


def analyze_teammates(
    repository: HistoryRepository,
    *,
    session_ids: tuple[str, ...],
    config: ProfileConfig,
    bootstrap: BootstrapConfig = BootstrapConfig(),
) -> dict:
    """Use explicitly selected races; reject event aliases and ambiguous rosters.

    The shared contexts inherit the original field support gate (three drivers
    in the current config), not a relaxed two-driver eligibility rule.
    """
    memberships, seen_races = [], set()
    for session in sorted(session_ids):
        sessions = tuple(repository.records("sessions", session_id=session))
        if len(sessions) != 1 or sessions[0]["kind"] != "R":
            raise ValueError("select unique race sessions")
        race = sessions[0]["race_id"]
        if race in seen_races:
            raise ValueError("a race must not appear through multiple session aliases")
        seen_races.add(race)
        roster = {
            r["driver_id"]
            for r in repository.records("session_drivers", session_id=session)
        }
        entries = {}
        for entry in repository.records("race_results", race_id=race):
            driver = entry["driver_id"]
            if driver in roster:
                if driver in entries:
                    raise ValueError("ambiguous event team")
                entries[driver] = entry["team_id"]
        if set(entries) != roster:
            raise ValueError("missing event team")
        memberships.extend(
            (session, team, driver) for driver, team in sorted(entries.items())
        )
    run = profile_drivers(repository, session_ids=session_ids, config=config)
    pairs = compare_teammates(run.profiles, tuple(memberships), config, bootstrap)
    keys = sorted({c.context for p in run.profiles for c in p.contexts})
    references = tuple(context_reference(run.profiles, key) for key in keys)
    settings = dict(
        method_version="shared-teammate-context-v1",
        session_ids=run.session_ids,
        config=asdict(config),
        bootstrap=asdict(bootstrap),
    )
    digest = hashlib.sha256(
        json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return dict(
        settings=settings,
        analysis_sha256=digest,
        run=asdict(run),
        pairs=pairs,
        team_names=tuple(
            sorted((r["team_id"], r["name"]) for r in repository.records("teams"))
        ),
        context_references=references,
        interpretation="observed matched teammate comparison; not isolated skill or new validation",
    )
