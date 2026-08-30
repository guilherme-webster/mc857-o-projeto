from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from f1_simulator.adapters.datasets.trotman import TrotmanDatasetAdapter
from f1_simulator.adapters.persistence.sqlite_race_data import SQLiteRaceDataWriter
from f1_simulator.domain.race_data import RaceData
from f1_simulator.factories.race_data_factory import RaceDataFactory


def run_trotman_etl(
    source: Path,
    race_external_id: int,
    destination: Path,
    report_destination: Path,
    *,
    overwrite: bool = False,
) -> dict[str, object]:
    normalized = TrotmanDatasetAdapter(source).load_race(race_external_id)
    race_data = RaceDataFactory.create(normalized)
    report = build_quality_report(race_data)
    SQLiteRaceDataWriter().write(race_data, destination, overwrite=overwrite)
    try:
        _write_report(report, report_destination, overwrite=overwrite)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return report


def build_quality_report(data: RaceData) -> dict[str, object]:
    long_pit_stops = sum(
        1
        for stop in data.pit_stops
        if stop.duration_ms is not None and stop.duration_ms > 300_000
    )
    return {
        "source": {
            "name": data.source_name,
            "version": data.source_version,
            "sha256": data.source_sha256,
        },
        "race": {
            "race_id": data.race.race_id,
            "name": data.race.name,
            "season": data.race.season,
            "circuit_id": data.circuit.circuit_id,
            "circuit_name": data.circuit.name,
        },
        "row_counts": {
            "circuits": 1,
            "races": 1,
            "drivers": len(data.drivers),
            "teams": len(data.teams),
            "race_entries": len(data.entries),
            "laps": len(data.laps),
            "pit_stops": len(data.pit_stops),
        },
        "null_counts": {
            "circuits.altitude_m": int(data.circuit.altitude_m is None),
            "drivers.code": sum(driver.code is None for driver in data.drivers),
            "race_entries.finish_position": sum(
                entry.finish_position is None for entry in data.entries
            ),
            "race_entries.elapsed_time_ms": sum(
                entry.elapsed_time_ms is None for entry in data.entries
            ),
            "pit_stops.duration_ms": sum(
                stop.duration_ms is None for stop in data.pit_stops
            ),
        },
        "duplicate_keys": 0,
        "orphan_references": 0,
        "warnings": {
            "pit_stops_over_300_seconds": long_pit_stops,
        },
    }


def _write_report(
    report: dict[str, object], destination: Path, *, overwrite: bool
) -> None:
    destination = destination.resolve()
    if destination.exists() and not overwrite:
        raise FileExistsError(f"quality report already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
