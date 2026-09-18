"""Minimal core consumer for the specified deterministic one-lap experiment."""

from f1_simulator.application.ports.driver_parameters import DriverParametersProvider
from f1_simulator.domain.driver_parameters import LapTime, deterministic_lap_time
from f1_simulator.domain.driver_profile import PaceContext


def simulate_profile_lap(
    provider: DriverParametersProvider,
    *,
    driver_id: str,
    team_id: str,
    context: PaceContext,
) -> LapTime:
    """Consume the Python port without knowing profiling, database or HTTP.

    A provider cannot silently substitute another participant or scope. This
    microexperiment has no traffic, tyre evolution, noise or repeated-lap clock.
    """
    parameters = provider.parameters(driver_id, team_id, context)
    if (parameters.driver_id, parameters.team_id, parameters.context) != (
        driver_id,
        team_id,
        context,
    ):
        raise ValueError("provider returned incompatible parameters")
    return deterministic_lap_time(parameters)
