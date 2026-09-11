"""Simulation-facing HTTP endpoints.

This router is a backend adapter: it exposes race telemetry and the simulation
inputs derived from the ETL. It reaches the ETL only through the engine loader,
so the engine stays independent of HTTP and SQLite (see ADR 0002).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.config import DATA_DIR, DEFAULT_RACE_DB
from app.engine.loader import load_driver_parameters
from app.schemas.simulation import DriverParametersResponse, LoadedDriversResponse
from fastapi import APIRouter, HTTPException, Query, status

router = APIRouter(prefix="/simulation", tags=["Simulation"])


@router.get("/race")
def obter_dados_corrida() -> dict:
    """Retorna a telemetria da corrida a partir do arquivo JSON versionado."""

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
def list_loaded_drivers(
    race_id: Optional[int] = Query(
        default=None,
        description="raceId curado a carregar; usa o banco padrao quando omitido.",
    ),
    limit: Optional[int] = Query(
        default=None,
        ge=1,
        description="Limita a quantidade de pilotos retornados.",
    ),
) -> LoadedDriversResponse:
    """Retorna todos os pilotos carregados do ETL com seus atributos de simulacao.

    Le o banco curado da corrida pelo loader do motor e expoe os parametros
    derivados por piloto. Pilotos que nao correram aparecem com
    ``base_lap_time_ms`` igual a ``null``. Retorna 404 quando o banco solicitado
    nao existe, para que o cliente distinga um dataset ausente de um vazio.
    """

    db_path = DEFAULT_RACE_DB if race_id is None else DATA_DIR / f"race-{race_id}.sqlite"
    try:
        parameters = load_driver_parameters(db_path, limit=limit)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error

    if race_id is not None:
        resolved_race_id = race_id
    else:
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
