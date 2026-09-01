from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from f1_simulator.adapters.datasets.trotman import (
    TrotmanDatasetAdapter,
    TrotmanDatasetError,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "trotman_v128_sample"


class TrotmanDatasetAdapterTest(unittest.TestCase):
    def test_normalizes_a_race_without_creating_domain_objects(self) -> None:
        normalized = TrotmanDatasetAdapter(FIXTURE).load_race(1141)

        self.assertEqual(normalized.source_version, 128)
        self.assertEqual(normalized.race["race_date"].isoformat(), "2024-11-03")
        self.assertEqual(normalized.circuit["latitude_deg"], -23.7036)
        self.assertEqual(normalized.entries[0]["driver_external_id"], "830")
        self.assertEqual(normalized.laps[0]["lap_time_ms"], 99_161)

    def test_rejects_race_without_results(self) -> None:
        with self.assertRaisesRegex(TrotmanDatasetError, "not found: raceId=9999"):
            TrotmanDatasetAdapter(FIXTURE).load_race(9999)

    def test_rejects_archive_that_does_not_match_version_128_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive = Path(temporary_directory) / "other-version.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("races.csv", "raceId\n1141\n")
            with self.assertRaisesRegex(TrotmanDatasetError, "checksum"):
                TrotmanDatasetAdapter(archive)


if __name__ == "__main__":
    unittest.main()
