"""Persistencia dos torneios salvos em JSON, fora do Git (ADR 0013).

Cada torneio e um arquivo ``<id>.json`` em ``SAVED_TOURNAMENTS_DIR``, escrito
de forma atomica pelo mesmo ``_write_json`` das corridas salvas. As invariantes
do registro ficam no nucleo (``application/saved_tournament.py``); este modulo
so le e grava arquivos, congela o grid atual e traduz erros para HTTP.
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime

from fastapi import HTTPException, status

from app.config import CURRENT_GRID_JSON, SAVED_TOURNAMENTS_DIR
from app.services import catalog


def save_tournament(request) -> dict:
    """Congele o grid atual junto das etapas ja simuladas e grave o torneio.

    O grid congelado e o ``current-grid.json`` no momento do pedido. O nucleo
    confere que as corridas foram simuladas com ele; se o usuario editou ou
    remontou o grid depois de simular, o pedido e recusado com 409 em vez de
    salvar um cenario que nao reproduz os resultados guardados.
    """

    from f1_simulator.application.saved_tournament import (
        SavedTournamentError,
        build_saved_tournament,
        tournament_summary,
    )

    grid_state = _current_grid_state()
    tournament_id = f"{catalog._slug(request.name)}-{secrets.token_hex(3)}"
    try:
        record = build_saved_tournament(
            tournament_id=tournament_id,
            name=request.name,
            saved_at=datetime.now(UTC).isoformat(),
            grid_state=grid_state,
            rules=request.rules,
            tournament_seed=request.tournament_seed,
            stages=[
                {
                    "name": stage.name,
                    "circuit_id": stage.circuit_id,
                    "plan": stage.plan,
                    "setup": stage.setup.model_dump(),
                    "race": stage.race,
                }
                for stage in request.stages
            ],
        )
    except SavedTournamentError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    catalog._write_json(SAVED_TOURNAMENTS_DIR / f"{tournament_id}.json", record)
    return tournament_summary(record)


def list_saved_tournaments() -> list[dict]:
    """Resumo de cada torneio legivel, do mais recente ao mais antigo.

    Arquivos corrompidos ou de outra versao sao ignorados na listagem, como nas
    corridas salvas; abri-los diretamente devolve o erro detalhado.
    """

    from f1_simulator.application.saved_tournament import (
        SavedTournamentError,
        check_saved_tournament,
        tournament_summary,
    )

    if not SAVED_TOURNAMENTS_DIR.exists():
        return []
    saved = []
    for path in SAVED_TOURNAMENTS_DIR.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            check_saved_tournament(record)
            saved.append(tournament_summary(record))
        except (OSError, ValueError, KeyError, TypeError, SavedTournamentError):
            continue
    saved.sort(key=lambda item: item["saved_at"], reverse=True)
    return saved


def read_saved_tournament(tournament_id: str) -> dict:
    """Registro completo, com as corridas; reabrir nao simula nada."""

    from f1_simulator.application.saved_tournament import check_saved_tournament

    path = SAVED_TOURNAMENTS_DIR / f"{catalog._safe_id(tournament_id)}.json"
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"saved tournament not found: {tournament_id}",
        )
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        check_saved_tournament(record)
    except (OSError, ValueError) as error:
        # ``SavedTournamentError`` tambem e ``ValueError``: formato invalido no
        # disco e falha do servidor, nao do pedido.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error
    return record


def restore_tournament_grid(tournament_id: str):
    """Torne o grid congelado o grid atual, preparando a reexecucao.

    Passa pelo mesmo ``_deserialize_grid`` do grid atual, que recusa (409) um
    esquema de atributos antigo, e regrava o estado atomicamente.
    """

    record = read_saved_tournament(tournament_id)
    pairs, attributes, seed = catalog._deserialize_grid(record["grid"])
    catalog._write_current_grid(pairs, attributes, seed)
    return pairs, attributes, seed


def _current_grid_state() -> dict:
    """Estado bruto do grid atual, conferido pelo mesmo leitor do backend."""

    catalog.read_current_grid()
    try:
        return json.loads(CURRENT_GRID_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error
