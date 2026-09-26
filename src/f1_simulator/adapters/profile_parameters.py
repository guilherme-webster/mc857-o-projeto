"""Translate a complete profiling run into scoped simulation parameters."""

from dataclasses import asdict
import hashlib
import json

from f1_simulator.application.profile_drivers import ProfileRun
from f1_simulator.domain.driver_parameters import DriverPaceParameters
from f1_simulator.domain.driver_profile import METHOD_VERSION, PaceContext
from f1_simulator.domain.teammates import context_reference


class ProfileParametersAdapter:
    """In-memory adapter; consumers never load CSV, SQLite or FastF1.

    The caller explicitly supplies permitted development sessions. Full field
    profiles are retained to verify the reference before selecting a driver.
    Aggregate ranking pace is never substituted for a context-specific effect.
    """

    def __init__(self, run: ProfileRun, *, allowed_sessions: tuple[str, ...]) -> None:
        if run.method_version != METHOD_VERSION:
            raise ValueError("unsupported profiling method")
        if (
            not run.session_ids
            or len(set(run.session_ids)) != len(run.session_ids)
            or not set(run.session_ids) <= set(allowed_sessions)
            or not run.source_reports_json
        ):
            raise ValueError(
                "run requires provenance and explicitly permitted sessions"
            )
        if len({p.driver_id for p in run.profiles}) != len(run.profiles):
            raise ValueError("duplicate driver profiles")
        if any(
            c.context.session_id not in run.session_ids
            for p in run.profiles
            for c in p.contexts
        ):
            raise ValueError("context outside source selection")
        self._run = run
        self._hash = hashlib.sha256(
            json.dumps(asdict(run), sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        self._manifests = tuple(
            sorted(
                hashlib.sha256(s.encode()).hexdigest() for s in run.source_reports_json
            )
        )

    def parameters(
        self, driver_id: str, team_id: str, context: PaceContext
    ) -> DriverPaceParameters:
        """Reject missing/insufficient profiles, team changes and scope mismatch."""
        profile = next(
            (p for p in self._run.profiles if p.driver_id == driver_id), None
        )
        if profile is None or profile.unavailable_reason:
            raise ValueError("driver profile unavailable")
        if profile.events < self._run.config.min_events:
            raise ValueError("insufficient profile events")
        matches = [c for c in profile.contexts if c.context == context]
        if len(matches) != 1 or matches[0].team_id != team_id:
            raise ValueError("missing or incompatible driver/team/context")
        estimate = matches[0]
        reference = context_reference(self._run.profiles, context)
        return DriverPaceParameters(
            driver_id=driver_id,
            team_id=team_id,
            context=context,
            reference_lap_time_ms=reference["reference_lap_time_ms"],
            pace_offset_pct=estimate.pace_delta_pct,
            profile_method_version=self._run.method_version,
            source_sessions=self._run.session_ids,
            source_manifest_hashes=self._manifests,
            profile_run_sha256=self._hash,
            events=profile.events,
            contexts=len(profile.contexts),
            compared_laps=profile.compared_laps,
            context_laps=estimate.laps,
            warnings=(
                "observational_driver_team_effect",
                "single_context_not_prediction",
            )
            + (("few_events",) if profile.events < 5 else ()),
        )
