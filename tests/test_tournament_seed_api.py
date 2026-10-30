"""Contrato HTTP e metadados de reproducao das seeds de torneio."""

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

from app.routers import catalog as catalog_router
from app.schemas.responses import RunGridRequest
from app.services import catalog as catalog_service

from f1_simulator.application.build_grid import GridEntry
from f1_simulator.domain.driver_attributes import ATTRIBUTE_FIELDS, DriverAttributes
from f1_simulator.domain.random_source import derive_tournament_stage_seed
from tests.model_support import parameters


def current_grid() -> tuple:
    entry = GridEntry("driver:1", "Piloto", "team:1", "Equipe")
    attributes = DriverAttributes(
        driver_id=entry.driver_id,
        archetype="balanced",
        pace_offset_pct=0.0,
        consistency_factor=1.0,
        tyre_management_factor=1.0,
        aggression=1.0,
        composure=1.0,
        sources={name: "generated" for name in ATTRIBUTE_FIELDS},
    )
    return (entry,), {entry.driver_id: attributes}, 42


class TournamentSeedSchemaTest(unittest.TestCase):
    def test_schema_rejects_invalid_tournament_seed_and_stage_index(self) -> None:
        invalid_setups = (
            {"total_laps": 5, "tournament_seed": -1},
            {"total_laps": 5, "tournament_seed": 2**53},
            {"total_laps": 5, "stage_index": -1},
        )

        for setup in invalid_setups:
            with self.subTest(setup=setup), self.assertRaises(ValidationError):
                RunGridRequest(setup=setup)

    def test_route_forwards_explicit_seed_and_stage_index(self) -> None:
        request = RunGridRequest(
            setup={
                "total_laps": 5,
                "track_id": "circuit:1",
                "tournament_seed": 105,
                "stage_index": 3,
            }
        )
        with patch.object(
            catalog_router.catalog, "run_grid", return_value={"ok": True}
        ) as run:
            catalog_router.run_grid(request)

        run.assert_called_once_with(
            total_laps=5,
            track_id="circuit:1",
            weather=[],
            engine="detailed",
            tournament_seed=105,
            stage_index=3,
        )


class TournamentSeedResponseTest(unittest.TestCase):
    def test_response_metadata_matches_the_core_derivation(self) -> None:
        detailed_result = {"total_laps": 1, "history": [], "classification": []}
        with (
            patch.object(
                catalog_service, "read_current_grid", return_value=current_grid()
            ),
            patch.object(
                catalog_service, "_track_reference", return_value=(None, None)
            ),
            patch.object(catalog_service, "_track_geometry", return_value=None),
            patch.object(catalog_service, "_model_parameters", return_value=parameters()),
            patch(
                "f1_simulator.application.run_grid_simulation.run_detailed_grid_simulation",
                return_value=detailed_result,
            ) as run,
            patch.object(catalog_service, "_write_json"),
            patch.object(catalog_service, "_persist_saved_race"),
        ):
            result = catalog_service.run_grid(
                total_laps=1,
                track_id=None,
                weather=[],
                tournament_seed=105,
                stage_index=3,
            )

        setup = run.call_args.args[2]
        self.assertEqual((setup.tournament_seed, setup.stage_index), (105, 3))
        self.assertEqual(result["seed"], 42)
        self.assertEqual(result["grid_seed"], 42)
        self.assertEqual(result["tournament_seed"], 105)
        self.assertEqual(result["stage_index"], 3)
        self.assertEqual(
            result["race_seed"], str(derive_tournament_stage_seed(105, 3))
        )
        self.assertEqual(result["race_stream_id"], "tournament-stage-v1:3")

    def test_legacy_response_identifies_the_unchanged_grid_race_stream(self) -> None:
        detailed_result = {"total_laps": 1, "history": [], "classification": []}
        with (
            patch.object(
                catalog_service, "read_current_grid", return_value=current_grid()
            ),
            patch.object(
                catalog_service, "_track_reference", return_value=(None, None)
            ),
            patch.object(catalog_service, "_track_geometry", return_value=None),
            patch.object(catalog_service, "_model_parameters", return_value=parameters()),
            patch(
                "f1_simulator.application.run_grid_simulation.run_detailed_grid_simulation",
                return_value=detailed_result,
            ),
            patch.object(catalog_service, "_write_json"),
            patch.object(catalog_service, "_persist_saved_race"),
        ):
            result = catalog_service.run_grid(
                total_laps=1, track_id=None, weather=[]
            )

        self.assertEqual(result["grid_seed"], 42)
        self.assertIsNone(result["tournament_seed"])
        self.assertEqual(result["stage_index"], 0)
        self.assertTrue(result["race_seed"].isdigit())
        self.assertEqual(result["race_stream_id"], "grid-seed-v1:race")


if __name__ == "__main__":
    unittest.main()
