"""Streaming acquisition and consumption boundaries for multi-event history."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Protocol

from f1_simulator.domain.history import HistoricalRecord, Scalar, Table


class HistoryDataset(Protocol):
    """A source supplies normalized rows and an auditable manifest.

    Adapters may update coverage in the manifest while their iterators are
    consumed. The writer records the final manifest only after all tables pass.
    """

    tables: tuple[Table, ...]
    manifest: dict[str, object]

    def rows(self, table: str) -> Iterable[Mapping[str, object]]:
        """Yield canonical fields for a named table without constructing models."""
        ...


class HistoryWriter(Protocol):
    """Publish validated history and its embedded quality report together."""

    def write(
        self,
        tables: tuple[Table, ...],
        records: Iterable[HistoricalRecord],
        manifest: dict[str, object],
        destination: Path,
        *,
        overwrite: bool = False,
        base: Path | None = None,
    ) -> dict[str, object]:
        """Publish a complete database, optionally enriching a copy of a base."""
        ...


class HistoryRepository(Protocol):
    """Query canonical facts using whitelisted fields, never SQL or dataframes."""

    def records(self, table: str, **filters: Scalar) -> Iterator[HistoricalRecord]:
        """Yield records in key order matching exact canonical field values."""
        ...

    def reports(self) -> list[dict[str, object]]:
        """Return provenance and quality reports associated with the observations."""
        ...
