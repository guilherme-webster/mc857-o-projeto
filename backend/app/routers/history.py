from __future__ import annotations

from app.schemas.responses import HistoryBuildErrorResponse, HistoryBuildResponse
from app.services import history
from app.services.errors import ETLError, http_from
from fastapi import APIRouter, Query, status

router = APIRouter(prefix="/api/history", tags=["Historical Archive (ETL B)"])

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
        report = history.build_history()
    except ETLError as error:
        message = _BUILD_ERROR_MESSAGE.get(
            error.reason, "Nao foi possivel gerar o banco historico."
        )
        raise http_from(error, message)

    return HistoryBuildResponse(
        schema_version=int(report["schema_version"]),
        row_counts={k: int(v) for k, v in report["row_counts"].items()},
        canonical_sha256=str(report["canonical_sha256"]),
    )


@router.get("/tables")
def list_history_tables() -> dict:
    return history.list_tables()


@router.get("/schema/{table_name}")
def get_history_table_schema(table_name: str) -> dict:
    return history.table_schema(table_name)


@router.get("/preview/{table_name}")
def preview_history_table(
    table_name: str,
    limit: int = Query(default=10, ge=1, le=1000),
) -> dict:
    return history.preview_table(table_name, limit)


@router.get("/reports")
def list_history_reports() -> dict:
    return history.list_reports()
