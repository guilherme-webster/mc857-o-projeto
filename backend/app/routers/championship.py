from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status

from app.schemas.responses import (
    ChampionshipRequest,
    ChampionshipResponse,
    ChampionshipRowResponse,
)

router = APIRouter(prefix="/championship", tags=["Championship"])


@router.post("/standings", response_model=ChampionshipResponse)
def championship_standings(request: ChampionshipRequest) -> ChampionshipResponse:
    """Classificacao de um torneio a partir da chegada de cada etapa.

    A regra de pontos e desempate e de dominio
    (``f1_simulator.domain.championship``); o endpoint so valida o formato e
    converte erros de consistencia (posicoes repetidas, etapa vazia) em 422.
    """

    from f1_simulator.domain.championship import (
        StageResult,
        championship_standings as compute,
    )

    stages = [
        [StageResult(e.driver_id, e.position, e.retired) for e in stage]
        for stage in request.stages
    ]
    try:
        rows = compute(stages, scoring=request.scoring, tiebreak=request.tiebreak)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return ChampionshipResponse(
        scoring=request.scoring,
        tiebreak=request.tiebreak,
        rows=[ChampionshipRowResponse(**asdict(row)) for row in rows],
    )
