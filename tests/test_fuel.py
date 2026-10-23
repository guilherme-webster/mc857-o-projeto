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
    run_detailed_grid_simulation,
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
from tests.model_support import parameters, provenance, track
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


class FuelPlanTest(unittest.TestCase):
    def test_burn_and_sensitivity_follow_length_and_lap_time(self) -> None:
        fuel = plan()
        self.assertAlmostEqual(fuel.burn_kg_per_lap, 2.0)
        self.assertAlmostEqual(fuel.ms_per_kg, 12.5)
        longer = FuelPlan(fuel.parameters, 2 * REFERENCE_MS, 8.0, "track_geometry")
        # Volta duas vezes mais longa queima o dobro e cada kg custa o dobro.
        self.assertAlmostEqual(longer.burn_kg_per_lap, 4.0)
        self.assertAlmostEqual(longer.ms_per_kg, 25.0)

    def test_start_load_covers_race_plus_reserve_up_to_regulation(self) -> None:
        fuel = plan()
        self.assertAlmostEqual(fuel.start_fuel_kg(20), 41.0)
        self.assertEqual(fuel.start_fuel_kg(80), 110.0)
        self.assertAlmostEqual(fuel.range_laps_at_max_fuel, 54.5)

    def test_invalid_parameters_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            fuel_parameters(finish_reserve_kg=110.0)
        with self.assertRaises(ValueError):
            fuel_parameters(sc_burn_factor=1.5)
        with self.assertRaises(ValueError):
            fuel_parameters(burn_kg_per_km=0.0)
        with self.assertRaises(ValueError):
            plan().burn_factor("CHEQUERED")


class FuelLapTest(unittest.TestCase):
    def test_green_lap_burns_one_lap_and_charges_mass_above_reserve(self) -> None:
        lap = fuel_lap(plan(), fuel_kg=41.0, laps_remaining=20)
        self.assertAlmostEqual(lap.burn_kg, 2.0)
        self.assertAlmostEqual(lap.end_kg, 39.0)
        self.assertAlmostEqual(lap.mass_ms, 12.5 * 38.0)
        self.assertEqual(lap.saving_ms, 0.0)
        self.assertFalse(lap.ran_dry)

    def test_final_green_lap_matches_reference_condition(self) -> None:
        lap = fuel_lap(plan(), fuel_kg=3.0, laps_remaining=1)
        self.assertAlmostEqual(lap.end_kg, 1.0)
        self.assertEqual(lap.mass_ms, 0.0)

    def test_neutralized_laps_burn_less(self) -> None:
        fuel = plan()
        self.assertAlmostEqual(
            fuel_lap(fuel, fuel_kg=41.0, laps_remaining=20, status="SC").burn_kg, 1.0
        )
        self.assertAlmostEqual(
            fuel_lap(fuel, fuel_kg=41.0, laps_remaining=20, status="VSC").burn_kg,
            1.2,
        )

    def test_short_car_lifts_and_coasts_within_the_cap(self) -> None:
        no_refuel = plan(refuelling_allowed=False)
        # Faltam 2 kg para 10 voltas: 0,2 kg/volta, dentro do teto de 8%.
        small = fuel_lap(no_refuel, fuel_kg=19.0, laps_remaining=10)
        self.assertAlmostEqual(small.saved_kg, 0.16)
        self.assertAlmostEqual(small.saving_ms, 0.16 * 1_500.0)
        # Deficit menor que o teto: economiza so o necessario.
        tiny = fuel_lap(no_refuel, fuel_kg=20.5, laps_remaining=10)
        self.assertAlmostEqual(tiny.saved_kg, 0.05)

    def test_refuelling_replaces_lift_and_coast(self) -> None:
        lap = fuel_lap(plan(), fuel_kg=19.0, laps_remaining=10)
        self.assertEqual(lap.saved_kg, 0.0)

    def test_no_saving_under_safety_car(self) -> None:
        lap = fuel_lap(
            plan(refuelling_allowed=False), fuel_kg=5.0, laps_remaining=10, status="SC"
        )
        self.assertEqual(lap.saved_kg, 0.0)

    def test_must_pit_when_the_next_pit_entry_is_out_of_reach(self) -> None:
        fuel = plan()
        # F = 2 kg e entrada na linha: com 2,0 kg ainda chega; com 1,99 nao.
        self.assertFalse(fuel.must_pit(2.0, lap=5, total_laps=10))
        self.assertTrue(fuel.must_pit(1.99, lap=5, total_laps=10))
        # A folga do piloto antecipa a obrigacao.
        self.assertTrue(fuel.must_pit(2.5, lap=5, total_laps=10, margin_kg=1.0))
        # Na ultima volta nao ha proxima volta para cobrir.
        self.assertFalse(fuel.must_pit(0.1, lap=10, total_laps=10))
        self.assertFalse(
            plan(refuelling_allowed=False).must_pit(0.1, lap=5, total_laps=10)
        )

    def test_pit_entry_before_the_line_needs_less_than_a_full_lap(self) -> None:
        fuel = FuelPlan(
            fuel_parameters(), REFERENCE_MS, 4.0, "track_geometry",
            pit_entry_fraction=0.95,
        )
        self.assertAlmostEqual(fuel.fuel_to_reach_pit_kg, 1.9)
        self.assertFalse(fuel.must_pit(1.95, lap=5, total_laps=10))

    def test_refuelling_time_only_counts_beyond_the_tyre_change(self) -> None:
        fuel = plan()
        # 9 kg/s: 45 kg levam 5 s, 2,5 s alem da troca de pneus (2,5 s).
        self.assertAlmostEqual(fuel.stationary_extra_ms(45.0), 2_500.0)
        self.assertEqual(fuel.stationary_extra_ms(10.0), 0.0)

    def test_refuel_target_covers_the_rest_of_the_race_up_to_the_tank(self) -> None:
        fuel = plan()
        self.assertAlmostEqual(fuel.refuel_target_kg(7), 15.0)
        self.assertEqual(fuel.refuel_target_kg(100), 110.0)

    def test_running_dry_burns_what_is_left(self) -> None:
        lap = fuel_lap(plan(), fuel_kg=0.5, laps_remaining=3)
        self.assertTrue(lap.ran_dry)
        self.assertEqual(lap.end_kg, 0.0)


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


#: Fracao "verdadeira" usada na amostra sintetica de calibracao.
TRUE_FRACTION_PER_KM = 1.2e-4
TRUE_TYRE_MS = 40.0


def synthetic_fuel_laps() -> tuple[list[LapObservation], dict[str, FuelRaceContext]]:
    """Corridas com extensoes e referencias diferentes, sem ruido.

    A inclinacao de combustivel de cada corrida e ``fracao * T * L``; um
    modelo linear (inclinacao unica) nao consegue reproduzir todas.
    """

    laps: list[LapObservation] = []
    contexts: dict[str, FuelRaceContext] = {}
    for race, (reference_ms, length_km, total) in enumerate(
        ((75_000.0, 3.3, 78), (90_000.0, 5.0, 60), (108_000.0, 7.0, 44))
    ):
        race_id = f"race:{race}"
        contexts[race_id] = FuelRaceContext(
            race_id, f"GP {race}", 2024, f"circuit:{race}", reference_ms, length_km
        )
        slope = TRUE_FRACTION_PER_KM * reference_ms * length_km
        stops = (total // 3, 2 * total // 3)
        for driver in range(8):
            for lap in range(2, total + 1):
                if lap in stops or (lap - 1) in stops:
                    continue
                last_stop = max((s for s in stops if s < lap), default=0)
                age = lap - 1 - last_stop
                laps.append(
                    LapObservation(
                        race_id=race_id,
                        circuit_id=f"circuit:{race}",
                        driver_id=f"driver:{driver}",
                        lap_number=lap,
                        tyre_age_laps=age,
                        lap_time_ms=round(
                            reference_ms + driver * 200 - slope * lap
                            + TRUE_TYRE_MS * age
                        ),
                    )
                )
    return laps, contexts


class FuelCalibrationTest(unittest.TestCase):
    def test_recovers_the_true_fraction(self) -> None:
        laps, contexts = synthetic_fuel_laps()
        fitted, diagnostics = calibrate_fuel(
            laps,
            contexts,
            version="fuel-sintetico",
            seasons=(2024,),
            source_name="teste",
            source_version=1,
            calibrated_at="2026-10-17",
        )
        self.assertAlmostEqual(
            fitted.lap_time_fraction_per_fuel_km / TRUE_FRACTION_PER_KM, 1.0, delta=0.02
        )
        self.assertAlmostEqual(diagnostics.tyre_ms_per_lap, TRUE_TYRE_MS, delta=1.0)

    def test_validation_prefers_the_mass_model_when_slopes_differ(self) -> None:
        laps, contexts = synthetic_fuel_laps()
        fitted = fuel_parameters(lap_time_fraction_per_fuel_km=TRUE_FRACTION_PER_KM)
        report = validate_fuel(
            laps,
            contexts,
            fitted,
            linear_ms_per_lap=54.0,
            seasons=(2024,),
            minimum_laps_per_race=100,
        )
        self.assertEqual(len(report.races), 3)
        self.assertLess(report.mass_weighted_mae_ms, 1.0)
        self.assertGreater(report.linear_weighted_mae_ms, 10.0)

    def test_races_without_context_are_skipped_not_invented(self) -> None:
        laps, contexts = synthetic_fuel_laps()
        del contexts["race:0"]
        _, diagnostics = calibrate_fuel(
            laps,
            contexts,
            version="fuel-sintetico",
            seasons=(2024,),
            source_name="teste",
            source_version=1,
        )
        self.assertEqual(diagnostics.skipped_races, ("race:0",))
        self.assertEqual(diagnostics.races, 2)


class FuelArtifactTest(unittest.TestCase):
    def test_roundtrip_keeps_every_parameter(self) -> None:
        original = fuel_parameters(sc_burn_factor=0.45)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fuel.json"
            write_fuel_parameters(original, path)
            self.assertEqual(read_fuel_parameters(path), original)

    def test_corrupted_artifact_is_a_readable_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fuel.json"
            write_fuel_parameters(fuel_parameters(), path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            del payload["assumed"]["burn_kg_per_km"]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(FuelParametersError):
                read_fuel_parameters(path)

    def test_versioned_artifact_is_valid(self) -> None:
        root = Path(__file__).resolve().parents[1]
        loaded = read_fuel_parameters(root / "data" / "parameters" / "fuel-v1.json")
        self.assertEqual(loaded.origin, "calibrated")
        self.assertEqual(loaded.max_fuel_kg, 110.0)


class GridFuelTest(unittest.TestCase):
    def test_grid_run_carries_fuel_to_the_contract(self) -> None:
        grid = (
            GridEntry("driver:1", "Primeiro", "team:solid", "Solida"),
            GridEntry("driver:2", "Segundo", "team:solid", "Solida"),
        )
        result = run_detailed_grid_simulation(
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
        result = run_detailed_grid_simulation(
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


class RefuelStopSamplingTest(unittest.TestCase):
    def stops_parameters(self, **overrides) -> RefuelStopParameters:
        defaults = dict(
            provenance=provenance(seasons=(2023, 2024)),
            team_offsets=(
                TeamPitOffset("team:fast", "Rapida", -400.0, 100),
                TeamPitOffset("team:slow", "Lenta", 400.0, 100),
            ),
            persistence=0.75,
            stop_sigma_ms=600.0,
            stop_skew=0.3,
        )
        defaults.update(overrides)
        return RefuelStopParameters(**defaults)

    def test_offsets_are_scaled_by_persistence_and_default_to_the_field(self) -> None:
        crews = self.stops_parameters()
        self.assertEqual(crews.offset_ms("team:fast"), -300.0)
        self.assertEqual(crews.offset_ms("team:unknown"), 0.0)
        self.assertEqual(crews.offset_ms(None), 0.0)

    def test_sampling_is_reproducible_and_centred_on_the_mean(self) -> None:
        crews = self.stops_parameters()
        first = sample_refuel_stops(
            23_000.0, crews, SeededRandomSource(5), 2_000, "refuel:stops:a"
        )
        second = sample_refuel_stops(
            23_000.0, crews, SeededRandomSource(5), 2_000, "refuel:stops:a"
        )
        self.assertEqual(first, second)
        samples = sorted(first.sampled_ms)
        self.assertAlmostEqual(samples[len(samples) // 2], 23_000.0, delta=60.0)
        # Cauda lenta mais longa que a rapida (assimetria positiva).
        self.assertGreater(samples[-100] - 23_000.0, 23_000.0 - samples[99])

    def test_without_spread_every_stop_is_the_mean(self) -> None:
        stops = sample_refuel_stops(23_000.0, None, SeededRandomSource(1), 3, "x")
        self.assertEqual(stops.sampled_ms, (23_000.0,) * 3)
        self.assertEqual(stops.loss_ms(10), 23_000.0)


def synthetic_stops() -> list[PitStopObservation]:
    """Tres equipes com desvio fixo (-300, 0, +300 ms) e quatro temporadas."""

    stops = []
    for season in (2021, 2022, 2023, 2024):
        for race in range(6):
            race_id = f"race:{season}:{race}"
            base = 20_000 + 1_000 * race
            for team_id, offset in (("team:a", -300), ("team:b", 0), ("team:c", 300)):
                for index in range(8):
                    jitter = (index - 3.5) * 120
                    stops.append(
                        PitStopObservation(
                            race_id, season, team_id, team_id.upper(),
                            int(base + offset + jitter),
                        )
                    )
    return stops


class RefuelStopCalibrationTest(unittest.TestCase):
    def calibrated(self) -> RefuelStopParameters:
        return calibrate_refuel_stops(
            synthetic_stops(),
            seasons=(2023, 2024),
            persistence_windows=[((2021, 2022), 2023), ((2022, 2023), 2024)],
            source_name="teste",
            source_version=1,
            calibrated_at="2026-10-21",
        )

    def test_recovers_team_offsets_and_full_persistence(self) -> None:
        crews = self.calibrated()
        offsets = {item.team_id: item.offset_ms for item in crews.team_offsets}
        self.assertAlmostEqual(offsets["team:a"], -300.0, delta=1.0)
        self.assertAlmostEqual(offsets["team:c"], 300.0, delta=1.0)
        self.assertAlmostEqual(crews.persistence, 1.0, delta=0.01)
        self.assertGreater(crews.stop_sigma_ms, 0.0)

    def test_red_flag_stops_are_ignored(self) -> None:
        stops = synthetic_stops()
        stops.append(PitStopObservation("race:2024:0", 2024, "team:a", "A", 900_000))
        crews = calibrate_refuel_stops(
            stops,
            seasons=(2023, 2024),
            persistence_windows=[((2021, 2022), 2023)],
            source_name="teste",
            source_version=1,
        )
        offsets = {item.team_id: item.offset_ms for item in crews.team_offsets}
        self.assertAlmostEqual(offsets["team:a"], -300.0, delta=1.0)

    def test_validation_reports_offset_error_and_spread_coverage(self) -> None:
        crews = self.calibrated()
        report = validate_refuel_stops(
            [stop for stop in synthetic_stops() if stop.season == 2024],
            crews,
            seasons=(2024,),
        )
        self.assertEqual(len(report.teams), 3)
        self.assertLess(report.model_mae_ms, report.zero_offset_mae_ms)
        self.assertGreater(report.p10_p90_coverage, 0.5)


class RefuelArtifactTest(unittest.TestCase):
    def test_roundtrip_keeps_refuel_stops_and_scenario(self) -> None:
        original = fuel_parameters(
            refuelling_allowed=False,
            refuel_stops=RefuelStopSamplingTest().stops_parameters(),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fuel.json"
            write_fuel_parameters(original, path)
            self.assertEqual(read_fuel_parameters(path), original)

    def test_versioned_artifact_allows_refuelling_with_team_times(self) -> None:
        root = Path(__file__).resolve().parents[1]
        loaded = read_fuel_parameters(root / "data" / "parameters" / "fuel-v1.json")
        self.assertTrue(loaded.refuelling_allowed)
        self.assertIsNotNone(loaded.refuel_stops)
        self.assertGreater(len(loaded.refuel_stops.team_offsets), 5)


class GridRefuelTest(unittest.TestCase):
    def test_each_car_gets_its_team_stop_time(self) -> None:
        crews = RefuelStopSamplingTest().stops_parameters()
        grid = (
            GridEntry("driver:1", "Rapido", "team:fast", "Rapida"),
            GridEntry("driver:2", "Lento", "team:slow", "Lenta"),
            GridEntry("driver:3", "Medio", "team:other", "Outra"),
        )
        result = run_detailed_grid_simulation(
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


if __name__ == "__main__":
    unittest.main()
