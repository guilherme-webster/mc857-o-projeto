from __future__ import annotations

import json
from pathlib import Path

from app.config import DEFAULT_RACE_DB, RACES_INDEX
from app.engine.loader import load_driver_parameters, load_race_summary
from app.race_store import RaceLoadError, load_race_into_current
from app.schemas.responses import (
    DriverParametersResponse,
    LoadRaceRequest,
    LoadedDriversResponse,
    RaceCatalogEntry,
    RaceCatalogResponse,
    RaceDetailsResponse,
    RaceLoadErrorResponse,
)
from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/simulation", tags=["Simulation"])


@router.get("/races", response_model=RaceCatalogResponse)
def list_races() -> RaceCatalogResponse:

    try:
        with open(RACES_INDEX, "r", encoding="utf-8") as stream:
            races = json.load(stream)
    except (FileNotFoundError, json.JSONDecodeError):
        races = []

    return RaceCatalogResponse(
        count=len(races),
        races=[
            RaceCatalogEntry(
                race_id=race["race_id"],
                name=race["name"],
                year=race["year"],
                round=race["round"],
                date=race["date"],
            )
            for race in races
        ],
    )


@router.get("/race")
def obter_dados_corrida() -> dict:

    data_file_path = Path(__file__).resolve().parent / "../../races/race.json"
    if not data_file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Arquivo de telemetria da corrida não encontrado.",
        )

    try:
        with open(data_file_path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except Exception as error:  # noqa: BLE001 - reporta erro de leitura ao cliente
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar dados da corrida: {error}",
        ) from error


@router.get("/drivers", response_model=LoadedDriversResponse)
def list_loaded_drivers() -> LoadedDriversResponse:

    db_path = DEFAULT_RACE_DB
    try:
        parameters = load_driver_parameters(db_path)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error

    # Extrai o id do nome "race-<id>.sqlite"; usa 0 quando o padrao difere.
    _, _, tail = db_path.stem.partition("race-")
    resolved_race_id = int(tail) if tail.isdigit() else 0

    return LoadedDriversResponse(
        race_id=resolved_race_id,
        count=len(parameters),
        drivers=[
            DriverParametersResponse(
                driver_id=item.driver_id,
                name=item.name,
                team_id=item.team_id,
                grid_position=item.grid_position,
                base_lap_time_ms=item.base_lap_time_ms,
                degradation_ms_per_lap=item.degradation_ms_per_lap,
                pit_loss_ms=item.pit_loss_ms,
                retirement_per_lap=item.retirement_per_lap,
            )
            for item in parameters
        ],
    )


@router.get("/details", response_model=RaceDetailsResponse)
def race_details() -> RaceDetailsResponse:

    try:
        summary = load_race_summary(DEFAULT_RACE_DB)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error

    return RaceDetailsResponse(**summary)


_LOAD_ERROR_STATUS = {
    "validation": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "source": status.HTTP_404_NOT_FOUND,
    "storage": status.HTTP_500_INTERNAL_SERVER_ERROR,
}

_LOAD_ERROR_MESSAGE = {
    "validation": (
        "O ETL rejeitou a corrida {race_id}: a tabela de resultados nao passou "
        "na validacao de integridade"
    ),
    "source": (
        "Nao foi possivel ler a corrida {race_id} da fonte bruta: dados "
        "ausentes ou malformados no dataset."
    ),
    "storage": (
        "Falha ao gravar a corrida {race_id} no armazenamento curado."
    ),
}


@router.post(
    "/load",
    response_model=RaceDetailsResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": RaceLoadErrorResponse},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": RaceLoadErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": RaceLoadErrorResponse},
    },
)
def load_race(request: LoadRaceRequest) -> RaceDetailsResponse:

    try:
        load_race_into_current(request.race_id)
    except RaceLoadError as error:
        http_status = _LOAD_ERROR_STATUS.get(
            error.reason, status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        message = _LOAD_ERROR_MESSAGE.get(
            error.reason,
            "Nao foi possivel carregar a corrida {race_id}.",
        ).format(race_id=request.race_id)
        raise HTTPException(
            status_code=http_status,
            detail=RaceLoadErrorResponse(
                reason=error.reason,
                message=message,
                race_id=request.race_id,
                detail=str(error),
            ).model_dump(),
        ) from error

    summary = load_race_summary(DEFAULT_RACE_DB)
    return RaceDetailsResponse(**summary)
