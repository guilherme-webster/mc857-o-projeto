"""Testes sem janela nem backend do caminho tela de configuracao -> corrida."""

from __future__ import annotations

import io
import unittest
import urllib.error

from frontend.arcade.configuration_state import (
    ConfigurationFormData,
    ConfigurationFormError,
    PlannedRace,
    SessionConfiguration,
    SimulationPlan,
    TournamentRules,
    WeatherSchedule,
)
from frontend.arcade.race_launcher import (
    DEFAULT_GRID_SIZE,
    GridOutdatedError,
    LaunchCancelled,
    launch_plan,
    run_setup,
    unsupported_options,
)
from frontend.arcade.track_client import BackendError, _error_detail


def planned(
    circuit_id: str = "circuit:24",
    name: str = "Yas Marina",
    laps: int = 10,
    schedule: WeatherSchedule | None = None,
    session: SessionConfiguration | None = None,
) -> PlannedRace:
    return PlannedRace(
        circuit_id=circuit_id,
        name=name,
        configuration=ConfigurationFormData(
            laps=laps, weather_schedule=schedule or WeatherSchedule.dry(laps)
        ),
        session=session,
    )


class FakeClient:
    def __init__(self, grid: dict | None | Exception = None) -> None:
        self.grid = grid
        self.calls: list[tuple] = []
        self.setups: list[dict] = []

    def fetch_current_grid(self) -> dict | None:
        self.calls.append(("fetch_current_grid",))
        if isinstance(self.grid, Exception):
            raise self.grid
        return self.grid

    def build_grid(self, size: int) -> dict:
        self.calls.append(("build_grid", size))
        return {"size": size, "seed": 7, "grid": []}

    def run_grid(self, setup: dict, on_lap=None) -> dict:
        self.calls.append(("run_grid", setup["track_id"]))
        self.setups.append(setup)
        if on_lap is not None:
            on_lap(1, setup["total_laps"])
        return {"total_laps": setup["total_laps"], "setup": setup}

    def fetch_track(self, circuit_id: str) -> dict:
        self.calls.append(("fetch_track", circuit_id))
        return {"circuit_id": circuit_id}


class RunSetupTest(unittest.TestCase):
    def test_weather_ranges_become_backend_segments(self) -> None:
        schedule = WeatherSchedule.dry(10).apply(4, 6, "Chuva intensa")
        schedule = schedule.apply(7, 7, "Chuva leve")
        setup = run_setup(planned(schedule=schedule), TournamentRules())
        self.assertEqual(setup["total_laps"], 10)
        self.assertEqual(setup["track_id"], "circuit:24")
        self.assertEqual(
            setup["weather"],
            [
                {"from_lap": 1, "to_lap": 3, "rain": "dry"},
                {"from_lap": 4, "to_lap": 6, "rain": "heavy_rain"},
                {"from_lap": 7, "to_lap": 7, "rain": "light_rain"},
                {"from_lap": 8, "to_lap": 10, "rain": "dry"},
            ],
        )

    def test_all_dry_rule_overrides_the_stage_weather(self) -> None:
        schedule = WeatherSchedule.dry(10).apply(4, 6, "Chuva intensa")
        setup = run_setup(
            planned(schedule=schedule), TournamentRules(weather_mode="Seco em todas")
        )
        self.assertEqual(
            setup["weather"], [{"from_lap": 1, "to_lap": 10, "rain": "dry"}]
        )

    def test_engine_is_sent_only_when_the_2d_engine_is_chosen(self) -> None:
        detailed = run_setup(planned(), TournamentRules())
        spatial = run_setup(planned(), TournamentRules(engine="2D com pit lane"))

        self.assertNotIn("engine", detailed)
        self.assertEqual(spatial["engine"], "2d")

    def test_unknown_engine_label_is_rejected(self) -> None:
        with self.assertRaises(ConfigurationFormError):
            TournamentRules(engine="Turbo")

    def test_tournament_seed_and_stage_index_are_sent_when_present(self) -> None:
        setup = run_setup(
            planned(), TournamentRules(), tournament_seed=2026, stage_index=3
        )

        self.assertEqual(setup["tournament_seed"], 2026)
        self.assertEqual(setup["stage_index"], 3)


class UnsupportedOptionsTest(unittest.TestCase):
    def test_full_standing_start_session_has_no_warning(self) -> None:
        self.assertEqual(
            unsupported_options(planned(session=SessionConfiguration(1, 10))), ()
        )
        self.assertEqual(unsupported_options(planned()), ())

    def test_rolling_start_is_reported(self) -> None:
        warnings = unsupported_options(
            planned(session=SessionConfiguration(1, 8, "Lançada"))
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn("lançada", warnings[0])

    def test_first_lap_is_supported_and_raises_no_warning(self) -> None:
        # A volta inicial so muda a reproducao; a corrida segue desde a largada.
        self.assertEqual(
            unsupported_options(planned(session=SessionConfiguration(3, 8))), ()
        )


class LaunchPlanTest(unittest.TestCase):
    def plan(self, *races: PlannedRace) -> SimulationPlan:
        return SimulationPlan(races or (planned(),), TournamentRules())

    def test_reuses_the_current_backend_grid(self) -> None:
        client = FakeClient(grid={"size": 20, "seed": 42, "grid": []})
        outcome = launch_plan(self.plan(), client)
        self.assertNotIn(("build_grid", DEFAULT_GRID_SIZE), client.calls)
        self.assertIn("grid atual", outcome.grid_note)
        self.assertIn("semente 42", outcome.grid_note)

    def test_creates_a_random_grid_when_none_exists(self) -> None:
        client = FakeClient(grid=None)
        outcome = launch_plan(self.plan(), client)
        self.assertIn(("build_grid", DEFAULT_GRID_SIZE), client.calls)
        self.assertIn("nenhum grid", outcome.grid_note)

    def test_rebuilds_an_outdated_grid(self) -> None:
        client = FakeClient(grid=GridOutdatedError("v1"))
        outcome = launch_plan(self.plan(), client)
        self.assertIn(("build_grid", DEFAULT_GRID_SIZE), client.calls)
        self.assertIn("formato antigo", outcome.grid_note)

    def test_runs_every_stage_in_order_and_reports_progress(self) -> None:
        client = FakeClient(grid={"size": 20, "seed": 1})
        messages: list[str] = []
        outcome = launch_plan(
            self.plan(
                planned("circuit:24", "Yas Marina"), planned("circuit:18", "Interlagos")
            ),
            client,
            lambda item: messages.append(item.message),
        )
        self.assertEqual(
            [call for call in client.calls if call[0] == "run_grid"],
            [("run_grid", "circuit:24"), ("run_grid", "circuit:18")],
        )
        self.assertEqual(
            [race.track["circuit_id"] for race in outcome.races],
            ["circuit:24", "circuit:18"],
        )
        self.assertIn("Simulando etapa 2/2: Interlagos…", messages)

    def test_progress_carries_stage_and_lap_for_the_loading_screen(self) -> None:
        client = FakeClient(grid={"size": 20, "seed": 1})
        seen = []
        launch_plan(
            self.plan(planned("circuit:18", "Interlagos")), client, seen.append
        )
        lap_events = [item for item in seen if item.lap]
        self.assertTrue(lap_events)
        last = lap_events[-1]
        self.assertEqual((last.stage_index, last.total_stages), (1, 1))
        self.assertEqual(last.stage_name, "Interlagos")
        self.assertEqual(last.lap, 1)
        self.assertEqual(last.laps, client.setups[0]["total_laps"])

    def test_cancel_stops_before_the_next_stage(self) -> None:
        client = FakeClient(grid={"size": 20, "seed": 1})
        with self.assertRaises(LaunchCancelled):
            launch_plan(
                self.plan(
                    planned("circuit:24", "Yas Marina"),
                    planned("circuit:18", "Interlagos"),
                ),
                client,
                cancelled=lambda: any(call[0] == "run_grid" for call in client.calls),
            )
        self.assertEqual(
            [call for call in client.calls if call[0] == "run_grid"],
            [("run_grid", "circuit:24")],
        )

    def test_sends_same_tournament_seed_and_distinct_zero_based_stage_indices(self) -> None:
        client = FakeClient(grid={"size": 20, "seed": 1})
        plan = SimulationPlan(
            (
                planned("circuit:24", "Yas Marina"),
                planned("circuit:18", "Interlagos"),
            ),
            TournamentRules(total_stages=2),
            tournament_seed=9876,
        )

        launch_plan(plan, client)

        self.assertEqual(
            [
                (setup["tournament_seed"], setup["stage_index"])
                for setup in client.setups
            ],
            [(9876, 0), (9876, 1)],
        )

    def test_collects_warnings_of_every_stage(self) -> None:
        client = FakeClient(grid={"size": 20, "seed": 1})
        outcome = launch_plan(
            self.plan(planned(session=SessionConfiguration(1, 10, "Lançada"))), client
        )
        self.assertEqual(len(outcome.warnings), 1)

    def test_backend_errors_propagate(self) -> None:
        class FailingClient(FakeClient):
            def run_grid(self, setup: dict, on_lap=None) -> dict:
                raise BackendError(422, "track_id desconhecido")

        with self.assertRaisesRegex(BackendError, "track_id desconhecido"):
            launch_plan(self.plan(), FailingClient(grid={"size": 1, "seed": 1}))


class BackendErrorDetailTest(unittest.TestCase):
    def http_error(self, body: bytes) -> urllib.error.HTTPError:
        return urllib.error.HTTPError(
            "http://x", 422, "Unprocessable", {}, io.BytesIO(body)
        )

    def test_text_detail(self) -> None:
        self.assertEqual(
            _error_detail(self.http_error(b'{"detail": "sem grid"}')), "sem grid"
        )

    def test_validation_detail_list(self) -> None:
        body = b'{"detail": [{"msg": "campo a"}, {"msg": "campo b"}]}'
        self.assertEqual(_error_detail(self.http_error(body)), "campo a; campo b")

    def test_non_json_body_falls_back_to_reason(self) -> None:
        self.assertEqual(_error_detail(self.http_error(b"<html>")), "Unprocessable")


if __name__ == "__main__":
    unittest.main()
