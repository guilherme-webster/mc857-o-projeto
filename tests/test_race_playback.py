"""Testes sem janela da reproducao volta a volta usada pela TrackView."""

from __future__ import annotations

import unittest

from frontend.arcade.race_playback import RacePlayback

from f1_simulator.application.build_grid import GridEntry
from f1_simulator.application.run_grid_simulation import (
    RaceSetup,
    run_detailed_grid_simulation,
)
from f1_simulator.domain.driver_attributes import ATTRIBUTE_FIELDS, DriverAttributes
from f1_simulator.domain.random_source import SeededRandomSource
from tests.model_support import parameters
from tests.test_fuel import fuel_parameters


def car(
    driver_id: str,
    laps: int,
    total_ms: float,
    status: str = "RUNNING",
    **extra: object,
) -> dict:
    return {
        "driver_id": driver_id,
        "name": f"Piloto {driver_id}",
        "laps_completed": laps,
        "total_time_ms": total_ms,
        "status": status,
        **extra,
    }


def race(total_laps: int, *laps: list[dict]) -> dict:
    return {
        "total_laps": total_laps,
        "history": [{"lap": index, "cars": cars} for index, cars in enumerate(laps, 1)],
    }


class RacePlaybackInterpolationTest(unittest.TestCase):
    def setUp(self) -> None:
        # B larga na frente, mas A e mais rapido e passa durante a volta 2.
        self.playback = RacePlayback(
            race(
                3,
                [car("B", 1, 100_000.0), car("A", 1, 101_000.0)],
                [car("A", 2, 199_000.0), car("B", 2, 200_000.0)],
                [car("A", 3, 297_000.0), car("B", 3, 300_000.0)],
            )
        )

    def test_progress_is_linear_inside_each_lap(self) -> None:
        a = self.playback.car("A")
        self.assertEqual(a.laps_at(0.0), 0.0)
        self.assertAlmostEqual(a.laps_at(50_500.0), 0.5)
        self.assertAlmostEqual(a.laps_at(101_000.0), 1.0)
        self.assertAlmostEqual(a.laps_at(150_000.0), 1.5)

    def test_cars_stop_on_the_finish_line(self) -> None:
        a = self.playback.car("A")
        self.assertEqual(a.laps_at(297_000.0), 3.0)
        self.assertEqual(a.laps_at(1e9), 3.0)
        self.assertEqual(self.playback.duration_ms, 300_000.0)

    def test_time_at_laps_inverts_progress(self) -> None:
        b = self.playback.car("B")
        self.assertEqual(b.time_at_laps(0.0), 0.0)
        self.assertAlmostEqual(b.time_at_laps(1.5), 150_000.0)
        self.assertIsNone(b.time_at_laps(3.5))

    def test_overtake_shows_up_in_the_live_order(self) -> None:
        order_lap_1 = [row.driver_id for row in self.playback.standings(100_000.0)]
        order_lap_2 = [row.driver_id for row in self.playback.standings(199_000.0)]
        self.assertEqual(order_lap_1, ["B", "A"])
        self.assertEqual(order_lap_2, ["A", "B"])

    def test_gap_is_the_interval_at_the_leaders_point(self) -> None:
        # Em t=100 s, B fecha a volta 1; A passara por ali em t=101 s.
        rows = self.playback.standings(100_000.0)
        self.assertIsNone(rows[0].gap_ms)
        self.assertAlmostEqual(rows[1].gap_ms, 1_000.0)

    def test_final_standings_use_finish_times(self) -> None:
        rows = self.playback.standings(self.playback.duration_ms)
        self.assertEqual([row.driver_id for row in rows], ["A", "B"])
        self.assertAlmostEqual(rows[1].gap_ms, 3_000.0)
        self.assertEqual([row.lap for row in rows], [3, 3])

    def test_current_lap_follows_the_leader(self) -> None:
        self.assertEqual(self.playback.current_lap(0.0), 1)
        self.assertEqual(self.playback.current_lap(150_000.0), 2)
        self.assertEqual(self.playback.current_lap(1e9), 3)

    def test_start_order_ties_break_by_first_lap_end(self) -> None:
        rows = self.playback.standings(0.0)
        self.assertEqual([row.driver_id for row in rows], ["B", "A"])


class RacePlaybackRetirementTest(unittest.TestCase):
    def setUp(self) -> None:
        self.playback = RacePlayback(
            race(
                3,
                [car("A", 1, 100_000.0), car("X", 1, 99_000.0)],
                [car("A", 2, 200_000.0), car("X", 2, 198_000.0, "RETIRED")],
                [car("A", 3, 300_000.0), car("X", 2, 198_000.0, "RETIRED")],
            )
        )

    def test_retired_car_leaves_the_track_after_its_last_lap(self) -> None:
        on_track = dict(self.playback.on_track(150_000.0))
        self.assertIn("X", on_track)
        self.assertNotIn("X", dict(self.playback.on_track(198_000.0)))

    def test_retired_car_goes_to_the_bottom_of_the_table(self) -> None:
        before = self.playback.standings(150_000.0)
        after = self.playback.standings(250_000.0)
        self.assertEqual(before[0].driver_id, "X")
        self.assertEqual([row.driver_id for row in after], ["A", "X"])
        self.assertTrue(after[1].retired)
        self.assertIsNone(after[1].gap_ms)
        self.assertEqual(after[1].lap, 2)

    def test_leader_retiring_does_not_freeze_the_lap_counter(self) -> None:
        self.assertEqual(self.playback.current_lap(250_000.0), 3)


def tyre(compound: str, age: int, stops: int) -> dict:
    return {"compound": compound, "tyre_age_laps": age, "stops_made": stops}


class RacePlaybackTyresAndPitsTest(unittest.TestCase):
    def setUp(self) -> None:
        # A larga em 2o e para ao fim da volta 2 (MEDIUM -> HARD); B larga na
        # pole, nao para e abandona por contato na volta 3.
        payload = race(
            4,
            [
                car("B", 1, 99_000.0, **tyre("MEDIUM", 1, 0)),
                car("A", 1, 100_000.0, **tyre("MEDIUM", 1, 0)),
            ],
            [
                car("B", 2, 198_000.0, **tyre("MEDIUM", 2, 0)),
                car("A", 2, 220_000.0, **tyre("HARD", 0, 1)),
            ],
            [
                car("A", 3, 318_000.0, **tyre("HARD", 1, 1)),
                car(
                    "B",
                    3,
                    297_000.0,
                    "RETIRED",
                    retirement_cause="CONTACT",
                    **tyre("MEDIUM", 3, 0),
                ),
            ],
            [
                car("A", 4, 416_000.0, **tyre("HARD", 2, 1)),
                car(
                    "B",
                    3,
                    297_000.0,
                    "RETIRED",
                    retirement_cause="CONTACT",
                    **tyre("MEDIUM", 3, 0),
                ),
            ],
        )
        payload["starting_grid"] = [
            {"position": 1, "driver_id": "B", "compound": "MEDIUM"},
            {"position": 2, "driver_id": "A", "compound": "MEDIUM"},
        ]
        self.playback = RacePlayback(payload)

    def test_starting_tyre_comes_from_the_grid(self) -> None:
        state = self.playback.car("A").tyre_at(0.0)
        self.assertEqual(
            (state.compound, state.age_laps, state.stops), ("MEDIUM", 0, 0)
        )

    def test_tyre_shown_is_the_one_of_the_last_completed_lap(self) -> None:
        a = self.playback.car("A")
        self.assertEqual(a.tyre_at(150_000.0).compound, "MEDIUM")
        self.assertEqual(a.tyre_at(219_999.0).compound, "MEDIUM")
        after_stop = a.tyre_at(220_000.0)
        self.assertEqual((after_stop.compound, after_stop.stops), ("HARD", 1))

    def test_whole_pit_lap_is_flagged(self) -> None:
        a = self.playback.car("A")
        self.assertFalse(a.in_pit_lap_at(99_000.0))
        self.assertTrue(a.in_pit_lap_at(100_001.0))
        self.assertTrue(a.in_pit_lap_at(219_000.0))
        self.assertFalse(a.in_pit_lap_at(220_001.0))
        self.assertFalse(a.in_pit_lap_at(1e9))

    def test_rows_carry_pit_and_positions_gained(self) -> None:
        rows = {row.driver_id: row for row in self.playback.standings(150_000.0)}
        self.assertTrue(rows["A"].in_pit)
        self.assertEqual(rows["A"].positions_gained, 0)
        self.assertEqual(rows["B"].positions_gained, 0)

        final = self.playback.standings(self.playback.duration_ms)
        self.assertEqual(final[0].driver_id, "A")
        self.assertEqual(final[0].positions_gained, 1)

    def test_retired_row_keeps_the_cause(self) -> None:
        final = self.playback.standings(self.playback.duration_ms)
        self.assertTrue(final[1].retired)
        self.assertEqual(final[1].retirement_cause, "CONTACT")
        self.assertIsNone(final[1].positions_gained)

    def test_race_without_starting_grid_hides_what_it_cannot_know(self) -> None:
        playback = RacePlayback(race(1, [car("A", 1, 100_000.0, **tyre("SOFT", 1, 0))]))
        a = playback.car("A")
        self.assertIsNone(a.tyre_at(0.0).compound)
        self.assertEqual(a.tyre_at(100_000.0).compound, "SOFT")
        self.assertIsNone(playback.standings(0.0)[0].positions_gained)

    def test_rejects_malformed_starting_grid(self) -> None:
        payload = race(1, [car("A", 1, 1.0)])
        payload["starting_grid"] = [{"driver_id": "A"}]
        with self.assertRaisesRegex(ValueError, "starting_grid"):
            RacePlayback(payload)


def fuel(kg: object, saving_laps: int = 0) -> dict:
    return {"fuel_kg": kg, "fuel_saving_laps": saving_laps}


def grid_slot(position: int, driver_id: str, **extra: object) -> dict:
    return {
        "position": position,
        "driver_id": driver_id,
        "compound": "MEDIUM",
        **extra,
    }


class RacePlaybackFuelTest(unittest.TestCase):
    def setUp(self) -> None:
        # A larga com 100 kg, queima 2 kg na volta 1 e faz a volta 2, mais
        # lenta (120 s), em lift-and-coast. X fica sem combustivel na volta 2.
        payload = race(
            3,
            [
                car("A", 1, 100_000.0, **fuel(98.0)),
                car("X", 1, 101_000.0, **fuel(1.5)),
            ],
            [
                car("A", 2, 220_000.0, **fuel(96.2, 1)),
                car(
                    "X", 2, 202_000.0, "RETIRED", retirement_cause="FUEL", **fuel(0.0)
                ),
            ],
            [
                car("A", 3, 320_000.0, **fuel(94.2, 1)),
                car(
                    "X", 2, 202_000.0, "RETIRED", retirement_cause="FUEL", **fuel(0.0)
                ),
            ],
        )
        payload["starting_grid"] = [
            grid_slot(1, "A", fuel_kg=100.0),
            grid_slot(2, "X", fuel_kg=3.5),
        ]
        payload["fuel"] = {
            "burn_kg_per_lap": 2.0,
            "max_fuel_kg": 110.0,
            "finish_reserve_kg": 1.0,
            "range_laps_at_max_fuel": 54.5,
            "race_exceeds_fuel_range": False,
        }
        self.playback = RacePlayback(payload)

    def test_starting_fuel_comes_from_the_grid(self) -> None:
        self.assertEqual(self.playback.car("A").fuel_at(0.0), 100.0)
        self.assertTrue(self.playback.has_fuel)
        self.assertEqual(self.playback.max_fuel_kg, 110.0)

    def test_fuel_is_linear_in_the_lap_fraction(self) -> None:
        a = self.playback.car("A")
        self.assertAlmostEqual(a.fuel_at(50_000.0), 99.0)
        self.assertEqual(a.fuel_at(100_000.0), 98.0)
        # Metade da volta 2 (100 s -> 220 s) e t = 160 s, nao t = 150 s.
        self.assertAlmostEqual(a.fuel_at(160_000.0), 97.1)
        self.assertEqual(a.fuel_at(220_000.0), 96.2)

    def test_fuel_follows_the_drawn_position(self) -> None:
        a = self.playback.car("A")
        for t_ms in range(0, 320_001, 7_000):
            laps = a.laps_at(t_ms)
            lap = min(int(laps), 2)
            start, end = a.fuel_states[lap].kg, a.fuel_states[lap + 1].kg
            expected = start + (laps - lap) * (end - start)
            self.assertAlmostEqual(a.fuel_at(t_ms), expected)

    def test_fuel_stays_at_the_last_snapshot(self) -> None:
        self.assertEqual(self.playback.car("A").fuel_at(1e9), 94.2)
        self.assertEqual(self.playback.car("X").fuel_at(1e9), 0.0)

    def test_whole_lift_and_coast_lap_is_flagged(self) -> None:
        a = self.playback.car("A")
        self.assertFalse(a.lift_and_coast_at(99_000.0))
        self.assertTrue(a.lift_and_coast_at(100_001.0))
        self.assertTrue(a.lift_and_coast_at(219_000.0))
        # Volta 3: a contagem nao sobe, entao nao ha nova economia.
        self.assertFalse(a.lift_and_coast_at(220_001.0))
        self.assertFalse(a.lift_and_coast_at(1e9))
        self.assertFalse(self.playback.car("X").lift_and_coast_at(150_000.0))

    def test_rows_carry_fuel_and_lift_and_coast(self) -> None:
        rows = {row.driver_id: row for row in self.playback.standings(160_000.0)}
        self.assertAlmostEqual(rows["A"].fuel_kg, 97.1)
        self.assertTrue(rows["A"].lift_and_coast)
        self.assertFalse(rows["X"].lift_and_coast)

    def test_car_that_ran_dry_keeps_the_cause(self) -> None:
        final = self.playback.standings(self.playback.duration_ms)
        self.assertEqual(final[1].driver_id, "X")
        self.assertEqual(final[1].retirement_cause, "FUEL")
        self.assertEqual(final[1].fuel_kg, 0.0)
        self.assertFalse(final[1].lift_and_coast)


class RacePlaybackWithoutFuelTest(unittest.TestCase):
    """Corridas sem o modelo de massa continuam abrindo, sem combustivel."""

    def assert_no_fuel(self, playback: RacePlayback, driver_id: str = "A") -> None:
        timeline = playback.car(driver_id)
        self.assertEqual(timeline.fuel_states, ())
        for t_ms in (0.0, 50_000.0, 1e9):
            self.assertIsNone(timeline.fuel_at(t_ms))
            self.assertFalse(timeline.lift_and_coast_at(t_ms))
        row = next(
            row for row in playback.standings(50_000.0) if row.driver_id == driver_id
        )
        self.assertIsNone(row.fuel_kg)
        self.assertFalse(row.lift_and_coast)

    def test_backend_without_fuel_parameters(self) -> None:
        # Formato atual sem ``fuel-v1.json``: largada sem ``fuel_kg``, retratos
        # sem combustivel e nenhum bloco ``fuel``.
        payload = race(1, [car("A", 1, 100_000.0)])
        payload["starting_grid"] = [grid_slot(1, "A")]
        playback = RacePlayback(payload)
        self.assert_no_fuel(playback)
        self.assertFalse(playback.has_fuel)
        self.assertIsNone(playback.max_fuel_kg)

    def test_old_saved_race_without_starting_grid(self) -> None:
        playback = RacePlayback(race(2, [car("A", 1, 100_000.0)], [car("A", 2, 2e5)]))
        self.assert_no_fuel(playback)
        self.assertFalse(playback.has_fuel)

    def test_fuel_without_starting_load_is_not_guessed(self) -> None:
        playback = RacePlayback(race(1, [car("A", 1, 100_000.0, **fuel(98.0))]))
        self.assert_no_fuel(playback)

    def test_missing_lap_drops_only_that_cars_fuel(self) -> None:
        payload = race(
            2,
            [
                car("A", 1, 100_000.0, **fuel(98.0)),
                car("B", 1, 101_000.0, **fuel(98.0)),
            ],
            [car("A", 2, 200_000.0), car("B", 2, 202_000.0, **fuel(96.0))],
        )
        payload["starting_grid"] = [
            grid_slot(1, "A", fuel_kg=100.0),
            grid_slot(2, "B", fuel_kg=100.0),
        ]
        playback = RacePlayback(payload)
        self.assert_no_fuel(playback, "A")
        self.assertEqual(playback.car("B").fuel_at(1e9), 96.0)
        self.assertTrue(playback.has_fuel)
        self.assertIsNone(playback.max_fuel_kg)

    def test_rejects_malformed_fuel(self) -> None:
        payload = race(1, [car("A", 1, 1.0, **fuel("cheio"))])
        payload["starting_grid"] = [grid_slot(1, "A", fuel_kg=100.0)]
        with self.assertRaisesRegex(ValueError, "combustivel"):
            RacePlayback(payload)

        payload["starting_grid"] = [grid_slot(1, "A", fuel_kg="cheio")]
        with self.assertRaisesRegex(ValueError, "starting_grid"):
            RacePlayback(payload)

        payload = race(1, [car("A", 1, 1.0)])
        payload["fuel"] = {"max_fuel_kg": 0}
        with self.assertRaisesRegex(ValueError, "max_fuel_kg"):
            RacePlayback(payload)


class RacePlaybackSafetyCarCompressionTest(unittest.TestCase):
    def test_compressed_lap_end_never_moves_a_car_backwards(self) -> None:
        # Sob SC o motor reescreve L para tempo_lider + 700 ms; L, que estava
        # mais de uma volta atras, fecha a volta 2 "antes" de fechar a 1.
        playback = RacePlayback(
            race(
                3,
                [car("A", 1, 100_000.0), car("L", 1, 260_000.0)],
                [car("A", 2, 250_000.0), car("L", 2, 250_700.0)],
                [car("A", 3, 350_000.0), car("L", 3, 351_000.0)],
            )
        )
        lapped = playback.car("L")
        self.assertEqual(lapped.lap_end_times_ms, (260_000.0, 260_000.0, 351_000.0))
        samples = [lapped.laps_at(t) for t in range(0, 360_000, 1_000)]
        self.assertEqual(samples, sorted(samples))
        self.assertEqual(lapped.laps_at(260_000.0), 2.0)


class RacePlaybackContractTest(unittest.TestCase):
    def test_rejects_race_without_history(self) -> None:
        with self.assertRaisesRegex(ValueError, "history"):
            RacePlayback({"total_laps": 3, "history": []})

    def test_rejects_skipped_laps(self) -> None:
        with self.assertRaisesRegex(ValueError, "salta"):
            RacePlayback(race(3, [car("A", 1, 1.0)], [car("A", 3, 3.0)]))

    def test_rejects_running_car_that_did_not_finish(self) -> None:
        with self.assertRaisesRegex(ValueError, "em prova"):
            RacePlayback(race(3, [car("A", 1, 1.0)], [car("A", 2, 2.0)]))

    def test_rejects_malformed_car(self) -> None:
        with self.assertRaisesRegex(ValueError, "malformado"):
            RacePlayback(race(1, [{"driver_id": "A"}]))


def run_engine_race(**options: object) -> dict:
    """Oito carros, 20 voltas de 5 km no motor detalhado, semente fixa."""

    grid = []
    attributes = {}
    for index in range(8):
        entry = GridEntry(
            f"driver:{index}", f"Piloto {index}", f"team:{index}", f"Equipe {index}"
        )
        grid.append(entry)
        attributes[entry.driver_id] = DriverAttributes(
            driver_id=entry.driver_id,
            archetype="balanced",
            pace_offset_pct=(index - 4) * 0.05,
            consistency_factor=1.0,
            tyre_management_factor=1.0,
            aggression=1.0,
            composure=1.0,
            sources={name: "generated" for name in ATTRIBUTE_FIELDS},
        )
    return run_detailed_grid_simulation(
        grid,
        attributes,
        RaceSetup(total_laps=20, track_id="circuit:1"),
        parameters=parameters(),
        lap_length_m=5_000.0,
        rng=SeededRandomSource(3).spawn("race"),
        **options,
    )


class RacePlaybackEngineContractTest(unittest.TestCase):
    """O formato lido aqui e o que o motor detalhado produz de fato."""

    def setUp(self) -> None:
        self.result = run_engine_race()
        self.playback = RacePlayback(self.result)

    def test_final_standings_match_engine_classification(self) -> None:
        rows = self.playback.standings(self.playback.duration_ms)
        classification = self.result["classification"]
        self.assertEqual(
            [row.driver_id for row in rows],
            [entry["driver_id"] for entry in classification],
        )
        self.assertEqual(
            [row.retired for row in rows],
            [entry["status"] == "RETIRED" for entry in classification],
        )

    def test_final_positions_gained_use_the_engine_starting_grid(self) -> None:
        grid = {
            entry["driver_id"]: entry["position"]
            for entry in self.result["starting_grid"]
        }
        for row in self.playback.standings(self.playback.duration_ms):
            if row.retired:
                continue
            self.assertEqual(row.positions_gained, grid[row.driver_id] - row.position)

    def test_tyre_states_follow_the_engine_snapshots(self) -> None:
        final = {car["driver_id"]: car for car in self.result["classification"]}
        for timeline in self.playback.cars:
            last = timeline.tyre_at(self.playback.duration_ms)
            entry = final[timeline.driver_id]
            self.assertEqual(last.compound, entry["compound"])
            self.assertEqual(last.stops, entry["stops_made"])

    def test_each_car_reaches_lap_k_at_its_recorded_time(self) -> None:
        for snapshot in self.result["history"]:
            for entry in snapshot["cars"]:
                if entry["laps_completed"] != snapshot["lap"]:
                    continue
                timeline = self.playback.car(entry["driver_id"])
                self.assertEqual(
                    timeline.laps_at(entry["total_time_ms"]), snapshot["lap"]
                )

    def test_race_without_mass_model_has_no_fuel(self) -> None:
        self.assertFalse(self.playback.has_fuel)
        self.assertIsNone(self.playback.max_fuel_kg)


class RacePlaybackEngineFuelContractTest(unittest.TestCase):
    """O combustivel lido aqui e o que o modelo de massa produz de fato."""

    def setUp(self) -> None:
        # 1,1 kg/km em 5 km e 5,5 kg por volta: 20 voltas pedem 111 kg com a
        # reserva, acima do teto de 110 kg. Sem reabastecimento (regra 2010+)
        # o motor precisa economizar.
        self.result = run_engine_race(
            fuel_parameters=fuel_parameters(
                burn_kg_per_km=1.1, refuelling_allowed=False
            )
        )
        self.playback = RacePlayback(self.result)

    def test_fuel_block_and_starting_load(self) -> None:
        self.assertTrue(self.playback.has_fuel)
        self.assertEqual(
            self.playback.max_fuel_kg, self.result["fuel"]["max_fuel_kg"]
        )
        for entry in self.result["starting_grid"]:
            timeline = self.playback.car(entry["driver_id"])
            self.assertEqual(timeline.fuel_at(0.0), entry["fuel_kg"])

    def test_fuel_at_each_lap_end_matches_the_snapshot(self) -> None:
        for snapshot in self.result["history"]:
            for entry in snapshot["cars"]:
                if entry["laps_completed"] != snapshot["lap"]:
                    continue
                timeline = self.playback.car(entry["driver_id"])
                self.assertAlmostEqual(
                    timeline.fuel_at(entry["total_time_ms"]), entry["fuel_kg"]
                )

    def test_lift_and_coast_laps_match_the_engine_count(self) -> None:
        final = {car["driver_id"]: car for car in self.result["classification"]}
        for timeline in self.playback.cars:
            self.assertEqual(
                timeline.fuel_states[-1].saving_laps,
                final[timeline.driver_id]["fuel_saving_laps"],
            )
        self.assertTrue(
            any(entry["fuel_saving_laps"] for entry in final.values()),
            "o cenario deveria forcar lift-and-coast",
        )


class RacePlaybackEngineRefuelContractTest(unittest.TestCase):
    """Reabastecimento: volta marcada como boxes e medidor sem subida falsa."""

    def setUp(self) -> None:
        # 1,3 kg/km em 5 km e 6,5 kg por volta: as 20 voltas pedem 130 kg e
        # 110 kg cobrem 16 voltas (sobram 6 kg < 6,5 kg), entao o carro para.
        # Com 5,5 kg/volta nao serviria: 110 kg cobrem exatamente as 20.
        self.result = run_engine_race(
            fuel_parameters=fuel_parameters(burn_kg_per_km=1.3)
        )
        self.playback = RacePlayback(self.result)
        self.events = self.result["fuel"]["refuel_stops"]

    def test_scenario_forces_a_refuel_stop(self) -> None:
        self.assertTrue(self.events, "o cenario deveria forcar reabastecimento")

    def test_refuel_lap_is_flagged_as_pit_and_tank_jumps_at_lap_end(self) -> None:
        for event in self.events:
            timeline = self.playback.car(event["driver_id"])
            lap = event["lap"]
            lap_start = timeline.lap_end_times_ms[lap - 2] if lap > 1 else 0.0
            lap_end = timeline.lap_end_times_ms[lap - 1]
            middle = (lap_start + lap_end) / 2
            self.assertTrue(timeline.in_pit_lap_at(middle))
            # Durante a volta de entrada o tanque so desce.
            self.assertLessEqual(
                timeline.fuel_at(middle), timeline.fuel_at(lap_start) + 1e-9
            )
            self.assertAlmostEqual(
                timeline.fuel_at(lap_end - 1e-6), event["fuel_before_kg"], places=3
            )
            self.assertAlmostEqual(
                timeline.fuel_at(lap_end),
                event["fuel_before_kg"] + event["added_kg"],
                places=3,
            )

    def test_refuel_stop_also_counts_as_a_tyre_stop(self) -> None:
        # Com reabastecimento, toda parada troca pneus: a contagem sobe na
        # volta do reabastecimento e o pneu recomeca do zero.
        for event in self.events:
            timeline = self.playback.car(event["driver_id"])
            lap = event["lap"]
            self.assertEqual(
                timeline.tyre_states[lap].stops,
                timeline.tyre_states[lap - 1].stops + 1,
            )
            self.assertEqual(timeline.tyre_states[lap].age_laps, 0)


if __name__ == "__main__":
    unittest.main()
