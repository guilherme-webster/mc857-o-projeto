"""Contrato HTTP/composition root da execucao do grid."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
BACKEND = str(ROOT / "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.routers import catalog as catalog_router  # noqa: E402
from app.schemas.responses import RunGridRequest  # noqa: E402
from app.services import catalog as catalog_service  # noqa: E402
from f1_simulator.application.build_grid import GridEntry  # noqa: E402
from f1_simulator.domain.driver_attributes import (  # noqa: E402
    ATTRIBUTE_FIELDS,
    DriverAttributes,
)
from tests.model_support import parameters  # noqa: E402


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


class CatalogGridRunRouteTest(unittest.TestCase):
    def test_route_defaults_to_detailed_engine(self) -> None:
        request = RunGridRequest(
            setup={"total_laps": 5, "track_id": "circuit:1"}
        )
        with patch.object(
            catalog_router.catalog, "run_grid", return_value={"engine": "detailed"}
        ) as run:
            result = catalog_router.run_grid(request)

        self.assertEqual(result, {"engine": "detailed"})
        run.assert_called_once_with(
            total_laps=5,
            track_id="circuit:1",
            weather=None,
            engine="detailed",
        )

    def test_route_forwards_explicit_simple_engine(self) -> None:
        request = RunGridRequest(
            setup={"total_laps": 5, "track_id": None, "engine": "simple"}
        )
        with patch.object(
            catalog_router.catalog, "run_grid", return_value={"engine": "simple"}
        ) as run:
            result = catalog_router.run_grid(request)

        self.assertEqual(result, {"engine": "simple"})
        self.assertEqual(run.call_args.kwargs["engine"], "simple")


class CatalogGridRunServiceTest(unittest.TestCase):
    def test_detailed_engine_loads_model_track_length_and_keeps_seed(self) -> None:
        model = parameters()
        detailed_result = {"total_laps": 5, "history": [], "classification": []}
        with (
            patch.object(
                catalog_service, "read_current_grid", return_value=current_grid()
            ),
            patch.object(catalog_service, "_model_parameters", return_value=model),
            patch.object(
                catalog_service,
                "_track_reference",
                return_value=("circuit:1", 4_000.0),
            ),
            patch(
                "f1_simulator.application.run_grid_simulation.run_detailed_grid_simulation",
                return_value=detailed_result,
            ) as run,
            patch.object(catalog_service, "_write_json") as write,
        ):
            result = catalog_service.run_grid(
                total_laps=5,
                track_id="circuit:1",
                weather="dry",
                engine="detailed",
            )

        self.assertEqual(result["seed"], 42)
        self.assertIs(run.call_args.kwargs["parameters"], model)
        self.assertEqual(run.call_args.kwargs["lap_length_m"], 4_000.0)
        self.assertEqual(run.call_args.args[2].track_id, "circuit:1")
        write.assert_called_once()

    def test_simple_engine_preserves_baseline_without_loading_model(self) -> None:
        simple_result = {"total_laps": 5, "history": [], "classification": []}
        with (
            patch.object(
                catalog_service, "read_current_grid", return_value=current_grid()
            ),
            patch.object(
                catalog_service, "_track_reference", return_value=(None, None)
            ),
            patch.object(catalog_service, "_model_parameters") as load_model,
            patch(
                "f1_simulator.application.run_grid_simulation.run_grid_simulation",
                return_value=simple_result,
            ) as run,
            patch.object(catalog_service, "_write_json"),
        ):
            result = catalog_service.run_grid(
                total_laps=5,
                track_id=None,
                weather=None,
                engine="simple",
            )

        self.assertEqual(result["seed"], 42)
        run.assert_called_once()
        load_model.assert_not_called()

    def test_missing_model_parameters_returns_503(self) -> None:
        missing = ROOT / "tmp" / "model-parameters-inexistentes.json"
        with (
            patch.object(catalog_service, "MODEL_PARAMETERS", missing),
            patch.object(
                catalog_service, "read_current_grid", return_value=current_grid()
            ),
            patch.object(
                catalog_service, "_track_reference", return_value=(None, None)
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                catalog_service.run_grid(
                    total_laps=5,
                    track_id=None,
                    weather=None,
                    engine="detailed",
                )

        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("parametros do modelo indisponiveis", raised.exception.detail)
        self.assertIn(missing.name, raised.exception.detail)

    def test_unknown_track_returns_422(self) -> None:
        with (
            patch.object(
                catalog_service, "read_current_grid", return_value=current_grid()
            ),
            patch(
                "app.services.track_geometry.list_available_tracks",
                return_value={
                    "count": 1,
                    "tracks": [
                        {
                            "circuit_id": "circuit:1",
                            "name": "Teste",
                            "lap_length_m": 4_000.0,
                        }
                    ],
                },
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                catalog_service.run_grid(
                    total_laps=5,
                    track_id="circuit:999",
                    weather=None,
                    engine="detailed",
                )

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("track_id desconhecido", raised.exception.detail)

    def test_v1_saved_grid_returns_409_with_rebuild_instruction(self) -> None:
        old_state = {
            "seed": 42,
            "grid": [
                {
                    "driver_id": "driver:1",
                    "driver_name": "Piloto",
                    "team_id": "team:1",
                    "team_name": "Equipe",
                    "attributes": {
                        "archetype": "balanced",
                        "pace_offset_pct": 0.0,
                        "consistency_factor": 1.0,
                        "tyre_management_factor": 1.0,
                        "sources": {
                            "pace_offset_pct": "generated",
                            "consistency_factor": "generated",
                            "tyre_management_factor": "generated",
                        },
                    },
                }
            ],
        }

        with self.assertRaises(HTTPException) as raised:
            catalog_service._deserialize_grid(old_state)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("POST /catalog/grid", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
