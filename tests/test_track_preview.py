"""Headless tests for fitting backend geometry into the configuration card."""

from __future__ import annotations

import unittest

from frontend.arcade.track_preview import fit_track_preview


class TrackPreviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = {
            "lap_length_m": 4309.0,
            "track_points": [
                {"sequence": 2, "x": 2, "y": 1},
                {"sequence": 0, "x": 0, "y": 0},
                {"sequence": 1, "x": 2, "y": 0},
                {"sequence": 3, "x": 0, "y": 1},
            ],
            "pit_lane_points": [
                {
                    "sequence": 1,
                    "x": 1,
                    "y": 0.25,
                    "is_service_point": True,
                },
                {
                    "sequence": 0,
                    "x": 0.5,
                    "y": 0.25,
                    "is_service_point": False,
                },
            ],
        }

    def test_fits_both_paths_with_one_shared_transform(self) -> None:
        preview = fit_track_preview(self.payload, (100, 50, 400, 200), padding=20)

        self.assertEqual(len(preview.track_points), 4)
        self.assertEqual(len(preview.pit_lane_points), 2)
        self.assertEqual(preview.service_point, preview.pit_lane_points[1])
        self.assertEqual(preview.lap_length_m, 4309.0)
        # The service point keeps its relative X/Y position in the track's
        # coordinate space; independently fitting the pit would fail this.
        start = preview.track_points[0]
        service = preview.service_point
        end = preview.track_points[2]
        self.assertAlmostEqual((service[0] - start[0]) / (end[0] - start[0]), 0.5)
        self.assertAlmostEqual((service[1] - start[1]) / (end[1] - start[1]), 0.25)
        for x, y in (*preview.track_points, *preview.pit_lane_points):
            self.assertGreaterEqual(x, 120)
            self.assertLessEqual(x, 480)
            self.assertGreaterEqual(y, 70)
            self.assertLessEqual(y, 230)

    def test_rejects_a_pit_lane_without_one_service_point(self) -> None:
        for service_flags in ((False, False), (True, True)):
            with self.subTest(service_flags=service_flags):
                payload = dict(self.payload)
                payload["pit_lane_points"] = [
                    dict(point, is_service_point=flag)
                    for point, flag in zip(
                        self.payload["pit_lane_points"], service_flags, strict=True
                    )
                ]
                with self.assertRaisesRegex(ValueError, "exatamente um"):
                    fit_track_preview(payload, (0, 0, 400, 200))

    def test_rejects_invalid_sample_distance(self) -> None:
        for distance in (0, -1, float("nan"), "unknown"):
            with self.subTest(distance=distance):
                payload = dict(self.payload, lap_length_m=distance)
                with self.assertRaisesRegex(ValueError, "comprimento da volta"):
                    fit_track_preview(payload, (0, 0, 400, 200))


if __name__ == "__main__":
    unittest.main()
