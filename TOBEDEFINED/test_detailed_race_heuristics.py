from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from f1_simulator.adapters.model_parameters_json import read_parameters
from f1_simulator.domain.driver_attributes import ATTRIBUTE_FIELDS, DriverAttributes
from f1_simulator.domain.lap_time import compute_lap_time
from f1_simulator.domain.race_control import HEURISTIC_RACE_CONTROL
from f1_simulator.domain.race_simulation import (
    CONTACT,
    CRASH,
    Entrant,
    simulate_detailed_race,
)
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.strategy import (
    HeuristicPitStrategy,
    NoStopStrategy,
    PitDecision,
    PlannedStopStrategy,
    StrategyState,
)
from f1_simulator.domain.tyres import TyreSet, tyre_penalty_ms
from scripts.race_control_frequency import run_frequency_sample
from tests.model_support import parameters, track


ROOT = Path(__file__).resolve().parents[1]


class ScriptedRandomSource:
    """Fonte que roteiriza uniformes por rotulo e registra toda a sequencia."""

    def __init__(
        self,
        values: dict[str, float] | None = None,
        normal_values: list[float] | None = None,
    ) -> None:
        self.values = values or {}
        self.normal_values = list(normal_values or [])
        self.labels: list[str] = []

    def uniform01(self, label: str = "") -> float:
        self.labels.append(label)
        return self.values.get(label, 1.0)

    def standard_normal(self, label: str = "") -> float:
        self.labels.append(label)
        return self.normal_values.pop(0) if self.normal_values else 0.0


class PitOnLap:
    """Estrategia de teste que pede exatamente uma troca na volta escolhida."""

    def __init__(self, lap: int, compound: str = "HARD") -> None:
        self.lap = lap
        self.compound = compound

    def decide(self, state: StrategyState) -> PitDecision:
        return PitDecision(
            state.lap_number == self.lap and state.stops_made == 0,
            self.compound
            if state.lap_number == self.lap and state.stops_made == 0
            else None,
        )


def driver_attributes(
    driver_id: str,
    *,
    pace_offset_pct: float = 0.0,
    consistency_factor: float = 1.0,
    tyre_management_factor: float = 1.0,
    aggression: float = 1.0,
    composure: float = 1.0,
) -> DriverAttributes:
    return DriverAttributes(
        driver_id=driver_id,
        archetype="balanced",
        pace_offset_pct=pace_offset_pct,
        consistency_factor=consistency_factor,
        tyre_management_factor=tyre_management_factor,
        aggression=aggression,
        composure=composure,
        sources={field: "manual" for field in ATTRIBUTE_FIELDS},
    )


def entrant(
    driver_id: str,
    reference_ms: float,
    grid_position: int,
    *,
    strategy=None,
) -> Entrant:
    return Entrant(
        driver_id=driver_id,
        name=driver_id,
        reference_lap_time_ms=reference_ms,
        grid_position=grid_position,
        strategy=strategy or NoStopStrategy(),
        starting_compound="MEDIUM",
    )


def forced_crash_control(*, response: str, duration_laps: int = 1):
    """Crie parametros validos cuja batida sempre escolhe a resposta pedida."""

    common = dict(
        solo_crash_probability_per_car_lap=0.10,
        first_lap_solo_crash_multiplier=2.0,
        vsc_min_duration_laps=duration_laps,
        vsc_max_duration_laps=duration_laps,
        sc_min_duration_laps=duration_laps,
        sc_max_duration_laps=duration_laps,
        red_duration_laps=duration_laps,
    )
    if response == "RED":
        return replace(HEURISTIC_RACE_CONTROL, crash_red_probability=1.0, **common)
    if response == "SC":
        return replace(
            HEURISTIC_RACE_CONTROL,
            crash_red_probability=0.0,
            crash_sc_probability=1.0,
            crash_vsc_probability=0.0,
            crash_yellow_probability=0.0,
            **common,
        )
    if response == "VSC":
        return replace(
            HEURISTIC_RACE_CONTROL,
            crash_red_probability=0.0,
            crash_sc_probability=0.0,
            crash_vsc_probability=1.0,
            crash_yellow_probability=0.0,
            **common,
        )
    raise ValueError(response)


class NeutralityTest(unittest.TestCase):
    def test_legacy_golden_hashes_remain_byte_for_byte_stable(self) -> None:
        model = read_parameters(ROOT / "data" / "parameters" / "model-v1.json")
        circuit = model.tracks[0]
        hashes = []
        for seed in (1, 7, 2026):
            entrants = [
                Entrant(
                    f"driver:{index}",
                    f"P{index}",
                    90_000 + 150 * index,
                    index,
                    PlannedStopStrategy(
                        1 + index % 2,
                        ("HARD", "MEDIUM"),
                        offset_laps=index % 3,
                    ),
                    "MEDIUM",
                    None,
                    1.0,
                )
                for index in range(1, 21)
            ]
            result = simulate_detailed_race(
                entrants,
                total_laps=58,
                parameters=model,
                track=circuit,
                rng=SeededRandomSource(seed),
                collect_breakdowns=True,
            )
            payload = json.dumps(result, sort_keys=True, default=str).encode()
            hashes.append(hashlib.sha256(payload).hexdigest()[:16])
        self.assertEqual(
            hashes,
            ["123f3a5b5379cf75", "4dad20aea2b5d608", "279d93bd90977a82"],
        )


class LapTimeModifierTest(unittest.TestCase):
    def test_modifiers_keep_compound_offset_and_scale_only_degradation(self) -> None:
        model = parameters(lap_noise_ms=100.0, lap_noise_skew=0.0)
        circuit = track()
        tyre = TyreSet("SOFT", 10)
        raw_tyre_ms = tyre_penalty_ms(tyre, model.compound("SOFT"), circuit)
        result = compute_lap_time(
            reference_ms=90_000.0,
            parameters=model,
            track=circuit,
            tyre=tyre,
            lap_number=10,
            total_laps=20,
            gap_ahead_ms=None,
            pitting=True,
            rng=ScriptedRandomSource(normal_values=[1.0]),
            noise_scale=2.0,
            degradation_factor=2.0,
            pit_loss_factor=0.5,
            lap_time_factor=1.4,
            lap_time_loss_ms=300.0,
        )
        offset_ms = model.compound("SOFT").pace_offset_ms
        self.assertEqual(
            result.tyre_ms,
            offset_ms + (raw_tyre_ms - offset_ms) * 2.0,
        )
        self.assertEqual(result.noise_ms, 200.0)
        self.assertEqual(result.pit_ms, circuit.pit_loss_ms * 0.5)
        self.assertAlmostEqual(result.components_sum_ms(), result.total_ms)


class IntegrationTest(unittest.TestCase):
    def test_same_seed_reproduces_everything_with_all_features(self) -> None:
        model = parameters(dnf_hazard_per_lap=0.01)
        circuit = track()
        attrs = {
            f"driver:{index}": driver_attributes(
                f"driver:{index}",
                pace_offset_pct=-0.3 + index * 0.1,
                aggression=0.8 + index * 0.1,
            )
            for index in range(6)
        }

        def run() -> dict:
            entrants = [
                entrant(
                    f"driver:{index}",
                    90_000.0 + index * 100.0,
                    index + 1,
                    strategy=HeuristicPitStrategy(
                        model,
                        circuit,
                        tyre_management_factor=(
                            attrs[f"driver:{index}"].tyre_management_factor
                        ),
                    ),
                )
                for index in range(6)
            ]
            return simulate_detailed_race(
                entrants,
                total_laps=20,
                parameters=model,
                track=circuit,
                rng=SeededRandomSource(67),
                attributes=attrs,
                dispute_model="pressure",
                race_control=HEURISTIC_RACE_CONTROL,
            )

        self.assertEqual(run(), run())
        result = run()
        self.assertIn("race_control_events", result)
        self.assertIn("race_control_by_lap", result)
        kinds = {item["kind"] for item in result["assumptions"]}
        self.assertIn("driver_attributes", kinds)
        self.assertIn("dispute_heuristics", kinds)
        self.assertIn("race_control", kinds)

    def test_scripted_contact_creates_incident_and_starts_sc(self) -> None:
        model = parameters(
            grid_penalty_ms_per_position=0.0,
            lap_noise_ms=0.0,
            dnf_hazard_per_lap=0.0,
            collision_probability_per_dispute=0.5,
        )
        control = forced_crash_control(response="SC")
        rng = ScriptedRandomSource(
            {
                "lap-dispute:driver:b:driver:a:pass": 1.0,
                "lap-dispute:driver:b:driver:a:contact": 0.0,
                "lap-dispute:driver:b:driver:a:contact-retiree": 0.0,
                "race_control:lap:1:incident:1:contact:driver:a,driver:b:severity": 0.5,
                "race_control:lap:1:incident:1:contact:driver:a,driver:b:response": 0.0,
                "race_control:lap:1:incident:1:contact:driver:a,driver:b:duration": 0.0,
            }
        )
        result = simulate_detailed_race(
            [entrant("driver:a", 90_000.0, 1), entrant("driver:b", 80_000.0, 2)],
            total_laps=2,
            parameters=model,
            track=track(),
            rng=rng,
            dispute_model="pressure",
            race_control=control,
        )
        response = next(
            event
            for event in result["race_control_events"]
            if event["type"] == "incident_response"
        )
        self.assertEqual(response["cause"]["kind"], "contact")
        self.assertEqual(response["cause"]["driver_ids"], ["driver:a", "driver:b"])
        self.assertEqual(response["response"], "SC")
        self.assertEqual(result["race_control_by_lap"][1]["status"], "SC")
        retired = {car["driver_id"]: car for car in result["classification"]}
        self.assertEqual(retired["driver:b"]["retirement_cause"], CONTACT)

    def test_sc_disables_disputes_compresses_field_and_discounts_pit(self) -> None:
        model = parameters(
            grid_penalty_ms_per_position=0.0,
            lap_noise_ms=0.0,
            dnf_hazard_per_lap=0.0,
            collision_probability_per_dispute=0.0,
        )
        control = forced_crash_control(response="SC")
        rng = ScriptedRandomSource(
            {
                "race-control:lap:1:driver:c:solo-crash": 0.0,
                "race_control:lap:1:incident:1:solo_crash:driver:c:severity": 0.5,
                "race_control:lap:1:incident:1:solo_crash:driver:c:response": 0.0,
                "race_control:lap:1:incident:1:solo_crash:driver:c:duration": 0.0,
            }
        )
        result = simulate_detailed_race(
            [
                entrant("driver:a", 90_000.0, 1, strategy=PitOnLap(2)),
                entrant("driver:b", 89_000.0, 2),
                entrant("driver:c", 91_000.0, 3),
                entrant("driver:d", 88_000.0, 4),
            ],
            total_laps=2,
            parameters=model,
            track=track(),
            rng=rng,
            collect_breakdowns=True,
            dispute_model="pressure",
            race_control=control,
        )
        pass_draws = [label for label in rng.labels if label.endswith(":pass")]
        # Tres pares disputam na primeira volta; a segunda, sob SC, nao cria
        # qualquer sorteio de ultrapassagem.
        self.assertEqual(len(pass_draws), 3)
        lap_two = result["history"][1]["cars"]
        running_times = [
            car["total_time_ms"] for car in lap_two if car["status"] == "RUNNING"
        ]
        self.assertEqual(
            [
                later - earlier
                for earlier, later in zip(running_times, running_times[1:])
            ],
            [model.minimum_gap_ms] * (len(running_times) - 1),
        )
        pit = next(
            item
            for item in result["breakdowns"]
            if item["lap"] == 2 and item["driver_id"] == "driver:a"
        )
        self.assertEqual(
            pit["pit_ms"], track().pit_loss_ms * control.sc_pit_loss_factor
        )

    def test_vsc_disables_disputes_without_compressing_field(self) -> None:
        model = parameters(
            grid_penalty_ms_per_position=0.0,
            lap_noise_ms=0.0,
            dnf_hazard_per_lap=0.0,
            collision_probability_per_dispute=0.0,
        )
        control = forced_crash_control(response="VSC")
        rng = ScriptedRandomSource(
            {
                "race-control:lap:1:driver:c:solo-crash": 0.0,
                "race_control:lap:1:incident:1:solo_crash:driver:c:severity": 0.5,
                "race_control:lap:1:incident:1:solo_crash:driver:c:response": 0.0,
                "race_control:lap:1:incident:1:solo_crash:driver:c:duration": 0.0,
            }
        )
        result = simulate_detailed_race(
            [
                entrant("driver:a", 90_000.0, 1),
                entrant("driver:b", 89_000.0, 2),
                entrant("driver:c", 91_000.0, 3),
            ],
            total_laps=2,
            parameters=model,
            track=track(),
            rng=rng,
            dispute_model="pressure",
            race_control=control,
        )
        self.assertEqual(result["race_control_by_lap"][1]["status"], "VSC")
        pass_draws = [label for label in rng.labels if label.endswith(":pass")]
        self.assertEqual(len(pass_draws), 2)
        running = [
            car for car in result["history"][1]["cars"] if car["status"] == "RUNNING"
        ]
        self.assertNotEqual(
            running[1]["total_time_ms"] - running[0]["total_time_ms"],
            model.minimum_gap_ms,
        )

    def test_red_allows_free_tyre_change_and_freezes_start_order(self) -> None:
        model = parameters(
            grid_penalty_ms_per_position=0.0,
            lap_noise_ms=0.0,
            dnf_hazard_per_lap=0.0,
            collision_probability_per_dispute=0.0,
        )
        control = forced_crash_control(response="RED")
        rng = ScriptedRandomSource(
            {
                "race-control:lap:1:driver:c:solo-crash": 0.0,
                "race_control:lap:1:incident:1:solo_crash:driver:c:severity": 0.0,
            }
        )
        result = simulate_detailed_race(
            [
                entrant("driver:a", 96_000.0, 1, strategy=PitOnLap(2)),
                entrant("driver:b", 84_000.0, 2, strategy=PitOnLap(2)),
                entrant("driver:c", 90_000.0, 3, strategy=PitOnLap(2)),
            ],
            total_laps=2,
            parameters=model,
            track=track(),
            rng=rng,
            dispute_model="pressure",
            race_control=control,
        )
        self.assertEqual(result["race_control_by_lap"][1]["status"], "RED")
        running = [
            car for car in result["history"][1]["cars"] if car["status"] == "RUNNING"
        ]
        self.assertEqual(
            [car["driver_id"] for car in running], ["driver:a", "driver:b"]
        )
        for car in running:
            self.assertEqual(car["compound"], "HARD")
            self.assertEqual(car["tyre_age_laps"], 1)
            self.assertEqual(car["stops_made"], 0)
        retired = next(
            car
            for car in result["classification"]
            if car["driver_id"] == "driver:c"
        )
        self.assertEqual(retired["retirement_cause"], CRASH)

    def test_blue_flag_is_derived_from_elapsed_time_not_loop_laps(self) -> None:
        model = parameters(
            grid_penalty_ms_per_position=110_000.0,
            lap_noise_ms=2_000.0,
            dnf_hazard_per_lap=0.0,
            collision_probability_per_dispute=0.0,
        )
        # Volta 1 mantem o intervalo acima de uma referencia. Na volta 2, um
        # ruido lento extremo do lider faria o retardatario cruza-lo; a bandeira
        # azul temporal deve evitar que isso vire disputa ou troca de ordem.
        rng = ScriptedRandomSource(normal_values=[0.0, 0.0, 100.0, 0.0])
        result = simulate_detailed_race(
            [
                entrant("driver:a", 90_000.0, 1),
                entrant("driver:b", 89_000.0, 2),
            ],
            total_laps=2,
            parameters=model,
            track=track(),
            rng=rng,
            dispute_model="pressure",
        )
        self.assertFalse(any(label.endswith(":pass") for label in rng.labels))
        self.assertEqual(result["classification"][0]["driver_id"], "driver:a")
        self.assertGreater(
            result["classification"][1]["total_time_ms"],
            result["classification"][0]["total_time_ms"],
        )


class MonteCarloSanityTest(unittest.TestCase):
    def test_faster_driver_wins_more_often(self) -> None:
        model = parameters(
            dnf_hazard_per_lap=0.0,
            collision_probability_per_dispute=0.0,
        )
        attrs = {
            "driver:fast": driver_attributes("driver:fast", pace_offset_pct=-1.5),
            "driver:slow": driver_attributes("driver:slow", pace_offset_pct=1.5),
        }
        wins = {"driver:fast": 0, "driver:slow": 0}
        for seed in range(30):
            result = simulate_detailed_race(
                [
                    entrant("driver:slow", 90_000.0, 1),
                    entrant("driver:fast", 90_000.0, 2),
                ],
                total_laps=12,
                parameters=model,
                track=track(),
                rng=SeededRandomSource(seed),
                attributes=attrs,
                dispute_model="pressure",
            )
            wins[result["classification"][0]["driver_id"]] += 1
        self.assertGreater(wins["driver:fast"], wins["driver:slow"])

    def test_aggressive_profile_produces_more_contacts(self) -> None:
        model = parameters(
            grid_penalty_ms_per_position=0.0,
            dnf_hazard_per_lap=0.0,
            collision_probability_per_dispute=0.10,
        )

        def contacts(aggression: float) -> int:
            total = 0
            attrs = {
                "driver:a": driver_attributes("driver:a"),
                "driver:b": driver_attributes("driver:b", aggression=aggression),
            }
            for seed in range(120):
                result = simulate_detailed_race(
                    [
                        entrant("driver:a", 90_000.0, 1),
                        entrant("driver:b", 88_000.0, 2),
                    ],
                    total_laps=2,
                    parameters=model,
                    track=track(),
                    rng=SeededRandomSource(seed),
                    attributes=attrs,
                    dispute_model="pressure",
                )
                total += sum(
                    car["retirement_cause"] == CONTACT
                    for car in result["classification"]
                )
            return total

        self.assertGreater(contacts(1.5), contacts(0.6))

    def test_monaco_has_fewer_passes_than_an_easy_circuit(self) -> None:
        model = parameters(
            grid_penalty_ms_per_position=0.0,
            dnf_hazard_per_lap=0.0,
            collision_probability_per_dispute=0.0,
        )

        def passes(difficulty: float) -> int:
            total = 0
            for seed in range(150):
                result = simulate_detailed_race(
                    [
                        entrant("driver:a", 90_000.0, 1),
                        entrant("driver:b", 88_000.0, 2),
                    ],
                    total_laps=1,
                    parameters=model,
                    track=track(overtaking_difficulty=difficulty),
                    rng=SeededRandomSource(seed),
                    dispute_model="pressure",
                )
                total += result["classification"][0]["driver_id"] == "driver:b"
            return total

        self.assertLess(passes(0.95), passes(0.10))

    def test_small_frequency_sample_stays_broadly_plausible(self) -> None:
        metrics = run_frequency_sample(20, seed=67_2026)
        self.assertGreaterEqual(metrics["neutralizations_per_race"], 0.10)
        self.assertLessEqual(metrics["neutralizations_per_race"], 1.50)
        self.assertGreaterEqual(metrics["red_flags_per_race"], 0.0)
        self.assertLessEqual(metrics["red_flags_per_race"], 0.50)
        self.assertGreater(metrics["pit_stops_per_car"], 0.25)
        self.assertLess(metrics["pit_stops_per_car"], 3.0)


if __name__ == "__main__":
    unittest.main()
