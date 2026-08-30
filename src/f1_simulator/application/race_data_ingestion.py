"""Source-independent articulation between dataset adapters and the domain."""

from __future__ import annotations

from f1_simulator.application.ports.race_data import RaceDatasetPort
from f1_simulator.domain.race_data import RaceData
from f1_simulator.factories.race_data_factory import RaceDataFactory


class RaceDataIngestionService:
    """Turn data supplied by any dataset adapter into canonical race data.

    This application service is the stable entry point for the rest of the
    system. Source-specific adapters stop at ``NormalizedRaceData``; the shared
    factory then applies the same identifiers and invariants to every source.
    Adding another dataset therefore does not require changes to this service,
    the domain model or persistence adapters.
    """

    def __init__(self, dataset: RaceDatasetPort) -> None:
        """Receive the dataset port explicitly so tests and adapters are swappable."""

        self._dataset = dataset

    def load_race(self, race_external_id: int) -> RaceData:
        """Normalize and validate one race before exposing it to consumers."""

        normalized = self._dataset.load_race(race_external_id)
        return RaceDataFactory.create(normalized)
