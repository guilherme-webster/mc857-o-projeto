from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from f1_simulator.adapters.datasets.trotman import TrotmanDatasetAdapter
from f1_simulator.adapters.persistence.sqlite_race_data import SQLiteRaceDataWriter
from f1_simulator.factories.race_data_factory import RaceDataFactory


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "trotman_v128_sample"


class SQLiteRaceDataWriterTest(unittest.TestCase):
    def test_persists_canonical_data_with_valid_foreign_keys(self) -> None:
        normalized = TrotmanDatasetAdapter(FIXTURE).load_race(1141)
        race_data = RaceDataFactory.create(normalized)

        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "race.sqlite"
            SQLiteRaceDataWriter().write(race_data, destination)

            with sqlite3.connect(destination) as connection:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM laps").fetchone(), (6,)
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT value FROM metadata WHERE key = 'source_version'"
                    ).fetchone(),
                    ("128",),
                )
                self.assertEqual(
                    connection.execute("PRAGMA foreign_key_check").fetchall(), []
                )

    def test_refuses_to_replace_existing_output_without_permission(self) -> None:
        normalized = TrotmanDatasetAdapter(FIXTURE).load_race(1141)
        race_data = RaceDataFactory.create(normalized)

        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "race.sqlite"
            destination.write_text("keep me", encoding="utf-8")

            with self.assertRaisesRegex(FileExistsError, "already exists"):
                SQLiteRaceDataWriter().write(race_data, destination)
            self.assertEqual(destination.read_text(encoding="utf-8"), "keep me")


if __name__ == "__main__":
    unittest.main()
