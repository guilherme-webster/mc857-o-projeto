"""Composicao pura do grid com o motor detalhado da corrida."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from f1_simulator.application.build_grid import GridEntry
from f1_simulator.application.run_grid_simulation import (
    ASSUMED_REFERENCE_PACE_MS_PER_KM,
    RaceSetup,
    run_detailed_grid_simulation,
)
from f1_simulator.domain.driver_attributes import ATTRIBUTE_FIELDS, DriverAttributes
from f1_simulator.domain.race_control import HEURISTIC_RACE_CONTROL
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.strategy import HeuristicPitStrategy
from tests.model_support import parameters


class ZeroRandomSource:
    """Fonte roteirizada que aciona todo evento de probabilidade positiva."""

    def standard_normal(self, label: str = "") -> float:
        return 0.0

    def uniform01(self, label: str = "") -> float:
        return 0.0

    def spawn(self, key: str) -> "ZeroRandomSource":
        return self


def attribute(driver_id: str, **overrides: float) -> DriverAttributes:
    values = {
        "pace_offset_pct": 0.0,
        "consistency_factor": 1.0,
        "tyre_management_factor": 1.0,
        "aggression": 1.0,
        "composure": 1.0,
    }
    values.update(overrides)
    return DriverAttributes(
        driver_id=driver_id,
        archetype="balanced",
        sources={name: "generated" for name in ATTRIBUTE_FIELDS},
        **values,
    )


class DetailedGridSimulationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.grid = (
            GridEntry("driver:2", "Segundo", "team:solid", "Solida"),
            GridEntry("driver:1", "Primeiro", "team:missing", "Sem modelo"),
        )
        self.attributes = {
            entry.driver_id: attribute(entry.driver_id) for entry in self.grid
        }
        self.parameters = parameters(dnf_hazard_per_lap=0.0)

    def test_builds_entrants_in_starting_order_and_applies_attributes(self) -> None:
        captured: dict = {}

        def fake_simulation(entrants, **kwargs):
            captured["entrants"] = entrants
            captured["kwargs"] = kwargs
            return {
                "total_laps": kwargs["total_laps"],
                "history": [],
                "classification": [],
                "assumptions": [],
            }

        with patch(
            "f1_simulator.application.run_grid_simulation.simulate_detailed_race",
            side_effect=fake_simulation,
        ):
            result = run_detailed_grid_simulation(
                self.grid,
                self.attributes,
                RaceSetup(5, track_id="circuit:1"),
                parameters=self.parameters,
                lap_length_m=4_000.0,
                rng=SeededRandomSource(42),
            )

        entrants = captured["entrants"]
        self.assertEqual(
            [item.driver_id for item in entrants], ["driver:2", "driver:1"]
        )
        self.assertEqual([item.grid_position for item in entrants], [1, 2])
        self.assertTrue(
            all(isinstance(item.strategy, HeuristicPitStrategy) for item in entrants)
        )
        self.assertEqual(entrants[0].starting_compound, "MEDIUM")
        self.assertEqual(entrants[0].reliability_factor, 0.5)
        self.assertEqual(entrants[1].reliability_factor, 1.0)
        self.assertIs(captured["kwargs"]["attributes"], self.attributes)
        self.assertEqual(captured["kwargs"]["dispute_model"], "pressure")
        self.assertIs(captured["kwargs"]["race_control"], HEURISTIC_RACE_CONTROL)
        self.assertEqual(result["reference_lap_time_ms"], 68_000.0)

    def test_uses_calibrated_track_and_geometry_reference(self) -> None:
        result = run_detailed_grid_simulation(
            self.grid,
            self.attributes,
            RaceSetup(2, track_id="circuit:1"),
            parameters=self.parameters,
            lap_length_m=5_000.0,
            rng=SeededRandomSource(17),
        )

        self.assertEqual(
            result["reference_lap_time_ms"],
            5.0 * ASSUMED_REFERENCE_PACE_MS_PER_KM,
        )
        self.assertEqual(result["track_reference"]["model_track_id"], "circuit:1")
        self.assertEqual(result["track_reference"]["model_track_origin"], "calibrated")

    def test_uses_assumed_track_fallback_for_uncalibrated_track(self) -> None:
        result = run_detailed_grid_simulation(
            self.grid,
            self.attributes,
            RaceSetup(1, track_id="circuit:999"),
            parameters=self.parameters,
            lap_length_m=4_200.0,
            rng=SeededRandomSource(18),
        )

        self.assertEqual(result["circuit_id"], "__fallback__")
        self.assertEqual(result["track_reference"]["requested_track_id"], "circuit:999")
        self.assertEqual(result["track_reference"]["model_track_id"], "__fallback__")
        self.assertEqual(result["track_reference"]["model_track_origin"], "assumed")

    def test_without_track_uses_nominal_lap_and_declares_assumption(self) -> None:
        result = run_detailed_grid_simulation(
            self.grid,
            self.attributes,
            RaceSetup(1),
            parameters=self.parameters,
            lap_length_m=None,
            rng=SeededRandomSource(19),
        )

        self.assertEqual(result["reference_lap_time_ms"], 90_000.0)
        reference = next(
            item for item in result["assumptions"] if item["kind"] == "reference_pace"
        )
        self.assertTrue(reference["used_nominal_lap_time_fallback"])
        self.assertEqual(reference["origin"], "assumed")

    def test_same_seed_reproduces_race_including_control_events(self) -> None:
        setup = RaceSetup(12, track_id="circuit:1")

        first = run_detailed_grid_simulation(
            self.grid,
            self.attributes,
            setup,
            parameters=self.parameters,
            lap_length_m=4_000.0,
            rng=SeededRandomSource(67202),
        )
        repeated = run_detailed_grid_simulation(
            self.grid,
            self.attributes,
            setup,
            parameters=self.parameters,
            lap_length_m=4_000.0,
            rng=SeededRandomSource(67202),
        )

        self.assertEqual(first, repeated)
        self.assertIn("race_control_events", first)
        self.assertIn("race_control_by_lap", first)
        self.assertEqual(len(first["race_control_by_lap"]), 12)

    def test_race_control_events_are_exposed_by_the_use_case(self) -> None:
        grid = (GridEntry("driver:1", "Piloto", "team:solid", "Solida"),)

        result = run_detailed_grid_simulation(
            grid,
            {"driver:1": attribute("driver:1")},
            RaceSetup(3, track_id="circuit:1"),
            parameters=self.parameters,
            lap_length_m=4_000.0,
            rng=ZeroRandomSource(),
        )

        self.assertTrue(result["race_control_events"])
        self.assertEqual(
            result["race_control_events"][0]["cause"]["kind"], "solo_crash"
        )

    def test_pace_attribute_changes_detailed_result(self) -> None:
        grid = (GridEntry("driver:1", "Piloto", "team:solid", "Solida"),)
        setup = RaceSetup(3, track_id="circuit:1")

        faster = run_detailed_grid_simulation(
            grid,
            {"driver:1": attribute("driver:1", pace_offset_pct=-1.0)},
            setup,
            parameters=self.parameters,
            lap_length_m=4_000.0,
            rng=SeededRandomSource(55),
        )
        slower = run_detailed_grid_simulation(
            grid,
            {"driver:1": attribute("driver:1", pace_offset_pct=1.0)},
            setup,
            parameters=self.parameters,
            lap_length_m=4_000.0,
            rng=SeededRandomSource(55),
        )

        self.assertLess(
            faster["classification"][0]["total_time_ms"],
            slower["classification"][0]["total_time_ms"],
        )


if __name__ == "__main__":
    unittest.main()
