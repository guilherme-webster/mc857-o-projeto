from __future__ import annotations

import urllib.error
from bisect import bisect_right
from collections.abc import Sequence

import arcade

from frontend.arcade.race_control_feed import RaceControlFeed
from frontend.arcade.race_playback import RacePlayback
from frontend.arcade.tournament_session import TournamentSession
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
# Largura visivel da faixa 2D (px), quando a corrida traz trajetoria espacial.
# E so apresentacao: a largura fisica real vem de ``track_space_2d.width_m``.
_TRACK_LANE_MIN_PX = 14.0
_TRACK_LANE_MAX_PX = 34.0
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
    "FUEL": "SEM COMB.",
}
_GAINED_COLOR = (70, 211, 142)
_LOST_COLOR = (255, 112, 112)
_PIT_COLOR = (240, 150, 40)
_HEADER_COLOR = (130, 140, 150)
_FUEL_COLOR = (170, 180, 195)
_LIFT_COAST_COLOR = (90, 200, 250)
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
    "fuel": ("COMB (kg)", 472, "right"),
    "saving": ("", 478, "left"),
    "speed": ("KM/H", 560, "right"),
}
# Colunas que so existem quando a corrida traz o modelo de massa.
_FUEL_COLUMNS = ("fuel", "saving")
# Medidor de combustivel a esquerda dos kg: (x a partir da margem, largura,
# altura) em px. A barra cheia e ``max_fuel_kg``, o teto regulamentar.
_FUEL_GAUGE = (400, 28, 7)
_TYRE_RADIUS = 8
# Largura reservada a esquerda para a classificacao; a pista e desenhada so no
# espaco restante, para que tabela e tracado nao se sobreponham. As colunas de
# combustivel alargam a tabela apenas nas corridas que as tem.
STANDINGS_WIDTH = 510
FUEL_STANDINGS_WIDTH = 580

_MENU_BG = (16, 22, 30)
_ROW_BG = (30, 41, 53)
_ROW_HOVER = (46, 62, 80)
_SWITCH_BG = (46, 62, 80)
_PRIMARY_BG = (190, 30, 45)
_PRIMARY_HOVER = (225, 45, 60)


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


def _unit_normals(unit):
    """Normal unitaria (para a esquerda do sentido) em cada ponto da centerline.

    Mesma construcao de ``build_track_space`` no motor: a tangente vem dos
    vizinhos no anel fechado e e girada 90 graus. ``unit`` sao os pontos ja
    normalizados; a normal fica no mesmo plano, para o offset lateral do carro
    casar com o desenho da pista.
    """

    n = len(unit)
    unique = n - 1  # o ultimo ponto repete o primeiro
    normals = []
    for i in range(n):
        prev_i = (i - 1) % unique
        next_i = (i + 1) % unique if i < unique else 1 % unique
        tx = unit[next_i][0] - unit[prev_i][0]
        ty = unit[next_i][1] - unit[prev_i][1]
        length = (tx * tx + ty * ty) ** 0.5 or 1.0
        normals.append((-ty / length, tx / length))
    return normals


def _build_time_to_distance(cum, physical=None):
    """Mapa fracao-de-tempo-da-volta -> distancia, pelo perfil fisico do motor.

    Usa o tempo acumulado de cada ponto, de modo que a posicao na tela e a
    velocidade exibida saem da mesma fonte. Sem perfil, o mapa e linear.
    """

    lap_length = cum[-1]
    if not physical or len(physical) < 2:
        return lambda t: max(0.0, min(1.0, t)) * lap_length

    total_time = physical[-1]["time_s"] or 1.0
    time_marks = [p["time_s"] / total_time for p in physical]
    dists = [p["distance_m"] for p in physical]
    marks = len(time_marks) - 1

    def mapper(t: float) -> float:
        t = max(0.0, min(1.0, t))
        i = max(0, min(bisect_right(time_marks, t) - 1, marks - 1))
        t0, t1 = time_marks[i], time_marks[i + 1]
        f = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
        return dists[i] + (dists[i + 1] - dists[i]) * f

    return mapper


def _build_speed_lookup(profile):
    if not profile:
        return None
    dists = [p["distance_m"] for p in profile]
    speeds_kmh = [p["speed_ms"] * 3.6 for p in profile]
    lap_length = dists[-1] or 1.0

    def lookup(distance_m: float) -> float:
        d = distance_m % lap_length
        i = max(1, min(bisect_right(dists, d), len(dists) - 1))
        d0, d1 = dists[i - 1], dists[i]
        f = (d - d0) / (d1 - d0) if d1 > d0 else 0.0
        return speeds_kmh[i - 1] + (speeds_kmh[i] - speeds_kmh[i - 1]) * f

    return lookup


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

    def __init__(
        self,
        track: dict,
        race: dict,
        notices: Sequence[str] = (),
        tournament: TournamentSession | None = None,
        stage_index: int = 1,
    ) -> None:
        """``notices`` sao avisos de quem disparou a corrida (origem do grid,
        opcoes ignoradas pelo motor), mostrados no canto superior direito.

        Com ``tournament``, a view mostra a etapa ``stage_index`` e oferece o
        botao para a proxima etapa ou, na ultima, para o resultado final.
        """

        super().__init__()
        self._tournament = tournament
        self._stage_index = stage_index
        pts = sorted(track["track_points"], key=lambda p: p["sequence"])
        self._cum = [p["cumulative_distance_m"] for p in pts]
        self._unit, self._aspect = _normalize([(p["x"], p["y"]) for p in pts])
        self._lap_length = track["lap_length_m"]
        track_physical = track.get("speed_profile_physical")

        self._playback = RacePlayback(race)
        self._total_laps = self._playback.total_laps
        self._color_by_driver = {
            car.driver_id: _PALETTE[i % len(_PALETTE)]
            for i, car in enumerate(self._playback.cars)
        }
        self._race_len_ms = self._playback.duration_ms
        # Perfil fisico por piloto (ADR da modelagem de pista): converte a
        # fracao de volta do RacePlayback em distancia na pista (reta rapida,
        # curva lenta) e em velocidade km/h. Sem perfil, cai no linear.
        per_driver = race.get("speed_profiles") or {}
        self._time_to_dist = {}
        self._speed_lookup = {}
        for car in self._playback.cars:
            profile = per_driver.get(car.driver_id, track_physical)
            self._time_to_dist[car.driver_id] = _build_time_to_distance(
                self._cum, profile
            )
            self._speed_lookup[car.driver_id] = _build_speed_lookup(profile)
        # Motor 2D: a corrida traz a trajetoria espacial (distancia + lateral por
        # instante). Com ela os carros andam lado a lado e ganham hitbox; sem
        # ela (motor detalhado ou corrida antiga) o desenho cai no circulo sobre
        # a linha de centro, como antes.
        self._trajectories = race.get("trajectories_2d") or {}
        self._space_2d = race.get("track_space_2d") or {}
        self._is_2d = bool(self._trajectories and self._space_2d)
        self._normals = _unit_normals(self._unit) if self._is_2d else []
        # Cache da faixa 2D: a geometria (bordas + asfalto) vai para a GPU uma
        # vez por tamanho de janela, num ShapeElementList desenhado em batch.
        # Recalcular e re-triangular a faixa (centenas de vertices) a cada frame
        # travava a animacao; o batch resolve isso.
        self._lane_cache_key: tuple[int, int, tuple] | None = None
        self._lane_shapes: arcade.shape_list.ShapeElementList | None = None
        self._lane_px = 1.0
        # Corridas sem o modelo de massa (salvas antes dele ou rodadas sem
        # ``fuel-v1.json``) mantem a tabela de antes, sem colunas vazias.
        self._show_fuel = self._playback.has_fuel
        self._standings_width = (
            FUEL_STANDINGS_WIDTH if self._show_fuel else STANDINGS_WIDTH
        )
        self._fuel_scale_kg = _fuel_scale_kg(self._playback)
        self._feed = RaceControlFeed(
            race, {car.driver_id: car.name for car in self._playback.cars}
        )
        self._weather = _weather_segments(race)

        self._elapsed = 0.0
        self._speed = 1.0
        self._speed_kmh: dict[str, float] = {}
        self._direction = 1  # +1 para frente, -1 para tras
        self._paused = False
        self._circuit = (
            tournament.stage_title(stage_index)
            if tournament is not None
            else _race_title(race, track)
        )
        self._switch_hover = False
        self._end_hover = False
        self._next_hover = False

        self._title = arcade.Text("", 20, 0, PRIMARY_TEXT_COLOR, 18, bold=True)
        self._hud = arcade.Text(
            "", 20, 24, PRIMARY_TEXT_COLOR, 13, font_name="monospace"
        )
        self._notice_texts = [
            arcade.Text(notice, 0, 0, _HEADER_COLOR, 10, anchor_x="right")
            for notice in notices
        ]
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
        next_label = None
        if tournament is not None:
            next_label = (
                "Próxima etapa"
                if tournament.has_next(stage_index)
                else "Resultado do torneio"
            )
        self._next_text = (
            arcade.Text(
                next_label,
                0,
                0,
                PRIMARY_TEXT_COLOR,
                13,
                bold=True,
                anchor_x="center",
                anchor_y="center",
            )
            if next_label
            else None
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

    def _next_rect(self):
        """(left, bottom, width, height) do botao de proxima etapa/resultado."""

        width, height = 190, 34
        end_left = self._end_rect()[0]
        return end_left - width - 10, 20, width, height

    def _open_next(self) -> None:
        """Avance para a proxima etapa ou abra o resultado do torneio."""

        tournament = self._tournament
        assert tournament is not None
        if tournament.has_next(self._stage_index):
            index = self._stage_index + 1
            stage = tournament.stage(index)
            self.window.show_view(
                TrackView(
                    stage.track,
                    stage.race,
                    notices=tournament.notices,
                    tournament=tournament,
                    stage_index=index,
                )
            )
            return
        from frontend.arcade.tournament_view import TournamentResultView

        self.window.show_view(TournamentResultView(tournament, return_view=self))

    def _projected(self) -> list[tuple[float, float]]:
        """Projete a geometria normalizada no tamanho atual da janela."""

        width, height = self.window.width, self.window.height
        area_left = self._standings_width
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
        self._next_hover = self._next_text is not None and self._in_rect(
            x, y, self._next_rect()
        )

    def on_mouse_press(self, x, y, button, modifiers) -> None:
        if self._next_text is not None and self._in_rect(x, y, self._next_rect()):
            self._open_next()
        elif self._in_rect(x, y, self._switch_rect()):
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

    def _lateral_at(self, driver_id: str, t_ms: float) -> float:
        """Deslocamento lateral (m) interpolado da trajetoria 2D no tempo.

        Cada ponto da serie e ``[t_ms, lateral_m]``. Zero quando o carro nao tem
        trajetoria. Antes do primeiro e depois do ultimo ponto, vale a borda.
        """

        series = self._trajectories.get(driver_id)
        if not series:
            return 0.0
        if t_ms <= series[0][0]:
            return series[0][1]
        if t_ms >= series[-1][0]:
            return series[-1][1]
        lo, hi = 0, len(series) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if series[mid][0] < t_ms:
                lo = mid + 1
            else:
                hi = mid
        a, b = series[lo - 1], series[lo]
        span = b[0] - a[0]
        f = (t_ms - a[0]) / span if span > 0 else 0.0
        return a[1] + (b[1] - a[1]) * f

    def _lane_scale_px(self, screen) -> float:
        """Metros laterais -> pixels, pela escala do desenho projetado atual.

        Converte o deslocamento lateral do motor (metros) para pixels usando a
        mesma razao perimetro-em-px / perimetro-em-metros do traçado desenhado,
        de modo que a faixa acompanhe o zoom da janela.
        """

        perimeter_px = sum(
            (
                (screen[i + 1][0] - screen[i][0]) ** 2
                + (screen[i + 1][1] - screen[i][1]) ** 2
            )
            ** 0.5
            for i in range(len(screen) - 1)
        )
        lap_m = self._space_2d.get("lap_length_m") or self._lap_length or 1.0
        return perimeter_px / lap_m

    def _space_pos_at(self, screen, lane_px: float, distance_m: float, lateral_m: float):
        """``(x, y)`` de tela a ``distance_m`` com deslocamento ``lateral_m``.

        Interpola o ponto da centerline e a normal projetada, e aplica o offset
        lateral em pixels. E a versao de tela de ``TrackSpace.position``.
        """

        d = distance_m % self._lap_length
        i = max(0, min(bisect_right(self._cum, d) - 1, len(self._cum) - 2))
        d0, d1 = self._cum[i], self._cum[i + 1]
        (x0, y0), (x1, y1) = screen[i], screen[i + 1]
        f = (d - d0) / (d1 - d0) if d1 > d0 else 0.0
        cx, cy = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
        (nx0, ny0), (nx1, ny1) = self._normals[i], self._normals[i + 1]
        nx, ny = nx0 + (nx1 - nx0) * f, ny0 + (ny1 - ny0) * f
        nlen = (nx * nx + ny * ny) ** 0.5 or 1.0
        offset = lateral_m * lane_px
        return (cx + nx / nlen * offset, cy + ny / nlen * offset, nx / nlen, ny / nlen)

    def _draw_cars(self, screen) -> None:
        """Desenho legado: circulo sobre a linha de centro (motor detalhado).

        Carros que abandonaram nao sao desenhados; os demais param na linha de
        chegada. O RacePlayback decide a volta e a fracao dela; o perfil fisico
        converte a fracao em distancia (reta rapida, curva lenta) e em km/h.
        """

        self._speed_kmh = {}
        for driver_id, laps in self._playback.on_track(self._elapsed):
            whole = int(laps)
            fraction = laps - whole
            to_dist = self._time_to_dist[driver_id]
            dist = whole * self._lap_length + to_dist(fraction)
            lookup = self._speed_lookup[driver_id]
            if lookup is not None:
                self._speed_kmh[driver_id] = lookup(dist)
            x, y = self._pos_at(screen, dist)
            arcade.draw_circle_filled(
                x, y, CAR_RADIUS, self._color_by_driver[driver_id]
            )

    def _ensure_lane_geometry(self, screen, track_color) -> None:
        """Monte a faixa num ShapeElementList, recriando so quando preciso.

        A faixa (asfalto como triangle strip + duas bordas) so muda quando a
        janela redimensiona ou a cor da bandeira troca. Enquanto a chave de
        cache nao muda, o batch ja na GPU e reaproveitado.
        """

        key = (self.window.width, self.window.height, tuple(track_color))
        if self._lane_cache_key == key and self._lane_shapes is not None:
            return
        lane_px = self._lane_scale_px(screen)
        half_px = self._space_2d.get("width_m", 12.0) / 2.0 * lane_px
        half_px = max(_TRACK_LANE_MIN_PX, min(_TRACK_LANE_MAX_PX, half_px)) / 2.0
        left_edge = []
        right_edge = []
        for i, (cx, cy) in enumerate(screen):
            nx, ny = self._normals[i]
            left_edge.append((cx + nx * half_px, cy + ny * half_px))
            right_edge.append((cx - nx * half_px, cy - ny * half_px))

        # Triangle strip intercalando as duas bordas: cada par de pontos vira
        # um quad (dois triangulos), sem o problema de concavidade de um unico
        # poligono grande. Fecha o anel repetindo o primeiro par.
        strip = []
        for lp, rp in zip([*left_edge, left_edge[0]], [*right_edge, right_edge[0]]):
            strip.append(lp)
            strip.append(rp)
        asphalt = (26, 28, 32, 255)
        edge = (*track_color[:3], 255)

        shapes = arcade.shape_list.ShapeElementList()
        shapes.append(
            arcade.shape_list.create_triangles_strip_filled_with_colors(
                strip, [asphalt] * len(strip)
            )
        )
        shapes.append(
            arcade.shape_list.create_line_strip([*left_edge, left_edge[0]], edge, 1.5)
        )
        shapes.append(
            arcade.shape_list.create_line_strip(
                [*right_edge, right_edge[0]], edge, 1.5
            )
        )
        self._lane_shapes = shapes
        self._lane_px = lane_px
        self._lane_cache_key = key

    def _draw_track_2d(self, screen, track_color) -> None:
        """Pista como faixa com largura, desenhada em batch pela GPU.

        A geometria vai para um ShapeElementList criado uma vez
        (``_ensure_lane_geometry``) e so e recriada ao redimensionar ou trocar a
        cor da bandeira; o desenho por frame e so um ``draw()`` em batch.
        """

        self._ensure_lane_geometry(screen, track_color)
        assert self._lane_shapes is not None
        self._lane_shapes.draw()

    def _draw_cars_2d(self, screen) -> None:
        """Carro como retangulo orientado (hitbox) na posicao lateral real.

        A posicao longitudinal vem do tempo de volta (como no modo legado) e o
        deslocamento lateral vem da trajetoria 2D exportada pelo motor, de modo
        que dois carros podem aparecer lado a lado. O retangulo tem o tamanho
        fisico do carro, alinhado a tangente da pista.
        """

        lane_px = self._lane_px
        length_m = self._space_2d.get("car_length_m", 5.0)
        width_m = self._space_2d.get("car_width_m", 2.0)
        half_len = max(4.0, length_m * lane_px / 2.0)
        half_wid = max(2.5, width_m * lane_px / 2.0)
        self._speed_kmh = {}
        for driver_id, laps in self._playback.on_track(self._elapsed):
            # Distancia longitudinal vem do tempo de volta + perfil (como no
            # modo legado); so o deslocamento lateral vem da trajetoria 2D.
            whole = int(laps)
            to_dist = self._time_to_dist[driver_id]
            dist = whole * self._lap_length + to_dist(laps - whole)
            lateral = self._lateral_at(driver_id, self._elapsed)
            lookup = self._speed_lookup[driver_id]
            if lookup is not None:
                self._speed_kmh[driver_id] = lookup(dist)
            x, y, nx, ny = self._space_pos_at(screen, lane_px, dist, lateral)
            # Tangente = perpendicular da normal; orienta o retangulo na pista.
            tx, ty = -ny, nx
            corners = [
                (x + tx * half_len + nx * half_wid, y + ty * half_len + ny * half_wid),
                (x + tx * half_len - nx * half_wid, y + ty * half_len - ny * half_wid),
                (x - tx * half_len - nx * half_wid, y - ty * half_len - ny * half_wid),
                (x - tx * half_len + nx * half_wid, y - ty * half_len + ny * half_wid),
            ]
            color = self._color_by_driver[driver_id]
            arcade.draw_polygon_filled(corners, color)
            arcade.draw_polygon_outline(corners, (12, 14, 18), 1.0)

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
        if self._is_2d:
            self._draw_track_2d(screen, track_color)
            self._draw_cars_2d(screen)
        else:
            arcade.draw_line_strip([*screen, screen[0]], track_color, 2)
            self._draw_cars(screen)

        rain = self._current_rain()
        label, color = _RAIN_LABEL.get(rain, (rain, PRIMARY_TEXT_COLOR))
        self._weather_text.text = label
        self._weather_text.color = color
        self._weather_text.x = width - 20
        self._weather_text.y = height - 40
        self._weather_text.draw()
        for i, notice in enumerate(self._notice_texts):
            notice.x = width - 20
            notice.y = height - 64 - i * 16
            notice.draw()

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
        if self._next_text is not None:
            self._draw_button(
                self._next_rect(), self._next_text, self._next_hover, primary=True
            )

    def _draw_button(self, rect, text, hover, primary: bool = False) -> None:
        left, bottom, width, height = rect
        if primary:
            color = _PRIMARY_HOVER if hover else _PRIMARY_BG
        else:
            color = _ROW_HOVER if hover else _SWITCH_BG
        arcade.draw_lbwh_rectangle_filled(left, bottom, width, height, color)
        text.x = left + width / 2
        text.y = bottom + height / 2
        text.draw()

    def _draw_standings(self, height: int) -> None:
        """Classificacao ao vivo com pneu, paradas, posicoes ganhas e combustivel.

        O composto e a idade sao os do ultimo retrato do carro; "BOX" marca a
        volta que termina com parada; quem abandonou mostra a causa. O
        combustivel e interpolado dentro da volta, e "L&C" marca a volta feita
        em lift-and-coast.
        """

        left = 20
        header_y = height - 74
        top = height - 96
        line_h = 20
        for key, text in self._header_texts.items():
            if key in _FUEL_COLUMNS and not self._show_fuel:
                continue
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
                        9 if key in ("tyre", "saving") else 12,
                        anchor_x=anchor,
                        anchor_y="center",
                        bold=key in ("tyre", "saving"),
                    )
                    for key, (_, _, anchor) in _STANDING_COLUMNS.items()
                }
            )
        for i, row in enumerate(standings):
            texts = self._row_texts[i]
            y = top - i * line_h
            car_color = self._color_by_driver.get(row.driver_id, PRIMARY_TEXT_COLOR)
            cells = self._standing_cells(row, car_color)
            if self._show_fuel and row.fuel_kg is not None and not row.retired:
                self._draw_fuel_gauge(left, y, row.fuel_kg, row.lift_and_coast)
            for key, (value, color) in cells.items():
                if key in _FUEL_COLUMNS and not self._show_fuel:
                    continue
                text = texts[key]
                text.text = value
                text.color = color
                text.x = left + _STANDING_COLUMNS[key][1]
                text.y = y
                if key == "tyre" and value:
                    arcade.draw_circle_outline(text.x, y, _TYRE_RADIUS, color, 2)
                text.draw()

    def _draw_fuel_gauge(
        self, left: float, y: float, fuel_kg: float, lift_and_coast: bool
    ) -> None:
        """Barra horizontal do tanque, cheia em ``_fuel_scale_kg``."""

        if self._fuel_scale_kg is None:
            return
        offset, gauge_w, gauge_h = _FUEL_GAUGE
        gauge_left = left + offset
        bottom = y - gauge_h / 2
        fraction = max(0.0, min(fuel_kg / self._fuel_scale_kg, 1.0))
        if fraction > 0.0:
            color = _LIFT_COAST_COLOR if lift_and_coast else _FUEL_COLOR
            arcade.draw_lbwh_rectangle_filled(
                gauge_left, bottom, gauge_w * fraction, gauge_h, color
            )
        arcade.draw_lbwh_rectangle_outline(
            gauge_left, bottom, gauge_w, gauge_h, _HEADER_COLOR, 1
        )

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

        fuel_text = ""
        saving = ("", car_color)
        if row.fuel_kg is not None and not row.retired:
            fuel_text = f"{row.fuel_kg:.1f}"
            if row.lift_and_coast:
                saving = ("L&C", _LIFT_COAST_COLOR)

        speed = self._speed_kmh.get(row.driver_id)
        speed_text = "" if speed is None or row.retired else f"{speed:.0f}"

        return {
            "position": (str(row.position), car_color),
            "name": (row.name[:18], car_color),
            "time": (time_text, car_color),
            "tyre": (letter, tyre_color),
            "age": (age_text, car_color),
            "stops": (stops_text, car_color),
            "delta": delta,
            "fuel": (fuel_text, car_color),
            "saving": saving,
            "speed": (speed_text, car_color),
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


def _fuel_scale_kg(playback: RacePlayback) -> float | None:
    """Massa que enche o medidor: o teto regulamentar ou, sem ele, a maior
    carga de largada. ``None`` quando nao ha escala positiva para desenhar.
    """

    if playback.max_fuel_kg is not None:
        return playback.max_fuel_kg
    largest = max(
        (car.fuel_states[0].kg for car in playback.cars if car.fuel_states),
        default=0.0,
    )
    return largest if largest > 0.0 else None


def _weather_segments(race: dict) -> list[dict]:
    setup = race.get("setup") if isinstance(race, dict) else None
    segments = setup.get("weather") if isinstance(setup, dict) else None
    return segments if isinstance(segments, list) else []


def _race_title(race: dict, track: dict) -> str:
    """Nome da pista quando o modelo a conhece; senao, o ID do circuito.

    A geometria nao traz nome. ``track_reference`` traz o nome do circuito
    calibrado, mas, para pistas fora do modelo, ele descreve o circuito de
    reserva ("mediana do campo"), e ai o ID e mais honesto.
    """

    reference = race.get("track_reference") if isinstance(race, dict) else None
    circuit_id = str(track["circuit_id"])
    if isinstance(reference, dict) and reference.get("model_track_id") == circuit_id:
        name = reference.get("model_track_name")
        if name:
            return str(name)
    return circuit_id


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
