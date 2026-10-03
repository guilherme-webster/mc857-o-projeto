from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, replace

from f1_simulator.domain.model_parameters import CompoundParameters
from f1_simulator.domain.strategy import (
    DEFAULT_HEURISTIC_PIT_PARAMETERS,
    HeuristicPitParameters,
    HeuristicPitStrategy,
    NoStopStrategy,
    PlannedStopStrategy,
    StrategyState,
    TyreLifeStrategy,
)
from f1_simulator.domain.tyres import TyreSet, tyre_penalty_ms
from tests.model_support import parameters, track


def tyre_parameters():
    """Modelo pequeno com contas inteiras para tornar os limiares auditaveis."""

    return parameters(
        compounds=(
            CompoundParameters("SOFT", 0.0, 0.0, 0.0, 5),
            CompoundParameters("MEDIUM", 0.0, 100.0, 0.0, 10),
            CompoundParameters("HARD", 200.0, 20.0, 0.0, 30),
        ),
        reference_compound="MEDIUM",
    )


def heuristics(**overrides) -> HeuristicPitParameters:
    """Altere uma hipotese sem omitir sua origem, versao ou justificativa."""

    return replace(DEFAULT_HEURISTIC_PIT_PARAMETERS, **overrides)


def state(
    *,
    lap_number: int,
    total_laps: int,
    age_laps: int,
    neutralization: str | None = None,
    pit_loss_factor: float = 1.0,
    compounds_used: tuple[str, ...] = ("MEDIUM",),
    free_tyre_change: bool = False,
) -> StrategyState:
    return StrategyState(
        lap_number=lap_number,
        total_laps=total_laps,
        tyre=TyreSet("MEDIUM", age_laps),
        stops_made=0,
        neutralization=neutralization,
        pit_loss_factor=pit_loss_factor,
        compounds_used=compounds_used,
        free_tyre_change=free_tyre_change,
    )


class EconomicRuleTest(unittest.TestCase):
    def test_pits_only_when_known_saving_exceeds_margin(self) -> None:
        model = tyre_parameters()
        circuit = track(pit_loss_ms=500.0, tyre_severity=1.0)
        race_state = state(lap_number=1, total_laps=5, age_laps=4)
        medium = model.compound("MEDIUM")
        soft = model.compound("SOFT")

        # Continuar: 400 + 500 + 600 + 700 + 800 = 3.000 ms.
        continue_cost_ms = sum(
            tyre_penalty_ms(TyreSet("MEDIUM", age), medium, circuit)
            for age in range(4, 9)
        )
        # Parar: volta de entrada (400), boxes (500) e quatro voltas de SOFT
        # sem degradacao neste fixture = 900 ms. Economia exata: 2.100 ms.
        stop_cost_ms = (
            tyre_penalty_ms(TyreSet("MEDIUM", 4), medium, circuit)
            + circuit.pit_loss_ms
            + sum(
                tyre_penalty_ms(TyreSet("SOFT", age), soft, circuit)
                for age in range(4)
            )
        )
        self.assertEqual(continue_cost_ms, 3_000.0)
        self.assertEqual(stop_cost_ms, 900.0)

        below_saving = HeuristicPitStrategy(
            model,
            circuit,
            heuristics(decision_margin_ms=2_099.0),
        )
        equal_to_saving = HeuristicPitStrategy(
            model,
            circuit,
            heuristics(decision_margin_ms=2_100.0),
        )

        self.assertEqual(below_saving.decide(race_state).compound, "SOFT")
        self.assertFalse(equal_to_saving.decide(race_state).pit)

    def test_tyre_management_factor_anticipates_or_delays_stop(self) -> None:
        model = tyre_parameters()
        circuit = track(pit_loss_ms=500.0)
        assumptions = heuristics(decision_margin_ms=700.0)
        race_state = state(lap_number=1, total_laps=5, age_laps=0)

        preserves_tyres = HeuristicPitStrategy(
            model,
            circuit,
            assumptions,
            tyre_management_factor=0.5,
        )
        neutral = HeuristicPitStrategy(model, circuit, assumptions)
        wears_tyres = HeuristicPitStrategy(
            model,
            circuit,
            assumptions,
            tyre_management_factor=2.0,
        )

        self.assertFalse(preserves_tyres.decide(race_state).pit)
        self.assertFalse(neutral.decide(race_state).pit)
        self.assertTrue(wears_tyres.decide(race_state).pit)


class SpecialOpportunityTest(unittest.TestCase):
    def test_low_remaining_life_pits_under_neutralization_not_green(self) -> None:
        model = tyre_parameters()
        circuit = track(pit_loss_ms=20_000.0)
        assumptions = heuristics(decision_margin_ms=100_000.0)
        strategy = HeuristicPitStrategy(model, circuit, assumptions)

        green = state(lap_number=5, total_laps=20, age_laps=8)
        self.assertFalse(strategy.decide(green).pit)

        for neutralization, factor in (("SC", 0.5), ("VSC", 0.7)):
            with self.subTest(neutralization=neutralization):
                neutralized = state(
                    lap_number=5,
                    total_laps=20,
                    age_laps=8,
                    neutralization=neutralization,
                    pit_loss_factor=factor,
                )
                self.assertTrue(strategy.decide(neutralized).pit)

    def test_free_tyre_change_ignores_pit_loss_when_useful(self) -> None:
        model = tyre_parameters()
        circuit = track(pit_loss_ms=20_000.0)
        strategy = HeuristicPitStrategy(
            model,
            circuit,
            heuristics(decision_margin_ms=0.0),
        )
        common = dict(lap_number=10, total_laps=20, age_laps=8)

        self.assertFalse(strategy.decide(state(**common)).pit)
        free = strategy.decide(state(**common, free_tyre_change=True))
        self.assertTrue(free.pit)
        self.assertEqual(free.compound, "HARD")


class RaceRuleTest(unittest.TestCase):
    def test_blocks_final_laps_except_extreme_overlife(self) -> None:
        model = tyre_parameters()
        strategy = HeuristicPitStrategy(
            model,
            track(pit_loss_ms=500.0),
            heuristics(decision_margin_ms=0.0, final_laps_without_pit=3),
        )

        self.assertFalse(
            strategy.decide(
                state(
                    lap_number=18,
                    total_laps=20,
                    age_laps=9,
                    compounds_used=("MEDIUM", "SOFT"),
                )
            ).pit
        )
        self.assertTrue(
            strategy.decide(
                state(
                    lap_number=18,
                    total_laps=20,
                    age_laps=14,
                    compounds_used=("MEDIUM", "SOFT"),
                )
            ).pit
        )
        self.assertFalse(
            strategy.decide(
                state(lap_number=20, total_laps=20, age_laps=30)
            ).pit
        )

    def test_forces_second_compound_before_final_no_pit_window(self) -> None:
        model = tyre_parameters()
        strategy = HeuristicPitStrategy(
            model,
            track(pit_loss_ms=20_000.0),
            heuristics(
                decision_margin_ms=1_000_000.0,
                final_laps_without_pit=3,
            ),
        )

        forced = strategy.decide(
            state(
                lap_number=17,
                total_laps=20,
                age_laps=0,
                compounds_used=(),
            )
        )
        self.assertTrue(forced.pit)
        self.assertEqual(forced.compound, "SOFT")
        self.assertFalse(
            strategy.decide(
                state(
                    lap_number=17,
                    total_laps=20,
                    age_laps=0,
                    compounds_used=("MEDIUM", "SOFT"),
                )
            ).pit
        )

    def test_selects_hard_for_long_horizon_and_soft_for_sprint(self) -> None:
        model = tyre_parameters()
        strategy = HeuristicPitStrategy(
            model,
            track(pit_loss_ms=20_000.0),
            heuristics(decision_margin_ms=0.0),
        )

        long_horizon = strategy.decide(
            state(
                lap_number=5,
                total_laps=30,
                age_laps=8,
                free_tyre_change=True,
            )
        )
        sprint = strategy.decide(
            state(
                lap_number=26,
                total_laps=30,
                age_laps=8,
                free_tyre_change=True,
            )
        )
        self.assertEqual(long_horizon.compound, "HARD")
        self.assertEqual(sprint.compound, "SOFT")


class VariationAndCompatibilityTest(unittest.TestCase):
    def test_heuristic_parameters_are_frozen_slotted_and_traceable(self) -> None:
        assumptions = DEFAULT_HEURISTIC_PIT_PARAMETERS

        self.assertEqual(assumptions.origin, "heuristic")
        self.assertEqual(assumptions.parameter_version, "heuristic-pit-v1")
        self.assertTrue(assumptions.rationale)
        self.assertFalse(hasattr(assumptions, "__dict__"))
        with self.assertRaises(FrozenInstanceError):
            setattr(assumptions, "decision_margin_ms", 0.0)

    def test_offset_is_deterministic_and_moves_decision_window(self) -> None:
        model = tyre_parameters()
        circuit = track(pit_loss_ms=500.0)
        assumptions = heuristics(
            decision_margin_ms=700.0,
            driver_variation_amplitude_laps=1,
        )

        neutral = HeuristicPitStrategy(model, circuit, assumptions)
        anticipates = HeuristicPitStrategy(
            model, circuit, assumptions, offset_laps=-1
        )
        delays = HeuristicPitStrategy(
            model, circuit, assumptions, offset_laps=1
        )

        young = state(lap_number=1, total_laps=5, age_laps=0)
        older = state(lap_number=1, total_laps=5, age_laps=1)
        self.assertFalse(neutral.decide(young).pit)
        self.assertTrue(anticipates.decide(young).pit)
        self.assertTrue(neutral.decide(older).pit)
        self.assertFalse(delays.decide(older).pit)
        self.assertEqual(anticipates.decide(young), anticipates.decide(young))

    def test_offset_must_fit_declared_draw_amplitude(self) -> None:
        with self.assertRaises(ValueError):
            HeuristicPitStrategy(
                tyre_parameters(),
                track(),
                heuristics(driver_variation_amplitude_laps=1),
                offset_laps=2,
            )

    def test_existing_strategies_keep_their_decisions(self) -> None:
        model = tyre_parameters()
        young = state(lap_number=10, total_laps=40, age_laps=5)
        planned_lap = state(lap_number=20, total_laps=40, age_laps=20)
        old = state(lap_number=30, total_laps=40, age_laps=10)

        self.assertFalse(NoStopStrategy().decide(old).pit)
        planned = PlannedStopStrategy(1, ("HARD",))
        self.assertFalse(planned.decide(young).pit)
        self.assertEqual(planned.decide(planned_lap).compound, "HARD")
        tyre_life = TyreLifeStrategy(model, "HARD")
        self.assertFalse(tyre_life.decide(young).pit)
        self.assertTrue(tyre_life.decide(old).pit)


if __name__ == "__main__":
    unittest.main()
