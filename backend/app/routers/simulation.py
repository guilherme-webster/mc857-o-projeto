from __future__ import annotations

import json

from app.config import CURRENT_RACE_JSON
from app.services.track_geometry import list_available_tracks, track_geometry_for
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/simulation", tags=["Simulation"])


@router.get("/race")
def obter_dados_corrida() -> dict:

    if not CURRENT_RACE_JSON.exists():
        raise HTTPException(
            status_code=404,
            detail="no current race; run POST /catalog/grid/run to produce one",
        )

    try:
        with open(CURRENT_RACE_JSON, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"error reading race data: {error}",
        ) from error


@router.get("/tracks")
def listar_pistas() -> dict:

    return list_available_tracks()


@router.get("/track/{circuit_id}")
def obter_geometria_pista_por_circuito(circuit_id: str) -> dict:

    return track_geometry_for(circuit_id)
