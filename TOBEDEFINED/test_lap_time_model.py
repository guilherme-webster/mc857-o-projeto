from __future__ import annotations

import unittest

from f1_simulator.domain.lap_time import (
    LapTimeBreakdown,
    compute_lap_time,
    fuel_penalty_ms,
    lap_noise_ms,
    traffic_penalty_ms,
)
from f1_simulator.domain.model_parameters import CompoundParameters, ModelParameters
from f1_simulator.domain.random_source import (
    FrozenRandomSource,
    SeededRandomSource,
)
from f1_simulator.domain.tyres import TyreSet, tyre_penalty_ms
from tests.model_support import parameters, track


class FuelPenaltyTest(unittest.TestCase):
    """O combustivel pesa no inicio e desaparece na ultima volta."""

    def test_zero_on_final_lap(self) -> None:
        # A referencia e a volta mais leve, entao a penalidade precisa zerar
        # exatamente ali; caso contrario o modelo estaria deslocado.
        self.assertEqual(fuel_penalty_ms(parameters(), 50, 50), 0.0)

    def test_decreases_monotonically(self) -> None:
        model = parameters()
        values = [fuel_penalty_ms(model, lap, 20) for lap in range(1, 21)]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertEqual(values[0], 25.0 * 19)

    def test_rejects_lap_outside_race(self) -> None:
        with self.assertRaises(ValueError):
            fuel_penalty_ms(parameters(), 0, 10)
        with self.assertRaises(ValueError):
            fuel_penalty_ms(parameters(), 11, 10)


class TyrePenaltyTest(unittest.TestCase):
    def test_fresh_tyre_costs_only_the_compound_offset(self) -> None:
        model = parameters()
        fresh = TyreSet("MEDIUM", 0)
        self.assertEqual(tyre_penalty_ms(fresh, model.compound("MEDIUM"), track()), 0.0)

    def test_penalty_grows_with_age(self) -> None:
        model = parameters()
        compound = model.compound("MEDIUM")
        values = [
            tyre_penalty_ms(TyreSet("MEDIUM", age), compound, track())
            for age in range(10)
        ]
        self.assertEqual(values, sorted(values))

    def test_severity_scales_wear_but_not_compound_offset(self) -> None:
        model = parameters()
        soft = model.compound("SOFT")
        fresh_normal = tyre_penalty_ms(TyreSet("SOFT", 0), soft, track())
        fresh_severe = tyre_penalty_ms(
            TyreSet("SOFT", 0), soft, track(tyre_severity=2.0)
        )
        # Com pneu novo nao ha desgaste para escalar: so o offset do composto.
        self.assertEqual(fresh_normal, fresh_severe)

        worn_normal = tyre_penalty_ms(TyreSet("SOFT", 10), soft, track())
        worn_severe = tyre_penalty_ms(
            TyreSet("SOFT", 10), soft, track(tyre_severity=2.0)
        )
        self.assertGreater(worn_severe, worn_normal)

    def test_rejects_mismatched_compound_parameters(self) -> None:
        model = parameters()
        with self.assertRaises(ValueError):
            tyre_penalty_ms(TyreSet("SOFT", 3), model.compound("HARD"), track())

    def test_aged_returns_new_object(self) -> None:
        original = TyreSet("HARD", 4)
        self.assertEqual(original.aged().age_laps, 5)
        self.assertEqual(original.age_laps, 4)

    def test_rejects_negative_age(self) -> None:
        with self.assertRaises(ValueError):
            TyreSet("SOFT", -1)


class TrafficPenaltyTest(unittest.TestCase):
    def test_leader_is_never_penalised(self) -> None:
        self.assertEqual(traffic_penalty_ms(parameters(), track(), None), 0.0)

    def test_no_penalty_beyond_threshold(self) -> None:
        model = parameters()
        self.assertEqual(traffic_penalty_ms(model, track(), 2500.0), 0.0)
        self.assertEqual(traffic_penalty_ms(model, track(), 9999.0), 0.0)

    def test_penalty_grows_as_the_gap_closes(self) -> None:
        model = parameters()
        far = traffic_penalty_ms(model, track(), 2000.0)
        near = traffic_penalty_ms(model, track(), 200.0)
        self.assertGreater(near, far)

    def test_overtaking_difficulty_scales_the_penalty(self) -> None:
        model = parameters()
        easy = traffic_penalty_ms(model, track(overtaking_difficulty=0.1), 500.0)
        hard = traffic_penalty_ms(model, track(overtaking_difficulty=1.0), 500.0)
        self.assertGreater(hard, easy)


class LapNoiseTest(unittest.TestCase):
    def test_frozen_source_produces_no_noise(self) -> None:
        self.assertEqual(lap_noise_ms(parameters(), FrozenRandomSource()), 0.0)

    def test_same_seed_produces_the_same_sequence(self) -> None:
        model = parameters()
        first = [lap_noise_ms(model, SeededRandomSource(7)) for _ in range(5)]
        second = [lap_noise_ms(model, SeededRandomSource(7)) for _ in range(5)]
        self.assertEqual(first, second)

    def test_different_seeds_diverge(self) -> None:
        model = parameters()
        a = [lap_noise_ms(model, SeededRandomSource(1)) for _ in range(5)]
        b = [lap_noise_ms(model, SeededRandomSource(2)) for _ in range(5)]
        self.assertNotEqual(a, b)

    def test_zero_scale_disables_noise_without_consuming_randomness(self) -> None:
        model = parameters(lap_noise_ms=0.0)
        rng = SeededRandomSource(3)
        self.assertEqual(lap_noise_ms(model, rng), 0.0)
        # A fonte nao foi consumida, entao o proximo sorteio e o primeiro.
        self.assertEqual(rng.uniform01(), SeededRandomSource(3).uniform01())

    def test_skew_makes_losses_larger_than_gains(self) -> None:
        model = parameters(lap_noise_ms=100.0, lap_noise_skew=0.5)
        rng = SeededRandomSource(11)
        draws = [lap_noise_ms(model, rng) for _ in range(4000)]
        losses = [d for d in draws if d > 0]
        gains = [-d for d in draws if d < 0]
        self.assertGreater(
            sum(losses) / len(losses), sum(gains) / len(gains)
        )


class ComputeLapTimeTest(unittest.TestCase):
    def test_components_sum_to_total(self) -> None:
        breakdown = compute_lap_time(
            reference_ms=90_000.0,
            parameters=parameters(),
            track=track(),
            tyre=TyreSet("MEDIUM", 5),
            lap_number=10,
            total_laps=50,
            gap_ahead_ms=800.0,
            pitting=False,
            rng=SeededRandomSource(5),
        )
        self.assertAlmostEqual(
            breakdown.components_sum_ms(), breakdown.total_ms, places=6
        )
        self.assertFalse(breakdown.floored)

    def test_pit_loss_applied_only_when_pitting(self) -> None:
        common = dict(
            reference_ms=90_000.0,
            parameters=parameters(),
            track=track(),
            tyre=TyreSet("MEDIUM", 5),
            lap_number=10,
            total_laps=50,
            gap_ahead_ms=None,
            rng=FrozenRandomSource(),
        )
        running = compute_lap_time(pitting=False, **common)
        stopping = compute_lap_time(pitting=True, **common)
        self.assertEqual(running.pit_ms, 0.0)
        self.assertEqual(stopping.pit_ms, 20_000.0)
        self.assertAlmostEqual(
            stopping.total_ms - running.total_ms, 20_000.0, places=6
        )

    def test_deterministic_with_frozen_source(self) -> None:
        def run() -> LapTimeBreakdown:
            return compute_lap_time(
                reference_ms=88_000.0,
                parameters=parameters(),
                track=track(),
                tyre=TyreSet("HARD", 2),
                lap_number=3,
                total_laps=40,
                gap_ahead_ms=None,
                pitting=False,
                rng=FrozenRandomSource(),
            )

        self.assertEqual(run(), run())

    def test_rejects_non_positive_reference(self) -> None:
        with self.assertRaises(ValueError):
            compute_lap_time(
                reference_ms=0.0,
                parameters=parameters(),
                track=track(),
                tyre=TyreSet("MEDIUM"),
                lap_number=1,
                total_laps=10,
                gap_ahead_ms=None,
                pitting=False,
                rng=FrozenRandomSource(),
            )

    def test_unknown_compound_is_an_error_not_a_default(self) -> None:
        with self.assertRaises(KeyError):
            compute_lap_time(
                reference_ms=90_000.0,
                parameters=parameters(),
                track=track(),
                tyre=TyreSet("WET"),
                lap_number=1,
                total_laps=10,
                gap_ahead_ms=None,
                pitting=False,
                rng=FrozenRandomSource(),
            )

    def test_floor_is_recorded_rather_than_hidden(self) -> None:
        # Ruido enorme e referencia minima forcam o piso; o resultado precisa
        # declarar que foi truncado em vez de fingir que a soma bate.
        breakdown = compute_lap_time(
            reference_ms=1.0,
            parameters=parameters(fuel_penalty_ms_per_remaining_lap=0.0),
            track=track(),
            tyre=TyreSet("SOFT", 0),
            lap_number=1,
            total_laps=1,
            gap_ahead_ms=None,
            pitting=False,
            rng=FrozenRandomSource(),
        )
        self.assertTrue(breakdown.floored)
        self.assertEqual(breakdown.total_ms, 1_000.0)


class ModelParametersValidationTest(unittest.TestCase):
    def test_rejects_unknown_reference_compound(self) -> None:
        with self.assertRaises(ValueError):
            parameters(reference_compound="WET")

    def test_rejects_duplicate_compound(self) -> None:
        with self.assertRaises(ValueError):
            parameters(
                compounds=(
                    CompoundParameters("MEDIUM", 0.0, 40.0, 0.0, 22),
                    CompoundParameters("MEDIUM", 0.0, 40.0, 0.0, 22),
                )
            )

    def test_rejects_negative_penalties(self) -> None:
        with self.assertRaises(ValueError):
            parameters(fuel_penalty_ms_per_remaining_lap=-1.0)
        with self.assertRaises(ValueError):
            parameters(grid_penalty_ms_per_position=-1.0)

    def test_rejects_hazard_outside_unit_interval(self) -> None:
        with self.assertRaises(ValueError):
            parameters(dnf_hazard_per_lap=1.0)
        with self.assertRaises(ValueError):
            parameters(dnf_hazard_per_lap=-0.1)

    def test_rejects_invalid_origin(self) -> None:
        with self.assertRaises(ValueError):
            track(origin="guessed")

    def test_unknown_circuit_falls_back_and_stays_traceable(self) -> None:
        model = parameters()
        chosen = model.track("circuit:does-not-exist")
        self.assertEqual(chosen.circuit_id, "__fallback__")
        # O fallback precisa continuar identificavel como hipotese.
        self.assertEqual(chosen.origin, "assumed")

    def test_known_circuit_is_returned_as_calibrated(self) -> None:
        self.assertEqual(parameters().track("circuit:1").origin, "calibrated")


class SeededRandomSourceTest(unittest.TestCase):
    def test_rejects_non_integer_seed(self) -> None:
        with self.assertRaises(ValueError):
            SeededRandomSource(1.5)
        with self.assertRaises(ValueError):
            SeededRandomSource(True)

    def test_is_isolated_from_the_global_random_state(self) -> None:
        import random

        random.seed(99)
        first = [SeededRandomSource(4).uniform01() for _ in range(3)]
        random.seed(12345)
        second = [SeededRandomSource(4).uniform01() for _ in range(3)]
        self.assertEqual(first, second)

    def test_frozen_source_never_triggers_a_hazard(self) -> None:
        # uniform01 devolve 1.0, estritamente acima de qualquer risco em [0, 1).
        self.assertEqual(FrozenRandomSource().uniform01(), 1.0)


if __name__ == "__main__":
    unittest.main()
