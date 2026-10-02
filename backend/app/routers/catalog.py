from __future__ import annotations

from app.schemas.responses import (
    BuildGridRequest,
    BuildGridResponse,
    CatalogEntryResponse,
    CatalogResponse,
    GridEntryResponse,
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


@router.post("/grid", response_model=BuildGridResponse)
def build_grid(request: BuildGridRequest) -> BuildGridResponse:
    grid, used_seed = catalog.build_grid(
        request.size,
        mode=request.mode,
        manual_pair_ids=request.pair_ids,
        seed=request.seed,
    )
    return BuildGridResponse(
        size=request.size,
        seed=used_seed,
        grid=[
            GridEntryResponse(
                driver_id=entry.driver_id,
                driver_name=entry.driver_name,
                team_id=entry.team_id,
                team_name=entry.team_name,
            )
            for entry in grid
        ],
    )
