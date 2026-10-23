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
    run_detailed_grid_simulation,
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
from tests.test_run_grid_detailed import attribute

#: Perda de parada usada nos estados de teste (ms).
STOP_LOSS_MS = 20_000.0


def strategy(circuit=None, **traits) -> HeuristicPitStrategy:
    return HeuristicPitStrategy(
        parameters(),
        circuit or track(),
        fuel_traits=FuelStrategyTraits(**traits) if traits else NEUTRAL_FUEL_TRAITS,
    )


def state(
    lap: int,
    total: int,
    fuel_kg: float | None,
    *,
    age: int = 0,
    compound: str = "MEDIUM",
    used: tuple[str, ...] = (),
    pit_loss_factor: float = 1.0,
    fuel_plan: FuelPlan | None = None,
) -> StrategyState:
    fuel_plan = fuel_plan or plan()
    return StrategyState(
        lap_number=lap,
        total_laps=total,
        tyre=TyreSet(compound, age),
        stops_made=0,
        pit_loss_factor=pit_loss_factor,
        compounds_used=used,
        fuel=(
            None
            if fuel_kg is None
            else FuelStatus(fuel_plan, fuel_kg, fuel_plan.burn_kg_per_lap, STOP_LOSS_MS)
        ),
    )


def first_stop(policy: HeuristicPitStrategy, start_kg: float, total: int) -> int:
    """Primeira volta de parada de um carro isolado, so com queima verde."""

    burn = plan().burn_kg_per_lap
    for lap in range(1, total + 1):
        decision = policy.decide(
            state(lap, total, start_kg - (lap - 1) * burn, age=lap - 1)
        )
        if decision.pit:
            return lap
    return total


class FuelAwareDecisionTest(unittest.TestCase):
    def test_without_fuel_the_traits_change_nothing(self) -> None:
        calm = strategy(margin_laps=1.5, stop_cost_bias=1.5, stint_shift=0.3)
        bold = strategy(margin_laps=0.2, stop_cost_bias=0.5, stint_shift=-0.3)
        for lap in range(1, 40):
            for age in range(0, 40, 3):
                tyre_state = state(lap, 40, None, age=age)
                self.assertEqual(calm.decide(tyre_state), bold.decide(tyre_state))

    def test_forced_when_the_next_pit_entry_is_out_of_reach(self) -> None:
        # 3 kg no inicio, 2 kg por volta: sobra 1 kg, menos que uma volta.
        decision = strategy().decide(state(10, 40, 3.0, age=9))
        self.assertTrue(decision.pit)
        self.assertGreater(decision.refuel_kg, 0.0)
        self.assertIsNotNone(decision.compound)

    def test_tank_covering_the_finish_leaves_the_call_to_the_tyres(self) -> None:
        # Volta 25 de 30 com 13 kg: sobram 11 kg para 5 voltas (10 kg + 1).
        fresh = strategy().decide(state(25, 30, 13.0, age=2, used=("HARD",)))
        self.assertFalse(fresh.pit)
        worn = strategy().decide(state(15, 30, 40.0, age=40, used=("HARD",)))
        self.assertTrue(worn.pit)
        self.assertEqual(worn.refuel_kg, 0.0)

    def test_cautious_driver_stops_earlier_than_a_risky_one(self) -> None:
        mild = track(tyre_severity=0.3)
        cautious = first_stop(strategy(mild, margin_laps=1.5, stop_cost_bias=1.0), 41.0, 60)
        risky = first_stop(strategy(mild, margin_laps=0.2, stop_cost_bias=1.0), 41.0, 60)
        self.assertLess(cautious, risky)
        # Ninguem chega aos boxes sem combustivel: 41 kg cobrem 20 voltas.
        self.assertLessEqual(risky, 20)

    def test_preference_for_light_cars_takes_smaller_fills(self) -> None:
        # Tanque quase vazio na volta 1 de 120: a parada e obrigatoria e o
        # abastecimento depende de quantos stints o piloto prefere.
        light = strategy(margin_laps=0.5, stop_cost_bias=0.5).decide(
            state(1, 120, 2.5)
        )
        heavy = strategy(margin_laps=0.5, stop_cost_bias=1.5).decide(
            state(1, 120, 2.5)
        )
        self.assertTrue(light.pit and heavy.pit)
        self.assertLess(light.refuel_kg, heavy.refuel_kg)

    def test_safety_car_brings_a_due_stop_forward(self) -> None:
        # 11 kg no inicio da volta 20 de 40: o tanque ainda cobre 4 voltas.
        green = strategy().decide(state(20, 40, 11.0, age=19))
        neutral = strategy().decide(
            state(20, 40, 11.0, age=19, pit_loss_factor=0.5)
        )
        self.assertFalse(green.pit)
        self.assertTrue(neutral.pit)

    def test_stint_preference_moves_the_starting_load(self) -> None:
        # A preferencia desloca o primeiro stint dentro de cada plano, mas
        # tambem pode mudar qual plano e o mais barato. Com paradas muito
        # caras os dois ficam no minimo de dois stints e so o desvio difere:
        # 30 voltas viram 21 (undercut) ou 39 (overcut).
        fuel_plan = plan()
        undercut = strategy(margin_laps=0.5, stop_cost_bias=1.0, stint_shift=-0.3)
        overcut = strategy(margin_laps=0.5, stop_cost_bias=1.0, stint_shift=0.3)
        short = undercut.plan_start_fuel_kg(fuel_plan, 60, "MEDIUM", 200_000.0)
        long = overcut.plan_start_fuel_kg(fuel_plan, 60, "MEDIUM", 200_000.0)
        self.assertAlmostEqual(short, 21 * 2.0 + 1.0)
        self.assertAlmostEqual(long, 39 * 2.0 + 1.0)
        self.assertLessEqual(long, fuel_plan.parameters.max_fuel_kg)


class FuelTraitDrawTest(unittest.TestCase):
    def test_draws_are_reproducible_and_bounded(self) -> None:
        first = draw_fuel_traits(1.2, SeededRandomSource(4), "strategy:fuel:a")
        second = draw_fuel_traits(1.2, SeededRandomSource(4), "strategy:fuel:a")
        self.assertEqual(first, second)
        for seed in range(200):
            traits = draw_fuel_traits(1.5, SeededRandomSource(seed), "x")
            self.assertGreaterEqual(traits.margin_laps, 0.2)
            self.assertLessEqual(abs(traits.stint_shift), 0.3)
            self.assertTrue(0.5 <= traits.stop_cost_bias <= 1.5)

    def test_aggressive_drivers_lean_towards_light_cars_and_early_stops(self) -> None:
        def mean(aggression: float, name: str) -> float:
            return statistics.fmean(
                getattr(draw_fuel_traits(aggression, SeededRandomSource(s), "x"), name)
                for s in range(300)
            )

        for name in ("margin_laps", "stop_cost_bias", "stint_shift"):
            self.assertLess(mean(1.4, name), mean(0.8, name))


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
        result = run_detailed_grid_simulation(
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


class PitEntryGeometryTest(unittest.TestCase):
    def test_every_circuit_has_its_pit_entry_late_in_the_lap(self) -> None:
        root = Path(__file__).resolve().parents[1]
        fixtures = root / "tests" / "fixtures" / "trotman_v128_tracks_2025"
        sources = root / "data" / "sources"
        adapter = MockTrackDatasetAdapter(
            fixtures / "track_points.csv",
            sources / "fastf1-tracks-2025.json",
            fixtures / "pit_lane_points.csv",
            sources / "fastf1-pit-lanes-2025.json",
        )
        manifest = json.loads(
            (sources / "fastf1-tracks-2025.json").read_text(encoding="utf-8")
        )
        fractions = []
        for event in manifest["source"]["events"]:
            geometry = TrackGeometryFactory.build(
                adapter.load_geometry(f"circuit:{event['circuit_id']}")
            )
            fractions.append(pit_entry_lap_fraction(geometry))
        self.assertEqual(len(fractions), 24)
        self.assertTrue(all(0.85 < value <= 1.0 for value in fractions))


if __name__ == "__main__":
    unittest.main()
