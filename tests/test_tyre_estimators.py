"""Neutralization boundaries, influence and held-event leakage regressions."""

from copy import deepcopy
import unittest

from f1_simulator.application.compare_tyre_estimators import (
    neutralizations,
    apply_windows,
    influence,
    transfer_benchmark,
)
from f1_simulator.application.analyze_tyres import describe_stint
from tests.test_tyres import rows


def statuses(values):
    return [
        dict(sequence=i, session_time_ms=i * 10, status=s) for i, s in enumerate(values)
    ]


class TyreEstimatorTests(unittest.TestCase):
    def test_neutralization_kinds_red_and_open(self):
        result = neutralizations(
            statuses(["1", "6", "7", "2", "1", "4", "5", "1", "4"])
        )
        self.assertEqual(
            result["releases"], [dict(start_ms=10, clear_ms=40, kinds=["VSC"])]
        )
        self.assertEqual(len(result["cancelled"]), 1)
        self.assertEqual(result["open_episode"], ["SC"])
        self.assertEqual(
            neutralizations(statuses(["4", "6", "1"]))["releases"][0]["kinds"],
            ["SC", "VSC"],
        )

    def test_simultaneous_sequence_and_unknown(self):
        with self.assertRaises(ValueError):
            neutralizations([])
        r = statuses(["4", "1"])
        r[1]["session_time_ms"] = 0
        self.assertEqual(
            neutralizations(list(reversed(r)))["releases"][0]["clear_ms"], 0
        )
        self.assertEqual(neutralizations(r)["simultaneous_times"], [0])
        with self.assertRaises(ValueError):
            neutralizations(statuses(["unknown"]))

    def test_window_union_and_gap(self):
        source = rows()
        for i, r in enumerate(source):
            r.update(lap_start_ms=i * 100, session_time_ms=(i + 1) * 100)
        original = describe_stint(source)
        result = apply_windows(
            [original], {"session:1:R": (100,)}, {"session:1:R": [200]}, 2
        )[0]
        self.assertFalse(result["rows"][1]["eligible"])
        self.assertFalse(result["rows"][2]["eligible"])
        self.assertFalse(result["rows"][3]["eligible"])
        self.assertTrue(original["rows"][3]["eligible"])

    def test_influence_known_line_and_shock(self):
        source = rows(100)
        self.assertAlmostEqual(influence(source)["ols"], 0)
        self.assertAlmostEqual(influence(source)["robust"], 0)
        source[0]["lap_time_ms"] += 40000
        result = influence(source)
        self.assertGreater(result["ols"], result["robust"])

    def test_held_event_not_in_training_and_future_not_in_anchor(self):
        stints = []
        for i in range(3):
            source = rows(100)
            for r in source:
                r["session_id"] = f"session:{i}:R"
                r["eligible"] = True
            stints.append(describe_stint(source))
        first = transfer_benchmark(stints)
        target = next(r for r in first if r["session_id"] == "session:0:R")
        self.assertNotIn("session:0:R", target["training_sessions"])
        self.assertFalse(set(target["anchor_laps"]) & set(target["test_laps"]))
        self.assertAlmostEqual(target["mae_ms"]["ols"], 0)
        modified = deepcopy(stints)
        for r in modified[0]["rows"][5:]:
            r["lap_time_ms"] += 5000
        modified[0] = describe_stint(modified[0]["rows"])
        after = next(
            r for r in transfer_benchmark(modified) if r["session_id"] == "session:0:R"
        )
        self.assertEqual(after["slopes"], target["slopes"])
        self.assertAlmostEqual(after["mae_ms"]["ols"], 5000)
