"""Normalized transfer objects shared by dataset adapters and the factory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


NormalizedRow: TypeAlias = dict[str, object]


@dataclass(frozen=True, slots=True)
class NormalizedRaceData:
    """Source-independent primitive rows exchanged by adapters and the factory.

    Dataset adapters must convert column names, null markers, dates and units to
    this contract. Values intentionally remain mappings here: the factory is the
    shared boundary that validates them and creates typed domain entities.
    Durations are milliseconds, coordinates are degrees and altitude is metres.
    """

    source_name: str
    source_version: int
    source_sha256: str | None
    circuit: NormalizedRow
    race: NormalizedRow
    drivers: tuple[NormalizedRow, ...]
    teams: tuple[NormalizedRow, ...]
    entries: tuple[NormalizedRow, ...]
    laps: tuple[NormalizedRow, ...]
    pit_stops: tuple[NormalizedRow, ...]
