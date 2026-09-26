"""Compose normalized sources, shared validation and atomic historical storage."""

from pathlib import Path

from f1_simulator.application.ports.history import HistoryDataset, HistoryWriter
from f1_simulator.factories.history_factory import HistoryFactory


def run_history_etl(
    dataset: HistoryDataset,
    writer: HistoryWriter,
    destination: Path,
    *,
    overwrite: bool = False,
    base: Path | None = None,
) -> dict[str, object]:
    """Stream a complete import and publish only after all records validate.

    Enrichment receives a base snapshot explicitly. The application never opens
    SQLite, imports FastF1 or chooses vendor field mappings. A report embedded
    in the same artifact prevents mismatched database/report pairs on failure.
    """
    records = (
        HistoryFactory.build(table, row)
        for table in dataset.tables
        for row in dataset.rows(table.name)
    )
    return writer.write(
        dataset.tables,
        records,
        dataset.manifest,
        destination,
        overwrite=overwrite,
        base=base,
    )
