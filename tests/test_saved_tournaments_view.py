"""Telas Arcade do torneio salvo (#109); exigem ARCADE_GUI_TEST=1."""

from __future__ import annotations

import os
import time
import unittest
from unittest.mock import patch

try:
    import arcade

    from frontend.arcade.configuration_state import (
        ConfigurationFormData,
        PlannedRace,
        TournamentRules,
        WeatherSchedule,
    )
    from frontend.arcade.race_launcher import LaunchedRace, LaunchOutcome
    from frontend.arcade.saved_tournaments_view import SavedTournamentsView
    from frontend.arcade.tournament_session import TournamentSession
    from frontend.arcade.tournament_view import TournamentResultView
except ModuleNotFoundError as error:
    if error.name != "arcade":
        raise
    arcade = None  # type: ignore[assignment]

ARCADE_GUI_TEST = arcade is not None and bool(os.environ.get("ARCADE_GUI_TEST"))

SUMMARY = {
    "id": "copa-abc123",
    "name": "Copa",
    "saved_at": "2026-10-30T12:00:00+00:00",
    "stage_count": 1,
    "circuits": ["circuit:1"],
    "tournament_seed": 109,
    "grid_seed": 42,
    "car_count": 2,
}


def session() -> TournamentSession:
    planned = PlannedRace(
        "circuit:1",
        "Albert Park",
        ConfigurationFormData(laps=3, weather_schedule=WeatherSchedule.dry(3)),
    )
    race = {
        "classification": [
            {"driver_id": "d1", "name": "Um", "position": 1, "status": "RUNNING"},
            {"driver_id": "d2", "name": "Dois", "position": 2, "status": "RUNNING"},
        ]
    }
    return TournamentSession(
        (LaunchedRace(planned, race, {}),), TournamentRules(name="Copa"), (), 109
    )


def pump(view, condition, timeout_s: float = 2.0) -> None:
    """Rode ``on_update`` ate a thread da view publicar o resultado."""

    deadline = time.monotonic() + timeout_s
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("a thread da view nao respondeu a tempo")
        view.on_update(0)
        time.sleep(0.01)


@unittest.skipUnless(ARCADE_GUI_TEST, "requires Arcade with ARCADE_GUI_TEST=True")
class SavedTournamentViewsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.window = arcade.Window(1280, 720, visible=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.window.close()

    def test_list_draws_rows_and_open_click_reopens_without_rerun(self) -> None:
        outcome = LaunchOutcome((), "nota", ())
        loaded: list[str] = []
        view = SavedTournamentsView(
            lister=lambda: {"saved": [SUMMARY]},
            loader=lambda tournament_id: (
                loaded.append(tournament_id) or {"id": tournament_id}
            ),
            reopener=lambda record: outcome,
            rerunner=lambda record, progress: self.fail("Abrir nao deve reexecutar"),
        )
        self.window.show_view(view)
        pump(view, lambda: bool(view._saved))
        view.on_draw()

        shown: list[LaunchOutcome] = []
        rect = view._button_rects()["open:copa-abc123"]
        with patch.object(view, "_show_outcome", shown.append):
            view.on_mouse_press(rect[0] + 5, rect[1] + 5, arcade.MOUSE_BUTTON_LEFT, 0)
            pump(view, lambda: bool(shown))

        self.assertEqual(loaded, ["copa-abc123"])
        self.assertIs(shown[0], outcome)

    def test_rerun_click_reports_progress_and_errors(self) -> None:
        def failing_rerun(record, progress):
            progress("Reexecutando etapa 1/1: Albert Park…")
            raise RuntimeError("backend fora do ar")

        view = SavedTournamentsView(
            lister=lambda: {"saved": [SUMMARY]},
            loader=lambda tournament_id: {"id": tournament_id},
            rerunner=failing_rerun,
        )
        self.window.show_view(view)
        pump(view, lambda: bool(view._saved))
        rect = view._button_rects()["rerun:copa-abc123"]
        view.on_mouse_press(rect[0] + 5, rect[1] + 5, arcade.MOUSE_BUTTON_LEFT, 0)
        pump(view, lambda: "backend fora do ar" in view._status)

        self.assertFalse(view._busy)
        view.on_draw()

    def test_result_view_saves_tournament_and_shows_the_id(self) -> None:
        requests: list[dict] = []
        view = TournamentResultView(
            session(),
            standings_loader=lambda request: {"rows": []},
            tournament_saver=lambda request: (
                requests.append(request)
                or {"id": "copa-abc123", "name": request["name"]}
            ),
        )
        self.window.show_view(view)
        rect = view._button_rects()["save"]
        view.on_mouse_press(rect[0] + 5, rect[1] + 5, arcade.MOUSE_BUTTON_LEFT, 0)
        pump(view, lambda: "copa-abc123" in view._save_status.text)
        view.on_draw()

        self.assertEqual(requests[0]["tournament_seed"], 109)
        self.assertEqual(requests[0]["stages"][0]["circuit_id"], "circuit:1")


if __name__ == "__main__":
    unittest.main()
