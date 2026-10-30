"""Defaults de voltas observados e assumidos, com proveniência explícita."""

from __future__ import annotations

import unittest

from f1_simulator.application.default_laps import (
    ASSUMED_DISTANCE_RULE,
    LATEST_OBSERVED_RACE,
    default_laps_for_circuit,
)
from f1_simulator.domain.history import HistoricalRecord


def record(table: str, **fields: object) -> HistoricalRecord:
    return HistoricalRecord(table, tuple(fields.items()))


class MemoryHistory:
    def __init__(self, *records: HistoricalRecord) -> None:
        self._records = records

    def records(self, table: str, **filters: object):
        return iter(
            row
            for row in self._records
            if row.table == table
            and all(row[field] == value for field, value in filters.items())
        )

    def reports(self) -> list[dict[str, object]]:
        return []


class DefaultLapsTest(unittest.TestCase):
    def test_most_recent_race_supplies_maximum_completed_laps(self) -> None:
        history = MemoryHistory(
            record(
                "races",
                race_id="race:old",
                circuit_id="circuit:18",
                season=2023,
                round_number=21,
            ),
            record(
                "races",
                race_id="race:new",
                circuit_id="circuit:18",
                season=2024,
                round_number=21,
            ),
            record("race_results", race_id="race:old", laps_completed=71),
            record("race_results", race_id="race:new", laps_completed=68),
            record("race_results", race_id="race:new", laps_completed=69),
        )

        result = default_laps_for_circuit("circuit:18", 4_231.626, history)

        self.assertEqual(result.laps, 69)
        self.assertEqual(result.source, LATEST_OBSERVED_RACE)
        self.assertEqual(result.race.race_id, "race:new")
        self.assertEqual(result.race.season, 2024)
        self.assertEqual(result.race.round_number, 21)

    def test_shortened_latest_race_is_preserved_as_observed(self) -> None:
        history = MemoryHistory(
            record(
                "races",
                race_id="race:full",
                circuit_id="circuit:13",
                season=2020,
                round_number=7,
            ),
            record(
                "races",
                race_id="race:red-flag",
                circuit_id="circuit:13",
                season=2021,
                round_number=12,
            ),
            record("race_results", race_id="race:full", laps_completed=44),
            record("race_results", race_id="race:red-flag", laps_completed=1),
        )

        result = default_laps_for_circuit("circuit:13", 7_004.0, history)

        self.assertEqual(result.laps, 1)
        self.assertEqual(result.race.race_id, "race:red-flag")

    def test_newer_event_without_completed_laps_is_not_an_observed_race(self) -> None:
        history = MemoryHistory(
            record(
                "races",
                race_id="race:observed",
                circuit_id="circuit:18",
                season=2024,
                round_number=21,
            ),
            record(
                "races",
                race_id="race:cancelled",
                circuit_id="circuit:18",
                season=2025,
                round_number=21,
            ),
            record("race_results", race_id="race:observed", laps_completed=69),
        )

        result = default_laps_for_circuit("circuit:18", 4_231.626, history)

        self.assertEqual(result.laps, 69)
        self.assertEqual(result.race.race_id, "race:observed")

    def test_circuit_without_history_uses_strict_305_km_rule(self) -> None:
        result = default_laps_for_circuit("circuit:999", 5_000.0, MemoryHistory())

        self.assertEqual(result.laps, 62)
        self.assertEqual(result.source, ASSUMED_DISTANCE_RULE)
        self.assertIsNone(result.race)
        self.assertGreater(result.laps * 5_000.0, 305_000.0)
        self.assertLessEqual((result.laps - 1) * 5_000.0, 305_000.0)

    def test_monaco_is_identified_by_trotman_id_and_uses_260_km(self) -> None:
        result = default_laps_for_circuit("6", 3_337.0)

        self.assertEqual(result.laps, 78)
        self.assertEqual(result.source, ASSUMED_DISTANCE_RULE)
        self.assertGreater(result.laps * 3_337.0, 260_000.0)
        self.assertLessEqual((result.laps - 1) * 3_337.0, 260_000.0)


if __name__ == "__main__":
    unittest.main()
