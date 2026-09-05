from __future__ import annotations

import unittest

from frontend.arcade.race_state import RaceCar, RaceState


class RaceCarTest(unittest.TestCase):
    def test_rejects_non_positive_speed(self) -> None:
        with self.assertRaises(ValueError):
            RaceCar("Carro", (255, 0, 0), speed=0)
        with self.assertRaises(ValueError):
            RaceCar("Carro", (255, 0, 0), speed=-1)

    def test_advance_moves_distance_linearly_with_time(self) -> None:
        car = RaceCar("Carro", (255, 0, 0), speed=0.5)

        car.advance(2.0)

        self.assertAlmostEqual(car.distance, 1.0)

    def test_laps_completed_and_lap_fraction_after_more_than_one_lap(self) -> None:
        car = RaceCar("Carro", (255, 0, 0), speed=1.0)

        car.advance(2.25)

        self.assertEqual(car.laps_completed, 2)
        self.assertAlmostEqual(car.lap_fraction, 0.25)


class RaceStateTest(unittest.TestCase):
    def test_advance_moves_every_car(self) -> None:
        fast = RaceCar("Rápido", (255, 0, 0), speed=1.0)
        slow = RaceCar("Lento", (0, 0, 255), speed=0.5)
        state = RaceState([fast, slow])

        state.advance(1.0)

        self.assertAlmostEqual(fast.distance, 1.0)
        self.assertAlmostEqual(slow.distance, 0.5)

    def test_standings_ranks_by_total_distance_not_only_lap_fraction(self) -> None:
        leader = RaceCar("Líder", (255, 0, 0), speed=1.0, distance=1.9)
        chaser = RaceCar("Perseguidor", (0, 0, 255), speed=1.0, distance=0.95)
        state = RaceState([chaser, leader])

        standings = state.standings()

        self.assertEqual(standings, [leader, chaser])


if __name__ == "__main__":
    unittest.main()
