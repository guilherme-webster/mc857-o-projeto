"""Testes do pneu assumido e do ruido com semente em ``simulate_race``.

Os literais ``GOLDEN_*`` foram gerados com o codigo ANTERIOR a esta fatia (o
``simulate_race`` sem parametros opcionais). Eles provam que o modo padrao nao
mudou nem um byte; nao devem ser regenerados com o codigo novo.
"""

from __future__ import annotations

import json
import math
import unittest

from f1_simulator.domain.race_simulation import (
    ASSUMED_LAP_VARIABILITY,
    Competitor,
    LapTimeBreakdown,
    LapVariabilityAssumption,
    simulate_race,
)
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.tyres import TyreModelParameters

GOLDEN_A = '{"classification":[{"driver_id":"driver:1","lap_time_ms":90000.0,"name":"Alice","position":1,"total_time_ms":450000.0},{"driver_id":"driver:2","lap_time_ms":90250.25,"name":"Bob","position":2,"total_time_ms":451251.2},{"driver_id":"driver:3","lap_time_ms":90500.5,"name":"Carol","position":3,"total_time_ms":452502.5}],"history":[{"cars":[{"driver_id":"driver:1","lap_time_ms":90000.0,"name":"Alice","position":1,"total_time_ms":90000.0},{"driver_id":"driver:2","lap_time_ms":90250.25,"name":"Bob","position":2,"total_time_ms":90250.2},{"driver_id":"driver:3","lap_time_ms":90500.5,"name":"Carol","position":3,"total_time_ms":90500.5}],"lap":1},{"cars":[{"driver_id":"driver:1","lap_time_ms":90000.0,"name":"Alice","position":1,"total_time_ms":180000.0},{"driver_id":"driver:2","lap_time_ms":90250.25,"name":"Bob","position":2,"total_time_ms":180500.5},{"driver_id":"driver:3","lap_time_ms":90500.5,"name":"Carol","position":3,"total_time_ms":181001.0}],"lap":2},{"cars":[{"driver_id":"driver:1","lap_time_ms":90000.0,"name":"Alice","position":1,"total_time_ms":270000.0},{"driver_id":"driver:2","lap_time_ms":90250.25,"name":"Bob","position":2,"total_time_ms":270750.8},{"driver_id":"driver:3","lap_time_ms":90500.5,"name":"Carol","position":3,"total_time_ms":271501.5}],"lap":3},{"cars":[{"driver_id":"driver:1","lap_time_ms":90000.0,"name":"Alice","position":1,"total_time_ms":360000.0},{"driver_id":"driver:2","lap_time_ms":90250.25,"name":"Bob","position":2,"total_time_ms":361001.0},{"driver_id":"driver:3","lap_time_ms":90500.5,"name":"Carol","position":3,"total_time_ms":362002.0}],"lap":4},{"cars":[{"driver_id":"driver:1","lap_time_ms":90000.0,"name":"Alice","position":1,"total_time_ms":450000.0},{"driver_id":"driver:2","lap_time_ms":90250.25,"name":"Bob","position":2,"total_time_ms":451251.2},{"driver_id":"driver:3","lap_time_ms":90500.5,"name":"Carol","position":3,"total_time_ms":452502.5}],"lap":5}],"total_laps":5}'
GOLDEN_B = '{"classification":[{"driver_id":"driver:7","lap_time_ms":90999.9,"name":"Eve","position":1,"total_time_ms":272999.7},{"driver_id":"driver:4","lap_time_ms":91000.0,"name":"Dan","position":2,"total_time_ms":273000.0},{"driver_id":"driver:9","lap_time_ms":91000.0,"name":"Zed","position":3,"total_time_ms":273000.0}],"history":[{"cars":[{"driver_id":"driver:7","lap_time_ms":90999.9,"name":"Eve","position":1,"total_time_ms":90999.9},{"driver_id":"driver:4","lap_time_ms":91000.0,"name":"Dan","position":2,"total_time_ms":91000.0},{"driver_id":"driver:9","lap_time_ms":91000.0,"name":"Zed","position":3,"total_time_ms":91000.0}],"lap":1},{"cars":[{"driver_id":"driver:7","lap_time_ms":90999.9,"name":"Eve","position":1,"total_time_ms":181999.8},{"driver_id":"driver:4","lap_time_ms":91000.0,"name":"Dan","position":2,"total_time_ms":182000.0},{"driver_id":"driver:9","lap_time_ms":91000.0,"name":"Zed","position":3,"total_time_ms":182000.0}],"lap":2},{"cars":[{"driver_id":"driver:7","lap_time_ms":90999.9,"name":"Eve","position":1,"total_time_ms":272999.7},{"driver_id":"driver:4","lap_time_ms":91000.0,"name":"Dan","position":2,"total_time_ms":273000.0},{"driver_id":"driver:9","lap_time_ms":91000.0,"name":"Zed","position":3,"total_time_ms":273000.0}],"lap":3}],"total_laps":3}'


def _dump(result: dict) -> str:
    return json.dumps(result, sort_keys=True, separators=(",", ":"))


def _field_a() -> list[Competitor]:
    return [
        Competitor("driver:3", "Carol", 90500.5),
        Competitor("driver:1", "Alice", 90000.0),
        Competitor("driver:2", "Bob", 90250.25),
    ]


def _field_b() -> list[Competitor]:
    return [
        Competitor("driver:9", "Zed", 91000.0),
        Competitor("driver:4", "Dan", 91000.0),
        Competitor("driver:7", "Eve", 90999.9),
    ]


class ScriptedRandomSource:
    """Fonte falsa: devolve valores conhecidos e registra as labels pedidas."""

    def __init__(self, values: list[float]) -> None:
        self._values = list(values)
        self.labels: list[str] = []

    def standard_normal(self, label: str) -> float:
        self.labels.append(label)
        return self._values.pop(0)


def _car(result: dict, lap: int, driver_id: str) -> dict:
    return next(
        car
        for car in result["history"][lap - 1]["cars"]
        if car["driver_id"] == driver_id
    )


class DefaultModeIsUnchangedTest(unittest.TestCase):
    def test_scenario_a_is_byte_identical_to_the_previous_engine(self) -> None:
        result = simulate_race(_field_a(), 5)

        self.assertEqual(_dump(result), GOLDEN_A)
        self.assertEqual(result, json.loads(GOLDEN_A))

    def test_scenario_b_with_exact_tie_is_byte_identical(self) -> None:
        result = simulate_race(_field_b(), 3)

        self.assertEqual(_dump(result), GOLDEN_B)
        self.assertEqual(result, json.loads(GOLDEN_B))

    def test_default_output_has_no_model_keys(self) -> None:
        result = simulate_race(_field_a(), 2)

        self.assertNotIn("assumptions", result)
        for lap in result["history"]:
            for car in lap["cars"]:
                self.assertNotIn("breakdown", car)

    def test_explicit_none_arguments_behave_like_the_default(self) -> None:
        result = simulate_race(
            _field_a(), 5, tyre_plan=None, variability=None, rng=None
        )

        self.assertEqual(_dump(result), GOLDEN_A)


class TyreModelTest(unittest.TestCase):
    def test_soft_effect_grows_by_the_slope_each_lap(self) -> None:
        result = simulate_race(
            [Competitor("driver:1", "A", 90000.0)],
            4,
            tyre_plan={"driver:1": "SOFT"},
        )

        effects = [
            _car(result, lap, "driver:1")["breakdown"]["tyre_effect_ms"]
            for lap in range(1, 5)
        ]
        lap_times = [
            _car(result, lap, "driver:1")["lap_time_ms"] for lap in range(1, 5)
        ]
        self.assertEqual(effects, [0.0, 30.0, 60.0, 90.0])
        self.assertEqual(lap_times, [90000.0, 90030.0, 90060.0, 90090.0])

    def test_each_compound_uses_its_own_assumed_slope(self) -> None:
        field = [
            Competitor("driver:1", "A", 90000.0),
            Competitor("driver:2", "B", 90000.0),
            Competitor("driver:3", "C", 90000.0),
        ]
        result = simulate_race(
            field,
            3,
            tyre_plan={
                "driver:1": "SOFT",
                "driver:2": "MEDIUM",
                "driver:3": "HARD",
            },
        )

        effects = {
            driver: _car(result, 3, driver)["breakdown"]["tyre_effect_ms"]
            for driver in ("driver:1", "driver:2", "driver:3")
        }
        # Idade 2 na terceira volta: 2 * (30, 20, 6).
        self.assertEqual(
            effects, {"driver:1": 60.0, "driver:2": 40.0, "driver:3": 12.0}
        )

    def test_tyre_only_run_is_deterministic_and_needs_no_rng(self) -> None:
        plan = {"driver:1": "SOFT", "driver:2": "MEDIUM", "driver:3": "HARD"}

        first = simulate_race(_field_a(), 5, tyre_plan=plan)
        second = simulate_race(_field_a(), 5, tyre_plan=plan)

        self.assertEqual(_dump(first), _dump(second))

    def test_noise_is_not_modelled_and_stays_none_with_tyre_only(self) -> None:
        result = simulate_race(
            [Competitor("driver:1", "A", 90000.0)],
            2,
            tyre_plan={"driver:1": "HARD"},
        )

        self.assertIsNone(_car(result, 1, "driver:1")["breakdown"]["noise_ms"])

    def test_total_time_is_the_sum_of_the_real_lap_times(self) -> None:
        result = simulate_race(
            [Competitor("driver:1", "A", 90000.0)],
            4,
            tyre_plan={"driver:1": "MEDIUM"},
        )

        # 90000*4 + 20*(0+1+2+3)
        self.assertEqual(result["classification"][0]["total_time_ms"], 360120.0)

    def test_slower_tyre_changes_the_order_over_a_long_race(self) -> None:
        # O SOFT e mais rapido de referencia, mas degrada 30 ms/volta contra 6 do
        # HARD; em 70 voltas a diferenca acumulada inverte a ordem.
        field = [
            Competitor("driver:1", "Soft", 90000.0),
            Competitor("driver:2", "Hard", 90500.0),
        ]
        result = simulate_race(
            field, 70, tyre_plan={"driver:1": "SOFT", "driver:2": "HARD"}
        )

        self.assertEqual(result["history"][0]["cars"][0]["driver_id"], "driver:1")
        self.assertEqual(result["classification"][0]["driver_id"], "driver:2")

    def test_incomplete_tyre_plan_raises(self) -> None:
        with self.assertRaises(ValueError):
            simulate_race(_field_a(), 3, tyre_plan={"driver:1": "SOFT"})

    def test_unknown_driver_in_tyre_plan_raises(self) -> None:
        plan = {
            "driver:1": "SOFT",
            "driver:2": "SOFT",
            "driver:3": "SOFT",
            "driver:99": "SOFT",
        }
        with self.assertRaises(ValueError):
            simulate_race(_field_a(), 3, tyre_plan=plan)

    def test_compound_outside_the_catalogue_raises(self) -> None:
        plan = {"driver:1": "SOFT", "driver:2": "SOFT", "driver:3": "WET"}
        with self.assertRaises(ValueError):
            simulate_race(_field_a(), 3, tyre_plan=plan)

    def test_race_longer_than_tyre_support_raises_but_the_limit_is_accepted(
        self,
    ) -> None:
        field = [Competitor("driver:1", "A", 90000.0)]
        plan = {"driver:1": "HARD"}

        ok = simulate_race(field, 81, tyre_plan=plan)  # idade maxima 80
        self.assertEqual(ok["total_laps"], 81)
        with self.assertRaises(ValueError):
            simulate_race(field, 82, tyre_plan=plan)  # idade 81 > 80

    def test_custom_catalogue_can_be_injected(self) -> None:
        catalogue = (
            TyreModelParameters(
                compound="SOFT",
                source_kind="assumed",
                parameter_version="teste-v1",
                anchor_age_laps=0,
                min_age_laps=0,
                max_age_laps=10,
                linear_ms_per_lap=100.0,
                rationale="Valor de teste.",
            ),
        )
        result = simulate_race(
            [Competitor("driver:1", "A", 90000.0)],
            3,
            tyre_plan={"driver:1": "SOFT"},
            tyre_catalogue=catalogue,
        )

        self.assertEqual(
            _car(result, 3, "driver:1")["breakdown"]["tyre_effect_ms"], 200.0
        )

    def test_non_positive_lap_time_raises_instead_of_being_clamped(self) -> None:
        catalogue = (
            TyreModelParameters(
                compound="SOFT",
                source_kind="assumed",
                parameter_version="teste-v1",
                anchor_age_laps=0,
                min_age_laps=0,
                max_age_laps=10,
                linear_ms_per_lap=-1000.0,
                rationale="Inclinacao negativa de teste.",
            ),
        )
        with self.assertRaises(ValueError):
            simulate_race(
                [Competitor("driver:1", "A", 1500.0)],
                3,  # volta 3: 1500 - 2000 < 0
                tyre_plan={"driver:1": "SOFT"},
                tyre_catalogue=catalogue,
            )

    def test_assumptions_list_the_used_compounds_sorted(self) -> None:
        result = simulate_race(
            _field_a(),
            2,
            tyre_plan={
                "driver:1": "SOFT",
                "driver:2": "HARD",
                "driver:3": "HARD",
            },
        )

        kinds = [(a["kind"], a.get("compound")) for a in result["assumptions"]]
        self.assertEqual(kinds, [("tyre", "HARD"), ("tyre", "SOFT")])
        for item in result["assumptions"]:
            self.assertEqual(item["source_kind"], "assumed")
            self.assertTrue(item["rationale"])
            self.assertIn("linear_ms_per_lap", item)


class VariabilityTest(unittest.TestCase):
    def test_variability_without_rng_raises(self) -> None:
        with self.assertRaises(ValueError):
            simulate_race(_field_a(), 3, variability=ASSUMED_LAP_VARIABILITY)

    def test_rng_without_variability_raises(self) -> None:
        with self.assertRaises(ValueError):
            simulate_race(_field_a(), 3, rng=SeededRandomSource(1))

    def test_noise_uses_the_injected_source_in_canonical_order(self) -> None:
        source = ScriptedRandomSource([1.0, -1.0, 0.5, 2.0])
        field = [
            Competitor("driver:2", "B", 100000.0),
            Competitor("driver:1", "A", 90000.0),
        ]

        result = simulate_race(
            field, 2, variability=ASSUMED_LAP_VARIABILITY, rng=source
        )

        # Voltas crescentes; dentro da volta, driver_id crescente,
        # independentemente da ordem de entrada.
        self.assertEqual(
            source.labels,
            [
                "lap:1:driver:1",
                "lap:1:driver:2",
                "lap:2:driver:1",
                "lap:2:driver:2",
            ],
        )
        # ruido = 0,2/100 * referencia * z
        expected = {
            (1, "driver:1"): 0.002 * 90000.0 * 1.0,
            (1, "driver:2"): 0.002 * 100000.0 * -1.0,
            (2, "driver:1"): 0.002 * 90000.0 * 0.5,
            (2, "driver:2"): 0.002 * 100000.0 * 2.0,
        }
        for (lap, driver), noise in expected.items():
            self.assertAlmostEqual(
                _car(result, lap, driver)["breakdown"]["noise_ms"], noise
            )

    def test_rejected_draw_repeats_the_same_label_and_uses_the_next(self) -> None:
        source = ScriptedRandomSource([5.0, 1.0])  # 5.0 excede 3 sigmas

        result = simulate_race(
            [Competitor("driver:1", "A", 90000.0)],
            1,
            variability=ASSUMED_LAP_VARIABILITY,
            rng=source,
        )

        self.assertEqual(source.labels, ["lap:1:driver:1", "lap:1:driver:1"])
        self.assertAlmostEqual(
            _car(result, 1, "driver:1")["breakdown"]["noise_ms"], 180.0
        )

    def test_same_seed_reproduces_the_whole_result(self) -> None:
        plan = {"driver:1": "SOFT", "driver:2": "MEDIUM", "driver:3": "HARD"}

        first = simulate_race(
            _field_a(),
            10,
            tyre_plan=plan,
            variability=ASSUMED_LAP_VARIABILITY,
            rng=SeededRandomSource(2026),
        )
        second = simulate_race(
            _field_a(),
            10,
            tyre_plan=plan,
            variability=ASSUMED_LAP_VARIABILITY,
            rng=SeededRandomSource(2026),
        )

        self.assertEqual(_dump(first), _dump(second))

    def test_different_seeds_change_the_result(self) -> None:
        first = simulate_race(
            _field_a(),
            10,
            variability=ASSUMED_LAP_VARIABILITY,
            rng=SeededRandomSource(1),
        )
        second = simulate_race(
            _field_a(),
            10,
            variability=ASSUMED_LAP_VARIABILITY,
            rng=SeededRandomSource(2),
        )

        self.assertNotEqual(_dump(first), _dump(second))

    def test_result_is_independent_of_competitor_input_order(self) -> None:
        plan = {"driver:1": "SOFT", "driver:2": "MEDIUM", "driver:3": "HARD"}
        results = []
        for field in (
            _field_a(),
            list(reversed(_field_a())),
            [_field_a()[1], _field_a()[2], _field_a()[0]],
        ):
            results.append(
                _dump(
                    simulate_race(
                        field,
                        8,
                        tyre_plan=plan,
                        variability=ASSUMED_LAP_VARIABILITY,
                        rng=SeededRandomSource(99),
                    )
                )
            )

        self.assertEqual(len(set(results)), 1)

    def test_variability_alone_leaves_the_tyre_effect_unmodelled(self) -> None:
        result = simulate_race(
            [Competitor("driver:1", "A", 90000.0)],
            2,
            variability=ASSUMED_LAP_VARIABILITY,
            rng=ScriptedRandomSource([0.0, 0.0]),
        )

        breakdown = _car(result, 1, "driver:1")["breakdown"]
        self.assertIsNone(breakdown["tyre_effect_ms"])
        self.assertEqual(breakdown["noise_ms"], 0.0)

    def test_breakdown_adds_up_to_the_reported_lap_time(self) -> None:
        result = simulate_race(
            _field_a(),
            12,
            tyre_plan={
                "driver:1": "SOFT",
                "driver:2": "MEDIUM",
                "driver:3": "HARD",
            },
            variability=ASSUMED_LAP_VARIABILITY,
            rng=SeededRandomSource(5),
        )

        for lap in result["history"]:
            for car in lap["cars"]:
                b = car["breakdown"]
                exact = b["reference_ms"] + b["tyre_effect_ms"] + b["noise_ms"]
                # lap_time_ms sai arredondado a 0,1 ms.
                self.assertLessEqual(abs(car["lap_time_ms"] - exact), 0.05 + 1e-9)

    def test_total_time_accumulates_the_unrounded_lap_times(self) -> None:
        source = ScriptedRandomSource([1.0, 1.0, 1.0])
        result = simulate_race(
            [Competitor("driver:1", "A", 90000.0)],
            3,
            variability=ASSUMED_LAP_VARIABILITY,
            rng=source,
        )

        # cada volta: 90000 + 0,002*90000*1 = 90180
        self.assertAlmostEqual(
            result["classification"][0]["total_time_ms"], 270540.0, places=6
        )

    def test_noise_that_makes_the_lap_non_positive_raises(self) -> None:
        extreme = LapVariabilityAssumption(
            sigma_pct_of_reference=40.0,
            truncation_sigmas=3.0,
            source_kind="assumed",
            parameter_version="teste-v1",
            rationale="Ruido extremo de teste.",
        )
        with self.assertRaises(ValueError):
            simulate_race(
                [Competitor("driver:1", "A", 90000.0)],
                1,
                variability=extreme,
                rng=ScriptedRandomSource([-3.0]),  # -120% do tempo
            )

    def test_assumptions_include_the_labelled_variability(self) -> None:
        result = simulate_race(
            _field_a(),
            2,
            variability=ASSUMED_LAP_VARIABILITY,
            rng=SeededRandomSource(3),
        )

        self.assertEqual(len(result["assumptions"]), 1)
        item = result["assumptions"][0]
        self.assertEqual(item["kind"], "lap_variability")
        self.assertEqual(item["source_kind"], "assumed")
        self.assertEqual(item["sigma_pct_of_reference"], 0.2)
        self.assertEqual(item["truncation_sigmas"], 3.0)
        self.assertTrue(item["rationale"])

    def test_assumptions_order_is_tyres_then_variability(self) -> None:
        result = simulate_race(
            _field_a(),
            2,
            tyre_plan={
                "driver:1": "SOFT",
                "driver:2": "MEDIUM",
                "driver:3": "HARD",
            },
            variability=ASSUMED_LAP_VARIABILITY,
            rng=SeededRandomSource(3),
        )

        self.assertEqual(
            [(a["kind"], a.get("compound")) for a in result["assumptions"]],
            [
                ("tyre", "HARD"),
                ("tyre", "MEDIUM"),
                ("tyre", "SOFT"),
                ("lap_variability", None),
            ],
        )

    def test_active_result_is_json_serializable_and_finite(self) -> None:
        result = simulate_race(
            _field_a(),
            6,
            tyre_plan={
                "driver:1": "SOFT",
                "driver:2": "MEDIUM",
                "driver:3": "HARD",
            },
            variability=ASSUMED_LAP_VARIABILITY,
            rng=SeededRandomSource(11),
        )

        json.dumps(result, allow_nan=False)  # falha se houver NaN/inf
        for car in result["classification"]:
            self.assertTrue(math.isfinite(car["total_time_ms"]))


class LapVariabilityAssumptionTest(unittest.TestCase):
    def _make(self, **overrides):
        values = {
            "sigma_pct_of_reference": 0.2,
            "truncation_sigmas": 3.0,
            "source_kind": "assumed",
            "parameter_version": "v1",
            "rationale": "Motivo.",
        }
        values.update(overrides)
        return LapVariabilityAssumption(**values)

    def test_default_constant_is_a_labelled_hypothesis(self) -> None:
        self.assertEqual(ASSUMED_LAP_VARIABILITY.source_kind, "assumed")
        self.assertEqual(ASSUMED_LAP_VARIABILITY.sigma_pct_of_reference, 0.2)
        self.assertEqual(ASSUMED_LAP_VARIABILITY.truncation_sigmas, 3.0)
        self.assertIn("nao calibrada", ASSUMED_LAP_VARIABILITY.rationale)

    def test_rejects_invalid_numbers(self) -> None:
        for field in ("sigma_pct_of_reference", "truncation_sigmas"):
            for bad in (0, -1.0, math.nan, math.inf, True, "0.2"):
                with self.subTest(field=field, bad=bad):
                    with self.assertRaises(ValueError):
                        self._make(**{field: bad})

    def test_rejects_invalid_labels(self) -> None:
        for field in ("source_kind", "parameter_version", "rationale"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self._make(**{field: "  "})
        with self.assertRaises(ValueError):
            self._make(source_kind="calibrated")

    def test_is_frozen(self) -> None:
        with self.assertRaises(Exception):
            ASSUMED_LAP_VARIABILITY.sigma_pct_of_reference = 1.0  # type: ignore[misc]


class LapTimeBreakdownTest(unittest.TestCase):
    def test_absent_components_do_not_count_as_zero_effects(self) -> None:
        breakdown = LapTimeBreakdown(100.0, None, None)

        self.assertEqual(breakdown.lap_time_ms, 100.0)
        self.assertIsNone(breakdown.tyre_effect_ms)
        self.assertIsNone(breakdown.noise_ms)

    def test_sums_the_present_components(self) -> None:
        self.assertEqual(LapTimeBreakdown(100.0, 5.0, -2.0).lap_time_ms, 103.0)
        self.assertEqual(LapTimeBreakdown(100.0, 5.0, None).lap_time_ms, 105.0)
        self.assertEqual(LapTimeBreakdown(100.0, None, -2.0).lap_time_ms, 98.0)


if __name__ == "__main__":
    unittest.main()
