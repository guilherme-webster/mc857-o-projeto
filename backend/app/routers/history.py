from __future__ import annotations

from app.schemas.responses import (
    HistoryBuildErrorResponse,
    HistoryBuildResponse,
    HistoryRaceResponse,
    HistoryRacesResponse,
)
from app.services import history
from app.services.errors import ETLError, http_from
from fastapi import APIRouter, Query, status

router = APIRouter(prefix="/api/history", tags=["Historical Archive (ETL B)"])

_BUILD_ERROR_MESSAGE = {
    "validation": (
        "history ETL rejected the import: a row violated the history schema "
        "contract during validation"
    ),
    "source": (
        "could not read the raw Trotman dataset: file missing or malformed; "
        "generate it with scripts/download_trotman.py"
    ),
    "storage": "failed to write the history database to curated storage",
}


@router.post(
    "/build",
    response_model=HistoryBuildResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": HistoryBuildErrorResponse},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": HistoryBuildErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": HistoryBuildErrorResponse},
    },
)
def build_history_database() -> HistoryBuildResponse:
    try:
        report = history.build_history()
    except ETLError as error:
        message = _BUILD_ERROR_MESSAGE.get(
            error.reason, "could not build the history database"
        )
        raise http_from(error, message)

    return HistoryBuildResponse(
        schema_version=int(report["schema_version"]),
        row_counts={k: int(v) for k, v in report["row_counts"].items()},
        canonical_sha256=str(report["canonical_sha256"]),
    )


@router.get("/tables")
def list_history_tables() -> dict:
    return history.list_tables()


@router.get("/schema/{table_name}")
def get_history_table_schema(table_name: str) -> dict:
    return history.table_schema(table_name)


@router.get("/preview/{table_name}")
def preview_history_table(
    table_name: str,
    limit: int = Query(default=10, ge=1, le=1000),
) -> dict:
    return history.preview_table(table_name, limit)


@router.get("/reports")
def list_history_reports() -> dict:
    return history.list_reports()


@router.get("/races", response_model=HistoryRacesResponse)
def list_history_races() -> HistoryRacesResponse:
    races = history.list_races()
    return HistoryRacesResponse(
        count=len(races),
        races=[
            HistoryRaceResponse(
                race_id=race.race_id,
                name=race.name,
                season=race.season,
                round_number=race.round_number,
                circuit_id=race.circuit_id,
                race_date=race.race_date,
                start_time_utc=race.start_time_utc,
            )
            for race in races
        ],
    )
