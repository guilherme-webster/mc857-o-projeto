from __future__ import annotations

from app.schemas.responses import (
    BuildGridRequest,
    BuildGridResponse,
    CatalogEntryResponse,
    CatalogResponse,
    DriverAttributesResponse,
    EditGridAttributesRequest,
    GridEntryResponse,
    RunGridRequest,
)
from app.services import catalog
from fastapi import APIRouter

router = APIRouter(prefix="/catalog", tags=["Catalog"])


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
    return BuildGridResponse(
        size=len(pairs),
        seed=seed,
        grid=[
            GridEntryResponse(
                driver_id=entry.driver_id,
                driver_name=entry.driver_name,
                team_id=entry.team_id,
                team_name=entry.team_name,
                attributes=_attributes_response(attributes[entry.driver_id]),
            )
            for entry in pairs
        ],
    )


@router.post("/grid", response_model=BuildGridResponse)
def build_grid(request: BuildGridRequest) -> BuildGridResponse:
    pairs, attributes, used_seed = catalog.build_grid(
        request.size,
        mode=request.mode,
        manual_pair_ids=request.pair_ids,
        seed=request.seed,
    )
    return _grid_response(pairs, attributes, used_seed)


@router.get("/grid", response_model=BuildGridResponse)
def view_grid() -> BuildGridResponse:
    pairs, attributes, seed = catalog.read_current_grid()
    return _grid_response(pairs, attributes, seed)


@router.patch("/grid", response_model=BuildGridResponse)
def edit_grid_attributes(request: EditGridAttributesRequest) -> BuildGridResponse:
    pairs, attributes, seed = catalog.edit_current_grid(request.overrides)
    return _grid_response(pairs, attributes, seed)


@router.post("/grid/run")
def run_grid(request: RunGridRequest) -> dict:
    return catalog.run_grid(
        total_laps=request.setup.total_laps,
        track_id=request.setup.track_id,
        weather=request.setup.weather,
    )
