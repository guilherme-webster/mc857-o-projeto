"""Modelo de massa de combustivel: dominio, motor, calibracao e artefato."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from f1_simulator.adapters.fuel_parameters_json import (
    FuelParametersError,
    read_fuel_parameters,
    write_fuel_parameters,
)
from f1_simulator.application.calibrate_fuel import (
    FuelRaceContext,
    calibrate_fuel,
    validate_fuel,
)
from f1_simulator.application.calibrate_model import LapObservation
from f1_simulator.domain.fuel import (
    FuelPlan,
    fuel_lap,
)
from tests.fuel_support import REFERENCE_MS, fuel_parameters, plan

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

