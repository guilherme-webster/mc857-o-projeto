from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from f1_simulator.adapters.model_parameters_json import (
    from_dict,
    read_parameters,
    to_dict,
    write_parameters,
)
from f1_simulator.application.calibrate_model import (
    AttritionObservation,
    CalibrationInput,
    GridObservation,
    LapObservation,
    PitLossObservation,
    PositionChurnObservation,
    QualifyingObservation,
    TeamAttritionObservation,
    calibrate,
)
from tests.model_support import parameters

#: Coeficientes "verdadeiros" usados para gerar a amostra sintetica. O teste
#: verifica se a calibracao consegue recupera-los.
TRUE_FUEL_MS = -25.0
TRUE_TYRE_MS = 45.0


def synthetic_laps(
    races: int = 8,
    drivers: int = 6,
    total_laps: int = 60,
    stops: tuple[int, ...] = (20, 40),
) -> list[LapObservation]:
    """Voltas geradas por uma regra conhecida, sem ruido.

    A construcao imita a estrutura real: o combustivel acompanha o numero da
    volta e a idade do pneu reinicia em cada parada. E essa diferenca de
    relogios que torna os dois efeitos separaveis.
    """

    observations: list[LapObservation] = []
    for race in range(races):
        for driver in range(drivers):
            base = 90_000 + driver * 250
            for lap in range(2, total_laps + 1):
                last_stop = max((s for s in stops if s < lap), default=0)
                age = lap - 1 - last_stop
                if lap in stops or (lap - 1) in stops:
                    continue
                observations.append(
                    LapObservation(
                        race_id=f"race:{race}",
                        circuit_id=f"circuit:{race % 3}",
                        driver_id=f"driver:{driver}",
                        lap_number=lap,
                        tyre_age_laps=age,
                        lap_time_ms=round(
                            base + TRUE_FUEL_MS * lap + TRUE_TYRE_MS * age
                        ),
                    )
                )
    return observations


def calibration_input(**overrides) -> CalibrationInput:
    defaults = dict(
        source_name="teste",
        source_version=128,
        seasons=(2022, 2023),
        laps=tuple(synthetic_laps()),
        pit_losses=tuple(
            PitLossObservation(f"circuit:{i % 3}", 22_000.0 + (i % 5) * 200)
            for i in range(120)
        ),
        grid=tuple(
            GridObservation(position, 8_000.0 + 700.0 * (position - 1))
            for _ in range(20)
            for position in range(1, 21)
        ),
        attrition=AttritionObservation(
            entries=800, retirements=112, mean_race_laps=60.0
        ),
        pit_window_spread_laps=6.2,
        position_churn=tuple(
            PositionChurnObservation(f"circuit:{i % 3}", 2.0 + (i % 3) * 1.5)
            for i in range(30)
        ),
        qualifying=tuple(
            QualifyingObservation(80_000, 84_000.0) for _ in range(50)
        ),
        team_attrition=(
            TeamAttritionObservation("team:frail", "Fragil", 80, 24),
            TeamAttritionObservation("team:solid", "Solida", 80, 4),
        ),
        circuit_names={f"circuit:{i}": f"Circuito {i}" for i in range(3)},
    )
    defaults.update(overrides)
    return CalibrationInput(**defaults)


class IdentificationTest(unittest.TestCase):
    """O coracao do metodo: separar combustivel de pneu."""

    def test_recovers_the_true_coefficients(self) -> None:
        _, diagnostics = calibrate(calibration_input(), version="t")
        self.assertAlmostEqual(diagnostics.fuel_ms_per_lap, TRUE_FUEL_MS, delta=1.0)
        self.assertAlmostEqual(diagnostics.tyre_ms_per_lap, TRUE_TYRE_MS, delta=1.0)

    def test_fuel_penalty_is_the_positive_mirror_of_the_slope(self) -> None:
        model, _ = calibrate(calibration_input(), version="t")
        self.assertAlmostEqual(
            model.fuel_penalty_ms_per_remaining_lap, -TRUE_FUEL_MS, delta=1.0
        )

    def test_collinearity_is_reported_and_below_one(self) -> None:
        # Se as duas contagens fossem identicas a regressao seria singular e os
        # coeficientes nao teriam significado separado.
        _, diagnostics = calibrate(calibration_input(), version="t")
        self.assertLess(diagnostics.collinearity, 1.0)
        self.assertGreater(diagnostics.collinearity, 0.0)

    def test_single_stint_sample_is_rejected_as_singular(self) -> None:
        # Sem paradas, idade do pneu e numero da volta sao a mesma variavel.
        laps = synthetic_laps(stops=())
        with self.assertRaises(ValueError):
            calibrate(calibration_input(laps=tuple(laps)), version="t")

    def test_a_faster_car_does_not_shift_the_coefficients(self) -> None:
        # A centragem por corrida/piloto precisa remover o ritmo proprio.
        slow = synthetic_laps(drivers=3)
        model_a, diag_a = calibrate(calibration_input(laps=tuple(slow)), version="t")
        shifted = [
            LapObservation(
                o.race_id, o.circuit_id, o.driver_id, o.lap_number,
                o.tyre_age_laps, o.lap_time_ms + 5_000,
            )
            for o in slow
        ]
        _, diag_b = calibrate(calibration_input(laps=tuple(shifted)), version="t")
        self.assertAlmostEqual(
            diag_a.fuel_ms_per_lap, diag_b.fuel_ms_per_lap, delta=0.01
        )


class DerivedParameterTest(unittest.TestCase):
    def test_pit_loss_uses_the_median_per_circuit(self) -> None:
        # Uma parada sob bandeira vermelha nao pode arrastar a estimativa.
        losses = [PitLossObservation("circuit:0", 22_000.0) for _ in range(40)]
        losses.append(PitLossObservation("circuit:0", 2_400_000.0))
        model, _ = calibrate(
            calibration_input(pit_losses=tuple(losses)),
            version="t",
            minimum_stops_per_circuit=20,
        )
        self.assertAlmostEqual(model.track("circuit:0").pit_loss_ms, 22_000.0, delta=1)

    def test_circuits_below_the_minimum_are_not_calibrated(self) -> None:
        losses = tuple(
            PitLossObservation("circuit:0", 22_000.0) for _ in range(25)
        ) + tuple(PitLossObservation("circuit:9", 30_000.0) for _ in range(3))
        model, _ = calibrate(
            calibration_input(pit_losses=losses),
            version="t",
            minimum_stops_per_circuit=20,
        )
        self.assertEqual(model.track("circuit:9").origin, "assumed")
        self.assertEqual(model.track("circuit:0").origin, "calibrated")

    def test_grid_penalty_excludes_the_common_standing_start_cost(self) -> None:
        # O excesso gerado tem intercepto 8000 ms e inclinacao 700 ms/posicao.
        # Sem intercepto na regressao, o custo comum vazaria para a inclinacao.
        model, _ = calibrate(calibration_input(), version="t")
        self.assertAlmostEqual(
            model.grid_penalty_ms_per_position, 700.0, delta=1.0
        )

    def test_hazard_converts_the_race_rate_to_a_per_lap_rate(self) -> None:
        model, _ = calibrate(calibration_input(), version="t")
        rate = 112 / 800
        expected = 1.0 - (1.0 - rate) ** (1.0 / 60.0)
        self.assertAlmostEqual(model.dnf_hazard_per_lap, expected, places=5)

    def test_compound_split_is_declared_as_a_hypothesis(self) -> None:
        # O Trotman nao registra composto: a divisao nao pode se apresentar
        # como calibrada, mesmo estando ancorada num valor medido.
        model, _ = calibrate(calibration_input(), version="t")
        for compound in model.compounds:
            self.assertEqual(compound.origin, "assumed")

    def test_softer_compound_degrades_faster_and_starts_quicker(self) -> None:
        model, _ = calibrate(calibration_input(), version="t")
        soft = model.compound("SOFT")
        hard = model.compound("HARD")
        self.assertGreater(soft.degradation_ms_per_lap, hard.degradation_ms_per_lap)
        self.assertLess(soft.pace_offset_ms, hard.pace_offset_ms)

    def test_provenance_records_the_calibration_scope(self) -> None:
        model, _ = calibrate(calibration_input(), version="t")
        self.assertEqual(model.provenance.seasons, (2022, 2023))
        self.assertEqual(model.provenance.source_version, 128)

    def test_rejects_empty_samples(self) -> None:
        with self.assertRaises(ValueError):
            calibrate(calibration_input(laps=()), version="t")
        with self.assertRaises(ValueError):
            calibrate(calibration_input(pit_losses=()), version="t")


class CircuitVariationTest(unittest.TestCase):
    """Circuitos precisam deixar de ser intercambiaveis."""

    def test_overtaking_difficulty_is_inverse_to_position_changes(self) -> None:
        model, _ = calibrate(calibration_input(), version="t")
        # circuit:0 tem 2.0 trocas/volta, circuit:2 tem 5.0 -- o primeiro
        # precisa ser o mais dificil de ultrapassar.
        self.assertGreater(
            model.track("circuit:0").overtaking_difficulty,
            model.track("circuit:2").overtaking_difficulty,
        )

    def test_overtaking_difficulty_stays_inside_bounds(self) -> None:
        model, _ = calibrate(calibration_input(), version="t")
        for track in model.tracks:
            self.assertGreaterEqual(track.overtaking_difficulty, 0.15)
            self.assertLessEqual(track.overtaking_difficulty, 0.95)

    def test_severity_never_leaves_the_physical_range(self) -> None:
        # A regressao por circuito chega a devolver inclinacao negativa onde ha
        # poucos stints; pneu que melhora com a idade nao pode virar parametro.
        model, _ = calibrate(calibration_input(), version="t")
        for track in model.tracks:
            self.assertGreaterEqual(track.tyre_severity, 0.30)
            self.assertLessEqual(track.tyre_severity, 2.50)

    def test_severity_is_reported_in_the_diagnostics(self) -> None:
        _, diagnostics = calibrate(calibration_input(), version="t")
        self.assertGreaterEqual(diagnostics.circuits_with_severity, 0)


class TeamReliabilityTest(unittest.TestCase):
    def test_fragile_team_gets_a_higher_hazard_than_a_solid_one(self) -> None:
        model, _ = calibrate(calibration_input(), version="t")
        self.assertGreater(
            model.reliability_factor("team:frail"),
            model.reliability_factor("team:solid"),
        )

    def test_unknown_team_falls_back_to_the_field_average(self) -> None:
        # Equipes mudam de nome entre temporadas; o cenario precisa continuar
        # executavel em vez de falhar por um identificador novo.
        model, _ = calibrate(calibration_input(), version="t")
        self.assertEqual(model.reliability_factor("team:renamed"), 1.0)
        self.assertEqual(model.reliability_factor(None), 1.0)

    def test_shrinkage_pulls_extremes_toward_the_field(self) -> None:
        # Taxa bruta da fragil = 24/80 = 30%, contra 14% do campo: a razao crua
        # seria 2.14x. O encolhimento precisa deixar o fator abaixo disso.
        model, _ = calibrate(calibration_input(), version="t")
        raw = (24 / 80) / (112 / 800)
        self.assertLess(model.reliability_factor("team:frail"), raw)
        self.assertGreater(model.reliability_factor("team:frail"), 1.0)

    def test_counts_travel_with_the_factor(self) -> None:
        model, _ = calibrate(calibration_input(), version="t")
        frail = next(t for t in model.team_reliability if t.team_id == "team:frail")
        self.assertEqual((frail.retirements, frail.observed_entries), (24, 80))
        self.assertEqual(frail.origin, "calibrated")

    def test_rejects_impossible_counts(self) -> None:
        from f1_simulator.domain.model_parameters import TeamReliability

        with self.assertRaises(ValueError):
            TeamReliability("team:x", "X", 1.0, 10, 11)
        with self.assertRaises(ValueError):
            TeamReliability("team:x", "X", 1.0, 0, 0)


class NoiseEstimationTest(unittest.TestCase):
    def test_noiseless_sample_yields_no_noise(self) -> None:
        # A amostra sintetica segue a regra exatamente: nao ha inovacao.
        model, _ = calibrate(calibration_input(), version="t")
        self.assertEqual(model.lap_noise_ms, 0.0)

    def test_noise_is_estimated_from_successive_differences(self) -> None:
        import random

        rng = random.Random(7)
        noisy = [
            LapObservation(
                o.race_id, o.circuit_id, o.driver_id, o.lap_number,
                o.tyre_age_laps, o.lap_time_ms + round(rng.gauss(0, 300)),
            )
            for o in synthetic_laps()
        ]
        model, _ = calibrate(calibration_input(laps=tuple(noisy)), version="t")
        # Recupera a escala injetada dentro de uma tolerancia ampla; o
        # estimador e robusto, nao exato.
        self.assertAlmostEqual(model.lap_noise_ms, 300.0, delta=60.0)


class JsonRoundTripTest(unittest.TestCase):
    def test_round_trip_preserves_every_field(self) -> None:
        original = parameters()
        self.assertEqual(from_dict(to_dict(original)), original)

    def test_written_file_reloads_identically(self) -> None:
        original = parameters()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "model.json"
            write_parameters(original, path)
            self.assertEqual(read_parameters(path), original)

    def test_missing_file_reports_how_to_generate_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError) as caught:
                read_parameters(Path(directory) / "absent.json")
        self.assertIn("calibrate_model", str(caught.exception))

    def test_corrupted_file_fails_validation_instead_of_loading(self) -> None:
        payload = to_dict(parameters())
        payload["dnf_hazard_per_lap"] = 5.0
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_parameters(path)

    def test_calibrated_output_survives_the_round_trip(self) -> None:
        model, _ = calibrate(calibration_input(), version="t")
        self.assertEqual(from_dict(to_dict(model)), model)


if __name__ == "__main__":
    unittest.main()
