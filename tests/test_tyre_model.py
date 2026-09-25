from __future__ import annotations

import math
import unittest
from dataclasses import FrozenInstanceError

from f1_simulator.domain import tyres
from f1_simulator.domain.tyres import (
    ASSUMED_DRY_TYRES,
    TyreModelParameters,
    TyreState,
    tyre_effect_ms,
    tyre_parameters_for,
)


def parameters(**changes: object) -> TyreModelParameters:
    values = {
        "compound": "SOFT",
        "source_kind": "assumed",
        "parameter_version": "test-v1",
        "anchor_age_laps": 2,
        "min_age_laps": 0,
        "max_age_laps": 5,
        "linear_ms_per_lap": 30.0,
        "rationale": "Hipotese explicita para o teste.",
    }
    values.update(changes)
    return TyreModelParameters(**values)  # type: ignore[arg-type]


class TyreEffectTest(unittest.TestCase):
    def test_effect_is_exactly_zero_at_anchor(self) -> None:
        model = parameters(anchor_age_laps=3, max_age_laps=6)

        effect_ms = tyre_effect_ms(model, TyreState("SOFT", 3))

        self.assertEqual(effect_ms, 0.0)
        self.assertIs(type(effect_ms), float)

    def test_effect_is_linear_around_anchor(self) -> None:
        model = parameters()

        self.assertEqual(tyre_effect_ms(model, TyreState("SOFT", 1)), -30.0)
        self.assertEqual(tyre_effect_ms(model, TyreState("SOFT", 4)), 60.0)
        self.assertEqual(tyre_effect_ms(model, TyreState("SOFT", 5)), 90.0)

    def test_rejects_age_below_or_above_support(self) -> None:
        model = parameters(min_age_laps=1)

        with self.assertRaises(ValueError):
            tyre_effect_ms(model, TyreState("SOFT", 0))
        with self.assertRaises(ValueError):
            tyre_effect_ms(model, TyreState("SOFT", 6))

    def test_rejects_compound_different_from_parameters(self) -> None:
        with self.assertRaises(ValueError):
            tyre_effect_ms(parameters(), TyreState("MEDIUM", 2))

    def test_accepts_zero_slope(self) -> None:
        model = parameters(linear_ms_per_lap=0.0)

        self.assertEqual(tyre_effect_ms(model, TyreState("SOFT", 5)), 0.0)

    def test_preserves_negative_slope(self) -> None:
        model = parameters(linear_ms_per_lap=-7.5)

        self.assertEqual(tyre_effect_ms(model, TyreState("SOFT", 4)), -15.0)


class TyreParametersValidationTest(unittest.TestCase):
    def test_rejects_empty_string_fields(self) -> None:
        for field_name in (
            "compound",
            "source_kind",
            "parameter_version",
            "rationale",
        ):
            with self.subTest(field=field_name):
                with self.assertRaises(ValueError):
                    parameters(**{field_name: "   "})

    def test_rejects_unknown_source_kind(self) -> None:
        with self.assertRaises(ValueError):
            parameters(source_kind="measured")

    def test_rejects_compound_outside_dry_scope(self) -> None:
        with self.assertRaises(ValueError):
            parameters(compound="WET")

    def test_rejects_bool_for_every_integer_age(self) -> None:
        for field_name in (
            "anchor_age_laps",
            "min_age_laps",
            "max_age_laps",
        ):
            with self.subTest(field=field_name):
                with self.assertRaises(ValueError):
                    parameters(**{field_name: True})

    def test_rejects_bool_nan_and_infinity_for_slope(self) -> None:
        for invalid in (True, math.nan, math.inf, -math.inf):
            with self.subTest(value=invalid):
                with self.assertRaises(ValueError):
                    parameters(linear_ms_per_lap=invalid)

    def test_rejects_negative_minimum_age(self) -> None:
        with self.assertRaises(ValueError):
            parameters(min_age_laps=-1)

    def test_rejects_anchor_outside_support_and_inverted_support(self) -> None:
        invalid_ranges = (
            {"anchor_age_laps": 6},
            {"anchor_age_laps": -1},
            {"min_age_laps": 4, "max_age_laps": 3},
        )
        for invalid_range in invalid_ranges:
            with self.subTest(values=invalid_range):
                with self.assertRaises(ValueError):
                    parameters(**invalid_range)

    def test_parameters_are_frozen_and_slotted(self) -> None:
        model = parameters()

        with self.assertRaises(FrozenInstanceError):
            model.compound = "HARD"  # type: ignore[misc]
        self.assertFalse(hasattr(model, "__dict__"))


class TyreStateValidationTest(unittest.TestCase):
    def test_first_lap_uses_age_zero(self) -> None:
        state = TyreState("SOFT", 0)

        self.assertEqual(state.age_laps_before_lap, 0)
        self.assertIn("TyreLife", TyreState.__doc__ or "")

    def test_rejects_invalid_compound_bool_and_negative_age(self) -> None:
        invalid_states = (
            ("", 0),
            ("INTERMEDIATE", 0),
            ("SOFT", True),
            ("SOFT", -1),
        )
        for compound, age in invalid_states:
            with self.subTest(compound=compound, age=age):
                with self.assertRaises(ValueError):
                    TyreState(compound, age)  # type: ignore[arg-type]

    def test_state_is_frozen_and_slotted(self) -> None:
        state = TyreState("SOFT", 0)

        with self.assertRaises(FrozenInstanceError):
            state.age_laps_before_lap = 1  # type: ignore[misc]
        self.assertFalse(hasattr(state, "__dict__"))


class TyreCatalogueTest(unittest.TestCase):
    def test_returns_parameters_for_present_compound(self) -> None:
        self.assertEqual(tyre_parameters_for("MEDIUM").compound, "MEDIUM")

    def test_rejects_compound_absent_from_catalogue(self) -> None:
        with self.assertRaises(ValueError):
            tyre_parameters_for("INTERMEDIATE")

    def test_assumed_compounds_follow_expected_slope_order(self) -> None:
        effects = {
            compound: tyre_effect_ms(
                tyre_parameters_for(compound),
                TyreState(compound, 1),
            )
            for compound in ("SOFT", "MEDIUM", "HARD")
        }

        self.assertGreater(effects["SOFT"], effects["MEDIUM"])
        self.assertGreater(effects["MEDIUM"], effects["HARD"])
        self.assertEqual(effects, {"SOFT": 30.0, "MEDIUM": 20.0, "HARD": 6.0})

    def test_default_catalogue_declares_assumed_non_calibrated_hypotheses(self) -> None:
        self.assertIs(type(ASSUMED_DRY_TYRES), tuple)
        self.assertIn("hipoteses assumidas", (tyres.__doc__ or "").lower())
        for model in ASSUMED_DRY_TYRES:
            with self.subTest(compound=model.compound):
                self.assertEqual(model.source_kind, "assumed")
                self.assertTrue(model.rationale.strip())
                self.assertIn("nunca foi calibrado", model.rationale.lower())
                self.assertEqual(model.anchor_age_laps, 0)
                self.assertEqual(model.min_age_laps, 0)
                self.assertEqual(model.max_age_laps, 80)


if __name__ == "__main__":
    unittest.main()
