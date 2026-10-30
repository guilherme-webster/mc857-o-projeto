"""Torneio salvo no frontend: pedido de salvamento, reabertura e reexecucao."""

from __future__ import annotations

import unittest

from frontend.arcade.configuration_state import (
    ConfigurationFormData,
    PlannedRace,
    SessionConfiguration,
    SimulationPlan,
    TournamentRules,
    WeatherSchedule,
)
from frontend.arcade.race_launcher import LaunchedRace, launch_plan
from frontend.arcade.saved_tournaments import (
    reopen,
    rerun,
    save_request,
    session_from_outcome,
)
from frontend.arcade.tournament_session import TournamentSession

RULES = TournamentRules(name="Copa salva", total_stages=2, scoring="Sem pontuação")


def planned(circuit_id: str, name: str, laps: int = 3) -> PlannedRace:
    return PlannedRace(
        circuit_id,
        name,
        ConfigurationFormData(
            laps=laps,
            weather_schedule=WeatherSchedule.dry(laps).apply(2, 2, "Chuva leve"),
        ),
        SessionConfiguration(1, laps, "Parada"),
    )


PLANNED = (planned("circuit:1", "Albert Park"), planned("circuit:18", "Interlagos", 4))


def race_for(setup: dict) -> dict:
    return {"setup": setup, "classification": [{"driver_id": "d1", "position": 1}]}


class FakeClient:
    """Backend falso que registra a ordem das chamadas."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def fetch_current_grid(self) -> dict:
        self.calls.append(("fetch_current_grid",))
        return {"size": 20, "seed": 5, "grid": []}

    def build_grid(self, size: int) -> dict:  # pragma: no cover - grid existe
        raise AssertionError("o grid atual deveria ser reutilizado")

    def restore_grid(self, tournament_id: str) -> dict:
        self.calls.append(("restore_grid", tournament_id))
        return {"seed": 5}

    def run_grid(self, setup: dict) -> dict:
        self.calls.append(("run_grid", setup))
        return race_for(setup)

    def fetch_track(self, circuit_id: str) -> dict:
        self.calls.append(("fetch_track", circuit_id))
        return {"circuit_id": circuit_id}


def simulated_session(seed: int | None = 109) -> tuple[TournamentSession, FakeClient]:
    client = FakeClient()
    outcome = launch_plan(SimulationPlan(PLANNED, RULES, seed), client)
    return session_from_outcome(outcome), client


def saved_record(session: TournamentSession) -> dict:
    """O que o backend devolveria: o pedido mais id, data e grid congelado."""

    request = save_request(session)
    return {
        "schema_version": 1,
        "id": "copa-salva-abc123",
        "saved_at": "2026-10-30T12:00:00+00:00",
        "grid": {"seed": 5, "grid": [{"driver_id": "d1"}]},
        **request,
    }


class SaveRequestTest(unittest.TestCase):
    def test_request_repeats_the_setups_sent_at_launch(self) -> None:
        session, client = simulated_session()
        sent = [call[1] for call in client.calls if call[0] == "run_grid"]

        request = save_request(session)

        self.assertEqual(request["name"], "Copa salva")
        self.assertEqual(request["tournament_seed"], 109)
        self.assertEqual([stage["setup"] for stage in request["stages"]], sent)
        self.assertEqual(
            [stage["setup"]["stage_index"] for stage in request["stages"]], [0, 1]
        )
        self.assertEqual(request["stages"][1]["race"], race_for(sent[1]))
        self.assertEqual(request["rules"]["scoring"], "Sem pontuação")

    def test_custom_name_overrides_rules_name(self) -> None:
        session, _ = simulated_session()
        self.assertEqual(save_request(session, "  Outra  ")["name"], "Outra")


class ReopenTest(unittest.TestCase):
    def test_reopen_rebuilds_plan_and_rules_without_running_races(self) -> None:
        session, _ = simulated_session()
        record = saved_record(session)
        tracks: list[str] = []

        outcome = reopen(record, lambda circuit_id: tracks.append(circuit_id) or {})

        self.assertEqual(tracks, ["circuit:1", "circuit:18"])
        self.assertEqual(outcome.rules, RULES)
        self.assertEqual(outcome.tournament_seed, 109)
        self.assertEqual([race.planned for race in outcome.races], list(PLANNED))
        self.assertEqual(
            [race.race for race in outcome.races],
            [race.race for race in session.races],
        )
        self.assertIn("reaberto sem simular", outcome.grid_note)
        reopened = session_from_outcome(outcome)
        self.assertEqual(reopened.standings_request(), session.standings_request())


class RerunTest(unittest.TestCase):
    def test_rerun_restores_grid_once_then_resends_each_saved_setup(self) -> None:
        session, _ = simulated_session()
        record = saved_record(session)
        client = FakeClient()
        messages: list[str] = []

        outcome = rerun(record, client, messages.append)

        self.assertEqual(client.calls[0], ("restore_grid", "copa-salva-abc123"))
        self.assertEqual(
            [call[1] for call in client.calls if call[0] == "run_grid"],
            [stage["setup"] for stage in record["stages"]],
        )
        self.assertEqual(sum(call[0] == "restore_grid" for call in client.calls), 1)
        self.assertEqual(len(outcome.races), 2)
        self.assertIn("reexecutado", outcome.grid_note)
        self.assertTrue(messages[0].startswith("Restaurando"))

    def test_session_without_tournament_seed_round_trips(self) -> None:
        session, _ = simulated_session(seed=None)
        record = saved_record(session)

        self.assertIsNone(record["tournament_seed"])
        self.assertNotIn("tournament_seed", record["stages"][0]["setup"])
        self.assertIsNone(reopen(record, lambda _: {}).tournament_seed)


class LaunchedRaceTypeTest(unittest.TestCase):
    def test_outcome_races_are_launched_races(self) -> None:
        session, _ = simulated_session()
        self.assertTrue(all(isinstance(race, LaunchedRace) for race in session.races))


if __name__ == "__main__":
    unittest.main()
