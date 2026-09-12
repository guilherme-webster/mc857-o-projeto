"""Validate canonical historical facts without depending on source libraries."""

from __future__ import annotations

import math
from datetime import date, datetime, time
from collections.abc import Mapping

from f1_simulator.domain.history import HistoricalRecord, Scalar, Table


class HistoryValidationError(ValueError):
    """An adapter or persisted record violated the historical data contract."""


class HistoryFactory:
    """Construct immutable rows; persistence also checks keys and references.

    Types are exact: booleans cannot accidentally pass for integers, and NaN
    cannot masquerade as a measured float. Missing is distinct from false/zero.
    Cross-row invariants are checked transactionally by the writer because the
    full history and telemetry are streamed, rather than retained in memory.
    """

    @staticmethod
    def build(table: Table, row: Mapping[str, object]) -> HistoricalRecord:
        """Validate shape, finite values, bounds and ISO temporal representations."""
        if set(row) != set(table.names):
            raise HistoryValidationError(
                f"{table.name}: unexpected/missing fields: {set(row) ^ set(table.names)}"
            )
        fields: list[tuple[str, Scalar]] = []
        for column in table.columns:
            value = row[column.name]
            label = f"{table.name}.{column.name}"
            if value is None:
                if not column.nullable or column.name in table.key:
                    raise HistoryValidationError(f"{label}: null is not allowed")
            else:
                kind = column.kind
                if kind in ("int", "float"):
                    types = (int,) if kind == "int" else (int, float)
                    if type(value) not in types or not math.isfinite(value):
                        raise HistoryValidationError(f"{label}: expected finite {kind}")
                    if column.minimum is not None and value < column.minimum:
                        raise HistoryValidationError(f"{label}: below {column.minimum}")
                    if column.maximum is not None and value > column.maximum:
                        raise HistoryValidationError(f"{label}: above {column.maximum}")
                elif kind == "bool":
                    if type(value) is not bool:
                        raise HistoryValidationError(f"{label}: expected boolean")
                else:
                    if not isinstance(value, str) or not value.strip():
                        raise HistoryValidationError(f"{label}: expected nonempty text")
                    try:
                        if kind == "date":
                            date.fromisoformat(value)
                        elif kind == "time":
                            time.fromisoformat(value)
                        elif kind == "datetime":
                            parsed = datetime.fromisoformat(value)
                            if parsed.tzinfo is None:
                                raise ValueError("timezone required")
                    except ValueError as error:
                        raise HistoryValidationError(
                            f"{label}: invalid ISO {kind}: {value}"
                        ) from error
            fields.append((column.name, value))
        return HistoricalRecord(table.name, tuple(fields))
