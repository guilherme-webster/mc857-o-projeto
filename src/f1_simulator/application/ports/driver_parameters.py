"""Python boundary between observational modeling and simulation setup."""

from typing import Protocol

from f1_simulator.domain.driver_parameters import DriverPaceParameters
from f1_simulator.domain.driver_profile import PaceContext


class DriverParametersProvider(Protocol):
    """Resolve an exact driver/team/context or raise ValueError; never default zero."""

    def parameters(
        self, driver_id: str, team_id: str, context: PaceContext
    ) -> DriverPaceParameters:
        """Return immutable, traceable parameters for a single-context experiment."""
        ...
