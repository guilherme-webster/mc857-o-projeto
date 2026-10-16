"""Testes sem janela da faixa e das mensagens de controle de prova."""

from __future__ import annotations

import unittest

from frontend.arcade.race_control_feed import RaceControlFeed

from f1_simulator.domain.race_control import (
    HEURISTIC_RACE_CONTROL,
    GREEN,
    Incident,
    RaceControlState,
    step,
)
from f1_simulator.domain.random_source import SeededRandomSource

NAMES = {"driver:5": "Piloto 5", "driver:6": "Piloto 6", "driver:9": "Piloto 9"}


def contact(lap: int) -> dict:
    return {"lap": lap, "kind": "contact", "driver_ids": ["driver:5", "driver:6"]}


# Recorte de uma corrida real do motor detalhado (SC acionado na volta 3).
RACE = {
    "race_control_by_lap": [
        {"lap": 1, "status": "GREEN", "restart_lap": False},
        {"lap": 2, "status": "GREEN", "restart_lap": False},
        {"lap": 3, "status": "GREEN", "restart_lap": False},
        {"lap": 4, "status": "SC", "restart_lap": False},
        {"lap": 5, "status": "SC", "restart_lap": False},
        {"lap": 6, "status": "GREEN", "restart_lap": True},
    ],
    "race_control_events": [
        {
            "lap": 2,
            "type": "incident_response",
            "cause": {"lap": 2, "kind": "mechanical", "driver_ids": ["driver:9"]},
            "response": "NONE",
            "duration_laps": 0,
        },
        {
            "lap": 3,
            "type": "incident_response",
            "cause": contact(3),
            "response": "SC",
            "duration_laps": 2,
        },
        {
            "lap": 3,
            "type": "race_control_started",
            "status": "SC",
            "duration_laps": 2,
            "cause": contact(3),
        },
        {"lap": 5, "type": "race_control_ended", "status": "SC", "cause": contact(3)},
        {"lap": 5, "type": "restart_scheduled", "source": "SC"},
    ],
}


class TrackStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.feed = RaceControlFeed(RACE, NAMES)

    def test_status_is_the_one_applied_during_the_lap(self) -> None:
        self.assertEqual(self.feed.status_on_lap(3).label, "BANDEIRA VERDE")
        self.assertEqual(self.feed.status_on_lap(4).label, "SAFETY CAR")
        self.assertEqual(self.feed.status_on_lap(6).label, "RELARGADA")

    def test_unknown_lap_has_no_status(self) -> None:
        self.assertIsNone(self.feed.status_on_lap(99))

    def test_race_without_race_control_has_no_band(self) -> None:
        feed = RaceControlFeed({}, NAMES)
        self.assertIsNone(feed.status_on_lap(1))
        self.assertEqual(feed.entries_through(10), [])


class FeedEntriesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.feed = RaceControlFeed(RACE, NAMES)

    def test_messages_appear_once_the_event_lap_is_completed(self) -> None:
        self.assertEqual(self.feed.entries_through(1.9), [])
        self.assertEqual(
            [entry.text for entry in self.feed.entries_through(2.0)],
            ["Quebra: Piloto 9"],
        )

    def test_full_sequence_of_a_safety_car(self) -> None:
        texts = [entry.text for entry in self.feed.entries_through(10)]
        self.assertEqual(
            texts,
            [
                "Quebra: Piloto 9",
                "Contato: Piloto 5 x Piloto 6",
                "Safety car (2 voltas)",
                "Safety car recolhido",
                "Relargada na volta 6",
            ],
        )

    def test_status_drives_message_color(self) -> None:
        statuses = [entry.status for entry in self.feed.entries_through(10)]
        self.assertEqual(statuses, [None, None, "SC", None, "GREEN"])

    def test_unknown_driver_falls_back_to_id(self) -> None:
        race = {
            "race_control_events": [
                {
                    "lap": 1,
                    "type": "incident_response",
                    "cause": {"lap": 1, "kind": "solo_crash", "driver_ids": ["x"]},
                }
            ]
        }
        entries = RaceControlFeed(race, NAMES).entries_through(1)
        self.assertEqual(entries[0].text, "Batida: x")

    def test_unknown_event_type_is_shown_raw(self) -> None:
        race = {"race_control_events": [{"lap": 1, "type": "novo_evento"}]}
        entries = RaceControlFeed(race, NAMES).entries_through(1)
        self.assertEqual(entries[0].text, "novo_evento")

    def test_malformed_event_is_an_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "malformado"):
            RaceControlFeed({"race_control_events": [{"type": "x"}]}, NAMES)


class FeedEngineContractTest(unittest.TestCase):
    """As transicoes do motor real viram mensagens conhecidas, nunca cruas."""

    def test_every_transition_of_the_engine_has_a_message(self) -> None:
        rng = SeededRandomSource(11)
        events = []
        state = RaceControlState(status=GREEN)
        for lap in range(1, 400):
            incidents = (
                [Incident(lap, "contact", ("driver:5", "driver:6"))]
                # Incidentes em voltas alternadas caem tambem durante uma
                # neutralizacao e exercitam escalada e prorrogacao.
                if lap % 2 == 0
                else []
            )
            state, lap_events = step(state, incidents, rng, HEURISTIC_RACE_CONTROL, lap)
            events.extend(lap_events)
        types = {event["type"] for event in events}
        self.assertEqual(
            types,
            {
                "incident_response",
                "race_control_started",
                "race_control_escalated",
                "race_control_extended",
                "race_control_ended",
                "restart_scheduled",
            },
        )

        feed = RaceControlFeed({"race_control_events": events}, NAMES)
        texts = {entry.text for entry in feed.entries_through(400)}
        self.assertTrue(types.isdisjoint(texts), types & texts)


if __name__ == "__main__":
    unittest.main()
