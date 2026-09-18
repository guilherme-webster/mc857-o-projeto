from __future__ import annotations

import arcade

from frontend.arcade.track_client import fetch_track
from frontend.arcade.theme import (
    BACKGROUND_COLOR,
    PRIMARY_TEXT_COLOR,
    TRACK_EDGE_COLOR,
)

SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 800
MARGIN = 80


def _to_screen(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Projeta pontos normalizados na tela, preservando a proporcao."""

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    span_x = max_x - min_x or 1
    span_y = max_y - min_y or 1

    scale = min(
        (SCREEN_WIDTH - 2 * MARGIN) / span_x,
        (SCREEN_HEIGHT - 2 * MARGIN) / span_y,
    )
    off_x = (SCREEN_WIDTH - span_x * scale) / 2 - min_x * scale
    off_y = (SCREEN_HEIGHT - span_y * scale) / 2 - min_y * scale
    return [(x * scale + off_x, y * scale + off_y) for x, y in points]


class TrackView(arcade.View):
    def __init__(self, track: dict) -> None:
        super().__init__()
        points = [
            (p["x"], p["y"])
            for p in sorted(track["track_points"], key=lambda p: p["sequence"])
        ]
        self._screen_points = _to_screen(points)
        self._title = arcade.Text(
            track["circuit_id"], 20, SCREEN_HEIGHT - 40, PRIMARY_TEXT_COLOR, 18, bold=True
        )

    def on_show_view(self) -> None:
        super().on_show_view()
        arcade.set_background_color(BACKGROUND_COLOR)

    def on_draw(self) -> None:
        self.clear()
        self._title.draw()
        pts = [*self._screen_points, self._screen_points[0]]
        arcade.draw_line_strip(pts, TRACK_EDGE_COLOR, 2)


def show_track(circuit_id: int | str = 18) -> None:
    """Abre uma janela desenhando a pista do circuito informado."""

    track = fetch_track(circuit_id)
    window = arcade.Window(SCREEN_WIDTH, SCREEN_HEIGHT, "Pista")
    window.show_view(TrackView(track))
    arcade.run()


if __name__ == "__main__":
    import sys

    show_track(sys.argv[1] if len(sys.argv) > 1 else 18)
