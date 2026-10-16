"""Regra de pontuacao e desempate do campeonato."""

from __future__ import annotations

import unittest

from f1_simulator.domain.championship import (
    F1_POINTS,
    StageResult,
    championship_standings,
)


def stage(*driver_ids: str, retired: tuple[str, ...] = ()) -> list[StageResult]:
    return [
        StageResult(driver_id, position, driver_id in retired)
        for position, driver_id in enumerate(driver_ids, start=1)
    ]


class ChampionshipPointsTest(unittest.TestCase):
    def test_official_points_for_the_top_ten(self) -> None:
        drivers = [f"d{i:02d}" for i in range(1, 13)]
        rows = championship_standings([stage(*drivers)])
        self.assertEqual([row.points for row in rows], [*F1_POINTS, 0, 0])

    def test_points_accumulate_across_stages(self) -> None:
        rows = championship_standings([stage("A", "B", "C"), stage("B", "A", "C")])
        points = {row.driver_id: row.points for row in rows}
        self.assertEqual(points, {"A": 43, "B": 43, "C": 30})

    def test_retired_driver_scores_nothing_even_inside_the_top_ten(self) -> None:
        rows = championship_standings([stage("A", "B", "X", retired=("X",))])
        by_id = {row.driver_id: row for row in rows}
        self.assertEqual(by_id["X"].points, 0)
        self.assertEqual(by_id["X"].stage_retired, (True,))

    def test_wins_and_podiums(self) -> None:
        rows = championship_standings(
            [stage("A", "B", "C", "D"), stage("A", "D", "C", "B")]
        )
        by_id = {row.driver_id: row for row in rows}
        self.assertEqual((by_id["A"].wins, by_id["A"].podiums), (2, 2))
        self.assertEqual((by_id["D"].wins, by_id["D"].podiums), (0, 1))


class ChampionshipTiebreakTest(unittest.TestCase):
    # Pontos: C 15+25=40, A 25+12=37, B 18+15=33, D 12+18=30.
    # Medias: C 2,0; A 2,5; B 2,5; D 3,0. Vitorias: A 1, C 1.
    STAGES = [stage("A", "B", "C", "D"), stage("C", "D", "B", "A")]

    def test_points_come_before_any_tiebreak(self) -> None:
        rows = championship_standings(self.STAGES)
        self.assertEqual([row.driver_id for row in rows], ["C", "A", "B", "D"])
        self.assertEqual([row.points for row in rows], [40, 37, 33, 30])

    def test_tied_points_use_best_average(self) -> None:
        rows = championship_standings([stage("A", "B", "C"), stage("B", "A", "C")])
        self.assertEqual([row.driver_id for row in rows][:2], ["A", "B"])
        self.assertEqual(rows[0].average_position, rows[1].average_position)

    def test_without_scoring_best_average_orders_the_table(self) -> None:
        rows = championship_standings(self.STAGES, scoring="none")
        self.assertEqual([row.points for row in rows], [0, 0, 0, 0])
        # Medias: A 2,5; B 2,5; C 2,0; D 3,0. C lidera; A e B empatam e A tem
        # uma vitoria.
        self.assertEqual([row.driver_id for row in rows], ["C", "A", "B", "D"])

    def test_without_scoring_most_wins_orders_the_table(self) -> None:
        rows = championship_standings(self.STAGES, scoring="none", tiebreak="most_wins")
        self.assertEqual([row.driver_id for row in rows][:2], ["C", "A"])


class ChampionshipContractTest(unittest.TestCase):
    def test_driver_missing_from_a_stage_keeps_a_gap(self) -> None:
        rows = championship_standings([stage("A", "B"), stage("A")])
        by_id = {row.driver_id: row for row in rows}
        self.assertEqual(by_id["B"].stage_positions, (2, None))
        self.assertEqual(by_id["B"].average_position, 2.0)

    def test_rejects_empty_championship(self) -> None:
        with self.assertRaises(ValueError):
            championship_standings([])

    def test_rejects_inconsistent_positions(self) -> None:
        with self.assertRaisesRegex(ValueError, "posicoes"):
            championship_standings(
                [[StageResult("A", 1, False), StageResult("B", 1, False)]]
            )

    def test_rejects_repeated_driver(self) -> None:
        with self.assertRaisesRegex(ValueError, "repetido"):
            championship_standings(
                [[StageResult("A", 1, False), StageResult("A", 2, False)]]
            )

    def test_rejects_unknown_rules(self) -> None:
        with self.assertRaises(ValueError):
            championship_standings([stage("A")], scoring="indy")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
