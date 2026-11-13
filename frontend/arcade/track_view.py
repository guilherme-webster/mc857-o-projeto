from __future__ import annotations

import urllib.error
from bisect import bisect_right
from collections.abc import Sequence
from queue import Empty, SimpleQueue
from threading import Thread

import arcade

from frontend.arcade.race_control_feed import RaceControlFeed
from frontend.arcade.race_playback import RacePlayback, track_condition_label
from frontend.arcade.theme import (
    BACKGROUND_COLOR,
    PRIMARY_TEXT_COLOR,
    TRACK_EDGE_COLOR,
)
from frontend.arcade.tournament_session import TournamentSession
from frontend.arcade.track_client import (
    fetch_race,
    fetch_saved_race,
    fetch_track,
    save_race,
)

SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 800
MARGIN = 80
CAR_RADIUS = 7
# Largura visivel da faixa 2D (px), quando a corrida traz trajetoria espacial.
# E so apresentacao: a largura fisica real vem de ``track_space_2d.width_m``.
_TRACK_LANE_MIN_PX = 14.0
_TRACK_LANE_MAX_PX = 34.0
# Linha de chegada/largada: onde a contagem de voltas recomeca (distancia zero).
_START_LINE_COLOR = (240, 240, 240)
_START_LINE_WIDTH = 3.0
_SAVE_OK_COLOR = (70, 211, 142)
_SAVE_ERROR_COLOR = (230, 120, 120)
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

_ROW_HOVER = (46, 62, 80)
# Linha realcada do carro selecionado para o grafico de decomposicao.
_SELECTED_ROW_COLOR = (54, 74, 96)
# Fatias do grafico de decomposicao de velocidade (fracao de v_max).
_BREAKDOWN_EFFECTIVE_COLOR = (90, 200, 120)
_BREAKDOWN_TRANSIENT_COLOR = (150, 150, 160)
_BREAKDOWN_CORNER_COLOR = (120, 150, 230)
_BREAKDOWN_FACTOR_COLORS = {
    "tyre": (230, 170, 70),
    "fuel": (170, 180, 195),
    "weather": (90, 200, 250),
    "race_control": (240, 150, 40),
}
_BREAKDOWN_LABELS = {
    "effective": "velocidade",
    "transient": "acel/freio",
    "corner": "curva",
    "tyre": "pneu",
    "fuel": "combustível",
    "weather": "clima",
    "race_control": "controle",
}
# Painel flutuante da decomposicao: um por piloto, arrastavel e fechavel.
_PANEL_W = 300.0
_PANEL_H = 252.0
_PANEL_TITLE_H = 20.0  # faixa de titulo (arrastar aqui)
_PANEL_CLOSE = 16.0  # lado do botao de fechar
_PANEL_BG = (22, 30, 40)
_PANEL_BORDER = (70, 84, 100)
_PANEL_CASCADE = 24.0  # deslocamento entre paineis novos


class _BreakdownPanel:
    """Painel flutuante da decomposicao de um piloto; posicao pelo canto inf-esq."""

    __slots__ = ("driver_id", "x", "y")

    def __init__(self, driver_id: str, x: float, y: float) -> None:
        self.driver_id = driver_id
        self.x = x
        self.y = y
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


def saved_race_inputs(saved_id: str | None) -> tuple[dict, dict]:
    """(pista, corrida) de uma corrida salva, ou da atual se ``saved_id`` for None.

    So faz as chamadas HTTP: pode rodar fora da thread do Arcade. A
    ``TrackView`` e criada depois, na thread da janela.
    """

    race = fetch_saved_race(saved_id) if saved_id else fetch_race()
    circuit_id = _race_circuit_id(race)
    if circuit_id is None:
        raise RuntimeError("a corrida nao tem pista no setup")
    return fetch_track(circuit_id), race


def _load_race_view(saved_id: str | None) -> TrackView:
    """Monte a TrackView de uma corrida salva (ou da atual, se ``saved_id`` None)."""

    track, race = saved_race_inputs(saved_id)
    return TrackView(track, race)


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
        list_view: arcade.View | None = None,
        saveable: bool = True,
    ) -> None:
        """``notices`` sao avisos de quem disparou a corrida (origem do grid,
        opcoes ignoradas pelo motor), mostrados no canto superior direito.

        Com ``tournament``, a view mostra a etapa ``stage_index`` e oferece o
        botao para a proxima etapa ou, na ultima, para o resultado final.
        """

        super().__init__()
        self._tournament = tournament
        # Lista de simulacoes salvas de onde a corrida foi aberta; sem ela, nao
        # ha botao de voltar. O botao ocupa o lugar do "Proxima etapa", que so
        # existe em torneio.
        self._list_view = list_view
        self._back_hover = False
        # Corridas abertas das simulacoes salvas ja estao salvas: sem "Salvar".
        self._saveable = saveable
        self._stage_index = stage_index
        pts = sorted(track["track_points"], key=lambda p: p["sequence"])
        self._cum = [p["cumulative_distance_m"] for p in pts]
        self._pit_path = (race.get("pit_lane_2d") or {}).get("points", [])
        self._pit_service_m = (race.get("pit_lane_2d") or {}).get("service_distance_m")
        self._pit_distances = [p[0] for p in self._pit_path]
        # O caminho aberto usa a mesma transformação da pista, inclusive nas
        # conexões de entrada/saída exportadas pelo motor.
        unit, self._aspect = _normalize(
            [(p["x"], p["y"]) for p in pts] + [(p[1], p[2]) for p in self._pit_path]
        )
        self._unit = unit[: len(pts)]
        self._pit_unit = unit[len(pts) :]
        self._pit_screen = []
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
        # Estado da pista por volta (agua, temperatura), quando o backend o envia.
        self._race = race

        # Volta inicial da exibicao (sessao da etapa). A corrida ja foi simulada
        # desde a largada; so o relogio da reproducao comeca mais adiante.
        session = (
            tournament.stage(stage_index).planned.session
            if tournament is not None
            else None
        )
        self._start_lap = 1 if session is None else session.first_lap
        self._elapsed = self._playback.lap_start_ms(self._start_lap)
        self._speed = 1.0
        self._speed_kmh: dict[str, float] = {}
        self._direction = 1  # +1 para frente, -1 para tras
        self._paused = False
        # Decomposicao de velocidade: paineis flutuantes, um por piloto. A
        # ordem da lista e o z-order (ultimo no topo). Clique numa linha da
        # tabela abre/fecha; o painel e arrastavel pela faixa de titulo.
        self._show_breakdown = self._playback.has_speed_breakdown
        self._breakdown_panels: list[_BreakdownPanel] = []
        self._standing_row_rects: list[tuple[str, tuple[float, float, float, float]]] = []
        # Painel em arraste e offset do cursor ate o canto, e contador de
        # cascata para paineis novos nao nascerem exatamente sobrepostos.
        self._dragging_panel: _BreakdownPanel | None = None
        self._drag_offset = (0.0, 0.0)
        self._panel_opened_count = 0
        self._circuit = (
            tournament.stage_title(stage_index)
            if tournament is not None
            else _race_title(race, track)
        )
        self._switch_hover = False
        self._end_hover = False
        self._next_hover = False
        self._prev_hover = False
        self._prev_text = arcade.Text(
            "‹  Etapa anterior",
            0,
            0,
            PRIMARY_TEXT_COLOR,
            13,
            anchor_x="center",
            anchor_y="center",
        )

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
        # Salvar a corrida exibida: o pedido roda numa thread e o resultado volta
        # pela fila, lido em ``on_update`` na thread do Arcade.
        self._saving = False
        self._save_results: SimpleQueue[tuple[str, str]] = SimpleQueue()
        self._save_message = arcade.Text(
            "", 0, 0, _SAVE_OK_COLOR, 10, anchor_x="right", anchor_y="bottom"
        )
        self._switch_text = arcade.Text(
            "Salvar corrida",
            0,
            0,
            PRIMARY_TEXT_COLOR,
            13,
            anchor_x="center",
            anchor_y="center",
        )
        self._back_text = arcade.Text(
            "‹  Voltar à lista",
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
        # Textos reutilizaveis do grafico de decomposicao de velocidade. Os
        # mesmos objetos sao reposicionados por painel a cada frame.
        self._breakdown_title = arcade.Text(
            "", 0, 0, PRIMARY_TEXT_COLOR, 11, bold=True, anchor_y="center"
        )
        self._breakdown_close_x = arcade.Text(
            "×", 0, 0, PRIMARY_TEXT_COLOR, 13, bold=True,
            anchor_x="center", anchor_y="center",
        )
        # Secao de contexto do painel: velocidade base e atributos do piloto.
        # Cada linha e um par (rotulo a esquerda, valor a direita) para alinhar.
        self._breakdown_context = [
            (
                arcade.Text("", 0, 0, _HEADER_COLOR, 10, anchor_y="center"),
                arcade.Text(
                    "", 0, 0, PRIMARY_TEXT_COLOR, 10,
                    anchor_x="right", anchor_y="center",
                ),
            )
            for _ in range(7)
        ]
        # Legenda das fatias: rotulo a esquerda, valor % alinhado a direita.
        self._breakdown_legend = {
            key: (
                arcade.Text("", 0, 0, PRIMARY_TEXT_COLOR, 10, anchor_y="center"),
                arcade.Text(
                    "", 0, 0, PRIMARY_TEXT_COLOR, 10,
                    anchor_x="right", anchor_y="center",
                ),
            )
            for key in (
                "effective",
                "transient",
                "corner",
                "tyre",
                "fuel",
                "weather",
                "race_control",
            )
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
        """(left, bottom, width, height) do botao 'Salvar corrida'."""

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

    def _prev_rect(self):
        """(left, bottom, width, height) do botao de etapa anterior: a esquerda da proxima."""

        left, bottom, width, height = self._next_rect()
        return left - width - 10, bottom, width, height

    def _has_previous(self) -> bool:
        return self._tournament is not None and self._stage_index > 1

    def _open_previous(self) -> None:
        """Volte para a etapa anterior do torneio, numa TrackView nova."""

        tournament = self._tournament
        assert tournament is not None
        index = self._stage_index - 1
        stage = tournament.stage(index)
        self.window.show_view(
            TrackView(
                stage.track,
                stage.race,
                notices=tournament.notices,
                tournament=tournament,
                stage_index=index,
                saveable=self._saveable,
            )
        )

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
                    saveable=self._saveable,
                )
            )
            return
        from frontend.arcade.tournament_view import TournamentResultView

        self.window.show_view(
            TournamentResultView(
                tournament, return_view=self, saveable=self._saveable
            )
        )

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
        self._pit_screen = [
            (off_x + ux * draw_w, off_y + uy * draw_h) for ux, uy in self._pit_unit
        ]
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
        self._drain_save_results()
        if self._paused:
            return
        step = dt * BASE_PLAYBACK_SPEED * self._speed * self._direction
        self._elapsed = max(0.0, min(self._elapsed + step, self._race_len_ms))

    @staticmethod
    def _in_rect(x, y, rect) -> bool:
        left, bottom, width, height = rect
        return left <= x <= left + width and bottom <= y <= bottom + height

    def on_mouse_motion(self, x, y, dx, dy) -> None:
        self._switch_hover = self._saveable and self._in_rect(x, y, self._switch_rect())
        self._end_hover = self._in_rect(x, y, self._end_rect())
        self._back_hover = self._list_view is not None and self._in_rect(
            x, y, self._next_rect()
        )
        self._next_hover = self._next_text is not None and self._in_rect(
            x, y, self._next_rect()
        )
        self._prev_hover = self._has_previous() and self._in_rect(x, y, self._prev_rect())

    def on_mouse_press(self, x, y, button, modifiers) -> None:
        if self._has_previous() and self._in_rect(x, y, self._prev_rect()):
            self._open_previous()
            return
        if self._next_text is not None and self._in_rect(x, y, self._next_rect()):
            self._open_next()
            return
        if self._list_view is not None and self._in_rect(x, y, self._next_rect()):
            self.window.show_view(self._list_view)
            return
        if self._saveable and self._in_rect(x, y, self._switch_rect()):
            self._save_race()
            return
        if self._in_rect(x, y, self._end_rect()):
            self._elapsed = self._race_len_ms
            self._paused = True
            self._direction = 1
            return
        if self._show_breakdown and self._press_breakdown(x, y):
            return

    def _press_breakdown(self, x: float, y: float) -> bool:
        """Trate o clique nos paineis e na tabela; devolve se consumiu o clique.

        Ordem: botao de fechar e faixa de titulo dos paineis (do topo para o
        fundo, respeitando a sobreposicao), depois as linhas da tabela (toggle).
        """

        # Paineis do topo para o fundo (fim da lista = topo).
        for panel in reversed(self._breakdown_panels):
            if self._in_rect(x, y, self._panel_close_rect(panel)):
                self._breakdown_panels.remove(panel)
                return True
            if self._in_rect(x, y, self._panel_title_rect(panel)):
                # Traz para frente e inicia o arraste pela faixa de titulo.
                self._breakdown_panels.remove(panel)
                self._breakdown_panels.append(panel)
                self._dragging_panel = panel
                self._drag_offset = (x - panel.x, y - panel.y)
                return True
            if self._in_rect(x, y, self._panel_body_rect(panel)):
                # Clicar no corpo so traz para frente, sem arrastar.
                self._breakdown_panels.remove(panel)
                self._breakdown_panels.append(panel)
                return True

        for driver_id, rect in self._standing_row_rects:
            if self._in_rect(x, y, rect):
                self._toggle_panel(driver_id)
                return True
        return False

    def _toggle_panel(self, driver_id: str) -> None:
        """Abre o painel do piloto, ou fecha se ja estiver aberto."""

        for panel in self._breakdown_panels:
            if panel.driver_id == driver_id:
                self._breakdown_panels.remove(panel)
                return
        # Cascata a partir do canto inferior direito, sempre dentro da janela.
        shift = (self._panel_opened_count % 6) * _PANEL_CASCADE
        self._panel_opened_count += 1
        max_x = max(0.0, self.window.width - _PANEL_W)
        max_y = max(0.0, self.window.height - _PANEL_H)
        base_x = min(self.window.width - _PANEL_W - MARGIN, max_x)
        x = max(0.0, min(base_x - shift, max_x))
        y = max(0.0, min(20.0 + shift, max_y))
        self._breakdown_panels.append(_BreakdownPanel(driver_id, x, y))

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers) -> None:
        panel = self._dragging_panel
        if panel is None:
            return
        ox, oy = self._drag_offset
        # Mantem o painel dentro da janela, pela faixa de titulo.
        panel.x = max(0.0, min(x - ox, self.window.width - _PANEL_W))
        panel.y = max(0.0, min(y - oy, self.window.height - _PANEL_H))

    def on_mouse_release(self, x, y, button, modifiers) -> None:
        self._dragging_panel = None

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
            self._elapsed = self._playback.lap_start_ms(self._start_lap)
            self._direction = 1
        elif symbol == arcade.key.M:
            self._open_saved_list()

    def _save_race(self) -> None:
        """Grava esta corrida (a exibida, nao o torneio), com nome padrao do backend."""

        if not self._saveable or self._saving:
            return
        self._saving = True
        self._save_message.text = "Salvando corrida…"
        self._save_message.color = _SAVE_OK_COLOR
        race = self._race
        results = self._save_results

        def run() -> None:
            try:
                meta = save_race(race)
            except (RuntimeError, OSError, ValueError) as error:
                results.put(("error", str(error)))
            else:
                results.put(("saved", str(meta.get("name", ""))))

        Thread(target=run, name="save-race", daemon=True).start()

    def _drain_save_results(self) -> None:
        while True:
            try:
                kind, text = self._save_results.get_nowait()
            except Empty:
                return
            self._saving = False
            if kind == "saved":
                self._save_message.text = f"Corrida salva como “{text}”."
                self._save_message.color = _SAVE_OK_COLOR
            else:
                self._save_message.text = f"Não foi possível salvar: {text}"
                self._save_message.color = _SAVE_ERROR_COLOR

    def _open_saved_list(self) -> None:
        """Corridas e torneios salvos; voltar retorna a esta corrida."""

        from frontend.arcade.saved_tournaments_view import SavedTournamentsView

        self.window.show_view(SavedTournamentsView(return_view=self))

    def _pos_at(self, screen, distance_m: float):
        d = distance_m % self._lap_length
        i = max(0, min(bisect_right(self._cum, d) - 1, len(self._cum) - 2))
        d0, d1 = self._cum[i], self._cum[i + 1]
        (x0, y0), (x1, y1) = screen[i], screen[i + 1]
        f = (d - d0) / (d1 - d0) if d1 > d0 else 0.0
        return (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)

    def _spatial_at(self, driver_id: str, t_ms: float):
        """``(distance_m, lateral_m, speed_kmh)`` interpolados da trajetoria 2D.

        Os quatro primeiros campos são tempo, distância, lateral e velocidade.
        Trajetórias novas incluem a distância nos boxes no quinto campo.
        ``None`` quando o carro nao tem trajetoria (corrida nao-2D). Antes do
        primeiro e depois do ultimo ponto, vale a borda (grid de largada /
        chegada ou abandono).
        """

        point = self._playback.car(driver_id).spatial_at(t_ms)
        if point is None:
            return None
        return point.distance_m, point.lateral_m, point.speed_kmh

    def _pit_pos_at(self, distance_m: float):
        """Posição e normal no caminho aberto dos boxes recebido por HTTP."""

        i = max(
            1,
            min(
                bisect_right(self._pit_distances, distance_m),
                len(self._pit_distances) - 1,
            ),
        )
        d0, d1 = self._pit_distances[i - 1], self._pit_distances[i]
        x0, y0 = self._pit_screen[i - 1]
        x1, y1 = self._pit_screen[i]
        f = max(0.0, min(1.0, (distance_m - d0) / (d1 - d0)))
        length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 or 1.0
        return x0 + f * (x1 - x0), y0 + f * (y1 - y0), -(y1 - y0) / length, (x1 - x0) / length

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

    def _draw_start_finish_line(self, screen) -> None:
        """Linha de chegada no ponto de distancia zero: onde cada volta comeca.

        Atravessa a faixa, perpendicular ao sentido do traçado. Na vista 2D a
        largura segue a faixa desenhada (mesma conta de ``_ensure_lane_geometry``).
        """

        if len(screen) < 2:
            return
        (x0, y0), (x1, y1) = screen[0], screen[1]
        dx, dy = x1 - x0, y1 - y0
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return
        nx, ny = -dy / length, dx / length
        if self._is_2d:
            lane_width = self._space_2d.get("width_m", 12.0) * self._lane_px
            visible = max(_TRACK_LANE_MIN_PX, min(_TRACK_LANE_MAX_PX, lane_width))
            half = visible / 2.0 + 2.0
        else:
            half = 8.0
        arcade.draw_line(
            x0 - nx * half,
            y0 - ny * half,
            x0 + nx * half,
            y0 + ny * half,
            _START_LINE_COLOR,
            _START_LINE_WIDTH,
        )

    def _draw_cars_2d(self, screen) -> None:
        """Carro como retangulo orientado (hitbox) na posicao espacial real.

        Posicao longitudinal e lateral vem da trajetoria 2D exportada pelo
        motor, nao do tempo de volta: assim o grid de largada escalonado, a
        largada parada e os carros lado a lado aparecem como na fisica. O
        retangulo tem o tamanho fisico do carro, alinhado a tangente da pista.
        """

        lane_px = self._lane_px
        length_m = self._space_2d.get("car_length_m", 5.0)
        width_m = self._space_2d.get("car_width_m", 2.0)
        half_len = max(4.0, length_m * lane_px / 2.0)
        half_wid = max(2.5, width_m * lane_px / 2.0)
        self._speed_kmh = {}
        for driver_id, laps in self._playback.on_track(self._elapsed):
            spatial = self._spatial_at(driver_id, self._elapsed)
            if spatial is None:
                whole = int(laps)
                to_dist = self._time_to_dist[driver_id]
                dist = whole * self._lap_length + to_dist(laps - whole)
                lateral = 0.0
                self._speed_kmh[driver_id] = (
                    lookup(dist) if (lookup := self._speed_lookup[driver_id]) else 0.0
                )
            else:
                dist, lateral, speed_kmh = spatial
                # Velocidade vem da propria trajetoria do motor (campo exportado),
                # para refletir a largada parada e o ritmo real por instante.
                self._speed_kmh[driver_id] = speed_kmh
            point = self._playback.car(driver_id).spatial_at(self._elapsed)
            if (
                point is not None
                and point.pit_distance_m is not None
                and self._pit_screen
            ):
                x, y, nx, ny = self._pit_pos_at(point.pit_distance_m)
            else:
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
            self._draw_start_finish_line(screen)
            if self._pit_screen:
                arcade.draw_line_strip(
                    self._pit_screen, (190, 146, 52), max(5.0, 4.0 * self._lane_px)
                )
                arcade.draw_line_strip(
                    self._pit_screen, (64, 68, 74), max(3.0, 3.0 * self._lane_px)
                )
                if self._pit_service_m is not None:
                    sx, sy, _, _ = self._pit_pos_at(self._pit_service_m)
                    arcade.draw_circle_filled(sx, sy, 3, (245, 197, 66))
            self._draw_cars_2d(screen)
        else:
            arcade.draw_line_strip([*screen, screen[0]], track_color, 2)
            self._draw_start_finish_line(screen)
            self._draw_cars(screen)

        rain = self._current_rain()
        label, color = _RAIN_LABEL.get(rain, (rain, PRIMARY_TEXT_COLOR))
        condition = track_condition_label(self._race, self._current_lap())
        self._weather_text.text = f"{label} · {condition}" if condition else label
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
        if self._show_breakdown:
            for panel in self._breakdown_panels:
                self._draw_breakdown_panel(panel)
        self._draw_race_control(status, width, height)
        if self._saveable:
            self._draw_button(self._switch_rect(), self._switch_text, self._switch_hover)
            if self._save_message.text:
                left, bottom, width, height = self._switch_rect()
                self._save_message.x = left + width
                self._save_message.y = bottom + height + 6
                self._save_message.draw()
        self._draw_button(self._end_rect(), self._end_text, self._end_hover)
        if self._list_view is not None:
            self._draw_button(self._next_rect(), self._back_text, self._back_hover)
        if self._has_previous():
            self._draw_button(self._prev_rect(), self._prev_text, self._prev_hover)
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

    #: Ordem fixa dos fatores no painel: cada um ocupa sempre o mesmo slot, para
    #: a leitura em tempo real nao "dancar" quando um valor muda.
    _BREAKDOWN_ORDER = ("corner", "transient", "tyre", "fuel", "weather", "race_control")

    def _breakdown_fraction(self, breakdown, key: str) -> float:
        if key == "corner":
            return breakdown.corner
        if key == "transient":
            return breakdown.transient
        return breakdown.penalties.get(key, 0.0)

    def _panel_title_rect(self, panel) -> tuple:
        """Faixa de titulo (arrastar) no topo do painel."""

        return (panel.x, panel.y + _PANEL_H - _PANEL_TITLE_H, _PANEL_W, _PANEL_TITLE_H)

    def _panel_close_rect(self, panel) -> tuple:
        """Botao de fechar, no canto superior direito."""

        pad = (_PANEL_TITLE_H - _PANEL_CLOSE) / 2
        return (
            panel.x + _PANEL_W - _PANEL_CLOSE - pad,
            panel.y + _PANEL_H - _PANEL_TITLE_H + pad,
            _PANEL_CLOSE,
            _PANEL_CLOSE,
        )

    def _panel_body_rect(self, panel) -> tuple:
        return (panel.x, panel.y, _PANEL_W, _PANEL_H)

    def _draw_breakdown_panel(self, panel) -> None:
        """Desenhe o painel flutuante de um piloto: titulo, fechar e as barras.

        A velocidade efetiva aparece no titulo. Abaixo, cada fator ocupa um
        slot fixo: os que reduzem a velocidade empilham na barra "tira"; os que
        a aumentam (pneu novo, inercia) na barra "da". O comprimento de cada
        fatia e a fracao de ``v_max``, entao os numeros sao "% da velocidade
        maxima", nao "% da perda". Carro parado nao tem velocidade para
        decompor e mostra so o aviso. Reusa os mesmos ``arcade.Text`` movendo-os
        por painel, ja que o desenho e imediato.
        """

        did = panel.driver_id
        name = self._playback.car(did).name
        # Moldura e faixa de titulo.
        arcade.draw_lbwh_rectangle_filled(panel.x, panel.y, _PANEL_W, _PANEL_H, _PANEL_BG)
        arcade.draw_lbwh_rectangle_outline(
            panel.x, panel.y, _PANEL_W, _PANEL_H, _PANEL_BORDER, 1
        )
        tl, tb, tw, th = self._panel_title_rect(panel)
        arcade.draw_lbwh_rectangle_filled(tl, tb, tw, th, _PANEL_BORDER)
        cl, cb, cw, ch = self._panel_close_rect(panel)
        arcade.draw_lbwh_rectangle_outline(cl, cb, cw, ch, PRIMARY_TEXT_COLOR, 1)
        self._breakdown_close_x.x = cl + cw / 2
        self._breakdown_close_x.y = cb + ch / 2
        self._breakdown_close_x.draw()

        breakdown = self._playback.speed_breakdown_at(did, self._elapsed)
        title = self._breakdown_title
        title.x = panel.x + 8
        title.y = tb + th / 2
        if breakdown is None or breakdown.speed_kmh < 1.0:
            title.text = f"{name[:20]} · parado"
            title.draw()
            return
        pct = breakdown.effective * 100.0
        title.text = f"{name[:16]}  {breakdown.speed_kmh:.0f} km/h · {pct:.0f}%"
        title.draw()

        bar_w = _PANEL_W - 16
        bar_h = 16.0
        left = panel.x + 8
        takes_y = panel.y + _PANEL_H - _PANEL_TITLE_H - 8 - bar_h
        gives_y = takes_y - bar_h - 4
        self._draw_breakdown_bar(breakdown, left, takes_y, bar_w, bar_h, positive=True)
        self._draw_breakdown_bar(breakdown, left, gives_y, bar_w, bar_h, positive=False)

        col_w = bar_w / 2
        row_h = 15.0
        for i, key in enumerate(self._BREAKDOWN_ORDER):
            fraction = self._breakdown_fraction(breakdown, key)
            label, value = self._breakdown_legend[key]
            color = (
                _BREAKDOWN_EFFECTIVE_COLOR
                if fraction < 0
                else self._breakdown_slice_color(key)
            )
            col = i % 2
            rown = i // 2
            x0 = left + col * col_w
            y = gives_y - 16 - rown * row_h
            label.text = _BREAKDOWN_LABELS[key]
            label.color = color
            label.x = x0
            label.y = y
            label.draw()
            value.text = f"{-fraction * 100:+.1f}%"
            value.color = color
            value.x = x0 + col_w - 10
            value.y = y
            value.draw()

        self._draw_breakdown_context(panel, did, left, gives_y - 16 - 3 * row_h)

    def _draw_breakdown_context(self, panel, did, bar_w_left, top_y) -> None:
        """Seção de contexto: velocidade base (v_max) e atributos do piloto.

        Os atributos moldam a velocidade BASE (ritmo, compostura, agressividade
        entram no envelope fisico; por isso aparecem aqui como contexto, nao
        como fatia das barras, que ja sao relativas a essa base). Consistencia
        e gestao de pneu atuam no ruido e na degradacao, nao no pico.
        """

        left = panel.x + 8
        right = panel.x + _PANEL_W - 8
        sep_y = top_y - 8
        arcade.draw_line(left, sep_y, right, sep_y, _PANEL_BORDER, 1)

        v_max = self._playback.driver_v_max_kmh(did)
        attrs = self._playback.driver_attributes(did)
        rows = []  # (rotulo, valor)
        if v_max is not None:
            rows.append(("velocidade base", f"{v_max:.0f} km/h"))
        if attrs is not None:
            rows.append(("arquétipo", str(attrs.get("archetype", "-"))))
            rows.append(("ritmo", f"{attrs.get('pace_offset_pct', 0.0):+.2f}%"))
            rows.append(("compostura", f"{attrs.get('composure', 1.0):.2f}"))
            rows.append(("agressividade", f"{attrs.get('aggression', 1.0):.2f}"))
            rows.append(("consistência", f"{attrs.get('consistency_factor', 1.0):.2f}"))
            rows.append(("gestão de pneu", f"{attrs.get('tyre_management_factor', 1.0):.2f}"))
        else:
            rows.append(("sem atributos de piloto", ""))

        for i, (lbl, val) in enumerate(rows):
            if i >= len(self._breakdown_context):
                break
            label, value = self._breakdown_context[i]
            y = sep_y - 14 - i * 15
            label.text = lbl
            label.x = left
            label.y = y
            label.draw()
            value.text = val
            value.x = right
            value.y = y
            value.draw()

    @staticmethod
    def _breakdown_slice_color(key: str) -> tuple:
        if key == "corner":
            return _BREAKDOWN_CORNER_COLOR
        if key == "transient":
            return _BREAKDOWN_TRANSIENT_COLOR
        return _BREAKDOWN_FACTOR_COLORS[key]

    def _draw_breakdown_bar(
        self, breakdown, left: float, y: float, bar_w: float, bar_h: float, *, positive: bool
    ) -> None:
        """Empilha numa barra os fatores do sinal pedido (tira vs da velocidade).

        ``positive=True`` desenha o que reduz a velocidade (fracao positiva);
        ``positive=False`` o que a aumenta (fracao negativa), em modulo. A
        escala e a mesma (fracao de ``v_max``), entao as duas barras sao
        comparaveis lado a lado.
        """

        cursor = left
        for key in self._BREAKDOWN_ORDER:
            fraction = self._breakdown_fraction(breakdown, key)
            take = fraction if positive else -fraction
            if take <= 0.0:
                continue
            seg_w = take * bar_w
            color = (
                self._breakdown_slice_color(key)
                if positive
                else _BREAKDOWN_EFFECTIVE_COLOR
            )
            arcade.draw_lbwh_rectangle_filled(cursor, y, seg_w, bar_h, color)
            cursor += seg_w
        arcade.draw_lbwh_rectangle_outline(left, y, bar_w, bar_h, _HEADER_COLOR, 1)

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
        self._standing_row_rects = []
        for i, row in enumerate(standings):
            texts = self._row_texts[i]
            y = top - i * line_h
            car_color = self._color_by_driver.get(row.driver_id, PRIMARY_TEXT_COLOR)
            cells = self._standing_cells(row, car_color)
            # Guarda a faixa clicavel da linha (do topo para baixo) para a
            # selecao do carro do grafico de decomposicao de velocidade.
            rect = (left - 4, y - line_h / 2, self._standings_width - left, line_h)
            self._standing_row_rects.append((row.driver_id, rect))
            # Realca as linhas cujos paineis estao abertos (pode ser varias).
            if self._show_breakdown and any(
                p.driver_id == row.driver_id for p in self._breakdown_panels
            ):
                arcade.draw_lbwh_rectangle_filled(*rect, _SELECTED_ROW_COLOR)
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

        code = _team_code(getattr(row, "team_name", ""))
        name_text = f"{row.name[:14]} · {code}" if code else row.name[:18]
        return {
            "position": (str(row.position), car_color),
            "name": (name_text, car_color),
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


# Codigos curtos das equipes conhecidas; o resto cai no fallback generico.
# So abreviam a exibicao compacta da classificacao; o nome completo aparece no
# painel de decomposicao de cada carro.
_TEAM_CODES = {
    "Red Bull": "RBR",
    "McLaren": "MCL",
    "Ferrari": "FER",
    "Mercedes": "MER",
    "Aston Martin": "AST",
    "Alpine F1 Team": "ALP",
    "RB F1 Team": "RB",
    "Haas F1 Team": "HAA",
    "Williams": "WIL",
    "Sauber": "SAU",
}


def _team_code(team_name: str) -> str:
    """Abrevie o nome da equipe para a classificacao compacta.

    Usa o codigo conhecido quando existe; senao, as tres primeiras letras da
    primeira palavra em maiusculas. Vazio continua vazio (corridas salvas antes
    de a equipe ser exposta).
    """

    team_name = (team_name or "").strip()
    if not team_name:
        return ""
    if team_name in _TEAM_CODES:
        return _TEAM_CODES[team_name]
    return team_name.split()[0][:3].upper()


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
        from frontend.arcade.saved_tournaments_view import SavedTournamentsView

        window.show_view(SavedTournamentsView())
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
