"""Ports used by the race-data ingestion use case.

The application owns these contracts. Dataset and persistence adapters depend
on them, which keeps source-specific schemas and storage technology outside the
application core.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from f1_simulator.application.race_data_dto import NormalizedRaceData
from f1_simulator.domain.race_data import RaceData


class RaceDatasetPort(Protocol):
    """Load one external race into the source-independent normalized contract.

    A new dataset adapter only needs to translate its schema, null markers and
    units into :class:`NormalizedRaceData`. It must not construct domain objects
    or persist results; those responsibilities remain shared across sources.
    """

    def load_race(self, race_external_id: int) -> NormalizedRaceData:
        """Return normalized rows for one external race identifier."""

        ...


class RaceDataWriterPort(Protocol):
    """Persist a validated canonical race without knowing its source schema."""

    def write(
        self, race_data: RaceData, destination: Path, *, overwrite: bool = False
    ) -> None:
        """Write all canonical entities to ``destination`` atomically."""

        ...
