"""Elenco do grid: adicionar e remover pilotos no PATCH /catalog/grid.

Usa o grid real em disco (num diretorio temporario), com o catalogo e a
largada historica substituidos por listas fixas. Sem rede e sem banco.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = str(ROOT / "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.schemas.responses import AttributeOverride  # noqa: E402
from app.services import catalog as catalog_service  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from f1_simulator.application.catalog import CatalogEntry  # noqa: E402

ATTRIBUTE_FIELDS = (
    "pace_offset_pct",
    "consistency_factor",
    "tyre_management_factor",
    "aggression",
    "composure",
)


def entry(index: int, team: str = "t1") -> CatalogEntry:
    return CatalogEntry(
        driver_id=f"d{index}",
        driver_name=f"Piloto {index}",
        driver_code=f"P{index}",
        team_id=team,
        team_name=f"Equipe {team}",
    )


def catalog_of(count: int) -> list[CatalogEntry]:
    entries = [entry(index) for index in range(1, count + 1)]
    # Um piloto com duas equipes, para testar que o par identifica o vinculo.
    entries.append(entry(1, team="t2"))
    return entries


class RosterEditTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "grid.json"
        self.missing_presets = Path(directory.name) / "sem-presets.json"
        self.catalog = catalog_of(3)
        self.patches = [
            patch.object(catalog_service, "CURRENT_GRID_JSON", self.path),
            patch.object(catalog_service, "DRIVER_PRESETS_JSON", self.missing_presets),
            patch.object(catalog_service, "list_entries", side_effect=lambda: self.catalog),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.start_grid(("d1@t1", "d2@t1"))

    def start_grid(self, pair_ids: tuple[str, ...]) -> None:
        catalog_service.build_grid(
            len(pair_ids), mode="manual", manual_pair_ids=list(pair_ids), seed=5
        )

    def state(self):
        return catalog_service.read_current_grid()

    def driver_ids(self) -> list[str]:
        pairs, _, _ = self.state()
        return [pair.driver_id for pair in pairs]

    def test_add_appends_new_driver_and_keeps_existing_attributes(self) -> None:
        _, before, _ = self.state()

        catalog_service.edit_current_grid(add=["d3@t1"])

        pairs, attributes, seed = self.state()
        self.assertEqual([p.driver_id for p in pairs], ["d1", "d2", "d3"])
        self.assertEqual(seed, 5)
        for driver_id in ("d1", "d2"):
            self.assertEqual(attributes[driver_id], before[driver_id])
        self.assertEqual(set(attributes["d3"].sources.values()), {"generated"})

    def test_added_driver_matches_full_generation_with_the_same_seed(self) -> None:
        catalog_service.build_grid(
            3, mode="manual", manual_pair_ids=["d1@t1", "d2@t1", "d3@t1"], seed=5
        )
        _, full, _ = self.state()

        self.start_grid(("d1@t1", "d2@t1"))
        catalog_service.edit_current_grid(add=["d3@t1"])
        _, edited, _ = self.state()

        # Os valores dependem so da semente e do ID: o elenco nao altera o piloto.
        self.assertEqual(edited["d3"].archetype, full["d3"].archetype)
        for field in ATTRIBUTE_FIELDS:
            self.assertEqual(
                getattr(edited["d3"], field), getattr(full["d3"], field), field
            )

    def test_remove_drops_driver_and_keeps_the_rest_in_order(self) -> None:
        catalog_service.edit_current_grid(add=["d3@t1"])

        catalog_service.edit_current_grid(remove=["d2"])

        pairs, attributes, _ = self.state()
        self.assertEqual([p.driver_id for p in pairs], ["d1", "d3"])
        self.assertNotIn("d2", attributes)

    def test_remove_then_add_same_driver_with_another_team_is_allowed(self) -> None:
        catalog_service.edit_current_grid(remove=["d1"], add=["d1@t2"])

        pairs, _, _ = self.state()
        self.assertEqual([(p.driver_id, p.team_id) for p in pairs],
                         [("d2", "t1"), ("d1", "t2")])

    def test_order_must_cover_the_resulting_roster(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            catalog_service.edit_current_grid(add=["d3@t1"], order=["d1", "d2"])
        self.assertEqual(caught.exception.status_code, 422)

        catalog_service.edit_current_grid(add=["d3@t1"], order=["d3", "d2", "d1"])
        self.assertEqual(self.driver_ids(), ["d3", "d2", "d1"])

    def test_grid_may_not_become_empty(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            catalog_service.edit_current_grid(remove=["d1", "d2"])
        self.assertEqual(caught.exception.status_code, 422)

    def test_grid_may_not_exceed_forty_drivers(self) -> None:
        self.catalog = [entry(index) for index in range(1, 42)]
        self.start_grid(tuple(f"d{index}@t1" for index in range(1, 41)))

        with self.assertRaises(HTTPException) as caught:
            catalog_service.edit_current_grid(add=["d41@t1"])
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(len(self.driver_ids()), 40)

    def test_invalid_edit_leaves_the_stored_grid_untouched(self) -> None:
        before = self.path.read_bytes()

        for kwargs in (
            {"remove": ["d9"]},
            {"add": ["d9@t9"]},
            {"add": ["d2@t1"]},
            {"add": ["d3@t1"], "remove": ["d3"]},
            {"remove": ["d1", "d1"]},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(HTTPException):
                    catalog_service.edit_current_grid(**kwargs)
                self.assertEqual(self.path.read_bytes(), before)

    def test_overrides_for_a_removed_driver_are_rejected(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            catalog_service.edit_current_grid(
                remove=["d2"],
                overrides=[AttributeOverride(driver_id="d2", aggression=1.1)],
            )
        self.assertEqual(caught.exception.status_code, 422)

    def test_race_largada_above_forty_is_rejected(self) -> None:
        pairs = [f"d{index}@t1" for index in range(1, 42)]
        with (
            patch.object(catalog_service, "_race_pair_ids", return_value=pairs),
            self.assertRaises(HTTPException) as caught,
        ):
            catalog_service.build_grid(
                None, mode="race", manual_pair_ids=[], seed=7, race_id="race:big"
            )
        self.assertEqual(caught.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
