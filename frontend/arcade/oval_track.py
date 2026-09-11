"""Geometry for a fictional stadium-shaped ("oval") test track.

This module intentionally contains no Arcade or rendering calls, so the
geometry is testable without a window or GPU (same rule the hexagonal
architecture applies to the simulation engine, in ``AGENTS.md``).

The Trotman dataset used by the MVP has no track geometry at all (see ADR
0002): only a single latitude/longitude point per circuit. Real circuit
tracing is a separate, still-open decision. This oval is a deliberately
fictional placeholder circuit so the race screen can be built and reviewed
before that decision is made; it must not be mistaken for a real circuit
layout.

The track is a "stadium" shape: two straight segments joined by two
semicircular turns, all sharing one centerline. Because the shape is a
simple analytic curve (unlike an arbitrary traced circuit), a car's
position can be computed exactly from the distance it has travelled,
without needing to sample the curve into a polyline and interpolate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OvalTrack:
    """A stadium-shaped centerline: two straights plus two semicircle turns.

    ``center_x``/``center_y`` place the track's geometric center.
    ``straight_length`` is the length of each straight segment.
    ``radius`` is the centerline radius of each semicircular turn.
    ``track_width`` is only used to offset the centerline outward or inward
    when drawing the road surface; it does not affect lap distance.
    """

    center_x: float
    center_y: float
    straight_length: float
    radius: float
    track_width: float

    def __post_init__(self) -> None:
        """Reject a track that could not be drawn or lapped meaningfully."""

        if self.straight_length <= 0:
            raise ValueError("straight_length must be positive")
        if self.radius <= 0:
            raise ValueError("radius must be positive")
        if self.track_width <= 0:
            raise ValueError("track_width must be positive")

    @property
    def right_turn_center(self) -> tuple[float, float]:
        """Return the center of curvature of the right-hand semicircle."""

        return (self.center_x + self.straight_length / 2, self.center_y)

    @property
    def left_turn_center(self) -> tuple[float, float]:
        """Return the center of curvature of the left-hand semicircle."""

        return (self.center_x - self.straight_length / 2, self.center_y)

    @property
    def perimeter(self) -> float:
        """Return one lap's length: two straights plus one full circle."""

        return 2 * self.straight_length + 2 * math.pi * self.radius

    def position_at_fraction(
        self, fraction: float, radial_offset: float = 0.0
    ) -> tuple[float, float]:
        """Return the (x, y) point at ``fraction`` of one lap, in [0, 1).

        ``fraction`` wraps around automatically, so callers can pass an
        ever-increasing lap-progress value without normalising it first.
        ``radial_offset`` moves the point outward (positive) or inward
        (negative) from the centerline, perpendicular to the direction of
        travel; it is what lets the same geometry produce the centerline,
        the outer edge and the inner edge of the road.
        """

        distance = (fraction % 1.0) * self.perimeter
        return self.position_at_distance(distance, radial_offset)

    def position_at_distance(
        self, distance: float, radial_offset: float = 0.0
    ) -> tuple[float, float]:
        """Return the (x, y) point ``distance`` units into one lap.

        The lap is walked counter-clockwise starting at the midpoint of the
        bottom straight, in four segments, in order: bottom straight, right
        turn, top straight, left turn. ``radial_offset`` is added to the
        straight's distance from the track center, or to the turn's radius,
        which keeps it consistently "outward" across all four segments.
        """

        distance %= self.perimeter
        half_circle = math.pi * self.radius

        if distance <= self.straight_length:
            # Bottom straight, travelled left to right.
            x = self.center_x - self.straight_length / 2 + distance
            y = self.center_y - self.radius - radial_offset
            return (x, y)
        distance -= self.straight_length

        if distance <= half_circle:
            # Right turn, swept counter-clockwise from the bottom (-90deg)
            # to the top (+90deg) of the right turn's circle.
            angle = -math.pi / 2 + (distance / self.radius)
            turn_x, turn_y = self.right_turn_center
            effective_radius = self.radius + radial_offset
            return (
                turn_x + effective_radius * math.cos(angle),
                turn_y + effective_radius * math.sin(angle),
            )
        distance -= half_circle

        if distance <= self.straight_length:
            # Top straight, travelled right to left.
            x = self.center_x + self.straight_length / 2 - distance
            y = self.center_y + self.radius + radial_offset
            return (x, y)
        distance -= self.straight_length

        # Left turn, swept counter-clockwise from the top (+90deg) to the
        # bottom (+270deg, i.e. -90deg) of the left turn's circle.
        angle = math.pi / 2 + (distance / self.radius)
        turn_x, turn_y = self.left_turn_center
        effective_radius = self.radius + radial_offset
        return (
            turn_x + effective_radius * math.cos(angle),
            turn_y + effective_radius * math.sin(angle),
        )

    def centerline_points(self, samples: int) -> list[tuple[float, float]]:
        """Return ``samples`` evenly spaced points along the centerline."""

        return [
            self.position_at_fraction(index / samples) for index in range(samples)
        ]

    def road_quads(
        self, samples: int
    ) -> list[tuple[
        tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]
    ]]:
        """Return small quads tiling the road surface, ready to fill.

        The road is a ring (an annulus), which is a concave shape: filling
        it as a single polygon is unreliable, because polygon fill
        algorithms generally assume convexity and will draw wrong
        triangles across the hole. Tiling the ring into many small quads
        between consecutive outer/inner sample points sidesteps that,
        since each quad on its own is convex enough to fill correctly.
        """

        half_width = self.track_width / 2
        outer = [
            self.position_at_fraction(index / samples, radial_offset=half_width)
            for index in range(samples)
        ]
        inner = [
            self.position_at_fraction(index / samples, radial_offset=-half_width)
            for index in range(samples)
        ]
        quads = []
        for index in range(samples):
            next_index = (index + 1) % samples
            quads.append(
                (
                    outer[index],
                    outer[next_index],
                    inner[next_index],
                    inner[index],
                )
            )
        return quads
