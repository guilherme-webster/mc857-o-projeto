# Arquivado de tests/test_fuel.py (issue #144/#145): testes do motor por volta
# removido (ADR 0011); dependem de simulate_detailed_race e lap_time. Nao executam.
"""Modelo de massa de combustivel: dominio, motor, calibracao e artefato."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from f1_simulator.adapters.fuel_parameters_json import (
    FuelParametersError,
    read_fuel_parameters,
    write_fuel_parameters,
)
from f1_simulator.application.build_grid import GridEntry
from f1_simulator.application.calibrate_fuel import (
    FuelRaceContext,
    PitStopObservation,
    calibrate_fuel,
    calibrate_refuel_stops,
    validate_fuel,
    validate_refuel_stops,
)
from f1_simulator.application.calibrate_model import LapObservation
from f1_simulator.application.run_grid_simulation import (
    RaceSetup,
    run_grid_simulation,
)
from f1_simulator.domain.fuel import (
    FuelModelParameters,
    FuelPlan,
    RefuelStopParameters,
    RefuelStops,
    TeamPitOffset,
    fuel_lap,
    sample_refuel_stops,
)
from f1_simulator.domain.lap_time import fuel_penalty_ms
from f1_simulator.domain.race_control import HEURISTIC_RACE_CONTROL
from f1_simulator.domain.race_simulation import (
    FUEL,
    Entrant,
    simulate_detailed_race,
)
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.strategy import NoStopStrategy, PlannedStopStrategy
from tests.model_support import parameters, provenance, track  # noqa
from tests.test_run_grid_detailed import attribute

REFERENCE_MS = 90_000.0


def fuel_parameters(**overrides) -> FuelModelParameters:
    """Parametros redondos: 0,5 kg/km e 12,5 ms/kg numa volta de 90 s.

    Com 4 km por volta, a queima e 2 kg/volta e a inclinacao 25 ms/volta, a
    mesma de ``tests.model_support.parameters``; isso permite comparar o
    modelo de massa com o linear legado numa corrida limpa.
    """

    defaults = dict(
        version="fuel-teste",
        provenance=provenance(),
        lap_time_fraction_per_fuel_km=12.5 / REFERENCE_MS * 0.5,
        burn_kg_per_km=0.5,
        finish_reserve_kg=1.0,
    )
    defaults.update(overrides)
    return FuelModelParameters(**defaults)


def plan(**overrides) -> FuelPlan:
    return FuelPlan(
        parameters=fuel_parameters(**overrides),
        reference_lap_ms=REFERENCE_MS,
        lap_length_km=4.0,
        lap_length_source="track_geometry",
    )


def plan(**overrides) -> FuelPlan:
    return FuelPlan(
        parameters=fuel_parameters(**overrides),
        reference_lap_ms=REFERENCE_MS,
        lap_length_km=4.0,
        lap_length_source="track_geometry",
    )


def quiet_model():
    """Sem ruido, abandono ou contato: o tempo vira funcao pura do modelo."""

    return parameters(
        lap_noise_ms=0.0,
        dnf_hazard_per_lap=0.0,
        collision_probability_per_dispute=0.0,
    )


def entrants(strategy=None, **overrides) -> list[Entrant]:
    return [
        Entrant(
            driver_id=f"driver:{index}",
            name=f"P{index}",
            reference_lap_time_ms=REFERENCE_MS,
            grid_position=index,
            strategy=strategy or NoStopStrategy(),
            starting_compound="MEDIUM",
            **overrides,
        )
        for index in (1, 2)
    ]


class EngineFuelTest(unittest.TestCase):
    def run_race(self, fuel=None, laps=30, **kwargs) -> dict:
        return simulate_detailed_race(
            kwargs.pop("cars", None) or entrants(),
            total_laps=laps,
            parameters=quiet_model(),
            track=track(),
            rng=SeededRandomSource(7),
            collect_breakdowns=True,
            attributes={},
            fuel=fuel,
            **kwargs,
        )

    def test_clean_race_reproduces_the_linear_model(self) -> None:
        """Mesmo produto calibrado, mesma corrida: massa == linear legado."""

        linear = self.run_race()
        mass = self.run_race(fuel=plan())
        for before, after in zip(linear["breakdowns"], mass["breakdowns"]):
            self.assertAlmostEqual(before["fuel_ms"], after["fuel_ms"], places=6)
        for before, after in zip(linear["classification"], mass["classification"]):
            self.assertEqual(before["driver_id"], after["driver_id"])
            self.assertAlmostEqual(
                before["total_time_ms"], after["total_time_ms"], places=3
            )
        model = quiet_model()
        self.assertAlmostEqual(
            mass["breakdowns"][0]["fuel_ms"], fuel_penalty_ms(model, 1, 30), places=6
        )

    def test_pit_stop_does_not_refuel(self) -> None:
        cars = entrants(strategy=PlannedStopStrategy(1, ("HARD",)))
        result = self.run_race(fuel=plan(), cars=cars)
        loads = [
            car["fuel_kg"]
            for snapshot in result["history"]
            for car in snapshot["cars"]
            if car["driver_id"] == "driver:1"
        ]
        steps = [round(a - b, 9) for a, b in zip(loads, loads[1:])]
        self.assertEqual(set(steps), {2.0})
        self.assertEqual(result["classification"][0]["stops_made"], 1)
        self.assertAlmostEqual(loads[-1], 1.0)

    def test_underfuelled_car_saves_then_runs_dry(self) -> None:
        cars = entrants(start_fuel_kg=30.0)
        result = self.run_race(fuel=plan(refuelling_allowed=False), cars=cars)
        for car in result["classification"]:
            self.assertEqual(car["retirement_cause"], FUEL)
            self.assertGreater(car["fuel_saving_laps"], 0)
            self.assertEqual(car["fuel_kg"], 0.0)

    def test_running_dry_under_race_control_becomes_an_incident(self) -> None:
        cars = entrants(start_fuel_kg=30.0)
        result = self.run_race(
            fuel=plan(refuelling_allowed=False),
            cars=cars,
            race_control=HEURISTIC_RACE_CONTROL,
        )
        causes = {car["retirement_cause"] for car in result["classification"]}
        self.assertEqual(causes, {FUEL})
        self.assertTrue(
            any(event.get("kind") == "mechanical" for event in _incidents(result))
        )

    def test_start_load_above_regulation_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.run_race(fuel=plan(), cars=entrants(start_fuel_kg=120.0))

    def test_summary_and_assumptions_declare_origins(self) -> None:
        result = self.run_race(fuel=plan(), laps=60)
        self.assertTrue(result["fuel"]["race_exceeds_fuel_range"])
        self.assertEqual(result["fuel"]["start_fuel_kg"]["driver:1"], 110.0)
        fuel_assumption = next(
            item for item in result["assumptions"] if item["kind"] == "fuel"
        )
        self.assertTrue(fuel_assumption["scenario"]["refuelling_allowed"])
        self.assertEqual(fuel_assumption["scenario"]["origin"], "assumed")
        self.assertIn("burn_kg_per_km", fuel_assumption["assumed"])

    def test_legacy_snapshot_has_no_fuel_fields(self) -> None:
        result = simulate_detailed_race(
            entrants(),
            total_laps=5,
            parameters=quiet_model(),
            track=track(),
            rng=SeededRandomSource(1),
        )
        self.assertNotIn("fuel_kg", result["classification"][0])
        self.assertNotIn("fuel", result)


def _incidents(result: dict) -> list[dict]:
    """Eventos do controle de prova que citam a causa do incidente."""

    found = []
    for event in result["race_control_events"]:
        cause = event.get("cause") or {}
        if isinstance(cause, dict) and "kind" in cause:
            found.append(cause)
        elif "kind" in event:
            found.append(event)
    return found


class GridFuelTest(unittest.TestCase):
    def test_grid_run_carries_fuel_to_the_contract(self) -> None:
        grid = (
            GridEntry("driver:1", "Primeiro", "team:solid", "Solida"),
            GridEntry("driver:2", "Segundo", "team:solid", "Solida"),
        )
        result = run_grid_simulation(
            grid,
            {entry.driver_id: attribute(entry.driver_id) for entry in grid},
            RaceSetup(total_laps=10),
            parameters=quiet_model(),
            lap_length_m=None,
            rng=SeededRandomSource(3),
            fuel_parameters=replace(fuel_parameters()),
        )
        self.assertEqual(result["fuel"]["lap_length_source"], "reference_pace")
        self.assertIn("fuel_kg", result["starting_grid"][0])
        self.assertIn("fuel_kg", result["history"][0]["cars"][0])
        self.assertTrue(
            any(item["kind"] == "fuel" for item in result["assumptions"])
        )

    def test_grid_run_without_fuel_keeps_the_linear_contract(self) -> None:
        grid = (GridEntry("driver:1", "Primeiro", "team:solid", "Solida"),)
        result = run_grid_simulation(
            grid,
            {"driver:1": attribute("driver:1")},
            RaceSetup(total_laps=5),
            parameters=quiet_model(),
            lap_length_m=4_000.0,
            rng=SeededRandomSource(3),
        )
        self.assertNotIn("fuel", result)
        self.assertNotIn("fuel_kg", result["starting_grid"][0])


class RefuelStopEngineTest(unittest.TestCase):
    """Rede de seguranca do motor para estrategias que nao olham combustivel.

    ``NoStopStrategy`` e ``PlannedStopStrategy`` nao sabem do tanque: com
    L = F * n + r, depois de n voltas sobra r < F e o motor chama o carro para
    os boxes. Toda parada com reabastecimento ligado tambem troca pneus.
    """

    #: F = 2 kg/volta; L = 2 * 5 + 0,5 -> n = 5, r = 0,5.
    START_KG = 10.5

    def run_race(self, cars, laps=12, **kwargs) -> dict:
        return simulate_detailed_race(
            cars,
            total_laps=laps,
            parameters=quiet_model(),
            track=track(),
            rng=SeededRandomSource(7),
            collect_breakdowns=True,
            attributes={},
            fuel=plan(),
            **kwargs,
        )

    def car_rows(self, result, driver_id="driver:1"):
        return [
            car
            for snapshot in result["history"]
            for car in snapshot["cars"]
            if car["driver_id"] == driver_id
        ]

    def test_stops_after_the_last_lap_it_can_complete(self) -> None:
        result = self.run_race(
            entrants(start_fuel_kg=self.START_KG, refuel_stops=RefuelStops(25_000.0))
        )
        events = [
            event
            for event in result["fuel"]["refuel_stops"]
            if event["driver_id"] == "driver:1"
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["lap"], 5)
        self.assertAlmostEqual(events[0]["fuel_before_kg"], 0.5)
        # Enche para as 7 voltas restantes mais a reserva: 2 * 7 + 1 = 15 kg.
        self.assertAlmostEqual(events[0]["added_kg"], 14.5)
        rows = self.car_rows(result)
        self.assertAlmostEqual(rows[4]["fuel_kg"], 15.0)
        self.assertAlmostEqual(rows[-1]["fuel_kg"], 1.0)
        self.assertEqual(rows[-1]["refuels_made"], 1)
        self.assertEqual(rows[-1]["status"], "RUNNING")
        self.assertEqual(events[0]["decided_by"], "engine")

    def test_every_refuel_stop_also_changes_tyres(self) -> None:
        result = self.run_race(entrants(start_fuel_kg=self.START_KG))
        rows = self.car_rows(result)
        # Pneu novo depois da volta 5: a idade recomeca.
        self.assertEqual(
            [row["tyre_age_laps"] for row in rows],
            [1, 2, 3, 4, 0, 1, 2, 3, 4, 5, 6, 7],
        )
        self.assertEqual(rows[-1]["stops_made"], 1)
        # Sem decisao de composto, a rede de seguranca repete o atual.
        self.assertEqual(rows[-1]["compound"], "MEDIUM")

    def test_stop_costs_the_time_of_that_car(self) -> None:
        cars = [
            replace(car, refuel_stops=RefuelStops(mean))
            for car, mean in zip(
                entrants(start_fuel_kg=self.START_KG), (24_000.0, 26_000.0)
            )
        ]
        result = self.run_race(cars)
        pit = {
            row["driver_id"]: row["pit_ms"]
            for row in result["breakdowns"]
            if row["lap"] == 5
        }
        self.assertEqual(pit, {"driver:1": 24_000.0, "driver:2": 26_000.0})
        stops = {
            event["driver_id"]: event["stop_ms"]
            for event in result["fuel"]["refuel_stops"]
        }
        self.assertEqual(stops, pit)

    def test_successive_stops_use_their_own_sample(self) -> None:
        cars = entrants(
            start_fuel_kg=self.START_KG,
            refuel_stops=RefuelStops(25_000.0, (24_500.0, 26_500.0)),
        )
        result = self.run_race(cars, laps=30)
        times = [
            event["stop_ms"]
            for event in result["fuel"]["refuel_stops"]
            if event["driver_id"] == "driver:1"
        ]
        # 10,5 kg cobrem 5 voltas; depois enche 50,5 kg para o resto, e
        # abastecer leva 5,6 s, 3,1 s alem da troca de pneus.
        fuel = plan()
        self.assertEqual(len(times), 1)
        self.assertAlmostEqual(
            times[0], 24_500.0 + fuel.stationary_extra_ms(50.5), places=0
        )
        long_race = self.run_race(cars, laps=80)
        events = [
            event
            for event in long_race["fuel"]["refuel_stops"]
            if event["driver_id"] == "driver:1"
        ]
        base = [
            event["stop_ms"] - fuel.stationary_extra_ms(event["added_kg"])
            for event in events
        ]
        self.assertEqual([round(value) for value in base[:2]], [24_500, 26_500])
        self.assertTrue(all(round(value) == 25_000 for value in base[2:]))

    def test_tyre_stop_on_the_same_lap_is_a_single_stop(self) -> None:
        # 2 paradas em 12 voltas: a primeira cai na volta 4, a segunda na 8.
        # Com 8,5 kg (n = 4) a falta de combustivel coincide com a volta 4.
        cars = entrants(
            strategy=PlannedStopStrategy(2, ("HARD", "MEDIUM")),
            start_fuel_kg=8.5,
            refuel_stops=RefuelStops(25_000.0),
        )
        result = self.run_race(cars)
        lap4 = next(
            row
            for row in result["breakdowns"]
            if row["lap"] == 4 and row["driver_id"] == "driver:1"
        )
        self.assertEqual(lap4["pit_ms"], 25_000.0)
        event = next(
            event
            for event in result["fuel"]["refuel_stops"]
            if event["driver_id"] == "driver:1"
        )
        self.assertEqual(event["compound"], "HARD")
        self.assertEqual(event["decided_by"], "strategy")
        final = self.car_rows(result)[-1]
        self.assertEqual(final["stops_made"], 2)
        self.assertEqual(final["refuels_made"], 1)

    def test_race_within_range_never_refuels(self) -> None:
        result = self.run_race(entrants(), laps=30)
        self.assertEqual(result["fuel"]["refuel_stops"], [])

    def test_long_race_refuels_instead_of_running_dry(self) -> None:
        result = self.run_race(entrants(), laps=120)
        self.assertTrue(result["fuel"]["race_exceeds_fuel_range"])
        for car in result["classification"]:
            self.assertEqual(car["status"], "RUNNING")
            self.assertGreaterEqual(car["refuels_made"], 2)


class GridRefuelTest(unittest.TestCase):
    def test_each_car_gets_its_team_stop_time(self) -> None:
        crews = RefuelStopSamplingTest().stops_parameters()
        grid = (
            GridEntry("driver:1", "Rapido", "team:fast", "Rapida"),
            GridEntry("driver:2", "Lento", "team:slow", "Lenta"),
            GridEntry("driver:3", "Medio", "team:other", "Outra"),
        )
        result = run_grid_simulation(
            grid,
            {entry.driver_id: attribute(entry.driver_id) for entry in grid},
            RaceSetup(total_laps=80, track_id="circuit:1"),
            parameters=quiet_model(),
            lap_length_m=4_000.0,
            rng=SeededRandomSource(3),
            fuel_parameters=fuel_parameters(refuel_stops=crews),
        )
        means = result["fuel"]["refuel_stop_mean_ms"]
        self.assertEqual(means["driver:1"], 20_000.0 - 300.0)
        self.assertEqual(means["driver:2"], 20_000.0 + 300.0)
        self.assertEqual(means["driver:3"], 20_000.0)
        self.assertTrue(result["fuel"]["refuel_stops"])
        stop_times = {event["stop_ms"] for event in result["fuel"]["refuel_stops"]}
        self.assertGreater(len(stop_times), 2)


