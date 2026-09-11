"""Integration tests for reading the canonical SQLite representation."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from f1_simulator.adapters.datasets.trotman import TrotmanDatasetAdapter
from f1_simulator.adapters.persistence.sqlite_race_data import SQLiteRaceDataWriter
from f1_simulator.adapters.persistence.sqlite_race_data_repository import (
    SQLiteRaceDataRepository,
)
from f1_simulator.application.ports.race_data import (
    RaceDataNotFoundError,
    RaceDataRepositoryError,
)
from f1_simulator.factories.race_data_factory import RaceDataFactory


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "trotman_v128_sample"


class SQLiteRaceDataRepositoryTest(unittest.TestCase):
    """Verify the complete writer-to-reader boundary and its failure modes."""

    def test_rejects_an_empty_canonical_race_id(self) -> None:
        repository = SQLiteRaceDataRepository(Path("unused.sqlite"))

        with self.assertRaisesRegex(ValueError, "race_id must be non-empty"):
            repository.get_race("  ")

    def test_reconstructs_the_complete_canonical_aggregate(self) -> None:
        expected = RaceDataFactory.create(
            TrotmanDatasetAdapter(FIXTURE).load_race(1141)
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "race.sqlite"
            SQLiteRaceDataWriter().write(expected, database)

            actual = SQLiteRaceDataRepository(database).get_race("race:1141")

        # Full equality covers metadata and every circuit, participant, lap,
        # stop and source-ID field rather than only proving that SQL returned.
        self.assertEqual(actual, expected)

    def test_reports_a_missing_race_separately_from_storage_failures(self) -> None:
        race_data = RaceDataFactory.create(
            TrotmanDatasetAdapter(FIXTURE).load_race(1141)
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "race.sqlite"
            SQLiteRaceDataWriter().write(race_data, database)

            with self.assertRaisesRegex(RaceDataNotFoundError, "race:9999"):
                SQLiteRaceDataRepository(database).get_race("race:9999")

    def test_does_not_create_a_database_when_the_source_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "missing.sqlite"

            with self.assertRaisesRegex(
                RaceDataRepositoryError, "database does not exist"
            ):
                SQLiteRaceDataRepository(database).get_race("race:1141")

            self.assertFalse(database.exists())

    def test_translates_an_invalid_schema_to_a_repository_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "invalid.sqlite"
            with closing(sqlite3.connect(database)):
                pass

            with self.assertRaisesRegex(
                RaceDataRepositoryError, "cannot read canonical race database"
            ):
                SQLiteRaceDataRepository(database).get_race("race:1141")

    def test_rejects_foreign_key_violations_before_loading(self) -> None:
        race_data = RaceDataFactory.create(
            TrotmanDatasetAdapter(FIXTURE).load_race(1141)
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "race.sqlite"
            SQLiteRaceDataWriter().write(race_data, database)
            with closing(sqlite3.connect(database)) as connection:
                # New SQLite connections disable FK enforcement by default.
                # This simulates a curated file modified outside our writer.
                connection.execute(
                    "INSERT INTO laps VALUES (?, ?, ?, ?, ?)",
                    ("race:1141", "driver:missing", 1, 90_000, 1),
                )
                connection.commit()

            with self.assertRaisesRegex(
                RaceDataRepositoryError, "foreign-key violations"
            ):
                SQLiteRaceDataRepository(database).get_race("race:1141")

    def test_rejects_a_missing_source_identifier(self) -> None:
        race_data = RaceDataFactory.create(
            TrotmanDatasetAdapter(FIXTURE).load_race(1141)
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "race.sqlite"
            SQLiteRaceDataWriter().write(race_data, database)
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    """
                    DELETE FROM source_ids
                    WHERE entity_type = 'driver' AND canonical_id = 'driver:830'
                    """
                )
                connection.commit()

            with self.assertRaisesRegex(
                RaceDataRepositoryError, "exactly one source identifier"
            ):
                SQLiteRaceDataRepository(database).get_race("race:1141")


if __name__ == "__main__":
    unittest.main()
