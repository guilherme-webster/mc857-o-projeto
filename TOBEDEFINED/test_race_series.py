"""Corridas livres sequenciais, independentes de banco de corridas históricas."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from f1_simulator.domain.race_simulation import ASSUMED_LAP_VARIABILITY
from f1_simulator.domain.race_series import (
    SeriesCompetitor,
    SeriesTrack,
    simulate_series,
)

BACKEND = str(Path(__file__).resolve().parents[1] / "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.routers.simulation import simular_sequencia  # noqa: E402
from app.schemas.responses import SeriesSimulationRequest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402


class RaceSeriesTest(unittest.TestCase):
    def test_runs_two_distinct_tracks_in_selected_order(self) -> None:
        tracks = (
            SeriesTrack("circuit:18", "Interlagos", 4000, 2),
            SeriesTrack("circuit:6", "Monaco", 3000, 1),
        )
        drivers = (
            SeriesCompetitor("alice", "Alice", 20000),
            SeriesCompetitor("bob", "Bob", 21000),
        )

        result = simulate_series(tracks, drivers)

        self.assertEqual(result["race_count"], 2)
        self.assertEqual(
            [race["circuit_id"] for race in result["races"]],
            ["circuit:18", "circuit:6"],
        )
        self.assertEqual(
            result["races"][0]["history"][0]["cars"][0]["lap_time_ms"], 80000
        )
        self.assertEqual(
            result["races"][1]["history"][0]["cars"][0]["lap_time_ms"], 60000
        )
        self.assertEqual(
            result["races"][0]["classification"][0]["total_time_ms"], 160000
        )
        self.assertEqual(
            result["races"][1]["classification"][0]["total_time_ms"], 60000
        )

    def test_rejects_empty_duplicate_and_invalid_inputs(self) -> None:
        track = SeriesTrack("circuit:18", "Interlagos", 4000, 2)
        driver = SeriesCompetitor("alice", "Alice", 20000)
        invalid = (
            ((), (driver,)),
            ((track,), ()),
            ((track, track), (driver,)),
            ((track,), (driver, driver)),
            ((SeriesTrack("circuit:18", "Interlagos", float("nan"), 2),), (driver,)),
            ((track,), (SeriesCompetitor("alice", "Alice", float("inf")),)),
            ((track,), (SeriesCompetitor("alice", "Alice", 1e308),)),
        )
        for tracks, drivers in invalid:
            with (
                self.subTest(tracks=tracks, drivers=drivers),
                self.assertRaises(ValueError),
            ):
                simulate_series(tracks, drivers)

    def test_route_uses_catalog_and_never_loads_historical_race(self) -> None:
        request = SeriesSimulationRequest.model_validate(
            {
                "tracks": [
                    {"circuit_id": "circuit:6", "total_laps": 1},
                    {"circuit_id": "circuit:18", "total_laps": 2},
                ],
                "competitors": [
                    {"driver_id": "a", "name": "A", "pace_ms_per_km": 20000}
                ],
            }
        )
        catalog = {
            "tracks": [
                {
                    "circuit_id": "circuit:18",
                    "name": "Interlagos",
                    "lap_length_m": 4000,
                },
                {"circuit_id": "circuit:6", "name": "Monaco", "lap_length_m": 3000},
            ]
        }

        with patch(
            "app.routers.simulation.list_available_tracks", return_value=catalog
        ):
            result = simular_sequencia(request)

        self.assertEqual(
            [race["circuit_id"] for race in result["races"]],
            ["circuit:6", "circuit:18"],
        )
        self.assertEqual(
            result["races"][0]["classification"][0]["total_time_ms"], 60000
        )

    def test_route_rejects_unknown_track(self) -> None:
        request = SeriesSimulationRequest.model_validate(
            {
                "tracks": [{"circuit_id": "circuit:999", "total_laps": 1}],
                "competitors": [
                    {"driver_id": "a", "name": "A", "pace_ms_per_km": 20000}
                ],
            }
        )
        with patch(
            "app.routers.simulation.list_available_tracks", return_value={"tracks": []}
        ):
            with self.assertRaises(HTTPException) as context:
                simular_sequencia(request)
        self.assertEqual(context.exception.status_code, 422)

    def test_route_validates_bounds_before_simulating(self) -> None:
        with self.assertRaises(ValidationError):
            SeriesSimulationRequest.model_validate(
                {
                    "tracks": [{"circuit_id": "circuit:18", "total_laps": 0}],
                    "competitors": [
                        {"driver_id": "a", "name": "A", "pace_ms_per_km": 20000}
                    ],
                }
            )


_SCENARIO_TRACKS = (
    SeriesTrack("circuit:18", "Interlagos", 4000, 10),
    SeriesTrack("circuit:6", "Monaco", 3000, 8),
)
_SCENARIO_DRIVERS = (
    SeriesCompetitor("a", "A", 20000),
    SeriesCompetitor("b", "B", 20100),
    SeriesCompetitor("c", "C", 20200),
)
_SCENARIO_TYRES = {"a": "SOFT", "b": "MEDIUM", "c": "HARD"}


def _dump(value: dict) -> str:
    return json.dumps(value, sort_keys=True, allow_nan=False)


class SeriesScenarioTest(unittest.TestCase):
    """Pneu assumido e ruído com semente na série de corridas (domínio)."""

    def test_default_series_has_no_scenario_keys(self) -> None:
        result = simulate_series(_SCENARIO_TRACKS, _SCENARIO_DRIVERS)

        self.assertEqual(set(result), {"race_count", "races"})
        for race in result["races"]:
            self.assertNotIn("assumptions", race)
            self.assertNotIn("breakdown", race["history"][0]["cars"][0])

    def test_tyres_only_is_deterministic_without_seed_and_labelled(self) -> None:
        first = simulate_series(
            _SCENARIO_TRACKS, _SCENARIO_DRIVERS, tyre_plan=_SCENARIO_TYRES
        )
        second = simulate_series(
            _SCENARIO_TRACKS, _SCENARIO_DRIVERS, tyre_plan=_SCENARIO_TYRES
        )

        self.assertEqual(_dump(first), _dump(second))
        self.assertNotIn("seed", first)
        self.assertEqual(
            [(a["kind"], a["compound"], a["source_kind"]) for a in first["assumptions"]],
            [
                ("tyre", "HARD", "assumed"),
                ("tyre", "MEDIUM", "assumed"),
                ("tyre", "SOFT", "assumed"),
            ],
        )
        for race in first["races"]:
            # Os mesmos parâmetros valem para todas as corridas: ficam só no topo.
            self.assertNotIn("assumptions", race)
            car = race["history"][0]["cars"][0]
            self.assertIsNone(car["breakdown"]["noise_ms"])

    def test_variability_returns_the_seed_and_the_labelled_assumption(self) -> None:
        result = simulate_series(
            _SCENARIO_TRACKS,
            _SCENARIO_DRIVERS,
            variability=ASSUMED_LAP_VARIABILITY,
            seed=7,
        )

        self.assertEqual(result["seed"], 7)
        self.assertEqual(
            [(a["kind"], a["source_kind"]) for a in result["assumptions"]],
            [("lap_variability", "assumed")],
        )
        self.assertIsNone(
            result["races"][0]["history"][0]["cars"][0]["breakdown"]["tyre_effect_ms"]
        )

    def test_same_seed_reproduces_and_different_seed_changes_the_series(self) -> None:
        def run(seed: int) -> dict:
            return simulate_series(
                _SCENARIO_TRACKS,
                _SCENARIO_DRIVERS,
                tyre_plan=_SCENARIO_TYRES,
                variability=ASSUMED_LAP_VARIABILITY,
                seed=seed,
            )

        self.assertEqual(_dump(run(2026)), _dump(run(2026)))
        self.assertNotEqual(_dump(run(2026)), _dump(run(2027)))

    def test_race_result_does_not_depend_on_the_order_of_the_tracks(self) -> None:
        def run(tracks: tuple[SeriesTrack, ...]) -> dict:
            result = simulate_series(
                tracks,
                _SCENARIO_DRIVERS,
                variability=ASSUMED_LAP_VARIABILITY,
                seed=99,
            )
            return {race["circuit_id"]: race for race in result["races"]}

        forward = run(_SCENARIO_TRACKS)
        backward = run(tuple(reversed(_SCENARIO_TRACKS)))
        only_second = run((_SCENARIO_TRACKS[1],))

        for circuit_id in ("circuit:18", "circuit:6"):
            self.assertEqual(_dump(forward[circuit_id]), _dump(backward[circuit_id]))
        # Remover outra etapa também não altera a corrida restante.
        self.assertEqual(_dump(forward["circuit:6"]), _dump(only_second["circuit:6"]))

    def test_variability_and_seed_must_come_together(self) -> None:
        with self.assertRaises(ValueError):
            simulate_series(
                _SCENARIO_TRACKS,
                _SCENARIO_DRIVERS,
                variability=ASSUMED_LAP_VARIABILITY,
            )
        with self.assertRaises(ValueError):
            simulate_series(_SCENARIO_TRACKS, _SCENARIO_DRIVERS, seed=1)
        with self.assertRaises(ValueError):  # bool não vale como semente
            simulate_series(
                _SCENARIO_TRACKS,
                _SCENARIO_DRIVERS,
                variability=ASSUMED_LAP_VARIABILITY,
                seed=True,
            )

    def test_incomplete_or_unknown_tyre_plan_raises(self) -> None:
        for plan in (
            {"a": "SOFT"},
            {**_SCENARIO_TYRES, "z": "SOFT"},
            {**_SCENARIO_TYRES, "c": "WET"},
        ):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                simulate_series(_SCENARIO_TRACKS, _SCENARIO_DRIVERS, tyre_plan=plan)

    def test_long_race_is_rejected_only_when_tyres_are_modelled(self) -> None:
        long_track = (SeriesTrack("circuit:18", "Interlagos", 4000, 100),)

        without_tyres = simulate_series(long_track, _SCENARIO_DRIVERS)
        self.assertEqual(without_tyres["races"][0]["total_laps"], 100)
        with self.assertRaises(ValueError) as context:
            simulate_series(long_track, _SCENARIO_DRIVERS, tyre_plan=_SCENARIO_TYRES)
        self.assertIn("suporte", str(context.exception))

    def test_active_series_is_json_serializable(self) -> None:
        result = simulate_series(
            _SCENARIO_TRACKS,
            _SCENARIO_DRIVERS,
            tyre_plan=_SCENARIO_TYRES,
            variability=ASSUMED_LAP_VARIABILITY,
            seed=5,
        )

        json.dumps(result, allow_nan=False)


_SCENARIO_CATALOG = {
    "tracks": [
        {"circuit_id": "circuit:18", "name": "Interlagos", "lap_length_m": 4000},
        {"circuit_id": "circuit:6", "name": "Monaco", "lap_length_m": 3000},
    ]
}


def _scenario_request(**extra: object) -> SeriesSimulationRequest:
    body: dict = {
        "tracks": [
            {"circuit_id": "circuit:18", "total_laps": 6},
            {"circuit_id": "circuit:6", "total_laps": 4},
        ],
        "competitors": [
            {"driver_id": "a", "name": "A", "pace_ms_per_km": 20000},
            {"driver_id": "b", "name": "B", "pace_ms_per_km": 20100},
        ],
    }
    body.update(extra)
    return SeriesSimulationRequest.model_validate(body)


def _call(request: SeriesSimulationRequest) -> dict:
    with patch(
        "app.routers.simulation.list_available_tracks", return_value=_SCENARIO_CATALOG
    ):
        return simular_sequencia(request)


class SeriesScenarioRouteTest(unittest.TestCase):
    """Semente, pneus e variância no endpoint ``POST /simulation/series/simulate``."""

    def test_request_without_new_fields_keeps_the_original_response(self) -> None:
        result = _call(_scenario_request())

        self.assertEqual(set(result), {"race_count", "races"})

    def test_router_draws_the_seed_and_returns_it_so_the_run_can_be_repeated(
        self,
    ) -> None:
        with patch("app.routers.simulation._new_seed", return_value=4242):
            first = _call(_scenario_request(variability=True))

        self.assertEqual(first["seed"], 4242)
        with patch(
            "app.routers.simulation._new_seed", side_effect=AssertionError("sorteio")
        ):
            repeated = _call(_scenario_request(variability=True, seed=first["seed"]))

        self.assertEqual(_dump(first), _dump(repeated))

    def test_explicit_seed_is_never_replaced_by_a_drawn_one(self) -> None:
        with patch(
            "app.routers.simulation._new_seed", side_effect=AssertionError("sorteio")
        ):
            result = _call(_scenario_request(variability=True, seed=0))

        self.assertEqual(result["seed"], 0)

    def test_different_seeds_change_the_response(self) -> None:
        first = _call(_scenario_request(variability=True, seed=1))
        second = _call(_scenario_request(variability=True, seed=2))

        self.assertNotEqual(_dump(first), _dump(second))

    def test_new_seed_is_a_non_negative_53_bit_integer(self) -> None:
        from app.routers.simulation import _new_seed

        for _ in range(20):
            seed = _new_seed()
            self.assertIsInstance(seed, int)
            self.assertTrue(0 <= seed < 2**53)

    def test_tyres_only_returns_assumptions_and_no_seed(self) -> None:
        result = _call(_scenario_request(tyres={"a": "SOFT", "b": "HARD"}))

        self.assertNotIn("seed", result)
        self.assertEqual(
            [item["compound"] for item in result["assumptions"]], ["HARD", "SOFT"]
        )
        self.assertIn("breakdown", result["races"][0]["history"][0]["cars"][0])

    def test_seed_without_variability_is_rejected_by_the_schema(self) -> None:
        with self.assertRaises(ValidationError):
            _scenario_request(seed=10)

    def test_seed_out_of_range_is_rejected_by_the_schema(self) -> None:
        for bad in (-1, 2**53):
            with self.subTest(seed=bad), self.assertRaises(ValidationError):
                _scenario_request(variability=True, seed=bad)

    def test_incomplete_or_unknown_tyres_are_rejected_by_the_schema(self) -> None:
        for tyres in (
            {"a": "SOFT"},
            {"a": "SOFT", "b": "SOFT", "z": "SOFT"},
            {"a": "SOFT", "b": " "},
        ):
            with self.subTest(tyres=tyres), self.assertRaises(ValidationError):
                _scenario_request(tyres=tyres)

    def test_unknown_compound_returns_422(self) -> None:
        with self.assertRaises(HTTPException) as context:
            _call(_scenario_request(tyres={"a": "SOFT", "b": "WET"}))

        self.assertEqual(context.exception.status_code, 422)

    def test_race_longer_than_the_tyre_support_returns_422(self) -> None:
        request = _scenario_request(
            tracks=[{"circuit_id": "circuit:18", "total_laps": 100}],
            tyres={"a": "SOFT", "b": "HARD"},
        )
        with self.assertRaises(HTTPException) as context:
            _call(request)

        self.assertEqual(context.exception.status_code, 422)
        self.assertIn("suporte", context.exception.detail)

    def test_full_scenario_response_is_json_serializable(self) -> None:
        result = _call(
            _scenario_request(
                tyres={"a": "MEDIUM", "b": "HARD"}, variability=True, seed=3
            )
        )

        json.dumps(result, allow_nan=False)
        self.assertEqual(result["seed"], 3)


if __name__ == "__main__":
    unittest.main()
