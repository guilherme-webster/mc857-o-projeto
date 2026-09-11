"""Arcade prototype of the race-simulation screen (issue #6 / #16 / #18).
 
This view is intentionally fictional and self-contained: two cars circle a
made-up oval track at constant speed, with no connection to the Django
backend or the simulation engine. Its purpose is to let the team see and
discuss how the track, cars and leaderboard could look before the real
snapshot contract with the backend is defined.
 
Renderer/clock note (see ``AGENTS.md``): a real integration must not let
Arcade's render loop be the source of truth for race time, since the
engine owns that. This prototype *does* drive ``RaceState`` straight from
``on_update``'s ``delta_time`` because there is no engine behind it yet;
that shortcut must not survive into the real integration without an
accepted decision on how render frames relate to simulated race time.
"""
 
from __future__ import annotations
 
import arcade
 
from frontend.arcade.oval_track import OvalTrack
from frontend.arcade.race_state import RaceCar, RaceState
from frontend.arcade.theme import (
    ACCENT_COLOR,
    BACKGROUND_COLOR,
    CAR_COLOR_ONE,
    CAR_COLOR_TWO,
    GRASS_COLOR,
    PANEL_BORDER_COLOR,
    PANEL_COLOR,
    PRIMARY_TEXT_COLOR,
    SECONDARY_TEXT_COLOR,
    SUCCESS_COLOR,
    TRACK_EDGE_COLOR,
    TRACK_SURFACE_COLOR,
)
 
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
 
# Mirrors ParametersView's dark top bar, so both screens share one header
# style even though this view does not (yet) share its layout module.
HEADER_BOUNDS = (0, 668, SCREEN_WIDTH, 52)
HEADER_COLOR = (7, 12, 19)
 
# The leaderboard now sits on the left, like a broadcast timing tower, with
# the oval filling the remaining area to its right, below the header.
LEADERBOARD_BOUNDS = (32, 40, 300, 560)
GRASS_BOUNDS = (364, 0, SCREEN_WIDTH - 364, 620)
 
TRACK = OvalTrack(
    center_x=822,
    center_y=310,
    straight_length=340,
    radius=170,
    track_width=20,
)
TRACK_SAMPLES = 96
CAR_RADIUS = 11
 
 
class RaceSimulationView(arcade.View):
    """Draw a fictional oval race with two constant-speed cars.
 
    ``cars`` defaults to two cars at different (but each individually
    constant) speeds, so the leaderboard actually changes over time and the
    faster car eventually laps the slower one — useful to see standings and
    lap counting update without needing real telemetry.
    """
 
    def __init__(self, cars: list[RaceCar] | None = None) -> None:
        super().__init__()
        self.state = RaceState(
            cars
            if cars is not None
            else [
                RaceCar("Carro vermelho", CAR_COLOR_ONE, speed=1 / 14),
                RaceCar("Carro azul", CAR_COLOR_TWO, speed=1 / 17),
            ]
        )
        self._road_quads = TRACK.road_quads(TRACK_SAMPLES)
        self._outer_edge = [
            TRACK.position_at_fraction(i / TRACK_SAMPLES, TRACK.track_width / 2)
            for i in range(TRACK_SAMPLES)
        ]
        self._inner_edge = [
            TRACK.position_at_fraction(i / TRACK_SAMPLES, -TRACK.track_width / 2)
            for i in range(TRACK_SAMPLES)
        ]
        self._title_text = arcade.Text(
            "SIMULAÇÃO DA CORRIDA",
            48,
            692,
            SECONDARY_TEXT_COLOR,
            10,
            bold=True,
            anchor_y="center",
        )
        self._subtitle_text = arcade.Text(
            "PISTA OVAL",
            48,
            636,
            SECONDARY_TEXT_COLOR,
            13,
        )
        # Updated every frame in `_draw_header`; starts at lap 1 before the
        # first `on_update` call moves anyone off the starting line.
        self._lap_counter_text = arcade.Text(
            "VOLTA 1",
            SCREEN_WIDTH / 2,
            692,
            PRIMARY_TEXT_COLOR,
            15,
            bold=True,
            anchor_x="center",
            anchor_y="center",
        )
 
    def on_show_view(self) -> None:
        """Apply the shared background color when this view becomes active."""
 
        super().on_show_view()
        arcade.set_background_color(BACKGROUND_COLOR)
 
    def on_update(self, delta_time: float) -> None:
        """Advance the fictional cars; see the module docstring's clock note."""
 
        self.state.advance(delta_time)
 
    def on_draw(self) -> None:
        """Redraw the whole screen: header, track, cars and leaderboard."""
 
        self.clear()
        self._draw_header()
        self._subtitle_text.draw()
        self._draw_track()
        self._draw_cars()
        self._draw_leaderboard()
 
    def _draw_header(self) -> None:
        """Draw the dark top bar, its eyebrow label and the current lap."""
 
        left, bottom, width, height = HEADER_BOUNDS
        arcade.draw_lbwh_rectangle_filled(left, bottom, width, height, HEADER_COLOR)
        arcade.draw_line(left, bottom, left + width, bottom, PANEL_BORDER_COLOR, 1)
        self._title_text.draw()
 
        leader = self.state.standings()[0] if self.state.cars else None
        current_lap = leader.laps_completed + 1 if leader is not None else 1
        self._lap_counter_text.text = f"VOLTA {current_lap}"
        self._lap_counter_text.draw()
 
    def _draw_track(self) -> None:
        """Draw the grass, the road surface and both edge lines of the oval."""
 
        arcade.draw_lbwh_rectangle_filled(*GRASS_BOUNDS, GRASS_COLOR)
        for quad in self._road_quads:
            arcade.draw_polygon_filled(quad, TRACK_SURFACE_COLOR)
        arcade.draw_line_strip(
            [*self._outer_edge, self._outer_edge[0]], TRACK_EDGE_COLOR, 2
        )
        arcade.draw_line_strip(
            [*self._inner_edge, self._inner_edge[0]], TRACK_EDGE_COLOR, 2
        )
 
    def _draw_cars(self) -> None:
        """Draw one filled circle per car at its current track position."""
 
        for car in self.state.cars:
            x, y = TRACK.position_at_fraction(car.lap_fraction)
            arcade.draw_circle_filled(x, y, CAR_RADIUS, car.color)
            arcade.draw_circle_outline(x, y, CAR_RADIUS, PRIMARY_TEXT_COLOR, 1.5)
 
    def _draw_leaderboard(self) -> None:
        """Draw the standings panel in a broadcast-timing-tower style.
 
        Each row shows a team-color bar, the position number, the car name
        and an interval to the leader — either a lap count (once a car has
        been lapped) or a rough time gap, similar to a real race's live
        timing screen. The leader's row shows "LÍDER" instead of a gap.
        """
 
        left, bottom, width, height = LEADERBOARD_BOUNDS
        arcade.draw_lbwh_rectangle_filled(left, bottom, width, height, PANEL_COLOR)
        arcade.draw_lbwh_rectangle_outline(
            left, bottom, width, height, PANEL_BORDER_COLOR, 2
        )
        arcade.Text(
            "CLASSIFICAÇÃO",
            left + 20,
            bottom + height - 36,
            PRIMARY_TEXT_COLOR,
            16,
            bold=True,
            anchor_y="center",
        ).draw()
        self._draw_live_pill(left + width - 84, bottom + height - 46, 68, 22)
 
        standings = self.state.standings()
        leader = standings[0] if standings else None
        row_top = bottom + height - 78
        row_height = 64
        for rank, car in enumerate(standings, start=1):
            row_y = row_top - (rank - 1) * row_height
            self._draw_leaderboard_row(left, width, row_y, rank, car, leader)
 
    def _draw_live_pill(self, left: float, bottom: float, width: float, height: float) -> None:
        """Draw the small 'AO VIVO' badge real timing towers usually show."""
 
        arcade.draw_lbwh_rectangle_filled(left, bottom, width, height, ACCENT_COLOR)
        arcade.Text(
            "AO VIVO",
            left + width / 2,
            bottom + height / 2,
            PRIMARY_TEXT_COLOR,
            9,
            bold=True,
            anchor_x="center",
            anchor_y="center",
        ).draw()
 
    def _draw_leaderboard_row(
        self,
        panel_left: float,
        panel_width: float,
        row_y: float,
        rank: int,
        car: RaceCar,
        leader: RaceCar | None,
    ) -> None:
        """Draw one standings row: color bar, position, name and interval."""
 
        bar_left = panel_left + 16
        arcade.draw_lbwh_rectangle_filled(bar_left, row_y - 34, 6, 46, car.color)
 
        arcade.Text(
            str(rank),
            bar_left + 20,
            row_y - 10,
            PRIMARY_TEXT_COLOR,
            20,
            bold=True,
            anchor_y="center",
        ).draw()
        arcade.Text(
            car.name,
            bar_left + 52,
            row_y,
            PRIMARY_TEXT_COLOR,
            13,
            bold=True,
            anchor_y="center",
        ).draw()
        arcade.Text(
            f"Volta {car.laps_completed + 1}",
            bar_left + 52,
            row_y - 18,
            SECONDARY_TEXT_COLOR,
            11,
            anchor_y="center",
        ).draw()
 
        interval_text, interval_color = self._format_interval(car, leader)
        arcade.Text(
            interval_text,
            panel_left + panel_width - 16,
            row_y - 10,
            interval_color,
            12,
            bold=True,
            anchor_x="right",
            anchor_y="center",
        ).draw()
 
    @staticmethod
    def _format_interval(
        car: RaceCar, leader: RaceCar | None
    ) -> tuple[str, tuple[int, int, int]]:
        """Return the gap-to-leader text and color for one standings row.
 
        Mirrors how a real timing screen reports the gap: whole laps once a
        car has been lapped (e.g. "+1 VOLTA"), otherwise a rough time gap
        estimated from the leader's own pace — this is a fictional race, so
        there is no real lap-time telemetry to compute an exact interval
        from.
        """
 
        if leader is None or car is leader:
            return "LÍDER", SUCCESS_COLOR
 
        lap_difference = leader.laps_completed - car.laps_completed
        if lap_difference >= 1:
            unit = "VOLTA" if lap_difference == 1 else "VOLTAS"
            return f"+{lap_difference} {unit}", SECONDARY_TEXT_COLOR
 
        gap_seconds = (leader.distance - car.distance) / leader.speed
        return f"+{gap_seconds:.1f}s", SECONDARY_TEXT_COLOR
 
 
def create_race_window() -> arcade.Window:
    """Open a standalone window showing only the fictional race prototype."""
 
    window = arcade.Window(
        SCREEN_WIDTH, SCREEN_HEIGHT, "Protótipo da tela de corrida", resizable=False
    )
    window.show_view(RaceSimulationView())
    return window
 
 
if __name__ == "__main__":
    create_race_window()
    arcade.run()
 