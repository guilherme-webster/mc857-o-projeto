"""Primitivas de desenho compartilhadas pelas telas Arcade.

Ficam fora das views para que nenhuma tela dependa de outra apenas para
reaproveitar um painel arredondado. Nao guardam estado: so desenham.
"""

from __future__ import annotations

import arcade


def draw_rounded_rectangle(
    left: float,
    bottom: float,
    width: float,
    height: float,
    radius: float,
    color: tuple[int, ...],
) -> None:
    """Fill a rounded rectangle using primitives available in Arcade 3.3."""

    radius = min(radius, width / 2, height / 2)
    arcade.draw_lbwh_rectangle_filled(
        left + radius, bottom, width - 2 * radius, height, color
    )
    arcade.draw_lbwh_rectangle_filled(
        left, bottom + radius, width, height - 2 * radius, color
    )
    for center_x in (left + radius, left + width - radius):
        for center_y in (bottom + radius, bottom + height - radius):
            arcade.draw_circle_filled(center_x, center_y, radius, color)


def draw_rounded_panel(
    left: float,
    bottom: float,
    width: float,
    height: float,
    radius: float,
    fill_color: tuple[int, ...],
    border_color: tuple[int, ...],
    border_width: int = 1,
) -> None:
    """Draw a rounded fill and a consistent border without texture assets."""

    draw_rounded_rectangle(left, bottom, width, height, radius, border_color)
    inset = border_width
    draw_rounded_rectangle(
        left + inset,
        bottom + inset,
        width - 2 * inset,
        height - 2 * inset,
        max(radius - inset, 0),
        fill_color,
    )
