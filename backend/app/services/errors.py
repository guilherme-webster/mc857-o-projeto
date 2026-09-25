from __future__ import annotations

from fastapi import HTTPException, status

_REASON_STATUS = {
    "validation": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "source": status.HTTP_404_NOT_FOUND,
    "storage": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


class ETLError(RuntimeError):
    """Falha de ETL classificada por ``reason`` (validation/source/storage)."""

    def __init__(self, message: str, *, reason: str = "storage") -> None:
        super().__init__(message)
        self.reason = reason


class RaceLoadError(ETLError):
    pass


class HistoryBuildError(ETLError):
    pass


def http_from(error: ETLError, message: str, extra: dict | None = None) -> HTTPException:
    """Traduza um ETLError em HTTPException com corpo estruturado."""

    detail = {"reason": error.reason, "message": message, "detail": str(error)}
    if extra:
        detail.update(extra)
    return HTTPException(
        status_code=_REASON_STATUS.get(error.reason, status.HTTP_400_BAD_REQUEST),
        detail=detail,
    )
