from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


NormalizedRow: TypeAlias = dict[str, object]


@dataclass(frozen=True, slots=True)
class NormalizedRaceData:
    """Primitive, normalized rows exchanged by an Adapter and a Factory."""

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
