"""Permutacao do grid e contrato PATCH entre nucleo e backend."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
BACKEND = str(ROOT / "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.routers import catalog as catalog_router  # noqa: E402
from app.schemas.responses import (  # noqa: E402
    AttributeOverride,
    EditGridAttributesRequest,
)
from app.services import catalog as catalog_service  # noqa: E402
from f1_simulator.application.build_grid import (  # noqa: E402
    GridEntry,
    GridOrderError,
    reorder_grid,
)
from f1_simulator.domain.driver_attributes import (  # noqa: E402
    ATTRIBUTE_FIELDS,
    DriverAttributes,
)


def grid() -> tuple[GridEntry, ...]:
    return (
        GridEntry("driver:1", "Primeiro", "team:1", "Equipe 1"),
        GridEntry("driver:2", "Segundo", "team:2", "Equipe 2"),
        GridEntry("driver:3", "Terceiro", "team:3", "Equipe 3"),
    )


def attributes(entries: tuple[GridEntry, ...]) -> dict[str, DriverAttributes]:
    return {
        entry.driver_id: DriverAttributes(
            driver_id=entry.driver_id,
            archetype="balanced",
            pace_offset_pct=index / 10,
            consistency_factor=1.0,
            tyre_management_factor=1.0,
            aggression=1.0,
            composure=1.0,
            sources={name: "preset" for name in ATTRIBUTE_FIELDS},
        )
        for index, entry in enumerate(entries)
    }


class ReorderGridTest(unittest.TestCase):
    def test_valid_permutation_reuses_the_existing_entries(self) -> None:
        current = grid()

        reordered = reorder_grid(current, ["driver:3", "driver:1", "driver:2"])

        self.assertEqual(
            [entry.driver_id for entry in reordered],
            ["driver:3", "driver:1", "driver:2"],
        )
        self.assertIs(reordered[0], current[2])

    def test_rejects_duplicate_id(self) -> None:
        with self.assertRaisesRegex(GridOrderError, "IDs duplicados"):
            reorder_grid(grid(), ["driver:1", "driver:1", "driver:3"])

    def test_rejects_missing_id(self) -> None:
        with self.assertRaisesRegex(GridOrderError, "IDs ausentes.*driver:2"):
            reorder_grid(grid(), ["driver:1", "driver:3"])

    def test_rejects_unknown_id(self) -> None:
        with self.assertRaisesRegex(GridOrderError, "IDs desconhecidos.*driver:99"):
            reorder_grid(grid(), ["driver:1", "driver:2", "driver:99"])


class EditGridRequestTest(unittest.TestCase):
    def test_requires_order_or_overrides(self) -> None:
        with self.assertRaises(ValidationError):
            EditGridAttributesRequest()

    def test_route_forwards_order_and_overrides_together(self) -> None:
        entries = grid()
        items = attributes(entries)
        request = EditGridAttributesRequest(
            order=["driver:2", "driver:1", "driver:3"],
            overrides=[AttributeOverride(driver_id="driver:1", aggression=1.2)],
        )
        with (
            patch.object(
                catalog_router.catalog,
                "edit_current_grid",
                return_value=(entries, items, 71),
            ) as edit,
            patch.object(
                catalog_router.catalog, "driver_profiles", return_value=({}, None)
            ),
        ):
            response = catalog_router.edit_grid_attributes(request)

        self.assertEqual(response.seed, 71)
        edit.assert_called_once_with(
            overrides=request.overrides,
            order=["driver:2", "driver:1", "driver:3"],
        )


class EditCurrentGridServiceTest(unittest.TestCase):
    def test_persists_order_while_preserving_attributes_profiles_and_seed(self) -> None:
        entries = grid()
        items = attributes(entries)
        with TemporaryDirectory() as raw:
            path = Path(raw) / "current-grid.json"
            with patch.object(catalog_service, "CURRENT_GRID_JSON", path):
                catalog_service._write_current_grid(entries, items, 8_675_309)

                reordered, restored, seed = catalog_service.edit_current_grid(
                    order=["driver:3", "driver:1", "driver:2"]
                )
                persisted, persisted_attributes, persisted_seed = (
                    catalog_service.read_current_grid()
                )
                with patch.object(
                    catalog_router.catalog,
                    "driver_profiles",
                    return_value=(
                        {
                            "driver:1": SimpleNamespace(
                                characterization="Perfil ficticio",
                                parameter_version="v1",
                            )
                        },
                        "Perfis ficticios.",
                    ),
                ):
                    response = catalog_router._grid_response(
                        reordered, restored, seed
                    )

            self.assertEqual(
                [entry.driver_id for entry in reordered],
                ["driver:3", "driver:1", "driver:2"],
            )
            self.assertEqual(persisted, reordered)
            self.assertEqual(restored, items)
            self.assertEqual(persisted_attributes, items)
            self.assertEqual(seed, 8_675_309)
            self.assertEqual(persisted_seed, 8_675_309)
            self.assertEqual(
                [entry.driver_id for entry in response.grid],
                ["driver:3", "driver:1", "driver:2"],
            )
            self.assertIsNotNone(response.grid[1].profile)
            self.assertEqual(
                response.grid[1].profile.characterization, "Perfil ficticio"
            )
            self.assertEqual(response.profiles_disclaimer, "Perfis ficticios.")
            self.assertEqual(list(Path(raw).glob("*.tmp")), [])

    def test_invalid_order_returns_422_without_replacing_the_file(self) -> None:
        entries = grid()
        with TemporaryDirectory() as raw:
            path = Path(raw) / "current-grid.json"
            with patch.object(catalog_service, "CURRENT_GRID_JSON", path):
                catalog_service._write_current_grid(entries, attributes(entries), 42)
                before = path.read_bytes()

                with self.assertRaises(HTTPException) as raised:
                    catalog_service.edit_current_grid(
                        order=["driver:1", "driver:1", "driver:3"]
                    )

                after = path.read_bytes()

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("ordem do grid invalida", raised.exception.detail)
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
