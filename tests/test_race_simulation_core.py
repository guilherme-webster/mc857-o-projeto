from __future__ import annotations

import unittest

from f1_simulator.domain.race_simulation import Competitor, simulate_race


class SimulateRaceTest(unittest.TestCase):
    def test_rejects_non_positive_total_laps(self) -> None:
        with self.assertRaises(ValueError):
            simulate_race([Competitor("driver:1", "A", 90000.0)], 0)
        with self.assertRaises(ValueError):
            simulate_race([Competitor("driver:1", "A", 90000.0)], -3)

    def test_rejects_non_positive_lap_time(self) -> None:
        with self.assertRaises(ValueError):
            simulate_race([Competitor("driver:1", "A", 0.0)], 5)
        with self.assertRaises(ValueError):
            simulate_race([Competitor("driver:1", "A", -1.0)], 5)

    def test_rejects_duplicate_driver_id(self) -> None:
        with self.assertRaises(ValueError):
            simulate_race(
                [
                    Competitor("driver:1", "A", 90000.0),
                    Competitor("driver:1", "B", 91000.0),
                ],
                5,
            )

    def test_accumulates_time_linearly_per_lap(self) -> None:
        result = simulate_race([Competitor("driver:1", "A", 90000.0)], 3)

        totals = [lap["cars"][0]["total_time_ms"] for lap in result["history"]]
        self.assertEqual(totals, [90000.0, 180000.0, 270000.0])

    def test_faster_pace_leads(self) -> None:
        result = simulate_race(
            [
                Competitor("driver:slow", "Slow", 92000.0),
                Competitor("driver:fast", "Fast", 90000.0),
            ],
            1,
        )

        cars = result["history"][0]["cars"]
        self.assertEqual(cars[0]["driver_id"], "driver:fast")
        self.assertEqual(cars[0]["position"], 1)
        self.assertEqual(cars[1]["driver_id"], "driver:slow")
        self.assertEqual(cars[1]["position"], 2)

    def test_result_is_independent_of_input_order(self) -> None:
        a = [
            Competitor("driver:1", "A", 90000.0),
            Competitor("driver:2", "B", 91000.0),
            Competitor("driver:3", "C", 90500.0),
        ]
        b = list(reversed(a))

        self.assertEqual(simulate_race(a, 4), simulate_race(b, 4))

    def test_ties_broken_by_driver_id(self) -> None:
        result = simulate_race(
            [
                Competitor("driver:b", "B", 90000.0),
                Competitor("driver:a", "A", 90000.0),
            ],
            2,
        )

        cars = result["history"][-1]["cars"]
        self.assertEqual([c["driver_id"] for c in cars], ["driver:a", "driver:b"])

    def test_history_shape_and_classification(self) -> None:
        result = simulate_race(
            [
                Competitor("driver:1", "A", 90000.0),
                Competitor("driver:2", "B", 91000.0),
            ],
            5,
        )

        self.assertEqual(result["total_laps"], 5)
        self.assertEqual(len(result["history"]), 5)
        for index, lap in enumerate(result["history"], start=1):
            self.assertEqual(lap["lap"], index)
            self.assertEqual(len(lap["cars"]), 2)
            self.assertEqual([c["position"] for c in lap["cars"]], [1, 2])
        # A classificação final espelha os carros da última volta.
        self.assertEqual(result["classification"], result["history"][-1]["cars"])

    def test_empty_field_produces_laps_without_cars(self) -> None:
        result = simulate_race([], 3)

        self.assertEqual(len(result["history"]), 3)
        self.assertEqual(result["history"][0]["cars"], [])
        self.assertEqual(result["classification"], [])


if __name__ == "__main__":
    unittest.main()
