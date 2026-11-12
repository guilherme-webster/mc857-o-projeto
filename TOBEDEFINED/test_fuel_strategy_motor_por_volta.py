# Arquivado de tests/test_fuel_strategy.py (issue #145): depende do motor por volta
# removido (simulate_detailed_race, start_fuel_kg por carro, refuel_stops por
# estrategia). O 2D nao reproduz esse contrato; ver comentario da issue #145.
"""Paradas estrategicas com reabastecimento: pneus e combustivel numa decisao."""

from __future__ import annotations

import json
import statistics
import unittest
from pathlib import Path

from f1_simulator.adapters.datasets.mock_track_geometry import MockTrackDatasetAdapter
from f1_simulator.application.build_grid import GridEntry
from f1_simulator.application.run_grid_simulation import (
    RaceSetup,
    run_grid_simulation,
)
from f1_simulator.domain.fuel import FuelPlan
from f1_simulator.domain.race_simulation import (
    FUEL,
    Entrant,
    simulate_detailed_race,
)
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.strategy import (
    NEUTRAL_FUEL_TRAITS,
    FuelStatus,
    FuelStrategyTraits,
    HeuristicPitStrategy,
    NoStopStrategy,
    StrategyState,
    draw_fuel_traits,
)
from f1_simulator.domain.track_geometry import pit_entry_lap_fraction
from f1_simulator.domain.tyres import TyreSet
from f1_simulator.factories.track_geometry_factory import TrackGeometryFactory
from tests.model_support import parameters, track
from tests.test_fuel import REFERENCE_MS, fuel_parameters, plan, quiet_model
from tests.geometry_support import attribute

class EngineRefuelStrategyTest(unittest.TestCase):
    def test_in_lap_burns_only_to_the_pit_entry(self) -> None:
        # Entrada a 90% da volta: com F = 2 kg a volta de entrada queima 1,8 kg.
        fuel_plan = FuelPlan(
            fuel_parameters(), REFERENCE_MS, 4.0, "track_geometry",
            pit_entry_fraction=0.9,
        )
        cars = [
            Entrant("driver:1", "P1", REFERENCE_MS, 1, NoStopStrategy(), "MEDIUM",
                    start_fuel_kg=10.5)
        ]
        result = simulate_detailed_race(
            cars, total_laps=12, parameters=quiet_model(), track=track(),
            rng=SeededRandomSource(1), attributes={}, fuel=fuel_plan,
        )
        event = result["fuel"]["refuel_stops"][0]
        self.assertEqual(event["lap"], 5)
        self.assertAlmostEqual(event["fuel_before_kg"], 0.7)

    def test_drivers_make_different_choices_and_none_runs_dry(self) -> None:
        grid = tuple(
            GridEntry(f"driver:{index}", f"P{index}", "team:solid", "Solida")
            for index in range(8)
        )
        attributes = {
            entry.driver_id: attribute(entry.driver_id, aggression=0.8 + 0.1 * index)
            for index, entry in enumerate(grid)
        }
        result = run_grid_simulation(
            grid,
            attributes,
            RaceSetup(total_laps=60, track_id="circuit:1"),
            parameters=quiet_model(),
            lap_length_m=4_000.0,
            rng=SeededRandomSource(9),
            fuel_parameters=fuel_parameters(),
            race_control=None,
        )
        starts = set(result["fuel"]["start_fuel_kg"].values())
        first_stops = {}
        for event in result["fuel"]["refuel_stops"]:
            first_stops.setdefault(event["driver_id"], event["lap"])
            self.assertEqual(event["decided_by"], "strategy")
        self.assertGreater(len(starts), 3)
        self.assertGreater(len(set(first_stops.values())), 2)
        for car in result["classification"]:
            self.assertNotEqual(car["retirement_cause"], FUEL)
            self.assertGreaterEqual(car["stops_made"], car["refuels_made"])
        traits = next(
            item for item in result["assumptions"] if item["kind"] == "fuel_strategy"
        )
        self.assertEqual(traits["origin"], "heuristic")
        self.assertEqual(len(traits["drivers"]), 8)



