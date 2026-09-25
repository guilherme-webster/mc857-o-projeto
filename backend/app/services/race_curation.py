from __future__ import annotations

import sqlite3

from app.config import CURRENT_RACE_DB, CURRENT_RACE_REPORT, RAW_SOURCE
from app.services.errors import RaceLoadError
from app.services.track_geometry import geometry_dataset


def load_race_into_current(race_id: int) -> dict[str, object]:

    from f1_simulator.adapters.datasets.mock_track_geometry import (
        MockTrackDatasetError,
    )
    from f1_simulator.adapters.datasets.trotman import (
        TrotmanDatasetAdapter,
        TrotmanDatasetError,
    )
    from f1_simulator.adapters.persistence.sqlite_race_data import (
        SQLiteRaceDataWriter,
    )
    from f1_simulator.application.etl import run_race_etl
    from f1_simulator.factories.race_data_factory import RaceDataValidationError
    from f1_simulator.factories.track_geometry_factory import (
        TrackGeometryValidationError,
    )

    if not RAW_SOURCE.exists():
        raise RaceLoadError(f"raw source not found: {RAW_SOURCE}", reason="source")

    def _run(geometry):
        return run_race_etl(
            TrotmanDatasetAdapter(RAW_SOURCE),
            SQLiteRaceDataWriter(),
            race_id,
            CURRENT_RACE_DB,
            CURRENT_RACE_REPORT,
            overwrite=True,
            geometry_dataset=geometry,
        )

    try:
        try:
            report = _run(geometry_dataset())
        except (MockTrackDatasetError, TrackGeometryValidationError):
            # Circuito sem geometria mapeada: repete sem geometria.
            report = _run(None)
    except RaceDataValidationError as error:
        raise RaceLoadError(str(error), reason="validation") from error
    except TrotmanDatasetError as error:
        raise RaceLoadError(str(error), reason="source") from error
    except (OSError, sqlite3.Error) as error:
        raise RaceLoadError(str(error), reason="storage") from error

    return report
