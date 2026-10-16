"""Contrato HTTP de POST /championship/standings."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
BACKEND = str(ROOT / "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.routers.championship import championship_standings  # noqa: E402
from app.schemas.responses import ChampionshipRequest  # noqa: E402


class ChampionshipRouteTest(unittest.TestCase):
    def test_returns_rows_in_championship_order(self) -> None:
        request = ChampionshipRequest(
            stages=[
                [
                    {"driver_id": "A", "position": 1},
                    {"driver_id": "B", "position": 2, "retired": True},
                ]
            ]
        )
        response = championship_standings(request)
        self.assertEqual(response.scoring, "f1")
        self.assertEqual([row.driver_id for row in response.rows], ["A", "B"])
        self.assertEqual([row.points for row in response.rows], [25, 0])
        self.assertEqual(response.rows[1].stage_retired, [True])

    def test_inconsistent_stage_is_422(self) -> None:
        request = ChampionshipRequest(
            stages=[
                [{"driver_id": "A", "position": 1}, {"driver_id": "B", "position": 1}]
            ]
        )
        with self.assertRaises(HTTPException) as caught:
            championship_standings(request)
        self.assertEqual(caught.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
