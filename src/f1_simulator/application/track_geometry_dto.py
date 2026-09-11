"""Primitive, normalized geometry exchanged by adapters and the factory."""

from dataclasses import dataclass

from f1_simulator.application.race_data_dto import NormalizedRow


@dataclass(frozen=True, slots=True)
class NormalizedTrackGeometry:
    """Paths in shared normalized XY; track distances in m, pit progress in [0,1]."""

    circuit_id: str
    track_points: tuple[NormalizedRow, ...]
    pit_lane_points: tuple[NormalizedRow, ...]
    track_source: NormalizedRow
    pit_lane_source: NormalizedRow
