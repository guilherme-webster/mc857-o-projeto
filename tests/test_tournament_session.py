"""Navegacao e contrato de campeonato do torneio, sem janela."""

from __future__ import annotations

import unittest

from frontend.arcade.configuration_state import (
    ConfigurationFormData,
    PlannedRace,
    TournamentRules,
    WeatherSchedule,
)
from frontend.arcade.race_launcher import LaunchedRace
from frontend.arcade.tournament_session import (
    TournamentSession,
    parse_standings,
)


def launched(name: str, *cars: tuple[str, int, str]) -> LaunchedRace:
    return LaunchedRace(
        planned=PlannedRace(
            f"circuit:{name}",
            name,
            ConfigurationFormData(laps=5, weather_schedule=WeatherSchedule.dry(5)),
        ),
        race={
            "classification": [
                {"driver_id": d, "name": f"Piloto {d}", "position": p, "status": s}
                for d, p, s in cars
            ]
        },
        track={},
    )


class TournamentSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session = TournamentSession(
            (
                launched("Suzuka", ("A", 1, "RUNNING"), ("B", 2, "RETIRED")),
                launched("Interlagos", ("B", 1, "RUNNING"), ("A", 2, "RUNNING")),
            ),
            TournamentRules(scoring="Sem pontuação", tiebreak="Mais vitórias"),
        )

    def test_navigation(self) -> None:
        self.assertEqual(self.session.stage_title(1), "Etapa 1/2 · Suzuka")
        self.assertTrue(self.session.has_next(1))
        self.assertFalse(self.session.has_next(2))
        with self.assertRaises(IndexError):
            self.session.stage(3)

    def test_request_translates_screen_labels_and_retirements(self) -> None:
        request = self.session.standings_request()
        self.assertEqual(request["scoring"], "none")
        self.assertEqual(request["tiebreak"], "most_wins")
        self.assertEqual(
            request["stages"][0],
            [
                {"driver_id": "A", "position": 1, "retired": False},
                {"driver_id": "B", "position": 2, "retired": True},
            ],
        )

    def test_names_come_from_the_classifications(self) -> None:
        self.assertEqual(
            self.session.driver_names(), {"A": "Piloto A", "B": "Piloto B"}
        )

    def test_rejects_empty_tournament(self) -> None:
        with self.assertRaises(ValueError):
            TournamentSession((), TournamentRules())


class ParseStandingsTest(unittest.TestCase):
    ROW = {
        "position": 1,
        "driver_id": "A",
        "points": 25,
        "wins": 1,
        "podiums": 1,
        "average_position": 1.0,
        "stage_positions": [1, None],
        "stage_retired": [False, False],
    }

    def test_parses_backend_rows(self) -> None:
        lines = parse_standings({"rows": [self.ROW]}, total_stages=2)
        self.assertEqual(lines[0].stage_positions, (1, None))

    def test_rejects_wrong_stage_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "etapas"):
            parse_standings({"rows": [self.ROW]}, total_stages=3)

    def test_rejects_malformed_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "inválida"):
            parse_standings({"rows": [{"driver_id": "A"}]}, total_stages=2)


if __name__ == "__main__":
    unittest.main()
