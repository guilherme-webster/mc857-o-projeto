from __future__ import annotations

import unittest

from f1_simulator.application.race_data_dto import NormalizedRaceData
from f1_simulator.application.race_data_ingestion import RaceDataIngestionService
from tests.test_race_data_factory import normalized_race_data


class StubDatasetAdapter:
    """Minimal alternate adapter used to verify the application port."""

    def __init__(self, data: NormalizedRaceData) -> None:
        self.data = data
        self.requested_race_ids: list[int] = []

    def load_race(self, race_external_id: int) -> NormalizedRaceData:
        self.requested_race_ids.append(race_external_id)
        return self.data


class RaceDataIngestionServiceTest(unittest.TestCase):
    def test_accepts_any_adapter_that_implements_the_dataset_port(self) -> None:
        adapter = StubDatasetAdapter(normalized_race_data())

        result = RaceDataIngestionService(adapter).load_race(1141)

        self.assertEqual(adapter.requested_race_ids, [1141])
        self.assertEqual(result.source_name, "example/source")
        self.assertEqual(result.race.race_id, "race:1141")
        self.assertEqual(result.entries[0].driver_id, "driver:830")


if __name__ == "__main__":
    unittest.main()
