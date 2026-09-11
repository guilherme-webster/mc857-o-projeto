"""Source-independent geometry for drawing a circuit and its pit lane.

X/Y are unitless, uniformly scaled coordinates shared by both paths. Only the
track's cumulative distance is in metres; pit progress is a fraction, not a
distance or duration. These educational mocks do not define race physics.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class GeometryProvenance:
    """Trace an artifact without conflating data and software licences.

    An omitted upstream label stays None; the upstream data licence remains
    mandatory. Both the artifact and its manifest are identified by checksum.
    """

    source_name: str
    source_version: str
    source_year: int
    generated_on: date
    upstream: str | None
    upstream_data_license: str
    artifact_sha256: str
    manifest_sha256: str
    transformation: str


@dataclass(frozen=True, slots=True)
class TrackPoint:
    """One ordered centerline point, including the repeated closing endpoint."""

    sequence: int
    x_normalized: float
    y_normalized: float
    cumulative_distance_m: float


@dataclass(frozen=True, slots=True)
class PitLanePoint:
    """One entry-to-exit sample; service marks a representative stopping point."""

    sequence: int
    x_normalized: float
    y_normalized: float
    path_fraction: float
    is_service_point: bool


@dataclass(frozen=True, slots=True)
class TrackGeometry:
    """Validated paths linked to a canonical circuit and versioned independently.

    Source year describes the mock, not the historical race using it. A later
    season's geometry must never be presented as that race's verified layout.
    """

    circuit_id: str
    track_points: tuple[TrackPoint, ...]
    pit_lane_points: tuple[PitLanePoint, ...]
    track_source: GeometryProvenance
    pit_lane_source: GeometryProvenance

    @property
    def lap_length_m(self) -> float:
        """Return the source lap distance, not a length measured in normalized XY."""

        return self.track_points[-1].cumulative_distance_m
