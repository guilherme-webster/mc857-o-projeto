from __future__ import annotations

import math
import unittest

from frontend.arcade.oval_track import OvalTrack


def make_track() -> OvalTrack:
    return OvalTrack(
        center_x=400, center_y=300, straight_length=360, radius=190, track_width=70
    )


class OvalTrackPerimeterTest(unittest.TestCase):
    def test_perimeter_is_two_straights_plus_one_full_circle(self) -> None:
        track = make_track()

        expected = 2 * track.straight_length + 2 * math.pi * track.radius
        self.assertAlmostEqual(track.perimeter, expected)

    def test_rejects_non_positive_dimensions(self) -> None:
        with self.assertRaises(ValueError):
            OvalTrack(center_x=0, center_y=0, straight_length=0, radius=10, track_width=5)
        with self.assertRaises(ValueError):
            OvalTrack(center_x=0, center_y=0, straight_length=10, radius=0, track_width=5)
        with self.assertRaises(ValueError):
            OvalTrack(center_x=0, center_y=0, straight_length=10, radius=10, track_width=0)


class OvalTrackPositionTest(unittest.TestCase):
    def test_position_wraps_around_after_one_full_lap(self) -> None:
        track = make_track()

        start = track.position_at_fraction(0.0)
        after_one_lap = track.position_at_fraction(1.0)
        after_two_laps = track.position_at_fraction(2.0)

        self.assertAlmostEqual(start[0], after_one_lap[0])
        self.assertAlmostEqual(start[1], after_one_lap[1])
        self.assertAlmostEqual(start[0], after_two_laps[0])
        self.assertAlmostEqual(start[1], after_two_laps[1])

    def test_start_of_lap_sits_on_the_bottom_straight(self) -> None:
        track = make_track()

        x, y = track.position_at_fraction(0.0)

        self.assertAlmostEqual(y, track.center_y - track.radius)
        self.assertAlmostEqual(x, track.center_x - track.straight_length / 2)

    def test_segment_boundaries_are_continuous(self) -> None:
        """The four segments must meet exactly, with no jump between them."""

        track = make_track()
        perimeter = track.perimeter
        boundaries_in_distance = [
            track.straight_length,
            track.straight_length + math.pi * track.radius,
            2 * track.straight_length + math.pi * track.radius,
        ]

        for boundary in boundaries_in_distance:
            just_before = track.position_at_distance(boundary - 1e-6)
            just_after = track.position_at_distance(boundary + 1e-6)
            self.assertAlmostEqual(just_before[0], just_after[0], places=3)
            self.assertAlmostEqual(just_before[1], just_after[1], places=3)

        # The end of the last segment must also reconnect to the start.
        end = track.position_at_distance(perimeter - 1e-6)
        start = track.position_at_distance(0.0)
        self.assertAlmostEqual(end[0], start[0], places=3)
        self.assertAlmostEqual(end[1], start[1], places=3)

    def test_radial_offset_moves_points_outward_on_every_segment(self) -> None:
        """Outer-edge points must be farther from the track center than the
        centerline, and inner-edge points must be closer, on all four
        segments — otherwise the drawn road band would pinch or cross
        itself at the turns."""

        track = make_track()
        center = (track.center_x, track.center_y)

        def distance_from_center(point: tuple[float, float]) -> float:
            return math.hypot(point[0] - center[0], point[1] - center[1])

        for fraction in (0.0, 0.15, 0.3, 0.5, 0.65, 0.8):
            inner = track.position_at_fraction(fraction, -10)
            mid = track.position_at_fraction(fraction, 0)
            outer = track.position_at_fraction(fraction, 10)
            self.assertLess(distance_from_center(inner), distance_from_center(mid))
            self.assertLess(distance_from_center(mid), distance_from_center(outer))

    def test_centerline_points_returns_requested_sample_count(self) -> None:
        track = make_track()

        points = track.centerline_points(40)

        self.assertEqual(len(points), 40)

    def test_road_quads_tile_the_full_ring_without_gaps(self) -> None:
        track = make_track()

        quads = track.road_quads(20)

        self.assertEqual(len(quads), 20)
        for quad in quads:
            self.assertEqual(len(quad), 4)
        # Consecutive quads must share an edge: this quad's second outer
        # point is the next quad's first outer point, and likewise for the
        # inner edge — otherwise the road surface would show gaps or
        # overlaps between tiles.
        for index, quad in enumerate(quads):
            next_quad = quads[(index + 1) % len(quads)]
            self.assertEqual(quad[1], next_quad[0])
            self.assertEqual(quad[2], next_quad[3])


if __name__ == "__main__":
    unittest.main()
