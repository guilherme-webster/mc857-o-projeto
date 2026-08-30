from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from f1_simulator.application.etl import run_trotman_etl


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "trotman_v128_sample"


class TrotmanEtlTest(unittest.TestCase):
    def test_ingests_fixture_into_canonical_sqlite_and_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            database = temporary / "race.sqlite"
            report_path = temporary / "quality.json"

            report = run_trotman_etl(
                FIXTURE,
                1141,
                database,
                report_path,
            )

            self.assertEqual(
                report["row_counts"],
                {
                    "circuits": 1,
                    "races": 1,
                    "drivers": 2,
                    "teams": 2,
                    "race_entries": 2,
                    "laps": 6,
                    "pit_stops": 2,
                },
            )
            self.assertEqual(report["duplicate_keys"], 0)
            self.assertEqual(report["orphan_references"], 0)
            self.assertEqual(report["warnings"]["pit_stops_over_300_seconds"], 2)
            self.assertEqual(
                json.loads(report_path.read_text(encoding="utf-8")), report
            )

            with sqlite3.connect(database) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT race_id, season, round_number FROM races"
                    ).fetchone(),
                    ("race:1141", 2024, 21),
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT lap_time_ms FROM laps "
                        "WHERE driver_id = 'driver:830' AND lap_number = 3"
                    ).fetchone(),
                    (86240,),
                )
                self.assertEqual(
                    connection.execute("PRAGMA foreign_key_check").fetchall(), []
                )


if __name__ == "__main__":
    unittest.main()
