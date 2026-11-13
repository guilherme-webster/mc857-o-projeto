from __future__ import annotations

import json
import queue
import threading

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.responses import (
    BuildGridRequest,
    BuildGridResponse,
    CatalogEntryResponse,
    CatalogResponse,
    DriverAttributesResponse,
    DriverProfileResponse,
    EditGridAttributesRequest,
    GridEntryResponse,
    RunGridRequest,
)
from app.services import catalog
from app.services.cancellation import Cancellation, SimulationCancelled

router = APIRouter(prefix="/catalog", tags=["Catalog"])

_running: dict[str, Cancellation] = {}
_running_lock = threading.Lock()


@router.get("", response_model=CatalogResponse)
def list_catalog() -> CatalogResponse:
    entries = catalog.list_entries()
    return CatalogResponse(
        count=len(entries),
        entries=[
            CatalogEntryResponse(
                driver_id=item.driver_id,
                driver_name=item.driver_name,
                driver_code=item.driver_code,
                team_id=item.team_id,
                team_name=item.team_name,
            )
            for item in entries
        ],
    )


def _attributes_response(item) -> DriverAttributesResponse:
    return DriverAttributesResponse(
        archetype=item.archetype,
        pace_offset_pct=item.pace_offset_pct,
        consistency_factor=item.consistency_factor,
        tyre_management_factor=item.tyre_management_factor,
        aggression=item.aggression,
        composure=item.composure,
        sources=dict(item.sources),
    )


def _grid_response(pairs, attributes, seed) -> BuildGridResponse:
    """Grid com o perfil ficticio de quem tem atributo de origem ``preset``.

    O perfil so aparece quando foi de fato aplicado: um piloto com perfil no
    arquivo mas sem nenhum campo ``preset`` (por exemplo, apos editar todos
    manualmente) nao exibe uma caracterizacao que ja nao o descreve.
    """

    profiles, disclaimer = catalog.driver_profiles()
    entries = []
    for entry in pairs:
        item = attributes[entry.driver_id]
        preset = profiles.get(entry.driver_id)
        applied = preset is not None and "preset" in item.sources.values()
        entries.append(
            GridEntryResponse(
                driver_id=entry.driver_id,
                driver_name=entry.driver_name,
                team_id=entry.team_id,
                team_name=entry.team_name,
                attributes=_attributes_response(item),
                profile=(
                    DriverProfileResponse(
                        characterization=preset.characterization,
                        parameter_version=preset.parameter_version,
                    )
                    if applied
                    else None
                ),
            )
        )
    return BuildGridResponse(
        size=len(pairs),
        seed=seed,
        grid=entries,
        profiles_disclaimer=(
            disclaimer if any(entry.profile for entry in entries) else None
        ),
    )


@router.post("/grid", response_model=BuildGridResponse)
def build_grid(request: BuildGridRequest) -> BuildGridResponse:
    pairs, attributes, used_seed = catalog.build_grid(
        request.size,
        mode=request.mode,
        manual_pair_ids=request.pair_ids,
        seed=request.seed,
        race_id=request.race_id,
    )
    return _grid_response(pairs, attributes, used_seed)


@router.get("/grid", response_model=BuildGridResponse)
def view_grid() -> BuildGridResponse:
    pairs, attributes, seed = catalog.read_current_grid()
    return _grid_response(pairs, attributes, seed)


@router.patch("/grid", response_model=BuildGridResponse)
def edit_grid_attributes(request: EditGridAttributesRequest) -> BuildGridResponse:
    pairs, attributes, seed = catalog.edit_current_grid(
        overrides=request.overrides,
        order=request.order,
    )
    return _grid_response(pairs, attributes, seed)


@router.post("/grid/run")
def run_grid(request: RunGridRequest) -> dict:
    arguments = {
        "total_laps": request.setup.total_laps,
        "track_id": request.setup.track_id,
        "weather": request.setup.weather,
    }
    if request.setup.tournament_seed is not None or request.setup.stage_index != 0:
        arguments["tournament_seed"] = request.setup.tournament_seed
        arguments["stage_index"] = request.setup.stage_index
    return catalog.run_grid(**arguments)


def _sse(event: str, data: dict) -> str:
    """Formate um evento SSE: uma linha ``event:`` e uma ``data:`` com JSON."""

    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/grid/run/stream/{run_id}/cancel")
def cancel_grid_run(run_id: str) -> dict:
    """Cancela uma execução ativa; 409 indica resultado já publicado."""
    with _running_lock:
        cancellation = _running.get(run_id)
    if cancellation is None:
        raise HTTPException(status_code=404, detail="simulation not running")
    if not cancellation.cancel():
        raise HTTPException(status_code=409, detail="simulation already completed")
    return {"cancelled": True}


@router.post("/grid/run/stream")
def run_grid_stream(
    request: RunGridRequest, x_run_id: str | None = Header(default=None)
) -> StreamingResponse:
    """Rode a corrida transmitindo o progresso por volta via SSE.

    A simulacao roda numa thread e empurra ``(lap, total)`` numa fila a cada
    volta; o gerador consome a fila e emite eventos ``progress``, fechando com
    ``done`` (resultado completo) ou ``error``. O motor so recebe um callback
    puro; HTTP e SSE ficam nesta borda.
    """

    arguments = {
        "total_laps": request.setup.total_laps,
        "track_id": request.setup.track_id,
        "weather": request.setup.weather,
    }
    if request.setup.tournament_seed is not None or request.setup.stage_index != 0:
        arguments["tournament_seed"] = request.setup.tournament_seed
        arguments["stage_index"] = request.setup.stage_index

    cancellation = Cancellation()
    if x_run_id is not None:
        with _running_lock:
            if x_run_id in _running:
                raise HTTPException(status_code=409, detail="simulation id already in use")
            _running[x_run_id] = cancellation

    events: queue.Queue = queue.Queue()
    _DONE = object()

    def on_progress(lap: int, total: int) -> None:
        events.put(("progress", {"lap": lap, "total": total}))

    def worker() -> None:
        try:
            result = catalog.run_grid(
                on_progress=on_progress, cancellation=cancellation, **arguments
            )
        except SimulationCancelled:
            events.put(("cancelled", {}))
        except Exception as error:  # a borda traduz qualquer falha em evento
            events.put(("error", {"detail": str(error)}))
        else:
            events.put(("done", result))
        finally:
            if x_run_id is not None:
                with _running_lock:
                    _running.pop(x_run_id, None)
            events.put((_DONE, None))

    def stream():
        thread = threading.Thread(target=worker, name="race-sse", daemon=True)
        thread.start()
        try:
            yield _sse("started", {})
            while True:
                kind, data = events.get()
                if kind is _DONE:
                    break
                yield _sse(kind, data)
        finally:
            cancellation.cancel()

    return StreamingResponse(stream(), media_type="text/event-stream")
