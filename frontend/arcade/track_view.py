from __future__ import annotations

from bisect import bisect_right

import arcade

from frontend.arcade.track_client import fetch_race, fetch_track
from frontend.arcade.theme import (
    BACKGROUND_COLOR,
    PRIMARY_TEXT_COLOR,
    TRACK_EDGE_COLOR,
)

SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 800
MARGIN = 80
CAR_RADIUS = 7
PLAYBACK_SPEED = 60_000.0  # ms de corrida por segundo de tela

_PALETTE = [
    (225, 36, 54), (58, 134, 218), (70, 211, 142), (245, 197, 66),
    (168, 100, 233), (240, 132, 60), (90, 200, 250), (255, 105, 180),
]


def _to_screen(points):
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
    def __init__(self, track: dict, race: dict) -> None:
        super().__init__()
        pts = sorted(track["track_points"], key=lambda p: p["sequence"])
        self._cum = [p["cumulative_distance_m"] for p in pts]
        self._screen = _to_screen([(p["x"], p["y"]) for p in pts])
        self._lap_length = track["lap_length_m"]

        self._total_laps = race["total_laps"]
        self._cars = [
            {"name": c["name"], "lap_time_ms": c["lap_time_ms"],
             "color": _PALETTE[i % len(_PALETTE)]}
            for i, c in enumerate(race["classification"])
        ]
        self._race_len_ms = max(
            (c["lap_time_ms"] * self._total_laps for c in self._cars), default=1
        )
        self._elapsed = 0.0
        self._title = arcade.Text(
            track["circuit_id"], 20, SCREEN_HEIGHT - 40,
            PRIMARY_TEXT_COLOR, 18, bold=True,
        )

    def on_show_view(self) -> None:
        super().on_show_view()
        arcade.set_background_color(BACKGROUND_COLOR)

    def on_update(self, dt: float) -> None:
        self._elapsed = min(self._elapsed + dt * PLAYBACK_SPEED, self._race_len_ms)

    def _pos_at(self, distance_m: float):
        d = distance_m % self._lap_length
        i = max(0, min(bisect_right(self._cum, d) - 1, len(self._cum) - 2))
        d0, d1 = self._cum[i], self._cum[i + 1]
        (x0, y0), (x1, y1) = self._screen[i], self._screen[i + 1]
        f = (d - d0) / (d1 - d0) if d1 > d0 else 0.0
        return (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)

    def on_draw(self) -> None:
        self.clear()
        self._title.draw()
        arcade.draw_line_strip([*self._screen, self._screen[0]], TRACK_EDGE_COLOR, 2)
        race_dist = self._total_laps * self._lap_length
        for car in self._cars:
            dist = min(self._elapsed / car["lap_time_ms"] * self._lap_length, race_dist)
            x, y = self._pos_at(dist)
            arcade.draw_circle_filled(x, y, CAR_RADIUS, car["color"])


def show(circuit_id: int | str = 18) -> None:
    track = fetch_track(circuit_id)
    race = fetch_race()
    window = arcade.Window(SCREEN_WIDTH, SCREEN_HEIGHT, "Simulacao")
    window.show_view(TrackView(track, race))
    arcade.run()


if __name__ == "__main__":
    import sys

    show(sys.argv[1] if len(sys.argv) > 1 else 18)
