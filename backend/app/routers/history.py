from __future__ import annotations

import json

from app.history_store import (
    HistoryBuildError,
    build_history,
    get_history_connection,
    validate_history_table,
)
from app.schemas.responses import HistoryBuildErrorResponse, HistoryBuildResponse
from fastapi import APIRouter, HTTPException, Query, status

router = APIRouter(prefix="/api/history", tags=["Historical Archive (ETL B)"])


_BUILD_ERROR_STATUS = {
    "validation": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "source": status.HTTP_404_NOT_FOUND,
    "storage": status.HTTP_500_INTERNAL_SERVER_ERROR,
}

_BUILD_ERROR_MESSAGE = {
    "validation": (
        "O ETL historico rejeitou a importacao: alguma linha violou o contrato "
        "do esquema historico durante a validacao."
    ),
    "source": (
        "Nao foi possivel ler o dataset bruto do Trotman: arquivo ausente ou "
        "malformado. Gere-o com scripts/download_trotman.py."
    ),
    "storage": "Falha ao gravar o banco historico no armazenamento curado.",
}


@router.post(
    "/build",
    response_model=HistoryBuildResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": HistoryBuildErrorResponse},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": HistoryBuildErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": HistoryBuildErrorResponse},
    },
)
def build_history_database() -> HistoryBuildResponse:

    try:
        report = build_history()
    except HistoryBuildError as error:
        http_status = _BUILD_ERROR_STATUS.get(
            error.reason, status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        message = _BUILD_ERROR_MESSAGE.get(
            error.reason, "Nao foi possivel gerar o banco historico."
        )
        raise HTTPException(
            status_code=http_status,
            detail=HistoryBuildErrorResponse(
                reason=error.reason, message=message, detail=str(error)
            ).model_dump(),
        ) from error

    return HistoryBuildResponse(
        schema_version=int(report["schema_version"]),
        row_counts={k: int(v) for k, v in report["row_counts"].items()},
        canonical_sha256=str(report["canonical_sha256"]),
    )


@router.get("/tables")
def list_history_tables() -> dict:

    connection = get_history_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name;"
        )
        names = [row["name"] for row in cursor.fetchall()]
        tables = []
        for name in names:
            count = cursor.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            tables.append({"name": name, "rows": count})
    finally:
        connection.close()
    return {"tables": tables, "count": len(tables)}


@router.get("/schema/{table_name}")
def get_history_table_schema(table_name: str) -> dict:

    connection = get_history_connection()
    try:
        validate_history_table(connection, table_name)
        cursor = connection.cursor()
        cursor.execute(f'PRAGMA table_info("{table_name}");')
        columns = [
            {
                "column_id": row[0],
                "name": row[1],
                "type": row[2],
                "notnull": bool(row[3]),
            }
            for row in cursor.fetchall()
        ]
    finally:
        connection.close()
    return {"table": table_name, "columns": columns}


@router.get("/preview/{table_name}")
def preview_history_table(
    table_name: str,
    limit: int = Query(
        default=10, ge=1, le=1000, description="Quantidade de linhas a retornar"
    ),
) -> dict:

    connection = get_history_connection()
    try:
        validate_history_table(connection, table_name)
        cursor = connection.cursor()
        cursor.execute(f'SELECT * FROM "{table_name}" LIMIT ?', (limit,))
        rows = [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()
    return {"table": table_name, "count": len(rows), "data": rows}


@router.get("/reports")
def list_history_reports() -> dict:

    connection = get_history_connection()
    try:
        validate_history_table(connection, "imports")
        cursor = connection.cursor()
        cursor.execute("SELECT report_json FROM imports ORDER BY import_key")
        reports = [json.loads(row[0]) for row in cursor.fetchall()]
    finally:
        connection.close()
    return {"count": len(reports), "reports": reports}
