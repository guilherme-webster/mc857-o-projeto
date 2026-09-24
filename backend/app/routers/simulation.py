from __future__ import annotations

import json

from app.config import DEFAULT_RACE_DB, RACE_JSON, RACES_INDEX
from app.loaders.loader import load_driver_parameters, load_race_summary
from app.services.errors import ETLError, http_from
from app.services.race_curation import load_race_into_current
from app.services.race_simulation import simulate_current_race
from app.services.track_geometry import list_available_tracks, track_geometry_for
from app.schemas.responses import (
    DriverParametersResponse,
    LoadRaceRequest,
    LoadedDriversResponse,
    RaceCatalogEntry,
    RaceCatalogResponse,
    RaceDetailsResponse,
    RaceLoadErrorResponse,
    SeriesSimulationRequest,
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

    if not RACE_JSON.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Simulacao ainda nao gerada. Rode POST /simulation/simulate "
                "para produzir as posicoes da corrida."
            ),
        )

    try:
        with open(RACE_JSON, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except Exception as error:  # noqa: BLE001 - reporta erro de leitura ao cliente
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar dados da corrida: {error}",
        ) from error


@router.post("/simulate")
def simular_corrida() -> dict:

    return simulate_current_race()


@router.post("/series/simulate")
def simular_sequencia(request: SeriesSimulationRequest) -> dict:
    """Simule corridas livres nas pistas escolhidas, sem carregar uma corrida.

    Os comprimentos e nomes vêm do catálogo publicado pelo backend, nunca de
    valores arbitrários enviados pelo cliente. A ordem enviada é preservada.
    """

    from f1_simulator.domain.race_series import (
        SeriesCompetitor,
        SeriesTrack,
        simulate_series,
    )

    catalog = {
        track["circuit_id"]: track for track in list_available_tracks()["tracks"]
    }
    unknown = [
        track.circuit_id for track in request.tracks if track.circuit_id not in catalog
    ]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Pistas indisponíveis: {unknown}")
    tracks = tuple(
        SeriesTrack(
            circuit_id=item.circuit_id,
            name=catalog[item.circuit_id]["name"],
            lap_length_m=catalog[item.circuit_id]["lap_length_m"],
            total_laps=item.total_laps,
        )
        for item in request.tracks
    )
    competitors = tuple(
        SeriesCompetitor(item.driver_id, item.name, item.pace_ms_per_km)
        for item in request.competitors
    )
    try:
        return simulate_series(tracks, competitors)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/tracks")
def listar_pistas() -> dict:

    return list_available_tracks()


@router.get("/track/{circuit_id}")
def obter_geometria_pista_por_circuito(circuit_id: str) -> dict:

    return track_geometry_for(circuit_id)


@router.get("/drivers", response_model=LoadedDriversResponse)
def list_loaded_drivers() -> LoadedDriversResponse:

    try:
        parameters = load_driver_parameters(DEFAULT_RACE_DB)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error

    return LoadedDriversResponse(
        race_id=0,
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


_LOAD_ERROR_MESSAGE = {
    "validation": (
        "O ETL rejeitou a corrida {race_id}: a tabela de resultados nao passou "
        "na validacao de integridade."
    ),
    "source": (
        "Nao foi possivel ler a corrida {race_id} da fonte bruta: dados "
        "ausentes ou malformados no dataset."
    ),
    "storage": "Falha ao gravar a corrida {race_id} no armazenamento curado.",
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
    except ETLError as error:
        message = _LOAD_ERROR_MESSAGE.get(
            error.reason, "Nao foi possivel carregar a corrida {race_id}."
        ).format(race_id=request.race_id)
        raise http_from(error, message, {"race_id": request.race_id})

    summary = load_race_summary(DEFAULT_RACE_DB)
    return RaceDetailsResponse(**summary)
