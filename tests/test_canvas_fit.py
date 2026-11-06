"""Geometria do ajuste de telas de layout fixo a uma janela redimensionavel.

Estes testes nao abrem janela: ``canvas_fit`` so importa Arcade dentro de
``make_canvas_camera``.
"""

from __future__ import annotations

import unittest

from frontend.arcade.canvas_fit import (
    MINIMUM_WINDOW_SIZE,
    CanvasFit,
    initial_window_size,
)


class CanvasFitTest(unittest.TestCase):
    def test_same_size_is_identity(self) -> None:
        fit = CanvasFit.fit((1280, 720), (1280, 720))

        self.assertEqual(fit.scale, 1)
        self.assertEqual(fit.viewport, (0, 0, 1280, 720))
        self.assertEqual(fit.to_logical(640, 360), (640, 360))

    def test_wider_window_scales_by_height_and_centers_horizontally(self) -> None:
        fit = CanvasFit.fit((1280, 720), (1672, 900))

        self.assertEqual(fit.scale, 900 / 720)
        self.assertEqual(fit.viewport, (36, 0, 1600, 900))

    def test_taller_window_scales_by_width_and_centers_vertically(self) -> None:
        fit = CanvasFit.fit((1672, 900), (1000, 700))

        self.assertAlmostEqual(fit.scale, 1000 / 1672)
        left, bottom, width, height = fit.viewport
        self.assertEqual(left, 0)
        self.assertAlmostEqual(width, 1000)
        self.assertAlmostEqual(bottom * 2 + height, 700)

    def test_pointer_round_trip_and_letterbox_falls_outside_canvas(self) -> None:
        fit = CanvasFit.fit((1672, 900), (1000, 700))

        x, y = fit.to_logical(*fit.to_window(45.0, 480.0))
        self.assertAlmostEqual(x, 45.0)
        self.assertAlmostEqual(y, 480.0)
        _, below = fit.to_logical(500, 0)
        self.assertLess(below, 0)

    def test_degenerate_window_does_not_divide_by_zero(self) -> None:
        fit = CanvasFit.fit((1280, 720), (0, 0))

        self.assertEqual(fit.scale, 1)
        self.assertEqual(fit.to_logical(10, 20), (10, 20))


class InitialWindowSizeTest(unittest.TestCase):
    def test_large_screen_keeps_design_size(self) -> None:
        self.assertEqual(initial_window_size((1672, 900), (2560, 1440)), (1672, 900))

    def test_scaled_laptop_screen_shrinks_keeping_aspect(self) -> None:
        # 2560×1440 at 5/3 (or 3072×1728 at 2) is 1536×864 window units.
        width, height = initial_window_size((1672, 900), (1536, 864))

        self.assertLessEqual(width, 1536 * 0.9)
        self.assertLessEqual(height, 864 * 0.9)
        self.assertAlmostEqual(width / height, 1672 / 900, places=2)

    def test_unknown_screen_keeps_design_size(self) -> None:
        self.assertEqual(initial_window_size((1672, 900), None), (1672, 900))

    def test_tiny_screen_is_clamped_to_minimum(self) -> None:
        self.assertEqual(
            initial_window_size((1672, 900), (800, 480)), MINIMUM_WINDOW_SIZE
        )


if __name__ == "__main__":
    unittest.main()
