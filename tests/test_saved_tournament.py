"""Torneio salvo: invariantes do nucleo, persistencia e reexecucao (#109)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND = str(ROOT / "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.main import app
from app.services import catalog as catalog_service
from app.services import tournaments as tournaments_service

from f1_simulator.application.build_grid import GridEntry
from f1_simulator.application.saved_tournament import (
    SAVED_TOURNAMENT_SCHEMA_VERSION,
    SavedTournamentError,
    build_saved_tournament,
    check_saved_tournament,
    tournament_summary,
)
from f1_simulator.domain.driver_attributes import ATTRIBUTE_FIELDS, DriverAttributes
from tests.model_support import parameters

GRID_SEED = 42
TOURNAMENT_SEED = 109


def grid_objects() -> tuple:
    entries = (
        GridEntry("driver:1", "Piloto Um", "team:1", "Equipe Um"),
        GridEntry("driver:2", "Piloto Dois", "team:2", "Equipe Dois"),
    )
    attributes = {
        entry.driver_id: DriverAttributes(
            driver_id=entry.driver_id,
            archetype="balanced",
            pace_offset_pct=0.1 * index,
            consistency_factor=1.0,
            tyre_management_factor=1.0,
            aggression=1.0,
            composure=1.0,
            sources={name: "generated" for name in ATTRIBUTE_FIELDS},
        )
        for index, entry in enumerate(entries)
    }
    return entries, attributes, GRID_SEED


def grid_state() -> dict:
    return catalog_service._serialize_grid(*grid_objects())


def race(stage_index: int, *, order=("driver:1", "driver:2"), grid_seed=GRID_SEED):
    """Resultado minimo no formato devolvido por ``POST /catalog/grid/run``."""

    return {
        "seed": grid_seed,
        "grid_seed": grid_seed,
        "tournament_seed": TOURNAMENT_SEED,
        "stage_index": stage_index,
        "setup": {"total_laps": 3, "track_id": "circuit:1", "weather": []},
        "starting_grid": [
            {"position": position, "driver_id": driver_id}
            for position, driver_id in enumerate(order, start=1)
        ],
        "classification": [
            {"position": 1, "driver_id": order[1], "status": "RUNNING"},
            {"position": 2, "driver_id": order[0], "status": "RUNNING"},
        ],
    }


def stage(stage_index: int, **race_options) -> dict:
    return {
        "name": f"Etapa {stage_index + 1}",
        "circuit_id": "circuit:1",
        "plan": {"laps": 3, "weather_by_lap": ["Seco"] * 3},
        "setup": {
            "total_laps": 3,
            "track_id": "circuit:1",
            "weather": [],
            "engine": "detailed",
            "tournament_seed": TOURNAMENT_SEED,
            "stage_index": stage_index,
        },
        "race": race(stage_index, **race_options),
    }


def build(**overrides) -> dict:
    arguments = {
        "tournament_id": "copa-abc123",
        "name": "Copa",
        "saved_at": "2026-10-30T12:00:00+00:00",
        "grid_state": grid_state(),
        "rules": {"name": "Copa", "scoring": "F1 oficial"},
        "tournament_seed": TOURNAMENT_SEED,
        "stages": [stage(0), stage(1)],
    }
    arguments.update(overrides)
    return build_saved_tournament(**arguments)


class SavedTournamentContractTest(unittest.TestCase):
    def test_record_is_versioned_and_keeps_grid_setups_and_races(self) -> None:
        record = build()

        self.assertEqual(record["schema_version"], SAVED_TOURNAMENT_SCHEMA_VERSION)
        self.assertEqual(record["grid"], grid_state())
        self.assertEqual(
            [item["setup"]["stage_index"] for item in record["stages"]], [0, 1]
        )
        self.assertEqual(record["stages"][1]["race"], race(1))
        check_saved_tournament(record)
        self.assertEqual(
            tournament_summary(record),
            {
                "id": "copa-abc123",
                "name": "Copa",
                "saved_at": "2026-10-30T12:00:00+00:00",
                "stage_count": 2,
                "circuits": ["circuit:1", "circuit:1"],
                "tournament_seed": TOURNAMENT_SEED,
                "grid_seed": GRID_SEED,
                "car_count": 2,
            },
        )

    def test_rejects_races_simulated_with_another_grid(self) -> None:
        cases = {
            "seed": [stage(0, grid_seed=7)],
            "ordem": [stage(0, order=("driver:2", "driver:1"))],
        }
        for label, stages in cases.items():
            with self.subTest(label), self.assertRaises(SavedTournamentError):
                build(stages=stages)

    def test_rejects_setup_that_would_rerun_a_different_race(self) -> None:
        wrong_index = stage(1)
        wrong_index["setup"]["stage_index"] = 0
        wrong_laps = stage(0)
        wrong_laps["setup"]["total_laps"] = 4
        cases = {
            "indice": [stage(0), wrong_index],
            "voltas": [wrong_laps],
            "seed do torneio": [stage(0)],
        }
        for label, stages in cases.items():
            seed = 1 if label == "seed do torneio" else TOURNAMENT_SEED
            with self.subTest(label), self.assertRaises(SavedTournamentError):
                build(stages=stages, tournament_seed=seed)

    def test_rejects_unknown_schema_version_on_read(self) -> None:
        record = build()
        record["schema_version"] = SAVED_TOURNAMENT_SCHEMA_VERSION + 1
        with self.assertRaises(SavedTournamentError):
            check_saved_tournament(record)


class SavedTournamentApiTest(unittest.TestCase):
    """Rotas reais sobre diretorios temporarios no lugar de ``/data``."""

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.grid_path = self.root / "current-grid.json"
        self.saved_dir = self.root / "saved-tournaments"
        stack = ExitStack()
        for module in (catalog_service, tournaments_service):
            stack.enter_context(
                patch.object(module, "CURRENT_GRID_JSON", self.grid_path)
            )
        stack.enter_context(
            patch.object(tournaments_service, "SAVED_TOURNAMENTS_DIR", self.saved_dir)
        )
        self.addCleanup(stack.close)
        self.addCleanup(self._directory.cleanup)
        catalog_service._write_current_grid(*grid_objects())
        self.client = TestClient(app)

    def save_body(self) -> dict:
        record = build()
        return {
            "name": "Copa de teste",
            "rules": record["rules"],
            "tournament_seed": TOURNAMENT_SEED,
            "stages": [
                {
                    key: item[key]
                    for key in ("name", "circuit_id", "plan", "setup", "race")
                }
                for item in record["stages"]
            ],
        }

    def test_save_list_open_and_restore_grid(self) -> None:
        saved = self.client.post("/tournaments", json=self.save_body())
        self.assertEqual(saved.status_code, 200, saved.text)
        meta = saved.json()
        self.assertEqual(meta["stage_count"], 2)
        self.assertTrue(meta["id"].startswith("copa-de-teste-"))

        listing = self.client.get("/tournaments").json()
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["saved"][0]["id"], meta["id"])

        opened = self.client.get(f"/tournaments/{meta['id']}").json()
        self.assertEqual(opened["stages"][0]["race"], race(0))
        self.assertEqual(opened["grid"], grid_state())

        # O usuario remonta o grid; restaurar volta exatamente ao congelado.
        entries, attributes, _ = grid_objects()
        catalog_service._write_current_grid(tuple(reversed(entries)), attributes, 7)
        restored = self.client.post(f"/tournaments/{meta['id']}/restore-grid")
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["seed"], GRID_SEED)
        self.assertEqual(
            json.loads(self.grid_path.read_text(encoding="utf-8")), grid_state()
        )

    def test_save_refuses_grid_changed_after_simulation(self) -> None:
        entries, attributes, _ = grid_objects()
        catalog_service._write_current_grid(
            tuple(reversed(entries)), attributes, GRID_SEED
        )

        response = self.client.post("/tournaments", json=self.save_body())

        self.assertEqual(response.status_code, 409)
        self.assertIn("ordem de largada", response.json()["detail"])
        self.assertFalse(self.saved_dir.exists())

    def test_open_rejects_unknown_and_path_like_ids(self) -> None:
        self.assertEqual(self.client.get("/tournaments/inexistente").status_code, 404)
        with self.assertRaises(HTTPException) as raised:
            tournaments_service.read_saved_tournament("../..")
        self.assertEqual(raised.exception.status_code, 422)

    def test_listing_skips_unreadable_files(self) -> None:
        self.saved_dir.mkdir()
        (self.saved_dir / "quebrado.json").write_text("{", encoding="utf-8")
        (self.saved_dir / "antigo.json").write_text(
            json.dumps({"schema_version": 0}), encoding="utf-8"
        )
        self.assertEqual(self.client.get("/tournaments").json()["count"], 0)


class SavedTournamentRerunTest(unittest.TestCase):
    """Salvar, remontar o grid, restaurar e rodar de novo da o mesmo torneio."""

    def test_rerun_after_restore_reproduces_saved_races(self) -> None:
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            for module in (catalog_service, tournaments_service):
                stack.enter_context(
                    patch.object(module, "CURRENT_GRID_JSON", root / "grid.json")
                )
            for name, value in (
                ("CURRENT_RACE_JSON", root / "race.json"),
                ("SAVED_RACES_DIR", root / "saved-races"),
            ):
                stack.enter_context(patch.object(catalog_service, name, value))
            stack.enter_context(
                patch.object(
                    tournaments_service, "SAVED_TOURNAMENTS_DIR", root / "tournaments"
                )
            )
            stack.enter_context(
                patch.object(
                    catalog_service, "_model_parameters", return_value=parameters()
                )
            )
            stack.enter_context(
                patch.object(
                    catalog_service,
                    "_track_reference",
                    return_value=("circuit:1", 4_000.0),
                )
            )
            client = TestClient(app)
            catalog_service._write_current_grid(*grid_objects())

            setups = [
                {
                    "total_laps": 4,
                    "track_id": "circuit:1",
                    "tournament_seed": TOURNAMENT_SEED,
                    "stage_index": index,
                }
                for index in range(2)
            ]
            first = [
                client.post("/catalog/grid/run", json={"setup": setup}).json()
                for setup in setups
            ]
            self.assertTrue(all("classification" in item for item in first), first)
            body = {
                "name": "Reexecucao",
                "rules": {},
                "tournament_seed": TOURNAMENT_SEED,
                "stages": [
                    {
                        "name": f"Etapa {index + 1}",
                        "circuit_id": "circuit:1",
                        "plan": {},
                        "setup": setup,
                        "race": result,
                    }
                    for index, (setup, result) in enumerate(zip(setups, first))
                ],
            }
            saved = client.post("/tournaments", json=body)
            self.assertEqual(saved.status_code, 200, saved.text)
            tournament_id = saved.json()["id"]

            entries, attributes, _ = grid_objects()
            catalog_service._write_current_grid(tuple(reversed(entries)), attributes, 7)
            client.post(f"/tournaments/{tournament_id}/restore-grid")
            record = client.get(f"/tournaments/{tournament_id}").json()
            second = [
                client.post("/catalog/grid/run", json={"setup": item["setup"]}).json()
                for item in record["stages"]
            ]

        for before, after in zip(first, second):
            self.assertEqual(after["classification"], before["classification"])
            self.assertEqual(after["race_seed"], before["race_seed"])


if __name__ == "__main__":
    unittest.main()
