from __future__ import annotations

import json
import os
import sqlite3
import tempfile

from app.config import (
    CURRENT_RACE_DB,
    CURRENT_RACE_REPORT,
    DEFAULT_RACE_DB,
    RACE_JSON,
    RAW_SOURCE,
)
from fastapi import HTTPException, status


def get_db_connection() -> sqlite3.Connection:

    if not DEFAULT_RACE_DB.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Arquivo {DEFAULT_RACE_DB} não encontrado no volume.",
        )
    conn = sqlite3.connect(f"file:{DEFAULT_RACE_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def validate_table_exists(conn: sqlite3.Connection, table_name: str) -> None:

    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    )
    if not cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tabela '{table_name}' não existe no banco de dados.",
        )


class RaceLoadError(RuntimeError):

    def __init__(self, message: str, *, reason: str = "storage") -> None:
        super().__init__(message)
        self.reason = reason


def _geometry_artifacts() -> tuple:
    """Retorne (track_csv, track_manifest, pit_csv, pit_manifest) da config."""

    from app.config import (
        GEOMETRY_PIT_LANE_POINTS,
        GEOMETRY_PIT_MANIFEST,
        GEOMETRY_TRACK_MANIFEST,
        GEOMETRY_TRACK_POINTS,
    )

    return (
        GEOMETRY_TRACK_POINTS,
        GEOMETRY_TRACK_MANIFEST,
        GEOMETRY_PIT_LANE_POINTS,
        GEOMETRY_PIT_MANIFEST,
    )


def _geometry_dataset():

    from f1_simulator.adapters.datasets.mock_track_geometry import (
        MockTrackDatasetAdapter,
    )

    artifacts = _geometry_artifacts()
    if not all(path.exists() for path in artifacts):
        return None
    return MockTrackDatasetAdapter(*artifacts)


def _geometry_payload(geometry) -> dict:
    """Serialize uma TrackGeometry no formato JSON consumido pelo frontend."""

    return {
        "circuit_id": geometry.circuit_id,
        "lap_length_m": geometry.lap_length_m,
        "track_points": [
            {
                "sequence": p.sequence,
                "x": p.x_normalized,
                "y": p.y_normalized,
                "cumulative_distance_m": p.cumulative_distance_m,
            }
            for p in geometry.track_points
        ],
    }


def list_available_tracks() -> dict:
    """Liste os circuitos com geometria disponivel, direto do manifesto.

    Independente do ETL: le apenas o manifesto de pistas para oferecer ao
    usuario as pistas que ele pode visualizar (id canonico, nome e comprimento).
    """

    import json as _json

    _, track_manifest, _, _ = _geometry_artifacts()
    if not track_manifest.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Manifesto de geometria nao encontrado: {track_manifest.name}.",
        )
    try:
        manifest = _json.loads(track_manifest.read_text(encoding="utf-8"))
        events = manifest["source"]["events"]
    except (OSError, ValueError, KeyError) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Manifesto de geometria invalido: {error}",
        ) from error

    tracks = [
        {
            "circuit_id": f"circuit:{event['circuit_id']}",
            "name": event.get("circuit_name"),
            "lap_length_m": event.get("lap_length_m"),
        }
        for event in events
    ]
    tracks.sort(key=lambda t: t["circuit_id"])
    return {"count": len(tracks), "tracks": tracks}


def track_geometry_for(circuit_id: str) -> dict:
    """Retorne a geometria de qualquer circuito, sem depender do ETL carregado.

    Le a geometria direto da fonte reduzida (ADR 0003) via adaptador + factory,
    entao o usuario pode visualizar qualquer pista mapeada mesmo sem ter curado
    a corrida correspondente. Aceita ``circuit:<id>`` ou apenas ``<id>``.
    """

    from f1_simulator.adapters.datasets.mock_track_geometry import (
        MockTrackDatasetAdapter,
        MockTrackDatasetError,
    )
    from f1_simulator.factories.track_geometry_factory import (
        TrackGeometryFactory,
        TrackGeometryValidationError,
    )

    canonical = circuit_id if circuit_id.startswith("circuit:") else f"circuit:{circuit_id}"

    artifacts = _geometry_artifacts()
    if not all(path.exists() for path in artifacts):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artefatos de geometria nao encontrados no volume /data/geometry.",
        )

    adapter = MockTrackDatasetAdapter(*artifacts)
    try:
        normalized = adapter.load_geometry(canonical)
        geometry = TrackGeometryFactory.build(normalized)
    except (MockTrackDatasetError, TrackGeometryValidationError) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Geometria indisponivel para {canonical}: {error}",
        ) from error

    return _geometry_payload(geometry)


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
        geometry = _geometry_dataset()
        try:
            report = _run(geometry)
        except (MockTrackDatasetError, TrackGeometryValidationError):
           report = _run(None)
    except RaceDataValidationError as error:
        raise RaceLoadError(str(error), reason="validation") from error
    except TrotmanDatasetError as error:
        raise RaceLoadError(str(error), reason="source") from error
    except (OSError, sqlite3.Error) as error:
        raise RaceLoadError(str(error), reason="storage") from error

    return report


def _total_laps(db_path) -> int:

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT MAX(lap_number) FROM laps").fetchone()
    finally:
        connection.close()
    return int(row[0]) if row and row[0] else 1


def _current_circuit_id(db_path) -> str:

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT circuit_id FROM races LIMIT 1").fetchone()
    finally:
        connection.close()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Banco curado nao contem corrida.",
        )
    return row[0]


def current_track_geometry() -> dict:

    from f1_simulator.adapters.persistence.sqlite_track_geometry import (
        SQLiteTrackGeometryRepository,
    )
    from f1_simulator.application.ports.track_geometry import (
        TrackGeometryNotFoundError,
        TrackGeometryRepositoryError,
    )

    if not DEFAULT_RACE_DB.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Banco curado ({DEFAULT_RACE_DB.name}) nao encontrado. "
                "Rode POST /simulation/load antes de pedir a geometria."
            ),
        )

    circuit_id = _current_circuit_id(DEFAULT_RACE_DB)
    repository = SQLiteTrackGeometryRepository(DEFAULT_RACE_DB)
    try:
        geometry = repository.get_geometry(circuit_id)
    except TrackGeometryNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"A corrida atual ({circuit_id}) nao tem geometria de pista. "
                "Carregue uma corrida de um circuito com geometria mapeada."
            ),
        ) from error
    except TrackGeometryRepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error

    return _geometry_payload(geometry)


def simulate_current_race() -> dict:

    from app.engine.loader import load_driver_parameters
    from f1_simulator.domain.race_simulation import Competitor, simulate_race

    if not DEFAULT_RACE_DB.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Banco curado ({DEFAULT_RACE_DB.name}) nao encontrado. "
                "Rode POST /simulation/load antes de simular."
            ),
        )

    parameters = load_driver_parameters(DEFAULT_RACE_DB)
    competitors = tuple(
        Competitor(p.driver_id, p.name, float(p.base_lap_time_ms))
        for p in parameters
        if p.base_lap_time_ms is not None
    )
    result = simulate_race(competitors, _total_laps(DEFAULT_RACE_DB))

    _write_json_atomic(RACE_JSON, result)
    return result


def _write_json_atomic(destination, payload: dict) -> None:

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(name, destination)
    except Exception:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise
