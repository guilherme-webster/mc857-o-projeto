"""Grid a partir da largada de uma corrida historica e perfis no grid."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
BACKEND = str(ROOT / "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.routers import catalog as catalog_router  # noqa: E402
from app.schemas.responses import BuildGridRequest  # noqa: E402
from app.services import catalog as catalog_service  # noqa: E402
from f1_simulator.adapters.driver_presets_json import (  # noqa: E402
    load_driver_preset_file,
    load_driver_presets,
)
from f1_simulator.application.build_grid import GridEntry  # noqa: E402
from f1_simulator.application.catalog import (  # noqa: E402
    CatalogEntry,
    starting_grid_pair_ids,
)
from f1_simulator.application.generate_attributes import (  # noqa: E402
    apply_presets,
    generate_attributes,
)
from f1_simulator.domain.random_source import SeededRandomSource  # noqa: E402

PRESETS_PATH = ROOT / "configs" / "drivers" / "perfis-ficticios.json"


class Record:
    """Como ``HistoricalRecord``: so indexacao, sem a API de ``dict``."""

    def __init__(self, values: dict) -> None:
        self._values = values

    def __getitem__(self, name: str):
        return self._values[name]


class FakeHistory:
    def __init__(self, results: list[dict]) -> None:
        self._results = results

    def records(self, table: str, **filters):
        assert table == "race_results"
        for row in self._results:
            if all(row.get(key) == value for key, value in filters.items()):
                yield Record(row)


def result(driver: str, team: str, grid: int | None, order: int, race="race:1") -> dict:
    return {
        "race_id": race,
        "driver_id": driver,
        "team_id": team,
        "grid_position": grid,
        "classification_order": order,
    }


class StartingGridPairIdsTest(unittest.TestCase):
    def test_orders_by_grid_and_sends_pit_lane_starts_to_the_back(self) -> None:
        history = FakeHistory(
            [
                result("driver:3", "team:1", 0, 4),
                result("driver:1", "team:1", 2, 1),
                result("driver:2", "team:2", 1, 2),
                result("driver:4", "team:2", None, 3),
                result("driver:9", "team:9", 1, 1, race="race:2"),
            ]
        )
        self.assertEqual(
            starting_grid_pair_ids(history, "race:1"),
            (
                "driver:2@team:2",
                "driver:1@team:1",
                "driver:4@team:2",
                "driver:3@team:1",
            ),
        )

    def test_shared_cars_keep_the_first_entry_of_each_driver(self) -> None:
        history = FakeHistory(
            [result("driver:1", "team:1", 1, 1), result("driver:1", "team:2", 5, 3)]
        )
        self.assertEqual(
            starting_grid_pair_ids(history, "race:1"), ("driver:1@team:1",)
        )

    def test_unknown_race_is_an_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "race:404"):
            starting_grid_pair_ids(FakeHistory([]), "race:404")


class BuildGridRequestTest(unittest.TestCase):
    def test_race_mode_requires_race_id_and_takes_size_from_the_race(self) -> None:
        BuildGridRequest(mode="race", race_id="race:1144")
        with self.assertRaises(ValidationError):
            BuildGridRequest(mode="race")
        with self.assertRaises(ValidationError):
            BuildGridRequest(mode="race", race_id="race:1144", size=20)

    def test_other_modes_still_require_size_and_reject_race_id(self) -> None:
        with self.assertRaises(ValidationError):
            BuildGridRequest(mode="random")
        with self.assertRaises(ValidationError):
            BuildGridRequest(mode="random", size=5, race_id="race:1")


class BuildGridServiceRaceModeTest(unittest.TestCase):
    def test_race_mode_builds_the_historical_starting_grid(self) -> None:
        pool = tuple(
            CatalogEntry(d, f"Piloto {d}", None, t, f"Equipe {t}")
            for d, t in (("driver:1", "team:1"), ("driver:2", "team:2"))
        )
        history = FakeHistory(
            [result("driver:1", "team:1", 2, 1), result("driver:2", "team:2", 1, 2)]
        )
        with (
            patch.object(catalog_service, "_repository", return_value=history),
            patch.object(catalog_service, "list_entries", return_value=pool),
            patch.object(catalog_service, "_write_current_grid"),
        ):
            pairs, _, seed = catalog_service.build_grid(
                None, mode="race", manual_pair_ids=[], seed=7, race_id="race:1"
            )
        self.assertEqual([entry.driver_id for entry in pairs], ["driver:2", "driver:1"])
        self.assertEqual(seed, 7)

    def test_unknown_race_is_404(self) -> None:
        from fastapi import HTTPException

        with (
            patch.object(catalog_service, "_repository", return_value=FakeHistory([])),
            self.assertRaises(HTTPException) as caught,
        ):
            catalog_service.build_grid(
                None, mode="race", manual_pair_ids=[], seed=7, race_id="race:404"
            )
        self.assertEqual(caught.exception.status_code, 404)


class GridProfilesTest(unittest.TestCase):
    def grid_response(self, driver_id: str, with_presets: bool):
        entry = GridEntry(driver_id, "Piloto", "team:9", "Equipe")
        source = SeededRandomSource(42).spawn("attributes")
        items = generate_attributes([driver_id], source)
        if with_presets:
            items = apply_presets(items, load_driver_presets(PRESETS_PATH), source)
        with (
            patch.object(catalog_service, "DRIVER_PRESETS_JSON", PRESETS_PATH),
            patch.object(
                catalog_router.catalog,
                "build_grid",
                return_value=((entry,), {driver_id: items[0]}, 42),
            ),
        ):
            return catalog_router.build_grid(
                BuildGridRequest(
                    size=1, mode="manual", pair_ids=[f"{driver_id}@team:9"]
                )
            )

    def test_applied_preset_exposes_characterization_and_disclaimer(self) -> None:
        presets, disclaimer = load_driver_preset_file(PRESETS_PATH)
        response = self.grid_response("driver:830", with_presets=True)
        profile = response.grid[0].profile
        self.assertEqual(
            profile.characterization, presets["driver:830"].characterization
        )
        self.assertEqual(response.profiles_disclaimer, disclaimer)

    def test_driver_without_applied_preset_has_no_profile(self) -> None:
        response = self.grid_response("driver:830", with_presets=False)
        self.assertIsNone(response.grid[0].profile)
        self.assertIsNone(response.profiles_disclaimer)


if __name__ == "__main__":
    unittest.main()
