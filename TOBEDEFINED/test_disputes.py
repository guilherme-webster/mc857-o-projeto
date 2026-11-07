from __future__ import annotations

import unittest

from f1_simulator.domain.disputes import pass_probability, resolve_disputes
from f1_simulator.domain.disputes import (
    DEFAULT_DISPUTE_HEURISTICS,
    DisputeOutcome,
    DisputeProfile,
    pressure_pass_probability,
)
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


class ScriptedRandomSource:
    """Fonte roteirizada que tambem torna os rotulos parte da assercao."""

    def __init__(self, *values: float) -> None:
        self._values = list(values)
        self.labels: list[str] = []

    def uniform01(self, label: str = "") -> float:
        if not self._values:
            raise AssertionError(f"sorteio uniforme inesperado: {label}")
        self.labels.append(label)
        return self._values.pop(0)

    def standard_normal(self, label: str = "") -> float:
        raise AssertionError(f"sorteio normal inesperado: {label}")


class LegacyNeutralityTest(unittest.TestCase):
    def test_defaults_preserve_outcome_and_two_unlabelled_draws(self) -> None:
        rows = [("a", 0.0, 90_000.0), ("b", 500.0, 89_500.0)]
        default_rng = ScriptedRandomSource(0.20, 0.90)
        explicit_rng = ScriptedRandomSource(0.20, 0.90)

        default = resolve_disputes(
            rows,
            parameters=parameters(),
            track=track(),
            rng=default_rng,
        )
        explicit = resolve_disputes(
            rows,
            parameters=parameters(),
            track=track(),
            rng=explicit_rng,
            model="legacy",
            profiles=None,
            heuristics=DEFAULT_DISPUTE_HEURISTICS,
            laps_completed=None,
            overtake_factor=1.0,
            contact_factor=1.0,
        )

        expected = (
            DisputeOutcome(driver_id="a", end_time_ms=90_000.0),
            DisputeOutcome(
                driver_id="b",
                end_time_ms=90_700.0,
                blocked_by="a",
            ),
        )
        self.assertEqual(default, expected)
        self.assertEqual(explicit, expected)
        self.assertEqual(default_rng.labels, ["", ""])
        self.assertEqual(explicit_rng.labels, ["", ""])


class PressureProbabilityTest(unittest.TestCase):
    def test_neutral_calibration_matches_legacy_at_five_hundred_ms(self) -> None:
        model = parameters(overtake_advantage_scale_ms=1_400.0)
        legacy = pass_probability(500.0, 0.5, model)
        pressure = pressure_pass_probability(500.0, 1.0, 0.5, model)

        self.assertAlmostEqual(legacy, 5.0 / 38.0, places=12)
        self.assertAlmostEqual(pressure, legacy, places=12)

    def test_no_advantage_means_no_pressure_or_pass(self) -> None:
        model = parameters()
        self.assertEqual(
            pressure_pass_probability(0.0, 1.0, 0.5, model),
            0.0,
        )
        self.assertEqual(
            pressure_pass_probability(-500.0, 1.0, 0.5, model),
            0.0,
        )

    def test_probability_is_monotonic_in_each_slide_component(self) -> None:
        model = parameters()
        base = pressure_pass_probability(500.0, 0.6, 0.5, model)

        self.assertGreater(
            pressure_pass_probability(700.0, 0.6, 0.5, model),
            base,
        )
        self.assertGreater(
            pressure_pass_probability(500.0, 0.8, 0.5, model),
            base,
        )
        self.assertGreater(
            pressure_pass_probability(
                500.0,
                0.6,
                0.5,
                model,
                attacker_profile=DisputeProfile(aggression=1.2),
            ),
            base,
        )
        self.assertLess(
            pressure_pass_probability(
                500.0,
                0.6,
                0.5,
                model,
                attacker_profile=DisputeProfile(consistency_factor=1.2),
            ),
            base,
        )
        self.assertLess(
            pressure_pass_probability(
                500.0,
                0.6,
                0.5,
                model,
                defender_profile=DisputeProfile(composure=1.2),
            ),
            base,
        )
        self.assertLess(
            pressure_pass_probability(500.0, 0.6, 0.7, model),
            base,
        )

    def test_overtake_factor_multiplies_without_silent_clamp(self) -> None:
        model = parameters()
        base = pressure_pass_probability(500.0, 0.8, 0.5, model)
        reduced = pressure_pass_probability(
            500.0,
            0.8,
            0.5,
            model,
            overtake_factor=0.5,
        )

        self.assertAlmostEqual(reduced, base * 0.5, places=12)
        with self.assertRaisesRegex(ValueError, "overtake_factor"):
            pressure_pass_probability(
                500.0,
                0.8,
                0.5,
                model,
                overtake_factor=10.0,
            )


class PressureResolutionTest(unittest.TestCase):
    def test_scripted_draws_have_exact_order_labels_and_outcome(self) -> None:
        rng = ScriptedRandomSource(0.10, 0.90)
        outcomes = resolve_disputes(
            [("a", 0.0, 90_000.0), ("b", 500.0, 89_500.0)],
            parameters=parameters(
                minimum_gap_ms=0.0,
                collision_probability_per_dispute=0.0,
            ),
            track=track(),
            rng=rng,
            model="pressure",
        )

        self.assertEqual(
            outcomes,
            (
                DisputeOutcome(driver_id="b", end_time_ms=89_500.0),
                DisputeOutcome(driver_id="a", end_time_ms=90_000.0),
            ),
        )
        self.assertEqual(
            rng.labels,
            ["lap-dispute:b:a:pass", "lap-dispute:b:a:contact"],
        )

    def test_frozen_source_blocks_without_contact(self) -> None:
        outcomes = resolve_disputes(
            [("a", 0.0, 90_000.0), ("b", 500.0, 89_500.0)],
            parameters=parameters(),
            track=track(),
            rng=FrozenRandomSource(),
            model="pressure",
        )
        by_id = {outcome.driver_id: outcome for outcome in outcomes}

        self.assertEqual(by_id["b"].end_time_ms, 90_700.0)
        self.assertEqual(by_id["b"].blocked_by, "a")
        self.assertTrue(all(not outcome.collided for outcome in outcomes))

    def test_overtake_factor_changes_the_scripted_decision(self) -> None:
        rows = [("a", 0.0, 90_000.0), ("b", 500.0, 89_500.0)]
        model = parameters(
            minimum_gap_ms=0.0,
            collision_probability_per_dispute=0.0,
        )
        normal = resolve_disputes(
            rows,
            parameters=model,
            track=track(),
            rng=ScriptedRandomSource(0.10, 0.90),
            model="pressure",
        )
        reduced = resolve_disputes(
            rows,
            parameters=model,
            track=track(),
            rng=ScriptedRandomSource(0.10, 0.90),
            model="pressure",
            overtake_factor=0.5,
        )

        normal_by_id = {outcome.driver_id: outcome for outcome in normal}
        reduced_by_id = {outcome.driver_id: outcome for outcome in reduced}
        self.assertIsNone(normal_by_id["b"].blocked_by)
        self.assertEqual(reduced_by_id["b"].blocked_by, "a")


class PressureContactTest(unittest.TestCase):
    def test_contact_retires_exactly_one_of_the_two_cars(self) -> None:
        rows = [("a", 0.0, 90_000.0), ("b", 500.0, 89_500.0)]
        profiles = {
            "a": DisputeProfile(aggression=1.0),
            "b": DisputeProfile(aggression=2.0),
        }

        for retiree_draw, expected_retiree in ((0.49, "b"), (0.50, "a")):
            with self.subTest(expected_retiree=expected_retiree):
                rng = ScriptedRandomSource(0.99, 0.59, retiree_draw)
                outcomes = resolve_disputes(
                    rows,
                    parameters=parameters(
                        minimum_gap_ms=0.0,
                        collision_probability_per_dispute=0.4,
                    ),
                    track=track(),
                    rng=rng,
                    model="pressure",
                    profiles=profiles,
                )
                by_id = {outcome.driver_id: outcome for outcome in outcomes}

                self.assertEqual(
                    [
                        driver_id
                        for driver_id, outcome in by_id.items()
                        if outcome.collided
                    ],
                    [expected_retiree],
                )
                self.assertEqual(by_id["a"].contact_with, "b")
                self.assertEqual(by_id["b"].contact_with, "a")
                self.assertEqual(
                    rng.labels,
                    [
                        "lap-dispute:b:a:pass",
                        "lap-dispute:b:a:contact",
                        "lap-dispute:b:a:contact-retiree",
                    ],
                )

    def test_contact_factor_scales_aggression_weighted_probability(self) -> None:
        rows = [("a", 0.0, 90_000.0), ("b", 500.0, 89_500.0)]
        model = parameters(
            minimum_gap_ms=0.0,
            collision_probability_per_dispute=0.2,
        )
        contact = resolve_disputes(
            rows,
            parameters=model,
            track=track(),
            rng=ScriptedRandomSource(0.99, 0.15, 0.20),
            model="pressure",
        )
        reduced = resolve_disputes(
            rows,
            parameters=model,
            track=track(),
            rng=ScriptedRandomSource(0.99, 0.15),
            model="pressure",
            contact_factor=0.5,
        )

        self.assertEqual(sum(outcome.collided for outcome in contact), 1)
        self.assertEqual(sum(outcome.collided for outcome in reduced), 0)


class BlueFlagTest(unittest.TestCase):
    def test_lapped_car_yields_without_blocking_draw_or_contact(self) -> None:
        rng = ScriptedRandomSource()
        outcomes = resolve_disputes(
            [("leader", 0.0, 90_000.0), ("lapped", 500.0, 89_500.0)],
            parameters=parameters(collision_probability_per_dispute=0.99),
            track=track(),
            rng=rng,
            model="pressure",
            laps_completed={"leader": 10, "lapped": 9},
        )
        by_id = {outcome.driver_id: outcome for outcome in outcomes}

        self.assertEqual(by_id["lapped"].end_time_ms, 90_700.0)
        self.assertIsNone(by_id["lapped"].blocked_by)
        self.assertTrue(all(not outcome.collided for outcome in outcomes))
        self.assertEqual(rng.labels, [])

    def test_lapped_car_yields_and_leader_keeps_its_own_time(self) -> None:
        # O lider nao ganha tempo artificial ao dar volta: quem cede e perde o
        # espaco minimo e o retardatario.
        outcomes = resolve_disputes(
            [("lapped", 0.0, 90_000.0), ("leader", 500.0, 89_900.0)],
            parameters=parameters(minimum_gap_ms=700.0),
            track=track(),
            rng=ScriptedRandomSource(),
            model="legacy",
            laps_completed={"lapped": 9, "leader": 10},
        )
        by_id = {outcome.driver_id: outcome for outcome in outcomes}

        self.assertEqual(by_id["leader"].end_time_ms, 89_900.0)
        self.assertEqual(by_id["lapped"].end_time_ms, 90_600.0)
        self.assertIsNone(by_id["leader"].blocked_by)
        self.assertIsNone(by_id["lapped"].blocked_by)

    def test_leader_close_behind_lapped_car_is_not_held_up(self) -> None:
        # Sem a cessao, a fase B empurraria o lider para 90_700 atras do
        # retardatario -- exatamente o bloqueio que a bandeira azul proibe.
        outcomes = resolve_disputes(
            [("lapped", 0.0, 90_000.0), ("leader", 500.0, 90_300.0)],
            parameters=parameters(minimum_gap_ms=700.0),
            track=track(),
            rng=ScriptedRandomSource(),
            model="pressure",
            laps_completed={"lapped": 9, "leader": 10},
        )
        by_id = {outcome.driver_id: outcome for outcome in outcomes}

        self.assertEqual(by_id["leader"].end_time_ms, 90_300.0)
        self.assertEqual(by_id["lapped"].end_time_ms, 91_000.0)
        self.assertIsNone(by_id["leader"].blocked_by)

    def test_car_behind_a_yielding_pair_disputes_with_the_lapped_car(self) -> None:
        # Depois da cessao, o carro seguinte encontra o retardatario (o mais
        # atrasado do par) e nao o lider.
        outcomes = resolve_disputes(
            [
                ("lapped", 0.0, 90_000.0),
                ("leader", 500.0, 89_900.0),
                ("third", 900.0, 90_650.0),
            ],
            parameters=parameters(minimum_gap_ms=700.0),
            track=track(),
            rng=ScriptedRandomSource(0.99, 0.99),
            model="legacy",
            laps_completed={"lapped": 9, "leader": 10, "third": 9},
        )
        by_id = {outcome.driver_id: outcome for outcome in outcomes}

        self.assertEqual(by_id["third"].blocked_by, "lapped")
        self.assertEqual(by_id["third"].end_time_ms, 91_300.0)


class PressureReproducibilityTest(unittest.TestCase):
    def test_same_seed_reproduces_pressure_contacts_and_retirees(self) -> None:
        rows = [(f"d{i}", i * 200.0, 90_000.0 + i * 150.0) for i in range(10)]
        profiles = {
            driver_id: DisputeProfile(
                aggression=1.0 + index / 20.0,
                composure=1.0 + index / 30.0,
            )
            for index, (driver_id, _start, _end) in enumerate(rows)
        }

        def run():
            return resolve_disputes(
                rows,
                parameters=parameters(collision_probability_per_dispute=0.2),
                track=track(),
                rng=SeededRandomSource(42),
                model="pressure",
                profiles=profiles,
            )

        self.assertEqual(run(), run())


if __name__ == "__main__":
    unittest.main()
