"""Fit fixed-coordinate screens into a resizable Arcade window.

The tournament and stage configuration screens place every element at absolute
coordinates of a *design canvas* (1280×720 and 1672×900). Rewriting those
layouts as responsive ones would touch hundreds of coordinates, so the screens
keep drawing in design units and this module maps them onto whatever size the
window currently has.

The mapping is a uniform scale plus centering offsets ("letterbox"): the same
factor applies to both axes so that text, track outlines and icons are never
distorted, and the leftover strip on one axis is left to the background color.
Pointer events arrive in window units and are converted back with
:meth:`CanvasFit.to_logical`, so hit tests keep using the design rectangles.

Units: "window units" are the coordinates pyglet reports to event handlers and
``Window.get_size()``. On HiDPI desktops with ``dpi_scaling="stretch"`` they are
*not* physical pixels (a 2× scale doubles the framebuffer); Arcade converts the
camera viewport to framebuffer pixels itself, so nothing here needs the pixel
ratio. The only exception is the screen size used to choose the initial window
size, which pyglet reports in physical pixels and must be divided by the scale.

The pure geometry has no Arcade dependency so it can be tested without a window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import arcade

# Fraction of the usable screen the first window may occupy. The remainder
# leaves room for the desktop's top bar, docks and the window title bar, which
# pyglet cannot measure.
INITIAL_SCREEN_FRACTION = 0.9
# Below this size the responsive screens (grid, playback, results) start to
# overlap their panels; the window manager will refuse smaller sizes.
MINIMUM_WINDOW_SIZE = (960, 540)


@dataclass(frozen=True)
class CanvasFit:
    """Uniform scale and offsets that place a design canvas inside a window.

    Invariant: ``scale > 0`` and the scaled canvas is centered, so
    ``to_window(to_logical(p)) == p`` for every point (up to float rounding).
    """

    logical_width: float
    logical_height: float
    scale: float
    offset_x: float
    offset_y: float

    @classmethod
    def fit(
        cls, logical_size: tuple[float, float], window_size: tuple[float, float]
    ) -> CanvasFit:
        """Return the largest uniform fit of ``logical_size`` into the window.

        A degenerate window (zero width or height, as happens transiently while
        minimizing) falls back to scale 1 so callers never divide by zero.
        """

        logical_width, logical_height = logical_size
        window_width, window_height = window_size
        if window_width <= 0 or window_height <= 0:
            return cls(logical_width, logical_height, 1.0, 0.0, 0.0)
        scale = min(window_width / logical_width, window_height / logical_height)
        return cls(
            logical_width,
            logical_height,
            scale,
            (window_width - logical_width * scale) / 2,
            (window_height - logical_height * scale) / 2,
        )

    @property
    def viewport(self) -> tuple[float, float, float, float]:
        """Left, bottom, width and height of the canvas in window units."""

        return (
            self.offset_x,
            self.offset_y,
            self.logical_width * self.scale,
            self.logical_height * self.scale,
        )

    def to_logical(self, x: float, y: float) -> tuple[float, float]:
        """Convert a pointer position in window units to design units.

        Points on the letterbox strips map outside ``[0, logical_size]`` and
        therefore miss every design rectangle, which is the desired behavior.
        """

        return (x - self.offset_x) / self.scale, (y - self.offset_y) / self.scale

    def to_window(self, x: float, y: float) -> tuple[float, float]:
        """Convert a design position to window units (inverse of ``to_logical``)."""

        return self.offset_x + x * self.scale, self.offset_y + y * self.scale


def make_canvas_camera(fit: CanvasFit, window: arcade.Window) -> arcade.Camera2D:
    """Build a camera that draws design units into the letterboxed viewport."""

    import arcade

    return arcade.Camera2D(
        projection=arcade.LBWH(
            -fit.logical_width / 2,
            -fit.logical_height / 2,
            fit.logical_width,
            fit.logical_height,
        ),
        viewport=arcade.LBWH(*fit.viewport),
        position=(fit.logical_width / 2, fit.logical_height / 2),
        window=window,
    )


def initial_window_size(
    design_size: tuple[int, int],
    screen_size: tuple[float, float] | None,
    *,
    fraction: float = INITIAL_SCREEN_FRACTION,
) -> tuple[int, int]:
    """Shrink the design size, keeping its aspect, to fit the usable screen.

    ``screen_size`` must be in window units (see the module docstring). The
    window never starts larger than the design size, and never smaller than
    :data:`MINIMUM_WINDOW_SIZE`; an unknown screen keeps the design size.
    """

    design_width, design_height = design_size
    if screen_size is None:
        return design_size
    available_width = screen_size[0] * fraction
    available_height = screen_size[1] * fraction
    scale = min(1.0, available_width / design_width, available_height / design_height)
    minimum_width, minimum_height = MINIMUM_WINDOW_SIZE
    return (
        max(minimum_width, int(design_width * scale)),
        max(minimum_height, int(design_height * scale)),
    )


def screen_size_in_window_units() -> tuple[float, float] | None:
    """Return the default screen size in window units, or ``None`` if unknown.

    pyglet reports the screen in physical pixels while window sizes are scaled
    by the desktop factor (e.g. 3072×1728 at 2× is 1536×864 window units).
    Headless runs and platforms without a display yield ``None``.
    """

    try:
        import pyglet

        screen = pyglet.display.get_display().get_default_screen()
        scale = screen.get_scale() or 1.0
    except Exception:  # noqa: BLE001 - optional desktop query, any failure is "unknown"
        return None
    return screen.width / scale, screen.height / scale
