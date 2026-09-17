"""Geometry ingestion and retrieval boundaries, independent of CSV and SQLite."""

from typing import Protocol

from f1_simulator.application.track_geometry_dto import NormalizedTrackGeometry
from f1_simulator.domain.track_geometry import TrackGeometry


class TrackGeometryRepositoryError(RuntimeError):
    """A canonical geometry could not be read or failed validation."""


class TrackGeometryNotFoundError(TrackGeometryRepositoryError):
    """The database has no geometry for the requested circuit."""


class TrackGeometryDatasetPort(Protocol):
    """Translate a reduced geometry source to the canonical circuit identifier."""

    def load_geometry(self, circuit_id: str) -> NormalizedTrackGeometry:
        """Return normalized data, or fail explicitly when the circuit is absent."""
        ...


class TrackGeometryRepository(Protocol):
    """Provide complete validated paths without exposing storage to consumers."""

    def get_geometry(self, circuit_id: str) -> TrackGeometry:
        """Return geometry or raise a geometry repository error."""
        ...
