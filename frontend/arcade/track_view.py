from __future__ import annotations

import urllib.error
from bisect import bisect_right

import arcade

from frontend.arcade.track_client import (
    fetch_race,
    fetch_saved_race,
    fetch_track,
)
from frontend.arcade.theme import (
    BACKGROUND_COLOR,
    PRIMARY_TEXT_COLOR,
    TRACK_EDGE_COLOR,
)

SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 800
MARGIN = 80
CAR_RADIUS = 7
BASE_PLAYBACK_SPEED = 20_000.0  # ms de corrida por segundo de tela, em 1x
MIN_SPEED = 0.125
SPEED_FACTOR = 2.0  # cada toque em up/down dobra ou divide a velocidade

_PALETTE = [
    (225, 36, 54), (58, 134, 218), (70, 211, 142), (245, 197, 66),
    (168, 100, 233), (240, 132, 60), (90, 200, 250), (255, 105, 180),
]

_RAIN_LABEL = {
    "dry": ("Seco", (150, 200, 255)),
    "light_rain": ("Chuva leve", (120, 190, 255)),
    "heavy_rain": ("Chuva forte", (90, 150, 255)),
}


def _normalize(points):
    """Reduza a geometria a coordenadas [0,1], preservando a razao de aspecto."""

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    span_x = max_x - min_x or 1
    span_y = max_y - min_y or 1
    return [((x - min_x) / span_x, (y - min_y) / span_y) for x, y in points], (
        span_x / span_y
    )


class TrackView(arcade.View):
    def __init__(self, track: dict, race: dict) -> None:
        super().__init__()
        pts = sorted(track["track_points"], key=lambda p: p["sequence"])
        self._cum = [p["cumulative_distance_m"] for p in pts]
        self._unit, self._aspect = _normalize([(p["x"], p["y"]) for p in pts])
        self._lap_length = track["lap_length_m"]

        self._total_laps = race["total_laps"]
        self._color_by_driver = {
            c["driver_id"]: _PALETTE[i % len(_PALETTE)]
            for i, c in enumerate(race["classification"])
        }
        self._cars = [
            {
                "driver_id": c["driver_id"],
                "name": c["name"],
                "lap_time_ms": c["lap_time_ms"],
                "color": self._color_by_driver[c["driver_id"]],
            }
            for c in race["classification"]
        ]
        self._history = race.get("history", [])
        self._race_len_ms = max(
            (c["lap_time_ms"] * self._total_laps for c in self._cars), default=1
        )
        self._lead_lap_time_ms = min(
            (c["lap_time_ms"] for c in self._cars), default=self._race_len_ms
        )
        self._weather = _weather_segments(race)

        self._elapsed = 0.0
        self._speed = 1.0
        self._direction = 1  # +1 para frente, -1 para tras
        self._paused = False
        self._circuit = str(track["circuit_id"])

        self._title = arcade.Text("", 20, 0, PRIMARY_TEXT_COLOR, 18, bold=True)
        self._hud = arcade.Text("", 20, 24, PRIMARY_TEXT_COLOR, 13, font_name="monospace")
        self._weather_text = arcade.Text(
            "", 0, 0, PRIMARY_TEXT_COLOR, 15, bold=True, anchor_x="right"
        )
        self._help = arcade.Text(
            "espaco pausa  |  <- -> inverte sentido  |  up/down velocidade  |  R reinicia",
            20, 6, (130, 140, 150), 10, font_name="monospace",
        )
        self._row_texts: list[arcade.Text] = []

    def on_show_view(self) -> None:
        super().on_show_view()
        arcade.set_background_color(BACKGROUND_COLOR)

    def _projected(self) -> list[tuple[float, float]]:
        """Projete a geometria normalizada no tamanho atual da janela."""

        width, height = self.window.width, self.window.height
        usable_w = max(1.0, width - 2 * MARGIN)
        usable_h = max(1.0, height - 2 * MARGIN)
        # Mantem a razao de aspecto da pista dentro do espaco util.
        if usable_w / usable_h > self._aspect:
            draw_h = usable_h
            draw_w = draw_h * self._aspect
        else:
            draw_w = usable_w
            draw_h = draw_w / self._aspect
        off_x = (width - draw_w) / 2
        off_y = (height - draw_h) / 2
        return [(off_x + ux * draw_w, off_y + uy * draw_h) for ux, uy in self._unit]

    def _current_lap(self) -> int:
        lead_dist = self._elapsed / self._lead_lap_time_ms * self._lap_length
        lap = int(lead_dist // self._lap_length) + 1
        return max(1, min(lap, self._total_laps))

    def _current_rain(self) -> str:
        lap = self._current_lap()
        for segment in self._weather:
            if segment["from_lap"] <= lap <= segment["to_lap"]:
                return segment["rain"]
        return "dry"

    def _current_standings(self) -> list[dict]:
        """Classificacao da volta corrente do playback (ou a ultima disponivel)."""

        if not self._history:
            return []
        index = min(self._current_lap(), len(self._history)) - 1
        cars = self._history[index].get("cars", [])
        return sorted(cars, key=lambda car: car["position"])

    def on_update(self, dt: float) -> None:
        if self._paused:
            return
        step = dt * BASE_PLAYBACK_SPEED * self._speed * self._direction
        self._elapsed = max(0.0, min(self._elapsed + step, self._race_len_ms))

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol == arcade.key.SPACE:
            self._paused = not self._paused
        elif symbol == arcade.key.LEFT:
            self._direction = -1
            self._paused = False
        elif symbol == arcade.key.RIGHT:
            self._direction = 1
            self._paused = False
        elif symbol == arcade.key.UP:
            self._speed *= SPEED_FACTOR
        elif symbol == arcade.key.DOWN:
            self._speed = max(MIN_SPEED, self._speed / SPEED_FACTOR)
        elif symbol == arcade.key.R:
            self._elapsed = 0.0
            self._direction = 1

    def _pos_at(self, screen, distance_m: float):
        d = distance_m % self._lap_length
        i = max(0, min(bisect_right(self._cum, d) - 1, len(self._cum) - 2))
        d0, d1 = self._cum[i], self._cum[i + 1]
        (x0, y0), (x1, y1) = screen[i], screen[i + 1]
        f = (d - d0) / (d1 - d0) if d1 > d0 else 0.0
        return (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)

    def on_draw(self) -> None:
        self.clear()
        width, height = self.window.width, self.window.height
        screen = self._projected()

        self._title.text = self._circuit
        self._title.y = height - 40
        self._title.draw()

        arcade.draw_line_strip([*screen, screen[0]], TRACK_EDGE_COLOR, 2)
        race_dist = self._total_laps * self._lap_length
        for car in self._cars:
            dist = min(self._elapsed / car["lap_time_ms"] * self._lap_length, race_dist)
            x, y = self._pos_at(screen, dist)
            arcade.draw_circle_filled(x, y, CAR_RADIUS, car["color"])

        rain = self._current_rain()
        label, color = _RAIN_LABEL.get(rain, (rain, PRIMARY_TEXT_COLOR))
        self._weather_text.text = label
        self._weather_text.color = color
        self._weather_text.x = width - 20
        self._weather_text.y = height - 40
        self._weather_text.draw()

        if self._paused:
            state = "PAUSADO"
        else:
            state = "<< voltando" if self._direction < 0 else "rodando"
        self._hud.text = (
            f"volta {self._current_lap()}/{self._total_laps}   "
            f"{self._speed:g}x   {state}"
        )
        self._hud.draw()
        self._help.draw()
        self._draw_standings(height)

    def _draw_standings(self, height: int) -> None:
        standings = self._current_standings()
        if not standings:
            return
        top = height - 80
        line_h = 20
        leader_time = standings[0].get("total_time_ms", 0.0)
        rows = []
        for car in standings:
            pos = car["position"]
            name = car["name"][:16]
            status = car.get("status")
            if status and status != "RUNNING":
                time_text = "OUT"
            elif pos == 1:
                time_text = _format_clock(car.get("total_time_ms", 0.0))
            else:
                time_text = _format_gap(
                    car.get("total_time_ms", 0.0) - leader_time
                )
            rows.append((car["driver_id"], f"{pos:>2}  {name:<16} {time_text:>10}"))

        while len(self._row_texts) < len(rows):
            self._row_texts.append(
                arcade.Text("", 20, 0, PRIMARY_TEXT_COLOR, 12, font_name="monospace")
            )
        for i, (driver_id, line) in enumerate(rows):
            text = self._row_texts[i]
            text.text = line
            text.x = 20
            text.y = top - i * line_h
            text.color = self._color_by_driver.get(driver_id, PRIMARY_TEXT_COLOR)
            text.draw()


def _format_clock(ms: float) -> str:
    total_seconds = ms / 1000.0
    minutes = int(total_seconds // 60)
    seconds = total_seconds - minutes * 60
    return f"{minutes}:{seconds:06.3f}"


def _format_gap(ms: float) -> str:
    return f"+{ms / 1000.0:.3f}"


def _weather_segments(race: dict) -> list[dict]:
    setup = race.get("setup") if isinstance(race, dict) else None
    segments = setup.get("weather") if isinstance(setup, dict) else None
    return segments if isinstance(segments, list) else []


def _race_circuit_id(race: dict) -> str | None:
    setup = race.get("setup") if isinstance(race, dict) else None
    track_id = setup.get("track_id") if isinstance(setup, dict) else None
    return track_id or None


def show(circuit_id: int | str | None = None, saved_id: str | None = None) -> None:
    try:
        race = fetch_saved_race(saved_id) if saved_id else fetch_race()
    except urllib.error.HTTPError as error:
        raise SystemExit(
            f"nao foi possivel carregar a corrida (HTTP {error.code})"
        ) from error
    resolved = circuit_id if circuit_id is not None else _race_circuit_id(race)
    if resolved is None:
        raise SystemExit(
            "a corrida nao tem pista no setup; informe o circuito: "
            "python -m frontend.arcade.track_view <circuit_id>"
        )
    try:
        track = fetch_track(resolved)
    except urllib.error.HTTPError as error:
        raise SystemExit(
            f"pista {resolved} sem geometria disponivel no backend "
            f"(HTTP {error.code})"
        ) from error
    window = arcade.Window(SCREEN_WIDTH, SCREEN_HEIGHT, "Simulacao", resizable=True)
    window.show_view(TrackView(track, race))
    arcade.run()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Visualiza uma corrida simulada.")
    parser.add_argument("circuit_id", nargs="?", default=None)
    parser.add_argument("--saved", dest="saved_id", default=None, help="id de uma corrida salva")
    args = parser.parse_args()
    show(args.circuit_id, args.saved_id)
