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


def car(driver_id: str, laps: int, total_ms: float, status: str = "RUNNING") -> dict:
    return {
        "driver_id": driver_id,
        "name": f"Piloto {driver_id}",
        "laps_completed": laps,
        "total_time_ms": total_ms,
        "status": status,
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


class RacePlaybackEngineContractTest(unittest.TestCase):
    """O formato lido aqui e o que o motor detalhado produz de fato."""

    def setUp(self) -> None:
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
        self.result = run_detailed_grid_simulation(
            grid,
            attributes,
            RaceSetup(total_laps=20, track_id="circuit:1"),
            parameters=parameters(),
            lap_length_m=5_000.0,
            rng=SeededRandomSource(3).spawn("race"),
        )
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

    def test_each_car_reaches_lap_k_at_its_recorded_time(self) -> None:
        for snapshot in self.result["history"]:
            for entry in snapshot["cars"]:
                if entry["laps_completed"] != snapshot["lap"]:
                    continue
                timeline = self.playback.car(entry["driver_id"])
                self.assertEqual(
                    timeline.laps_at(entry["total_time_ms"]), snapshot["lap"]
                )


if __name__ == "__main__":
    unittest.main()
