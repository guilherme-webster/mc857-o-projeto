"""Gestao de pneus amortecida no motor detalhado e na estrategia de parada."""

from __future__ import annotations

import unittest

from f1_simulator.application.build_grid import GridEntry
from f1_simulator.application.run_grid_simulation import (
    RaceSetup,
    run_detailed_grid_simulation,
)
from f1_simulator.domain.attribute_effects import (
    DETAILED_TYRE_MANAGEMENT,
    DetailedTyreManagementHeuristic,
    detailed_degradation_factor,
)
from f1_simulator.domain.random_source import SeededRandomSource
from tests.model_support import parameters
from tests.test_run_grid_detailed import attribute


class DetailedTyreManagementTest(unittest.TestCase):
    def test_neutral_without_attributes_and_at_one(self) -> None:
        self.assertEqual(detailed_degradation_factor(None), 1.0)
        self.assertEqual(
            detailed_degradation_factor(attribute("d", tyre_management_factor=1.0)),
            1.0,
        )

    def test_applies_elasticity_and_preserves_order(self) -> None:
        elasticity = DETAILED_TYRE_MANAGEMENT.elasticity
        values = [
            detailed_degradation_factor(attribute("d", tyre_management_factor=f))
            for f in (0.65, 1.0, 1.45)
        ]

        self.assertAlmostEqual(values[0], 1 + elasticity * -0.35)
        self.assertAlmostEqual(values[2], 1 + elasticity * 0.45)
        self.assertEqual(values, sorted(values))
        # A faixa efetiva dos arquetipos fica perto de +/-15%.
        self.assertTrue(0.8 < values[0] and values[2] < 1.25)

    def test_parameters_are_validated_and_labelled(self) -> None:
        self.assertEqual(DETAILED_TYRE_MANAGEMENT.origin, "heuristic")
        for bad in (0.0, -0.1, 1.5, float("nan"), True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                DetailedTyreManagementHeuristic(elasticity=bad)

    def test_detailed_race_uses_the_damped_factor_and_declares_it(self) -> None:
        grid = (GridEntry("driver:1", "Um", "team:x", "X"),)
        model = parameters(dnf_hazard_per_lap=0.0)

        def tyre_cost(factor: float) -> tuple[float, dict]:
            result = run_detailed_grid_simulation(
                grid,
                {"driver:1": attribute("driver:1", tyre_management_factor=factor)},
                RaceSetup(10, "circuit:1"),
                parameters=model,
                lap_length_m=4_000.0,
                rng=SeededRandomSource(3),
                race_control=None,
            )
            return result["classification"][0]["total_time_ms"], result

        neutral, _ = tyre_cost(1.0)
        worse, result = tyre_cost(2.0)
        better, _ = tyre_cost(0.5)

        self.assertGreater(worse, neutral)
        self.assertLess(better, neutral)
        declared = next(
            a for a in result["assumptions"] if a["kind"] == "detailed_tyre_management"
        )
        self.assertEqual(declared["elasticity"], DETAILED_TYRE_MANAGEMENT.elasticity)


if __name__ == "__main__":
    unittest.main()
