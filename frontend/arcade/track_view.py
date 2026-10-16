from __future__ import annotations

import urllib.error
from bisect import bisect_right

import arcade

from frontend.arcade.race_control_feed import RaceControlFeed
from frontend.arcade.race_playback import RacePlayback
from frontend.arcade.theme import (
    BACKGROUND_COLOR,
    PRIMARY_TEXT_COLOR,
    TRACK_EDGE_COLOR,
)
from frontend.arcade.track_client import (
    fetch_race,
    fetch_saved_race,
    fetch_saved_races,
    fetch_track,
)

SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 800
MARGIN = 80
CAR_RADIUS = 7
BASE_PLAYBACK_SPEED = 1_000.0  # 1x = tempo real (1 s de simulacao por 1 s de tela)
MIN_SPEED = 1.0 / 256.0  # ~0,004x: permite camera lenta extrema
SPEED_FACTOR = 2.0  # cada toque em up/down dobra ou divide a velocidade

# Uma cor por carro para um grid de ate 20 carros; acima disso as cores voltam
# a se repetir. Todas com contraste suficiente sobre o fundo preto.
_PALETTE = [
    (225, 36, 54),
    (58, 134, 218),
    (70, 211, 142),
    (245, 197, 66),
    (168, 100, 233),
    (240, 132, 60),
    (90, 200, 250),
    (255, 105, 180),
    (160, 220, 80),
    (0, 175, 175),
    (200, 160, 255),
    (255, 160, 120),
    (210, 210, 210),
    (255, 225, 150),
    (110, 140, 255),
    (60, 180, 90),
    (230, 90, 140),
    (190, 150, 100),
    (150, 230, 220),
    (255, 240, 90),
]

_RAIN_LABEL = {
    "dry": ("Seco", (150, 200, 255)),
    "light_rain": ("Chuva leve", (120, 190, 255)),
    "heavy_rain": ("Chuva forte", (90, 150, 255)),
}

# Faixa de controle de prova: (fundo, texto) por status do motor. A pista
# inteira tambem e tingida, porque a bandeira do motor e global.
_STATUS_STYLE = {
    "GREEN": ((28, 110, 60), PRIMARY_TEXT_COLOR),
    "YELLOW": ((235, 190, 40), (20, 20, 20)),
    "VSC": ((235, 150, 40), (20, 20, 20)),
    "SC": ((235, 150, 40), (20, 20, 20)),
    "RED": ((200, 30, 40), PRIMARY_TEXT_COLOR),
}
_RESTART_STYLE = ((40, 170, 90), PRIMARY_TEXT_COLOR)
_TRACK_TINT = {
    "YELLOW": (235, 190, 40),
    "VSC": (235, 150, 40),
    "SC": (235, 150, 40),
    "RED": (200, 30, 40),
}
_FEED_TINT = {**_TRACK_TINT, "GREEN": (70, 211, 142)}
_FEED_LINES = 6
_FEED_COLOR = (190, 198, 210)

# Composto -> (letra, cor). Composto desconhecido aparece como "?".
_COMPOUND_STYLE = {
    "SOFT": ("S", (225, 36, 54)),
    "MEDIUM": ("M", (245, 197, 66)),
    "HARD": ("H", (235, 235, 235)),
    "INTERMEDIATE": ("I", (70, 211, 142)),
    "WET": ("W", (58, 134, 218)),
}
_RETIREMENT_LABEL = {
    "CONTACT": "CONTATO",
    "CRASH": "BATIDA",
    "MECHANICAL": "QUEBRA",
}
_GAINED_COLOR = (70, 211, 142)
_LOST_COLOR = (255, 112, 112)
_PIT_COLOR = (240, 150, 40)
_HEADER_COLOR = (130, 140, 150)
# Colunas da classificacao: (cabecalho, x em px a partir da margem, ancora).
# Cada coluna e um texto proprio porque a fonte "monospace" nem sempre e
# monoespacada e alinhar com espacos deixava as colunas tortas.
_STANDING_COLUMNS = {
    "position": ("P", 22, "right"),
    "name": ("PILOTO", 32, "left"),
    "time": ("INTERVALO", 262, "right"),
    "tyre": ("PN", 280, "center"),
    "age": ("VOL", 318, "right"),
    "stops": ("PAR", 350, "right"),
    "delta": ("+/-", 392, "right"),
}
_TYRE_RADIUS = 8
# Largura reservada a esquerda para a classificacao; a pista e desenhada so no
# espaco restante, para que tabela e tracado nao se sobreponham.
STANDINGS_WIDTH = 440

_MENU_BG = (16, 22, 30)
_ROW_BG = (30, 41, 53)
_ROW_HOVER = (46, 62, 80)
_SWITCH_BG = (46, 62, 80)


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


def _load_race_view(saved_id: str | None) -> TrackView:
    """Monte a TrackView de uma corrida salva (ou da atual, se ``saved_id`` None)."""

    race = fetch_saved_race(saved_id) if saved_id else fetch_race()
    circuit_id = _race_circuit_id(race)
    if circuit_id is None:
        raise RuntimeError("a corrida nao tem pista no setup")
    track = fetch_track(circuit_id)
    return TrackView(track, race)


class MenuView(arcade.View):
    """Lista as corridas salvas; um clique abre a corrida selecionada."""

    ROW_H = 44
    LIST_TOP = 120

    def __init__(self) -> None:
        super().__init__()
        self._saved: list[dict] = []
        self._error: str | None = None
        self._hover = -1
        self._title = arcade.Text(
            "Corridas salvas", 40, 0, PRIMARY_TEXT_COLOR, 24, bold=True
        )
        self._subtitle = arcade.Text("", 40, 0, (150, 160, 170), 13)
        self._refresh()

    def _refresh(self) -> None:
        try:
            self._saved = fetch_saved_races().get("saved", [])
            self._error = None
        except (urllib.error.URLError, OSError) as error:
            self._saved = []
            self._error = f"nao foi possivel listar as corridas: {error}"

    def on_show_view(self) -> None:
        super().on_show_view()
        arcade.set_background_color(_MENU_BG)

    def _row_rect(self, index: int):
        """(left, bottom, width, height) da linha ``index``, do topo para baixo."""

        top = self.window.height - self.LIST_TOP
        bottom = top - (index + 1) * self.ROW_H + 6
        return 40, bottom, self.window.width - 80, self.ROW_H - 10

    def on_mouse_motion(self, x, y, dx, dy) -> None:
        self._hover = -1
        for i in range(len(self._saved)):
            left, bottom, width, height = self._row_rect(i)
            if left <= x <= left + width and bottom <= y <= bottom + height:
                self._hover = i
                break

    def on_mouse_press(self, x, y, button, modifiers) -> None:
        if self._hover < 0 or self._hover >= len(self._saved):
            return
        saved_id = self._saved[self._hover]["id"]
        try:
            view = _load_race_view(saved_id)
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            RuntimeError,
            ValueError,
        ) as error:
            self._error = f"nao foi possivel abrir a corrida: {error}"
            return
        self.window.show_view(view)

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol == arcade.key.R:
            self._refresh()

    def on_draw(self) -> None:
        self.clear()
        self._title.y = self.window.height - 60
        self._title.draw()
        self._subtitle.text = (
            self._error
            if self._error
            else f"{len(self._saved)} corridas  |  clique para abrir  |  R atualiza"
        )
        self._subtitle.y = self.window.height - 90
        self._subtitle.color = (230, 120, 120) if self._error else (150, 160, 170)
        self._subtitle.draw()

        for i, item in enumerate(self._saved):
            left, bottom, width, height = self._row_rect(i)
            if bottom < 0:
                break
            color = _ROW_HOVER if i == self._hover else _ROW_BG
            arcade.draw_lbwh_rectangle_filled(left, bottom, width, height, color)
            label = item.get("name", item["id"])
            detail = (
                f"{item.get('track_id') or '-'}   "
                f"{item.get('total_laps') or '?'} voltas   "
                f"{item.get('car_count') or '?'} carros"
            )
            arcade.draw_text(
                label,
                left + 16,
                bottom + height - 24,
                PRIMARY_TEXT_COLOR,
                15,
                bold=True,
            )
            arcade.draw_text(
                detail,
                left + 16,
                bottom + 6,
                (150, 160, 170),
                11,
            )


class TrackView(arcade.View):
    """Reproduz a corrida volta a volta sobre a geometria da pista.

    ``_elapsed`` e o relogio da corrida em ms. Posicoes, volta atual e
    classificacao vem de ``RacePlayback``, construido a partir do ``history``
    do motor; a view so converte voltas em metros e metros em pontos da tela.
    """

    def __init__(self, track: dict, race: dict) -> None:
        super().__init__()
        pts = sorted(track["track_points"], key=lambda p: p["sequence"])
        self._cum = [p["cumulative_distance_m"] for p in pts]
        self._unit, self._aspect = _normalize([(p["x"], p["y"]) for p in pts])
        self._lap_length = track["lap_length_m"]

        self._playback = RacePlayback(race)
        self._total_laps = self._playback.total_laps
        self._color_by_driver = {
            car.driver_id: _PALETTE[i % len(_PALETTE)]
            for i, car in enumerate(self._playback.cars)
        }
        self._race_len_ms = self._playback.duration_ms
        self._feed = RaceControlFeed(
            race, {car.driver_id: car.name for car in self._playback.cars}
        )
        self._weather = _weather_segments(race)

        self._elapsed = 0.0
        self._speed = 1.0
        self._direction = 1  # +1 para frente, -1 para tras
        self._paused = False
        self._circuit = str(track["circuit_id"])
        self._switch_hover = False
        self._end_hover = False

        self._title = arcade.Text("", 20, 0, PRIMARY_TEXT_COLOR, 18, bold=True)
        self._hud = arcade.Text(
            "", 20, 24, PRIMARY_TEXT_COLOR, 13, font_name="monospace"
        )
        self._weather_text = arcade.Text(
            "", 0, 0, PRIMARY_TEXT_COLOR, 15, bold=True, anchor_x="right"
        )
        self._help = arcade.Text(
            "espaco pausa  |  <- -> inverte sentido  |  up/down velocidade  |  R reinicia",
            20,
            6,
            (130, 140, 150),
            10,
            font_name="monospace",
        )
        self._switch_text = arcade.Text(
            "Trocar corrida",
            0,
            0,
            PRIMARY_TEXT_COLOR,
            13,
            anchor_x="center",
            anchor_y="center",
        )
        self._end_text = arcade.Text(
            "Pular pro fim",
            0,
            0,
            PRIMARY_TEXT_COLOR,
            13,
            anchor_x="center",
            anchor_y="center",
        )
        self._row_texts: list[dict[str, arcade.Text]] = []
        self._header_texts = {
            key: arcade.Text(label, 0, 0, _HEADER_COLOR, 9, bold=True, anchor_x=anchor)
            for key, (label, _, anchor) in _STANDING_COLUMNS.items()
        }
        self._status_text = arcade.Text(
            "",
            0,
            0,
            PRIMARY_TEXT_COLOR,
            14,
            bold=True,
            anchor_x="center",
            anchor_y="center",
        )
        self._feed_texts = [
            arcade.Text("", 20, 0, _FEED_COLOR, 11, font_name="monospace")
            for _ in range(_FEED_LINES)
        ]

    def on_show_view(self) -> None:
        super().on_show_view()
        arcade.set_background_color(BACKGROUND_COLOR)

    def _switch_rect(self):
        """(left, bottom, width, height) do botao 'Trocar corrida'."""

        width, height = 150, 34
        return self.window.width - width - 20, 20, width, height

    def _end_rect(self):
        """(left, bottom, width, height) do botao 'Pular pro fim'."""

        width, height = 150, 34
        switch_left = self.window.width - width - 20
        return switch_left - width - 10, 20, width, height

    def _projected(self) -> list[tuple[float, float]]:
        """Projete a geometria normalizada no tamanho atual da janela."""

        width, height = self.window.width, self.window.height
        area_left = STANDINGS_WIDTH
        usable_w = max(1.0, width - area_left - MARGIN)
        usable_h = max(1.0, height - 2 * MARGIN)
        if usable_w / usable_h > self._aspect:
            draw_h = usable_h
            draw_w = draw_h * self._aspect
        else:
            draw_w = usable_w
            draw_h = draw_w / self._aspect
        off_x = area_left + (width - area_left - MARGIN - draw_w) / 2
        off_y = (height - draw_h) / 2
        return [(off_x + ux * draw_w, off_y + uy * draw_h) for ux, uy in self._unit]

    def _current_lap(self) -> int:
        return self._playback.current_lap(self._elapsed)

    def _current_rain(self) -> str:
        lap = self._current_lap()
        for segment in self._weather:
            if segment["from_lap"] <= lap <= segment["to_lap"]:
                return segment["rain"]
        return "dry"

    def on_update(self, dt: float) -> None:
        if self._paused:
            return
        step = dt * BASE_PLAYBACK_SPEED * self._speed * self._direction
        self._elapsed = max(0.0, min(self._elapsed + step, self._race_len_ms))

    @staticmethod
    def _in_rect(x, y, rect) -> bool:
        left, bottom, width, height = rect
        return left <= x <= left + width and bottom <= y <= bottom + height

    def on_mouse_motion(self, x, y, dx, dy) -> None:
        self._switch_hover = self._in_rect(x, y, self._switch_rect())
        self._end_hover = self._in_rect(x, y, self._end_rect())

    def on_mouse_press(self, x, y, button, modifiers) -> None:
        if self._in_rect(x, y, self._switch_rect()):
            self.window.show_view(MenuView())
        elif self._in_rect(x, y, self._end_rect()):
            self._elapsed = self._race_len_ms
            self._paused = True
            self._direction = 1

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
        elif symbol == arcade.key.M:
            self.window.show_view(MenuView())

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

        status = self._feed.status_on_lap(self._current_lap())
        track_color = (
            _TRACK_TINT.get(status.status, TRACK_EDGE_COLOR)
            if status
            else TRACK_EDGE_COLOR
        )
        arcade.draw_line_strip([*screen, screen[0]], track_color, 2)
        # Carros que abandonaram nao sao desenhados; os demais param na linha
        # de chegada, onde ``laps`` vale ``total_laps``.
        for driver_id, laps in self._playback.on_track(self._elapsed):
            x, y = self._pos_at(screen, laps * self._lap_length)
            arcade.draw_circle_filled(
                x, y, CAR_RADIUS, self._color_by_driver[driver_id]
            )

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
        self._draw_race_control(status, width, height)
        self._draw_button(self._switch_rect(), self._switch_text, self._switch_hover)
        self._draw_button(self._end_rect(), self._end_text, self._end_hover)

    def _draw_button(self, rect, text, hover) -> None:
        left, bottom, width, height = rect
        color = _ROW_HOVER if hover else _SWITCH_BG
        arcade.draw_lbwh_rectangle_filled(left, bottom, width, height, color)
        text.x = left + width / 2
        text.y = bottom + height / 2
        text.draw()

    def _draw_standings(self, height: int) -> None:
        """Classificacao ao vivo com pneu, paradas e posicoes ganhas.

        O composto e a idade sao os do ultimo retrato do carro; "BOX" marca a
        volta que termina com parada; quem abandonou mostra a causa.
        """

        left = 20
        header_y = height - 74
        top = height - 96
        line_h = 20
        for key, text in self._header_texts.items():
            text.x = left + _STANDING_COLUMNS[key][1]
            text.y = header_y
            text.draw()

        standings = self._playback.standings(self._elapsed)
        while len(self._row_texts) < len(standings):
            self._row_texts.append(
                {
                    key: arcade.Text(
                        "",
                        0,
                        0,
                        PRIMARY_TEXT_COLOR,
                        9 if key == "tyre" else 12,
                        anchor_x=anchor,
                        anchor_y="center",
                        bold=key == "tyre",
                    )
                    for key, (_, _, anchor) in _STANDING_COLUMNS.items()
                }
            )
        for i, row in enumerate(standings):
            texts = self._row_texts[i]
            y = top - i * line_h
            car_color = self._color_by_driver.get(row.driver_id, PRIMARY_TEXT_COLOR)
            cells = self._standing_cells(row, car_color)
            for key, (value, color) in cells.items():
                text = texts[key]
                text.text = value
                text.color = color
                text.x = left + _STANDING_COLUMNS[key][1]
                text.y = y
                if key == "tyre" and value:
                    arcade.draw_circle_outline(text.x, y, _TYRE_RADIUS, color, 2)
                text.draw()

    def _standing_cells(self, row, car_color) -> dict[str, tuple[str, tuple]]:
        """Texto e cor de cada coluna de uma linha da classificacao."""

        if row.retired:
            time_text = _RETIREMENT_LABEL.get(row.retirement_cause, "OUT")
        elif row.position == 1:
            leader = self._playback.car(row.driver_id)
            time_text = _format_clock(min(self._elapsed, leader.finish_time_ms))
        elif row.gap_ms is None:
            time_text = "-"
        else:
            time_text = _format_gap(row.gap_ms)

        tyre = row.tyre
        letter, tyre_color = ("", car_color)
        age_text = stops_text = ""
        if tyre is not None and not row.retired:
            letter, tyre_color = _COMPOUND_STYLE.get(
                tyre.compound, ("?", _HEADER_COLOR)
            )
            age_text = "" if tyre.age_laps is None else str(tyre.age_laps)
            stops_text = str(tyre.stops)

        if row.retired:
            delta = ("", car_color)
        elif row.in_pit:
            delta = ("BOX", _PIT_COLOR)
        elif row.positions_gained is None:
            delta = ("", car_color)
        elif row.positions_gained > 0:
            delta = (f"+{row.positions_gained}", _GAINED_COLOR)
        elif row.positions_gained < 0:
            delta = (str(row.positions_gained), _LOST_COLOR)
        else:
            delta = ("=", _HEADER_COLOR)

        return {
            "position": (str(row.position), car_color),
            "name": (row.name[:18], car_color),
            "time": (time_text, car_color),
            "tyre": (letter, tyre_color),
            "age": (age_text, car_color),
            "stops": (stops_text, car_color),
            "delta": delta,
        }

    def _draw_race_control(self, status, width: int, height: int) -> None:
        """Faixa do estado da pista no topo e ultimas mensagens embaixo."""

        if status is not None:
            if status.restart and status.status == "GREEN":
                background, foreground = _RESTART_STYLE
            else:
                background, foreground = _STATUS_STYLE.get(
                    status.status, (_SWITCH_BG, PRIMARY_TEXT_COLOR)
                )
            band_w, band_h = 260, 30
            left, bottom = (width - band_w) / 2, height - 52
            arcade.draw_lbwh_rectangle_filled(left, bottom, band_w, band_h, background)
            self._status_text.text = status.label
            self._status_text.color = foreground
            self._status_text.x = width / 2
            self._status_text.y = bottom + band_h / 2
            self._status_text.draw()

        entries = self._feed.entries_through(self._playback.leader_laps(self._elapsed))
        recent = entries[-_FEED_LINES:]
        # A mais recente fica embaixo, logo acima do HUD; as antigas sobem.
        for i, entry in enumerate(reversed(recent)):
            text = self._feed_texts[i]
            text.text = f"V{entry.lap:<3} {entry.text}"
            text.color = _FEED_TINT.get(entry.status, _FEED_COLOR)
            text.y = 52 + i * 18
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


def show(saved_id: str | None = None) -> None:
    window = arcade.Window(SCREEN_WIDTH, SCREEN_HEIGHT, "Simulacao", resizable=True)
    if saved_id:
        try:
            window.show_view(_load_race_view(saved_id))
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            RuntimeError,
            ValueError,
        ) as error:
            raise SystemExit(f"nao foi possivel abrir a corrida: {error}") from error
    else:
        window.show_view(MenuView())
    arcade.run()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Visualiza corridas simuladas salvas.")
    parser.add_argument(
        "--saved",
        dest="saved_id",
        default=None,
        help="abre direto uma corrida salva por id (sem passar pelo menu)",
    )
    args = parser.parse_args()
    show(args.saved_id)
