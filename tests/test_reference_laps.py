"""Volta de referencia historica por circuito, do historico ao caso de uso."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from f1_simulator.adapters.reference_laps_json import (
    ReferenceLapsError,
    read_reference_laps,
    write_reference_laps,
)
from f1_simulator.application.build_grid import GridEntry
from f1_simulator.application.reference_laps import (
    METHOD_VERSION,
    ReferenceLap,
    build_reference_laps,
)
from f1_simulator.application.run_grid_simulation import (
    ASSUMED_REFERENCE_PACE_MS_PER_KM,
    RaceSetup,
    run_detailed_grid_simulation,
)
from f1_simulator.domain.random_source import SeededRandomSource
from tests.model_support import parameters
from tests.test_run_grid_detailed import attribute


class FakeHistory:
    """Repositorio em memoria com filtros de igualdade, como a porta exige."""

    def __init__(self, races: list[dict], results: list[dict]) -> None:
        self._tables = {"races": races, "race_results": results}

    def records(self, table: str, **filters):
        for row in self._tables[table]:
            if all(row.get(key) == value for key, value in filters.items()):
                yield row

    def reports(self) -> list[dict]:
        return []


def _race(race_id: str, season: int, circuit_id: str) -> dict:
    return {"race_id": race_id, "season": season, "circuit_id": circuit_id}


def _results(race_id: str, fastest_ms: list[float | None]) -> list[dict]:
    return [
        {"race_id": race_id, "driver_id": f"driver:{i}", "fastest_lap_time_ms": ms}
        for i, ms in enumerate(fastest_ms)
    ]


class BuildReferenceLapsTest(unittest.TestCase):
    def test_median_per_race_then_median_across_races(self) -> None:
        history = FakeHistory(
            races=[
                _race("race:1", 2022, "circuit:6"),
                _race("race:2", 2023, "circuit:6"),
                _race("race:3", 2024, "circuit:6"),
            ],
            results=[
                *_results("race:1", [77_000.0, 78_000.0, 79_000.0]),
                *_results("race:2", [76_000.0, 77_000.0, None]),
                # Corrida de chuva isolada: nao desloca a mediana entre corridas.
                *_results("race:3", [95_000.0, 96_000.0, 97_000.0]),
            ],
        )

        (lap,) = build_reference_laps(
            history, circuit_ids=["circuit:6"], seasons=[2022, 2023, 2024]
        )

        # medianas por corrida: 78_000, 76_500 (None ignorado), 96_000
        self.assertEqual(lap.reference_lap_time_ms, 78_000.0)
        self.assertEqual(lap.races, 3)
        self.assertEqual(lap.seasons, (2022, 2023, 2024))

    def test_circuit_without_data_is_omitted_not_invented(self) -> None:
        history = FakeHistory(
            races=[_race("race:1", 2022, "circuit:6")],
            results=_results("race:1", [77_000.0]),
        )

        laps = build_reference_laps(
            history, circuit_ids=["circuit:6", "circuit:99"], seasons=[2022]
        )

        self.assertEqual([lap.circuit_id for lap in laps], ["circuit:6"])

    def test_seasons_outside_the_interval_are_ignored(self) -> None:
        history = FakeHistory(
            races=[
                _race("race:1", 2021, "circuit:6"),
                _race("race:2", 2022, "circuit:6"),
            ],
            results=[
                *_results("race:1", [60_000.0]),
                *_results("race:2", [80_000.0]),
            ],
        )

        (lap,) = build_reference_laps(
            history, circuit_ids=["circuit:6"], seasons=[2022]
        )

        self.assertEqual(lap.reference_lap_time_ms, 80_000.0)

    def test_rejects_empty_selection(self) -> None:
        history = FakeHistory([], [])
        with self.assertRaises(ValueError):
            build_reference_laps(history, circuit_ids=[], seasons=[2022])
        with self.assertRaises(ValueError):
            build_reference_laps(history, circuit_ids=["circuit:6"], seasons=[])

    def test_reference_lap_validation(self) -> None:
        for bad in (0.0, -1.0, float("nan"), True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ReferenceLap("circuit:6", bad, 1, (2022,))


class ReferenceLapsJsonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "reference-laps-v1.json"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_round_trip(self) -> None:
        laps = (
            ReferenceLap("circuit:6", 77_150.0, 2, (2022, 2023)),
            ReferenceLap("circuit:13", 110_520.0, 3, (2022, 2023, 2024)),
        )
        write_reference_laps(laps, self.path, seasons=[2022, 2023, 2024], source="teste")

        table = read_reference_laps(self.path)

        self.assertEqual(table["circuit:6"], laps[0])
        self.assertEqual(table["circuit:13"], laps[1])
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["method_version"], METHOD_VERSION)
        self.assertEqual(payload["origin"], "historical-median")

    def test_missing_file_raises_file_not_found(self) -> None:
        with self.assertRaises(FileNotFoundError):
            read_reference_laps(self.path)

    def test_invalid_payloads_are_rejected(self) -> None:
        good = {
            "schema_version": 1,
            "method_version": METHOD_VERSION,
            "circuits": [
                {
                    "circuit_id": "circuit:6",
                    "reference_lap_time_ms": 77_000.0,
                    "races": 2,
                    "seasons": [2022, 2023],
                }
            ],
        }
        variants = (
            {**good, "schema_version": 2},
            {**good, "method_version": "outro"},
            {**good, "circuits": [{"circuit_id": "circuit:6"}]},
            {**good, "circuits": good["circuits"] * 2},
        )
        for payload in variants:
            with self.subTest(payload=payload):
                self.path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ReferenceLapsError):
                    read_reference_laps(self.path)
        self.path.write_text("{nao e json", encoding="utf-8")
        with self.assertRaises(ReferenceLapsError):
            read_reference_laps(self.path)

    def test_versioned_artifact_covers_the_track_catalog(self) -> None:
        root = Path(__file__).resolve().parents[1]
        table = read_reference_laps(
            root / "data" / "parameters" / "reference-laps-v1.json"
        )
        manifest = json.loads(
            (root / "data" / "sources" / "fastf1-tracks-2025.json").read_text(
                encoding="utf-8"
            )
        )
        catalog = {
            f"circuit:{event['circuit_id']}" for event in manifest["source"]["events"]
        }
        self.assertEqual(set(table), catalog)
        # Sanidade, nao calibracao: Monaco e mais lento por km que Monza.
        monaco = table["circuit:6"].reference_lap_time_ms
        monza = table["circuit:14"].reference_lap_time_ms
        self.assertTrue(70_000 < monaco < 85_000)
        self.assertTrue(80_000 < monza < 95_000)


class DetailedGridReferenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.grid = (GridEntry("driver:1", "Um", "team:x", "X"),)
        self.attributes = {"driver:1": attribute("driver:1")}
        self.parameters = parameters(dnf_hazard_per_lap=0.0)

    def _run(self, **kwargs) -> dict:
        return run_detailed_grid_simulation(
            self.grid,
            self.attributes,
            RaceSetup(3, "circuit:1"),
            parameters=self.parameters,
            rng=SeededRandomSource(1),
            race_control=None,
            **kwargs,
        )

    @staticmethod
    def _reference_assumption(result: dict) -> dict:
        return next(a for a in result["assumptions"] if a["kind"] == "reference_pace")

    def test_historical_reference_wins_over_pace_per_km(self) -> None:
        result = self._run(
            lap_length_m=4_000.0,
            reference_lap=ReferenceLap("circuit:1", 81_000.0, 3, (2022, 2023, 2024)),
        )

        self.assertEqual(result["reference_lap_time_ms"], 81_000.0)
        assumption = self._reference_assumption(result)
        self.assertEqual(assumption["reference_source"], "historical_median")
        self.assertEqual(assumption["historical_reference"]["races"], 3)

    def test_without_table_entry_falls_back_to_pace_per_km(self) -> None:
        result = self._run(lap_length_m=4_000.0)

        self.assertEqual(
            result["reference_lap_time_ms"],
            4.0 * ASSUMED_REFERENCE_PACE_MS_PER_KM,
        )
        assumption = self._reference_assumption(result)
        self.assertEqual(assumption["reference_source"], "assumed_pace_per_km")
        self.assertIsNone(assumption["historical_reference"])

    def test_reference_for_another_circuit_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._run(
                lap_length_m=4_000.0,
                reference_lap=ReferenceLap("circuit:6", 77_000.0, 2, (2022, 2023)),
            )


if __name__ == "__main__":
    unittest.main()
