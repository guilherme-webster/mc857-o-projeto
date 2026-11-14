"""A escala de exibição não deve criar contatos visuais artificiais."""

import unittest
from types import SimpleNamespace

from frontend.arcade.track_view import TrackView, _car_half_size_px


class CarRenderScaleTest(unittest.TestCase):
    def test_uses_track_scale_at_typical_window_size(self):
        half_length, half_width = _car_half_size_px(5.0, 2.0, 0.74)
        self.assertAlmostEqual(2 * half_length, 3.7)
        self.assertAlmostEqual(2 * half_width, 1.48)

    def test_very_small_render_preserves_aspect_ratio(self):
        half_length, half_width = _car_half_size_px(5.0, 2.0, 0.05)
        self.assertEqual(2 * half_width, 1.0)
        self.assertEqual(half_length / half_width, 2.5)

    def test_normals_are_perpendicular_after_aspect_ratio_projection(self):
        view = SimpleNamespace(
            window=SimpleNamespace(width=1600, height=900),
            _standings_width=510,
            _aspect=2.0,
            _pit_unit=[],
            _unit=[(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)],
            _is_2d=True,
        )
        screen = TrackView._projected(view)
        dx = screen[2][0] - screen[0][0]
        dy = screen[2][1] - screen[0][1]
        nx, ny = view._normals[1]
        self.assertAlmostEqual(dx * nx + dy * ny, 0.0)


if __name__ == "__main__":
    unittest.main()
