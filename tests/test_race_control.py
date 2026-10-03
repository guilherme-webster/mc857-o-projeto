from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError, replace

from f1_simulator.domain.race_control import (
    GREEN,
    RED,
    SC,
    VSC,
    YELLOW,
    HEURISTIC_RACE_CONTROL,
    Incident,
    LapEffects,
    RaceControlParameters,
    RaceControlState,
    RaceStatus,
    effects,
    should_yield_blue_flag,
    solo_crash_probability,
    step,
)
from f1_simulator.domain.random_source import SeededRandomSource



def _crash_response_draw(status: RaceStatus) -> float:
    """Sorteio no ponto medio da faixa da resposta a uma batida.

    Derivado dos parametros padrao, para que o teste verifique a logica de
    selecao e nao um valor de ajuste de frequencia, que pode mudar de versao.
    """

    p = HEURISTIC_RACE_CONTROL
    if status == SC:
        return p.crash_sc_probability / 2
    if status == VSC:
        return p.crash_sc_probability + p.crash_vsc_probability / 2
    return (
        p.crash_sc_probability
        + p.crash_vsc_probability
        + p.crash_yellow_probability / 2
    )


def _mechanical_response_draw(response: str) -> float:
    """Sorteio no ponto medio da faixa da resposta a um abandono mecanico."""

    p = HEURISTIC_RACE_CONTROL
    if response == "NONE":
        return p.mechanical_no_intervention_probability / 2
    if response == "YELLOW":
        return (
            p.mechanical_no_intervention_probability
            + p.mechanical_yellow_probability / 2
        )
    return (
        p.mechanical_no_intervention_probability
        + p.mechanical_yellow_probability
        + p.mechanical_vsc_probability / 2
    )

class ScriptedRandomSource:
    """Fonte estrita: faltar ou sobrar sorteio torna a ordem observavel."""

    def __init__(self, *values: float) -> None:
        self._values = list(values)
        self.labels: list[str] = []

    def uniform01(self, label: str = "") -> float:
        self.labels.append(label)
        if not self._values:
            raise AssertionError(f"sorteio inesperado: {label}")
        return self._values.pop(0)

    def standard_normal(self, label: str = "") -> float:
        raise AssertionError(f"normal inesperada: {label}")

    def assert_exhausted(self, test: unittest.TestCase) -> None:
        test.assertEqual(self._values, [])


class ExplodingRandomSource:
    def uniform01(self, label: str = "") -> float:
        raise AssertionError(f"nao deveria sortear: {label}")

    def standard_normal(self, label: str = "") -> float:
        raise AssertionError(f"nao deveria sortear: {label}")


def incident(lap: int, kind: str = "contact") -> Incident:
    driver_ids = ("driver:1", "driver:2") if kind == "contact" else ("driver:1",)
    return Incident(lap=lap, kind=kind, driver_ids=driver_ids)  # type: ignore[arg-type]


class IncidentAndParametersTest(unittest.TestCase):
    def test_incident_and_parameters_are_frozen_and_slotted(self) -> None:
        occurrence = incident(1)

        with self.assertRaises(FrozenInstanceError):
            occurrence.lap = 2  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            HEURISTIC_RACE_CONTROL.origin = "calibrated"  # type: ignore[misc]
        self.assertFalse(hasattr(occurrence, "__dict__"))
        self.assertFalse(hasattr(HEURISTIC_RACE_CONTROL, "__dict__"))

    def test_incident_validates_lap_kind_and_driver_ids(self) -> None:
        invalid_builders = (
            lambda: Incident(0, "contact", ("driver:1",)),
            lambda: Incident(True, "contact", ("driver:1",)),
            lambda: Incident(1, "spin", ("driver:1",)),
            lambda: Incident(1, "contact", ()),
            lambda: Incident(1, "contact", ("",)),
            lambda: Incident(1, "contact", ("driver:1", "driver:1")),
            lambda: Incident(1, "contact", ["driver:1"]),
        )

        for build in invalid_builders:
            with self.subTest(builder=build):
                with self.assertRaises(ValueError):
                    build()  # type: ignore[misc]

    def test_default_parameters_declare_heuristic_provenance(self) -> None:
        self.assertEqual(HEURISTIC_RACE_CONTROL.origin, "heuristic")
        self.assertTrue(HEURISTIC_RACE_CONTROL.parameter_version)
        self.assertTrue(HEURISTIC_RACE_CONTROL.rationale)
        self.assertGreaterEqual(HEURISTIC_RACE_CONTROL.crash_red_probability, 0.05)
        self.assertLessEqual(HEURISTIC_RACE_CONTROL.crash_red_probability, 0.10)

    def test_parameters_validate_probability_sums_ranges_and_durations(self) -> None:
        invalid_replacements = (
            {"crash_red_probability": -0.01},
            {"crash_sc_probability": 0.50},
            {"mechanical_vsc_probability": 0.20},
            {"vsc_min_duration_laps": 0},
            {"vsc_min_duration_laps": 4},
            {"yellow_overtake_factor": 1.01},
            {"sc_pit_loss_factor": 1.01},
            {"vsc_lap_time_factor": 0.99},
            {"restart_contact_factor": 1.0},
            {"first_lap_solo_crash_multiplier": 1.0},
            {"vsc_lap_time_factor": float("inf")},
            {"solo_crash_probability_per_car_lap": 0.5},
            {"parameter_version": ""},
            {"origin": "calibrated"},
        )

        for changes in invalid_replacements:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    replace(HEURISTIC_RACE_CONTROL, **changes)

    def test_state_rejects_incoherent_combinations(self) -> None:
        occurrence = incident(1)
        invalid_builders = (
            lambda: RaceControlState(status=GREEN, laps_remaining=1),
            lambda: RaceControlState(status=SC, laps_remaining=0, cause=occurrence),
            lambda: RaceControlState(status=SC, laps_remaining=1),
            lambda: RaceControlState(restart_lap=True),
            lambda: RaceControlState(restart_source=SC),
            lambda: RaceControlState(
                status=VSC,
                laps_remaining=1,
                cause=occurrence,
                restart_lap=True,
                restart_source=SC,
            ),
        )

        for build in invalid_builders:
            with self.subTest(builder=build):
                with self.assertRaises(ValueError):
                    build()


class RaceControlTransitionsTest(unittest.TestCase):
    def test_contact_can_trigger_red_without_other_draws(self) -> None:
        rng = ScriptedRandomSource(0.01)

        state, events = step(
            RaceControlState(), (incident(7),), rng, HEURISTIC_RACE_CONTROL, 7
        )

        self.assertEqual(state.status, RED)
        self.assertEqual(state.laps_remaining, 1)
        self.assertEqual(events[0]["response"], "RED")
        self.assertEqual(len(rng.labels), 1)
        self.assertTrue(rng.labels[0].endswith(":severity"))
        rng.assert_exhausted(self)

    def test_crash_responses_cover_sc_vsc_and_yellow(self) -> None:
        cases = (
            ((0.50, _crash_response_draw(SC), 0.00), SC, 3),
            ((0.50, _crash_response_draw(VSC), 1.00), VSC, 3),
            ((0.50, _crash_response_draw(YELLOW)), YELLOW, 1),
        )

        for values, expected_status, expected_duration in cases:
            with self.subTest(status=expected_status):
                rng = ScriptedRandomSource(*values)
                state, events = step(
                    RaceControlState(),
                    (incident(2, "solo_crash"),),
                    rng,
                    HEURISTIC_RACE_CONTROL,
                    2,
                )
                self.assertEqual(state.status, expected_status)
                self.assertEqual(state.laps_remaining, expected_duration)
                self.assertEqual(events[0]["response"], expected_status.value)
                rng.assert_exhausted(self)

    def test_mechanical_responses_cover_none_yellow_and_vsc(self) -> None:
        cases = (
            ((_mechanical_response_draw("NONE"),), GREEN, 0, "NONE"),
            ((_mechanical_response_draw("YELLOW"),), YELLOW, 1, "YELLOW"),
            ((_mechanical_response_draw("VSC"), 0.00), VSC, 1, "VSC"),
        )

        for values, expected_status, duration, response in cases:
            with self.subTest(response=response):
                rng = ScriptedRandomSource(*values)
                state, events = step(
                    RaceControlState(),
                    (incident(4, "mechanical"),),
                    rng,
                    HEURISTIC_RACE_CONTROL,
                    4,
                )
                self.assertEqual(state.status, expected_status)
                self.assertEqual(state.laps_remaining, duration)
                self.assertEqual(events[0]["response"], response)
                rng.assert_exhausted(self)

    def test_duration_draws_reach_inclusive_bounds(self) -> None:
        for draw, expected_sc, expected_vsc in ((0.0, 3, 1), (1.0, 5, 3)):
            with self.subTest(draw=draw):
                sc_state, _ = step(
                    RaceControlState(),
                    (incident(1),),
                    ScriptedRandomSource(0.5, _crash_response_draw(SC), draw),
                    HEURISTIC_RACE_CONTROL,
                    1,
                )
                vsc_state, _ = step(
                    RaceControlState(),
                    (incident(1),),
                    ScriptedRandomSource(0.5, _crash_response_draw(VSC), draw),
                    HEURISTIC_RACE_CONTROL,
                    1,
                )
                self.assertEqual(sc_state.laps_remaining, expected_sc)
                self.assertEqual(vsc_state.laps_remaining, expected_vsc)

    def test_sc_duration_counts_future_laps_and_schedules_one_restart(self) -> None:
        state, _ = step(
            RaceControlState(),
            (incident(1),),
            ScriptedRandomSource(0.5, 0.1, 0.0),
            HEURISTIC_RACE_CONTROL,
            1,
        )

        for lap, expected_remaining in ((2, 2), (3, 1)):
            state, events = step(
                state, (), ExplodingRandomSource(), HEURISTIC_RACE_CONTROL, lap
            )
            self.assertEqual(state.status, SC)
            self.assertEqual(state.laps_remaining, expected_remaining)
            self.assertEqual(events, ())

        state, events = step(
            state, (), ExplodingRandomSource(), HEURISTIC_RACE_CONTROL, 4
        )
        self.assertEqual(
            state,
            RaceControlState(restart_lap=True, restart_source=SC),
        )
        self.assertEqual([event["type"] for event in events], [
            "race_control_ended",
            "restart_scheduled",
        ])

        state, events = step(
            state, (), ExplodingRandomSource(), HEURISTIC_RACE_CONTROL, 5
        )
        self.assertEqual(state, RaceControlState())
        self.assertEqual(events, ())

    def test_yellow_and_vsc_end_without_restart(self) -> None:
        for status in (YELLOW, VSC):
            with self.subTest(status=status):
                state = RaceControlState(
                    status=status,
                    laps_remaining=1,
                    cause=incident(3),
                )
                next_state, events = step(
                    state, (), ExplodingRandomSource(), HEURISTIC_RACE_CONTROL, 4
                )
                self.assertEqual(next_state, RaceControlState())
                self.assertEqual(events[0]["type"], "race_control_ended")

    def test_red_ends_in_grouped_restart(self) -> None:
        state = RaceControlState(status=RED, laps_remaining=1, cause=incident(8))

        next_state, events = step(
            state, (), ExplodingRandomSource(), HEURISTIC_RACE_CONTROL, 9
        )

        self.assertEqual(next_state.restart_source, RED)
        self.assertTrue(next_state.restart_lap)
        self.assertTrue(effects(next_state).compress_field)
        self.assertEqual(events[-1]["source"], "RED")

    def test_incident_during_vsc_escalates_to_sc(self) -> None:
        original = incident(2, "mechanical")
        state = RaceControlState(status=VSC, laps_remaining=2, cause=original)
        crash = incident(3, "solo_crash")

        next_state, events = step(
            state,
            (crash,),
            ScriptedRandomSource(0.5, 0.1, 0.0),
            HEURISTIC_RACE_CONTROL,
            3,
        )

        self.assertEqual(next_state.status, SC)
        self.assertEqual(next_state.laps_remaining, 3)
        self.assertEqual(next_state.cause, crash)
        self.assertEqual(events[-1]["type"], "race_control_escalated")

    def test_incident_during_sc_never_shortens_duration(self) -> None:
        original = incident(2)
        state = RaceControlState(status=SC, laps_remaining=5, cause=original)

        next_state, events = step(
            state,
            (incident(3, "solo_crash"),),
            ScriptedRandomSource(0.5, 0.1, 0.0),
            HEURISTIC_RACE_CONTROL,
            3,
        )

        # A volta vigente consome uma das cinco; o novo SC de tres nao volta o
        # contador a cinco nem reduz as quatro voltas que ja restavam.
        self.assertEqual(next_state.status, SC)
        self.assertEqual(next_state.laps_remaining, 4)
        self.assertEqual(next_state.cause, original)
        self.assertEqual(len(events), 1)

    def test_incident_during_sc_extends_to_later_new_deadline(self) -> None:
        state = RaceControlState(
            status=SC,
            laps_remaining=2,
            cause=incident(2),
        )
        new_cause = incident(3, "solo_crash")

        next_state, events = step(
            state,
            (new_cause,),
            ScriptedRandomSource(0.5, 0.1, 1.0),
            HEURISTIC_RACE_CONTROL,
            3,
        )

        self.assertEqual(next_state.status, SC)
        self.assertEqual(next_state.laps_remaining, 5)
        self.assertEqual(next_state.cause, new_cause)
        self.assertEqual(events[-1]["type"], "race_control_extended")

    def test_less_severe_incident_does_not_replace_sc(self) -> None:
        state = RaceControlState(status=SC, laps_remaining=3, cause=incident(2))

        next_state, events = step(
            state,
            (incident(3, "mechanical"),),
            ScriptedRandomSource(0.7),
            HEURISTIC_RACE_CONTROL,
            3,
        )

        self.assertEqual(next_state.status, SC)
        self.assertEqual(next_state.laps_remaining, 2)
        self.assertEqual(next_state.cause, state.cause)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["response"], "YELLOW")

    def test_multiple_incidents_use_canonical_draw_order_and_most_severe_response(self) -> None:
        mechanical = Incident(6, "mechanical", ("driver:9",))
        contact = Incident(6, "contact", ("driver:2", "driver:3"))
        rng = ScriptedRandomSource(0.01, 0.20)

        state, events = step(
            RaceControlState(),
            (mechanical, contact),
            rng,
            HEURISTIC_RACE_CONTROL,
            6,
        )

        self.assertEqual(state.status, RED)
        self.assertIn(":incident:1:contact:", rng.labels[0])
        self.assertIn(":incident:2:mechanical:", rng.labels[1])
        self.assertEqual([event["response"] for event in events[:2]], ["RED", "NONE"])

    def test_step_rejects_incident_from_another_lap(self) -> None:
        with self.assertRaisesRegex(ValueError, "pertencer"):
            step(
                RaceControlState(),
                (incident(2),),
                ExplodingRandomSource(),
                HEURISTIC_RACE_CONTROL,
                3,
            )

    def test_no_incident_never_consumes_randomness(self) -> None:
        states = (
            RaceControlState(),
            RaceControlState(restart_lap=True, restart_source=SC),
            RaceControlState(status=YELLOW, laps_remaining=1, cause=incident(1)),
            RaceControlState(status=VSC, laps_remaining=2, cause=incident(1)),
            RaceControlState(status=SC, laps_remaining=2, cause=incident(1)),
            RaceControlState(status=RED, laps_remaining=1, cause=incident(1)),
        )

        for state in states:
            with self.subTest(state=state):
                step(state, (), ExplodingRandomSource(), HEURISTIC_RACE_CONTROL, 2)

    def test_events_are_directly_json_serializable(self) -> None:
        _, events = step(
            RaceControlState(),
            (incident(1),),
            ScriptedRandomSource(0.5, 0.1, 0.0),
            HEURISTIC_RACE_CONTROL,
            1,
        )

        encoded = json.dumps(events)

        self.assertIn('"incident_response"', encoded)
        self.assertIn('"driver:1"', encoded)


class RaceControlEffectsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cause = incident(1)
        self.params = HEURISTIC_RACE_CONTROL

    def test_green_and_yellow_effects(self) -> None:
        green = effects(RaceControlState(), self.params)
        yellow = effects(
            RaceControlState(status=YELLOW, laps_remaining=1, cause=self.cause),
            self.params,
        )

        self.assertEqual(green.lap_time_factor, 1.0)
        self.assertTrue(green.disputes_enabled)
        self.assertFalse(green.neutralized)
        self.assertEqual(yellow.lap_time_loss_ms, self.params.yellow_lap_time_loss_ms)
        self.assertEqual(yellow.overtake_factor, self.params.yellow_overtake_factor)
        self.assertTrue(yellow.disputes_enabled)
        self.assertFalse(yellow.neutralized)

    def test_vsc_preserves_field_and_reduces_pit_loss(self) -> None:
        result = effects(
            RaceControlState(status=VSC, laps_remaining=1, cause=self.cause),
            self.params,
        )

        self.assertEqual(result.lap_time_factor, 1.4)
        self.assertFalse(result.disputes_enabled)
        self.assertFalse(result.compress_field)
        self.assertEqual(result.pit_loss_factor, 0.7)
        self.assertTrue(result.neutralized)

    def test_sc_compresses_field_and_reduces_pit_loss(self) -> None:
        result = effects(
            RaceControlState(status=SC, laps_remaining=2, cause=self.cause),
            self.params,
        )

        self.assertFalse(result.disputes_enabled)
        self.assertTrue(result.compress_field)
        self.assertEqual(result.pit_loss_factor, 0.5)
        self.assertTrue(result.neutralized)

    def test_red_freezes_disputes_and_allows_free_tyre_change(self) -> None:
        result = effects(
            RaceControlState(status=RED, laps_remaining=1, cause=self.cause),
            self.params,
        )

        self.assertFalse(result.disputes_enabled)
        self.assertTrue(result.free_tyre_change)
        self.assertTrue(result.freeze_order)
        self.assertEqual(result.pit_loss_factor, 0.0)
        self.assertEqual(result.solo_crash_multiplier, 0.0)

    def test_restart_boosts_disputes_contact_and_solo_crash(self) -> None:
        after_sc = effects(
            RaceControlState(restart_lap=True, restart_source=SC), self.params
        )
        after_red = effects(
            RaceControlState(restart_lap=True, restart_source=RED), self.params
        )

        self.assertEqual(after_sc.overtake_factor, self.params.restart_overtake_factor)
        self.assertEqual(after_sc.contact_factor, self.params.restart_contact_factor)
        self.assertEqual(
            after_sc.solo_crash_multiplier,
            self.params.restart_solo_crash_multiplier,
        )
        self.assertFalse(after_sc.compress_field)
        self.assertTrue(after_red.compress_field)

    def test_solo_crash_probability_applies_first_lap_and_restart_factors(self) -> None:
        green = effects(RaceControlState(), self.params)
        restart = effects(
            RaceControlState(restart_lap=True, restart_source=SC), self.params
        )

        self.assertEqual(
            solo_crash_probability(2, green, self.params),
            self.params.solo_crash_probability_per_car_lap,
        )
        self.assertEqual(
            solo_crash_probability(1, green, self.params),
            self.params.solo_crash_probability_per_car_lap
            * self.params.first_lap_solo_crash_multiplier,
        )
        self.assertEqual(
            solo_crash_probability(2, restart, self.params),
            self.params.solo_crash_probability_per_car_lap
            * self.params.restart_solo_crash_multiplier,
        )

    def test_blue_flag_requires_lapped_defender_to_yield(self) -> None:
        self.assertTrue(should_yield_blue_flag(18, 19))
        self.assertTrue(should_yield_blue_flag(18, 20))
        self.assertFalse(should_yield_blue_flag(19, 19))
        self.assertFalse(should_yield_blue_flag(20, 19))
        with self.assertRaises(ValueError):
            should_yield_blue_flag(-1, 2)

    def test_lap_effects_validate_values(self) -> None:
        with self.assertRaises(ValueError):
            replace(effects(RaceControlState()), lap_time_factor=0.0)
        with self.assertRaises(ValueError):
            replace(effects(RaceControlState()), neutralized=1)


class RaceControlRandomnessTest(unittest.TestCase):
    def test_same_seed_reproduces_states_events_and_draw_labels(self) -> None:
        def run(seed: int) -> tuple[list[RaceControlState], list[tuple[dict, ...]], tuple]:
            rng = SeededRandomSource(seed, record_draws=True)
            state = RaceControlState()
            states = []
            all_events = []
            for lap in range(1, 31):
                occurrences: tuple[Incident, ...] = ()
                if lap % 5 == 0:
                    kind = "mechanical" if lap % 10 == 0 else "solo_crash"
                    occurrences = (incident(lap, kind),)
                state, events = step(
                    state, occurrences, rng, HEURISTIC_RACE_CONTROL, lap
                )
                states.append(state)
                all_events.append(events)
            return states, all_events, rng.draws

        first = run(2026)
        repeated = run(2026)
        different = run(2027)

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, different)

    def test_monte_carlo_response_frequencies_match_parameters(self) -> None:
        rng = SeededRandomSource(817_263)
        counts = {
            "crash": {"RED": 0, "SC": 0, "VSC": 0, "YELLOW": 0},
            "mechanical": {"NONE": 0, "YELLOW": 0, "VSC": 0},
        }
        totals = {"crash": 0, "mechanical": 0}

        # A taxa sintetica e fixa: ha um incidente a cada quatro voltas, com
        # tipos alternados. Voltas sem incidente tambem atravessam ``step`` e
        # demonstram que nao deslocam a sequencia pseudoaleatoria.
        for lap in range(1, 80_001):
            occurrences: tuple[Incident, ...] = ()
            category: str | None = None
            if lap % 4 == 0:
                category = "crash" if (lap // 4) % 2 else "mechanical"
                kind = "solo_crash" if category == "crash" else "mechanical"
                occurrences = (incident(lap, kind),)
            _, events = step(
                RaceControlState(),
                occurrences,
                rng,
                HEURISTIC_RACE_CONTROL,
                lap,
            )
            if category is not None:
                response = events[0]["response"]
                counts[category][response] += 1  # type: ignore[index]
                totals[category] += 1

        params = HEURISTIC_RACE_CONTROL
        expected_crash = {
            "RED": params.crash_red_probability,
            "SC": (1.0 - params.crash_red_probability)
            * params.crash_sc_probability,
            "VSC": (1.0 - params.crash_red_probability)
            * params.crash_vsc_probability,
            "YELLOW": (1.0 - params.crash_red_probability)
            * params.crash_yellow_probability,
        }
        expected_mechanical = {
            "NONE": params.mechanical_no_intervention_probability,
            "YELLOW": params.mechanical_yellow_probability,
            "VSC": params.mechanical_vsc_probability,
        }
        for category, expected in (
            ("crash", expected_crash),
            ("mechanical", expected_mechanical),
        ):
            for response, probability in expected.items():
                with self.subTest(category=category, response=response):
                    observed = counts[category][response] / totals[category]
                    self.assertAlmostEqual(observed, probability, delta=0.02)


if __name__ == "__main__":
    unittest.main()
