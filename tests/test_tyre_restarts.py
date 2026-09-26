"""Operational restart boundaries are independent of filtering and tyre changes."""

import unittest
from copy import deepcopy

from f1_simulator.application.analyze_tyre_restarts import (
    restart_times,
    mark_windows,
    analyze_restarts,
)
from tests.test_profile_evaluation import MemoryHistory
from tests.test_driver_profile import CONFIG


class TyreRestartTests(unittest.TestCase):
    def test_initial_repeated_and_multiple_starts(self):
        rows = [
            dict(session_time_ms=t, status=s)
            for t, s in enumerate(
                [
                    "Started",
                    "Started",
                    "Aborted",
                    "Started",
                    "Started",
                    "Aborted",
                    "Started",
                ]
            )
        ]
        self.assertEqual(restart_times(rows), (3, 6))
        with self.assertRaises(ValueError):
            restart_times(rows + [dict(session_time_ms=3, status="Aborted")])
        with self.assertRaises(ValueError):
            restart_times([dict(session_time_ms=None, status="Started")])

    def test_crossing_gaps_and_excluded_anchor(self):
        rows = [
            dict(
                driver_id="a",
                lap_number=n,
                lap_start_ms=start,
                session_time_ms=end,
                eligible=ok,
            )
            for n, start, end, ok in [
                (1, 0, 110, False),
                (2, 110, 120, False),
                (3, 120, 130, True),
                (5, 150, 160, True),
            ]
        ]
        marks = mark_windows(rows, (100,))
        self.assertEqual(marks[0]["anchor_lap"], 2)
        self.assertEqual(rows[0]["spans_resumes"], [100])
        self.assertNotIn("restart_offset", rows[0])
        self.assertEqual([r["restart_offset"] for r in rows[1:]], [1, 2, 4])

    def test_next_restart_and_retired_driver(self):
        rows = [
            dict(driver_id="a", lap_number=n, lap_start_ms=t, session_time_ms=t + 5)
            for n, t in [(1, 10), (2, 110), (3, 210)]
        ]
        rows.append(
            dict(driver_id="retired", lap_number=1, lap_start_ms=10, session_time_ms=15)
        )
        marks = mark_windows(rows, (100, 200))
        self.assertEqual(rows[2]["restart_offset"], 1)
        self.assertEqual(sum(m["anchor_lap"] is None for m in marks), 2)

    def test_no_restart_preserves_all_variants_and_is_reproducible(self):
        r = analyze_restarts(
            MemoryHistory(), session_ids=("session:1:R",), config=CONFIG
        )
        expected = deepcopy(r["summaries"][0])
        expected.pop("window")
        for summary in r["summaries"]:
            current = dict(summary)
            current.pop("window")
            self.assertEqual(current, expected)
        self.assertEqual(
            r,
            analyze_restarts(
                MemoryHistory(), session_ids=("session:1:R",), config=CONFIG
            ),
        )
