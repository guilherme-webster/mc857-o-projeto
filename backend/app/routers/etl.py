from __future__ import annotations

from app.services import race_inspection
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/etl", tags=["Race Inspector (ETL A)"])


@router.get("/tables")
def list_tables() -> dict:
    tables = race_inspection.list_tables()
    return {"tables": tables, "count": len(tables)}


@router.get("/schema/{table_name}")
def get_table_schema(table_name: str) -> dict:
    return race_inspection.table_schema(table_name)


@router.get("/preview/{table_name}")
def preview_table_data(
    table_name: str,
    limit: int = Query(default=10, ge=1, le=1000),
) -> dict:
    return race_inspection.preview_table(table_name, limit)


@router.get("/table/{table_name}")
def get_full_table(table_name: str) -> dict:
    return race_inspection.full_table(table_name)


@router.get("/database/dump")
def dump_entire_database() -> dict:
    return race_inspection.dump_database()
