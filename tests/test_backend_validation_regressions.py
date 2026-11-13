"""Contratos HTTP de validacao e preservacao de dados da issue #170."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.main import app  # noqa: E402
from app.services import catalog  # noqa: E402

from tests.test_grid_ordering import attributes, grid  # noqa: E402


class BackendValidationRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_duplicate_overrides_reject_entire_patch_without_changing_grid(
        self,
    ) -> None:
        path = self.root / "grid.json"
        with patch.object(catalog, "CURRENT_GRID_JSON", path):
            catalog._write_current_grid(grid(), attributes(grid()), 42)
            before = path.read_bytes()
            for overrides in (
                [
                    {"driver_id": "driver:1", "aggression": 1.2},
                    {"driver_id": "driver:1", "composure": 1.3},
                ],
                [
                    {"driver_id": "driver:1", "aggression": 1.2},
                    {"driver_id": "driver:1", "aggression": 1.4},
                ],
            ):
                with self.subTest(overrides=overrides):
                    response = self.client.patch(
                        "/catalog/grid",
                        json={
                            "order": ["driver:3", "driver:2", "driver:1"],
                            "overrides": overrides,
                        },
                    )
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertEqual(path.read_bytes(), before)

            with patch.object(catalog, "driver_profiles", return_value=({}, None)):
                response = self.client.patch(
                    "/catalog/grid",
                    json={
                        "order": ["driver:3", "driver:2", "driver:1"],
                        "overrides": [
                            {"driver_id": "driver:1", "aggression": 1.2},
                            {"driver_id": "driver:2", "composure": 1.3},
                        ],
                    },
                )
            self.assertEqual(response.status_code, 200, response.text)
            entries, updated, seed = catalog.read_current_grid()
            self.assertEqual(
                [item.driver_id for item in entries],
                ["driver:3", "driver:2", "driver:1"],
            )
            self.assertEqual(updated["driver:1"].aggression, 1.2)
            self.assertEqual(updated["driver:2"].composure, 1.3)
            self.assertEqual(seed, 42)

    def test_invalid_saved_race_types_do_not_persist_or_modify_existing_data(
        self,
    ) -> None:
        existing = self.root / "existing.json"
        existing.write_text('{"existing": true}', encoding="utf-8")
        with patch.object(catalog, "SAVED_RACES_DIR", self.root):
            for field, invalid in (
                ("setup", None),
                ("setup", []),
                ("classification", None),
                ("classification", {}),
                ("classification", "not a list"),
            ):
                with self.subTest(field=field, invalid=invalid):
                    race = {"setup": {}, "classification": []}
                    race[field] = invalid
                    response = self.client.post(
                        "/simulation/saved", json={"race": race}
                    )
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertEqual(list(self.root.iterdir()), [existing])
                    self.assertEqual(
                        existing.read_text(encoding="utf-8"), '{"existing": true}'
                    )

            race = {"setup": {}, "classification": [], "extra": {"legacy": True}}
            response = self.client.post("/simulation/saved", json={"race": race})
            self.assertEqual(response.status_code, 200, response.text)
            opened = self.client.get(f"/simulation/saved/{response.json()['id']}")
            self.assertEqual(opened.status_code, 200, opened.text)
            self.assertEqual(opened.json(), race)

    def test_empty_stage_is_rejected_by_http_contract(self) -> None:
        for stages in ([[]], [[{"driver_id": "A", "position": 1}], []]):
            with self.subTest(stages=stages):
                response = self.client.post(
                    "/championship/standings", json={"stages": stages}
                )
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn("etapa vazia", response.json()["detail"])
