"""Fator heuristico da largada e sua composicao com o valor calibrado."""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from f1_simulator.adapters.grid_start_parameters_json import (
    GridStartParametersError,
    read_grid_start_parameters,
)
from f1_simulator.domain.driver_attributes import ATTRIBUTE_FIELDS, DriverAttributes
from f1_simulator.domain.grid_start import GridStartParameters
from f1_simulator.domain.race_simulation import Entrant, simulate_detailed_race
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.strategy import NoStopStrategy
from scripts.analyze_grid_start_sensitivity import run_sensitivity
from tests.model_support import parameters, track

ROOT = Path(__file__).resolve().parents[1]


def grid_start(factor: float) -> GridStartParameters:
    return GridStartParameters(
        penalty_factor=factor,
        origin="heuristic",
        parameter_version="test-grid-start-v1",
        rationale="Parametro controlado pelo teste.",
    )


def entrants() -> list[Entrant]:
    return [
        Entrant("driver:a", "A", 90_000.0, 1, NoStopStrategy(), "MEDIUM"),
        Entrant("driver:b", "B", 90_000.0, 2, NoStopStrategy(), "MEDIUM"),
    ]


class GridStartParametersTest(unittest.TestCase):
    def test_versioned_artifact_is_heuristic_and_selected(self) -> None:
        configured = read_grid_start_parameters(
            ROOT / "data" / "parameters" / "grid-start-v1.json"
        )
        self.assertEqual(configured.origin, "heuristic")
        self.assertEqual(configured.parameter_version, "heuristic-grid-start-v1")
        self.assertEqual(configured.penalty_factor, 0.1)

    def test_rejects_negative_boolean_and_non_finite_without_clamp(self) -> None:
        for invalid in (-0.01, True, math.inf, math.nan):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                grid_start(invalid)

    def test_adapter_rejects_unknown_field(self) -> None:
        payload = {
            "schema_version": 1,
            "origin": "heuristic",
            "parameter_version": "v1",
            "rationale": "teste",
            "grid_start_penalty_factor": 0.5,
            "grid_start_penality_factor": 0.5,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grid.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(GridStartParametersError):
                read_grid_start_parameters(path)


class GridStartRaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.model = parameters(
            grid_penalty_ms_per_position=800.0,
            lap_noise_ms=0.0,
            dnf_hazard_per_lap=0.0,
            traffic_penalty_ms=0.0,
        )

    def test_factor_is_applied_exactly_once_and_published_with_calibrated_value(
        self,
    ) -> None:
        result = simulate_detailed_race(
            entrants(),
            total_laps=1,
            parameters=self.model,
            track=track(),
            rng=SeededRandomSource(108),
            resolve_position_disputes=False,
            attributes={},
            grid_start=grid_start(0.5),
        )
        by_id = {row["driver_id"]: row for row in result["classification"]}
        self.assertEqual(
            by_id["driver:b"]["total_time_ms"]
            - by_id["driver:a"]["total_time_ms"],
            400.0,
        )
        assumption = result["assumptions"][0]
        self.assertEqual(assumption["calibrated_ms_per_position"], 800.0)
        self.assertEqual(assumption["factor"], 0.5)
        self.assertEqual(assumption["effective_ms_per_position"], 400.0)

    def test_factor_one_reproduces_previous_history_and_classification(self) -> None:
        previous = simulate_detailed_race(
            entrants(),
            total_laps=3,
            parameters=self.model,
            track=track(),
            rng=SeededRandomSource(7),
            resolve_position_disputes=False,
        )
        explicit = simulate_detailed_race(
            entrants(),
            total_laps=3,
            parameters=self.model,
            track=track(),
            rng=SeededRandomSource(7),
            resolve_position_disputes=False,
            grid_start=grid_start(1.0),
        )
        self.assertEqual(explicit["history"], previous["history"])
        self.assertEqual(explicit["classification"], previous["classification"])

    def test_enhanced_race_is_deterministic_with_fixed_seed(self) -> None:
        attrs = {
            entry.driver_id: DriverAttributes(
                driver_id=entry.driver_id,
                archetype="balanced",
                pace_offset_pct=0.0,
                consistency_factor=1.0,
                tyre_management_factor=1.0,
                aggression=1.0,
                composure=1.0,
                sources={field: "manual" for field in ATTRIBUTE_FIELDS},
            )
            for entry in entrants()
        }

        def run() -> dict:
            return simulate_detailed_race(
                entrants(),
                total_laps=5,
                parameters=self.model,
                track=track(),
                rng=SeededRandomSource(108),
                attributes=attrs,
                dispute_model="pressure",
                grid_start=grid_start(0.25),
            )

        self.assertEqual(run(), run())


class GridStartSensitivityTest(unittest.TestCase):
    def test_offline_analysis_repeats_with_same_seed(self) -> None:
        kwargs = {
            "factors": (0.5,),
            "races_per_track": 1,
            "seed": 108,
            "tracks": (("circuit:13", 3),),
        }
        self.assertEqual(run_sensitivity(**kwargs), run_sensitivity(**kwargs))


if __name__ == "__main__":
    unittest.main()
