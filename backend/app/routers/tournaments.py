"""Rotas dos torneios salvos: salvar, listar, reabrir e preparar a reexecucao.

A reexecucao em si nao tem rota propria: depois de ``restore-grid``, o cliente
reenvia o ``setup`` salvo de cada etapa a ``POST /catalog/grid/run``, o mesmo
caminho de uma simulacao nova (ADR 0013).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.routers.catalog import _grid_response
from app.schemas.responses import (
    BuildGridResponse,
    SavedTournamentMeta,
    SavedTournamentsResponse,
    SaveTournamentRequest,
)
from app.services import tournaments

router = APIRouter(prefix="/tournaments", tags=["Tournaments"])


@router.post("", response_model=SavedTournamentMeta)
def save_tournament(request: SaveTournamentRequest) -> SavedTournamentMeta:
    return SavedTournamentMeta(**tournaments.save_tournament(request))


@router.get("", response_model=SavedTournamentsResponse)
def list_tournaments() -> SavedTournamentsResponse:
    saved = tournaments.list_saved_tournaments()
    return SavedTournamentsResponse(
        count=len(saved),
        saved=[SavedTournamentMeta(**item) for item in saved],
    )


@router.get("/{tournament_id}")
def open_tournament(tournament_id: str) -> dict:
    return tournaments.read_saved_tournament(tournament_id)


@router.post("/{tournament_id}/restore-grid", response_model=BuildGridResponse)
def restore_grid(tournament_id: str) -> BuildGridResponse:
    pairs, attributes, seed = tournaments.restore_tournament_grid(tournament_id)
    return _grid_response(pairs, attributes, seed)
