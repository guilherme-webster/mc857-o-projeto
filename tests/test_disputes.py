from __future__ import annotations

import unittest

from f1_simulator.domain.disputes import pass_probability, resolve_disputes
from f1_simulator.domain.random_source import FrozenRandomSource, SeededRandomSource
from tests.model_support import parameters, track


class AlwaysPass:
    """Fonte degenerada em que todo sorteio de ultrapassagem tem sucesso."""

    def uniform01(self) -> float:
        return 0.0

    def standard_normal(self) -> float:
        return 0.0


class PassProbabilityTest(unittest.TestCase):
    def test_no_advantage_means_no_pass(self) -> None:
        # Ninguem passa sem ser mais rapido naquela volta.
        self.assertEqual(pass_probability(0.0, 0.5, parameters()), 0.0)
        self.assertEqual(pass_probability(-500.0, 0.5, parameters()), 0.0)

    def test_probability_grows_with_pace_advantage(self) -> None:
        model = parameters()
        values = [pass_probability(v, 0.5, model) for v in (100, 500, 2000, 8000)]
        self.assertEqual(values, sorted(values))

    def test_saturates_below_one_so_monaco_stays_hard(self) -> None:
        # Mesmo uma vantagem enorme nao garante passagem onde ultrapassar e
        # dificil: o teto e 1 - dificuldade, nunca 1.
        model = parameters()
        huge = pass_probability(1_000_000.0, 0.95, model)
        self.assertLess(huge, 0.06)
        self.assertGreater(huge, 0.0)

    def test_easy_circuit_allows_far_more_passes_than_a_hard_one(self) -> None:
        model = parameters()
        easy = pass_probability(800.0, 0.30, model)
        hard = pass_probability(800.0, 0.95, model)
        self.assertGreater(easy, hard * 5)


class BlockingTest(unittest.TestCase):
    """O fenomeno que faltava: um carro rapido preso atras de um lento."""

    def test_failed_pass_holds_the_faster_car_behind(self) -> None:
        model = parameters()
        # driver:b terminaria 2 s a frente de driver:a, mas a passagem falha.
        outcomes = resolve_disputes(
            [("a", 0.0, 90_000.0), ("b", 500.0, 88_000.0)],
            parameters=model,
            track=track(overtaking_difficulty=1.0),  # passagem impossivel
            rng=FrozenRandomSource(),
        )
        by_id = {o.driver_id: o for o in outcomes}
        self.assertEqual(by_id["b"].blocked_by, "a")
        self.assertGreater(by_id["b"].end_time_ms, by_id["a"].end_time_ms)

    def test_successful_pass_lets_the_faster_car_through(self) -> None:
        outcomes = resolve_disputes(
            [("a", 0.0, 90_000.0), ("b", 500.0, 88_000.0)],
            parameters=parameters(),
            track=track(overtaking_difficulty=0.0),
            rng=AlwaysPass(),
        )
        by_id = {o.driver_id: o for o in outcomes}
        self.assertIsNone(by_id["b"].blocked_by)
        self.assertLess(by_id["b"].end_time_ms, by_id["a"].end_time_ms)

    def test_a_car_in_clear_air_is_never_blocked(self) -> None:
        outcomes = resolve_disputes(
            [("a", 0.0, 90_000.0), ("b", 60_000.0, 150_000.0)],
            parameters=parameters(),
            track=track(),
            rng=FrozenRandomSource(),
        )
        self.assertTrue(all(o.blocked_by is None for o in outcomes))

    def test_blocking_propagates_into_a_queue(self) -> None:
        # Um carro preso segura quem vem atras: e assim que se forma um trem.
        model = parameters()
        outcomes = resolve_disputes(
            [
                ("slow", 0.0, 95_000.0),
                ("fast1", 300.0, 90_000.0),
                ("fast2", 600.0, 90_100.0),
            ],
            parameters=model,
            track=track(overtaking_difficulty=1.0),
            rng=FrozenRandomSource(),
        )
        by_id = {o.driver_id: o for o in outcomes}
        self.assertEqual(by_id["fast1"].blocked_by, "slow")
        self.assertEqual(by_id["fast2"].blocked_by, "fast1")
        # A ordem original sobrevive a volta inteira.
        self.assertLess(by_id["slow"].end_time_ms, by_id["fast1"].end_time_ms)
        self.assertLess(by_id["fast1"].end_time_ms, by_id["fast2"].end_time_ms)


class PhysicalExclusionTest(unittest.TestCase):
    """Dois carros nao podem ocupar o mesmo ponto da pista."""

    def test_minimum_gap_is_enforced_between_every_pair(self) -> None:
        model = parameters(minimum_gap_ms=700.0)
        outcomes = resolve_disputes(
            [(f"d{i}", i * 10.0, 90_000.0 + i) for i in range(8)],
            parameters=model,
            track=track(),
            rng=SeededRandomSource(3),
        )
        times = sorted(o.end_time_ms for o in outcomes)
        for earlier, later in zip(times, times[1:]):
            self.assertGreaterEqual(later - earlier, 700.0 - 1e-6)

    def test_identical_proposed_times_are_separated(self) -> None:
        outcomes = resolve_disputes(
            [("a", 0.0, 90_000.0), ("b", 1.0, 90_000.0), ("c", 2.0, 90_000.0)],
            parameters=parameters(minimum_gap_ms=500.0),
            track=track(),
            rng=SeededRandomSource(1),
        )
        times = sorted(o.end_time_ms for o in outcomes)
        self.assertEqual(len(set(times)), 3)
        self.assertGreaterEqual(times[1] - times[0], 500.0 - 1e-6)

    def test_empty_field_is_handled(self) -> None:
        self.assertEqual(
            resolve_disputes(
                [], parameters=parameters(), track=track(), rng=FrozenRandomSource()
            ),
            (),
        )

    def test_single_car_keeps_its_time(self) -> None:
        outcomes = resolve_disputes(
            [("solo", 0.0, 91_234.0)],
            parameters=parameters(),
            track=track(),
            rng=FrozenRandomSource(),
        )
        self.assertEqual(outcomes[0].end_time_ms, 91_234.0)
        self.assertIsNone(outcomes[0].blocked_by)


class CollisionTest(unittest.TestCase):
    def test_collisions_only_happen_during_a_dispute(self) -> None:
        # Carros em ar livre nunca batem: o contato e endogeno ao trafego.
        model = parameters(collision_probability_per_dispute=0.99)
        outcomes = resolve_disputes(
            [("a", 0.0, 90_000.0), ("b", 60_000.0, 150_000.0)],
            parameters=model,
            track=track(),
            rng=AlwaysPass(),
        )
        self.assertTrue(all(not o.collided for o in outcomes))

    def test_a_dispute_can_end_in_contact(self) -> None:
        model = parameters(collision_probability_per_dispute=0.99)
        outcomes = resolve_disputes(
            [("a", 0.0, 90_000.0), ("b", 200.0, 89_500.0)],
            parameters=model,
            track=track(),
            rng=AlwaysPass(),
        )
        self.assertTrue(any(o.collided for o in outcomes))

    def test_zero_probability_never_produces_contact(self) -> None:
        model = parameters(collision_probability_per_dispute=0.0)
        outcomes = resolve_disputes(
            [("a", 0.0, 90_000.0), ("b", 200.0, 89_500.0)],
            parameters=model,
            track=track(),
            rng=SeededRandomSource(5),
        )
        self.assertTrue(all(not o.collided for o in outcomes))

    def test_mechanical_hazard_excludes_the_contact_share(self) -> None:
        # O contato e modelado nas disputas; conta-lo tambem no risco por volta
        # dobraria o numero de abandonos.
        model = parameters(dnf_hazard_per_lap=0.004, contact_dnf_share=0.25)
        self.assertAlmostEqual(model.mechanical_hazard_per_lap(), 0.003, places=9)


class ReproducibilityTest(unittest.TestCase):
    def test_same_seed_resolves_identically(self) -> None:
        rows = [(f"d{i}", i * 200.0, 90_000.0 + i * 150) for i in range(10)]

        def run():
            return resolve_disputes(
                rows,
                parameters=parameters(),
                track=track(),
                rng=SeededRandomSource(42),
            )

        self.assertEqual(run(), run())

    def test_input_order_does_not_change_the_outcome(self) -> None:
        rows = [(f"d{i}", i * 200.0, 90_000.0 + i * 150) for i in range(10)]
        forward = resolve_disputes(
            rows, parameters=parameters(), track=track(), rng=SeededRandomSource(9)
        )
        backward = resolve_disputes(
            list(reversed(rows)),
            parameters=parameters(),
            track=track(),
            rng=SeededRandomSource(9),
        )
        self.assertEqual(forward, backward)


if __name__ == "__main__":
    unittest.main()
