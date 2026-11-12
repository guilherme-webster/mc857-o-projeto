from __future__ import annotations

from fastapi import APIRouter

from app.config import DEFAULT_RACE_DB

router = APIRouter(tags=["Health"])


@router.get("/")
def health_check() -> dict:

    return {"status": "online", "etl_db_found": DEFAULT_RACE_DB.exists()}
