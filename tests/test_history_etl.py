"""Contract/rollback tests for the complete 14-file historical ingestion."""

import csv
import hashlib
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from f1_simulator.adapters.datasets.trotman import TrotmanDatasetError
from f1_simulator.adapters.datasets.trotman_history import (
    MAPPINGS,
    TrotmanHistoryAdapter,
    duration_ms,
)
from f1_simulator.adapters.persistence.sqlite_history import (
    SQLiteHistoryRepository,
    SQLiteHistoryWriter,
)
from f1_simulator.application.history_etl import run_history_etl
from f1_simulator.domain.history import HISTORY_SCHEMA, Column, Table
from f1_simulator.factories.history_factory import (
    HistoryFactory,
    HistoryValidationError,
)
from tests.history_support import FIXTURE, make_history


class HistoryEtlTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "history.sqlite"

    def test_complete_schema_is_preserved_and_readable_by_python_and_race_repository(
        self,
    ):
        report = make_history(self.database)
        self.assertEqual(len(report["row_counts"]), 14)
        self.assertEqual(report["row_counts"]["laps"], 6)
        self.assertEqual(report["row_counts"]["qualifying"], 2)
        self.assertEqual(report["row_counts"]["sprint_results"], 2)
        self.assertEqual(len(report["source"]["files"]), 14)
        repository = SQLiteHistoryRepository(self.database)
        self.assertEqual(repository.reports()[0], report)
        driver = next(repository.records("drivers", driver_id="driver:830"))
        self.assertEqual(driver["driver_ref"], "max_verstappen")
        self.assertEqual(driver["birth_date"], "1997-09-30")
        race = repository.get_race("race:1141")
        self.assertEqual(race.race.season, 2024)
        self.assertEqual(len(race.drivers), 2)
        self.assertEqual(len(race.source_ids), 6)
        for name, (filename, mapping) in MAPPINGS.items():
            with (FIXTURE / filename).open() as stream:
                self.assertEqual(set(next(csv.reader(stream))), set(mapping))
            derived = {"record_number"} if name == "laps" else set()
            self.assertEqual(
                set(mapping.values()) | derived, set(HISTORY_SCHEMA[name].names)
            )

    def test_preserves_conflicting_laps_and_rejects_ambiguous_race_projection(self):
        source = self.root / "source"
        shutil.copytree(FIXTURE, source)
        path = source / "lap_times.csv"
        with path.open() as stream:
            rows = list(csv.reader(stream))
        duplicate = rows[1].copy()
        duplicate[-1] = str(int(duplicate[-1]) + 1)
        with path.open("a") as stream:
            csv.writer(stream).writerow(duplicate)
        report = run_history_etl(
            TrotmanHistoryAdapter(source), SQLiteHistoryWriter(), self.database
        )
        self.assertEqual(report["row_counts"]["laps"], 7)
        self.assertEqual(report["business_key_warnings"]["conflicting_lap_keys"], 1)
        with self.assertRaisesRegex(HistoryValidationError, "multiple observations"):
            SQLiteHistoryRepository(self.database).get_race("race:1141")

    def test_failure_does_not_replace_existing_output_or_leave_partial_artifacts(self):
        make_history(self.database)
        before = hashlib.sha256(self.database.read_bytes()).hexdigest()
        source = self.root / "bad-source"
        shutil.copytree(FIXTURE, source)
        path = source / "drivers.csv"
        with path.open() as stream:
            duplicate = list(csv.reader(stream))[1]
        with path.open("a") as stream:
            csv.writer(stream).writerow(duplicate)
        with self.assertRaises(sqlite3.IntegrityError):
            run_history_etl(
                TrotmanHistoryAdapter(source),
                SQLiteHistoryWriter(),
                self.database,
                overwrite=True,
            )
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(), before)
        self.assertFalse(list(self.root.glob("*.tmp")))
        with self.assertRaises(FileExistsError):
            make_history(self.database)

    def test_missing_file_and_orphan_do_not_publish_an_output(self):
        source = self.root / "source"
        shutil.copytree(FIXTURE, source)
        (source / "qualifying.csv").unlink()
        with self.assertRaises(TrotmanDatasetError):
            run_history_etl(
                TrotmanHistoryAdapter(source), SQLiteHistoryWriter(), self.database
            )
        self.assertFalse(self.database.exists())
        shutil.copy(FIXTURE / "qualifying.csv", source / "qualifying.csv")
        text = (source / "races.csv").read_text().replace(",18,", ",999999,")
        (source / "races.csv").write_text(text)
        with self.assertRaisesRegex(HistoryValidationError, "orphan"):
            run_history_etl(
                TrotmanHistoryAdapter(source), SQLiteHistoryWriter(), self.database
            )
        self.assertFalse(self.database.exists())

    def test_queries_reject_unknown_names_and_do_not_create_missing_database(self):
        repository = SQLiteHistoryRepository(self.database)
        with self.assertRaises(ValueError):
            list(repository.records("drivers; DROP TABLE drivers"))
        with self.assertRaises(ValueError):
            list(repository.records("drivers", arbitrary="1"))
        with self.assertRaises(FileNotFoundError):
            list(repository.records("drivers"))
        self.assertFalse(self.database.exists())

    def test_reingestion_has_stable_canonical_checksum(self):
        first = make_history(self.database)
        second = run_history_etl(
            TrotmanHistoryAdapter(FIXTURE),
            SQLiteHistoryWriter(),
            self.database,
            overwrite=True,
        )
        self.assertEqual(first["canonical_sha256"], second["canonical_sha256"])
        self.assertEqual(first["row_counts"], second["row_counts"])

    def test_multiple_historical_entries_are_preserved_but_not_projected(self):
        source = self.root / "shared-entry"
        shutil.copytree(FIXTURE, source)
        path = source / "results.csv"
        with path.open() as stream:
            reader = csv.DictReader(stream)
            fields, duplicate = reader.fieldnames, next(reader)
        duplicate["resultId"] = "99999999"
        with path.open("a") as stream:
            csv.DictWriter(stream, fieldnames=fields).writerow(duplicate)
        report = run_history_etl(
            TrotmanHistoryAdapter(source), SQLiteHistoryWriter(), self.database
        )
        self.assertEqual(report["row_counts"]["race_results"], 3)
        with self.assertRaisesRegex(HistoryValidationError, "multiple entries"):
            SQLiteHistoryRepository(self.database).get_race("race:1141")

    def test_factory_rejects_boolean_integer_nan_out_of_range_and_bad_date(self):
        table = Table(
            "test",
            (
                Column("key", "int", False, 1),
                Column("value", "float", False, 0, 10),
                Column("date", "date", False),
            ),
            ("key",),
        )
        valid = {"key": 1, "value": 2.5, "date": "2024-01-01"}
        for field, value in (
            ("key", True),
            ("value", float("nan")),
            ("value", 11),
            ("date", "2024-02-31"),
        ):
            with (
                self.subTest(field=field, value=value),
                self.assertRaises(HistoryValidationError),
            ):
                HistoryFactory.build(table, {**valid, field: value})
        self.assertEqual(duration_ms("1:12.345"), 72345)
        self.assertEqual(duration_ms("1:02:03.456"), 3723456)


if __name__ == "__main__":
    unittest.main()
