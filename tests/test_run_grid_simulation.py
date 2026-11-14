"""Composicao pura do grid com o motor 2D (ADR 0011).

Cada teste usa a geometria real do fixture Trotman (``tests/geometry_support``)
e poucas voltas para manter a suite rapida.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from f1_simulator.application.build_grid import GridEntry, reorder_grid
from f1_simulator.application.run_grid_simulation import (
    ASSUMED_REFERENCE_PACE_MS_PER_KM,
    RaceSetup,
    run_grid_simulation,
)
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.weather import RainLevel, WeatherSegment
from tests.geometry_support import attribute, fixture_geometry
from tests.model_support import parameters

GEOMETRY = fixture_geometry()
LAP_M = GEOMETRY.lap_length_m


class ScriptedFailureSource:
    """Fonte roteirizada: so a falha mecanica de ``driver:2`` na volta 1 ocorre.

    Os demais sorteios de probabilidade ficam no valor alto e nao disparam;
    isolar um unico evento deixa o controle de prova deterministico.
    """

    def standard_normal(self, label: str = "") -> float:
        return 0.0

    def uniform01(self, label: str = "") -> float:
        return 0.0 if label == "mechanical:driver:2:lap:1" else 0.99

    def spawn(self, key: str) -> "ScriptedFailureSource":
        return self


class GridSimulationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.grid = (
            GridEntry("driver:2", "Segundo", "team:solid", "Solida"),
            GridEntry("driver:1", "Primeiro", "team:missing", "Sem modelo"),
        )
        self.attributes = {
            entry.driver_id: attribute(entry.driver_id) for entry in self.grid
        }
        self.parameters = parameters(dnf_hazard_per_lap=0.0)

    def run_grid(self, setup=None, *, grid=None, attributes=None, **overrides):
        options = dict(
            parameters=self.parameters,
            lap_length_m=LAP_M,
            rng=SeededRandomSource(42),
            geometry=GEOMETRY,
        )
        options.update(overrides)
        return run_grid_simulation(
            grid or self.grid,
            attributes or self.attributes,
            setup or RaceSetup(2, track_id="circuit:1"),
            **options,
        )

    def capture_entrants(self, grid) -> list[dict]:
        captured: dict = {}

        def fake_simulation(entrants, geometry, **kwargs):
            captured["entrants"] = entrants
            return {
                "total_laps": kwargs["total_laps"],
                "history": [],
                "classification": [],
                "assumptions": [],
            }

        with patch(
            "f1_simulator.domain.race_simulation_2d.simulate_2d_race",
            side_effect=fake_simulation,
        ):
            self.run_grid(RaceSetup(1, track_id="circuit:1"), grid=grid)
        return captured["entrants"]

    def test_builds_entrants_in_starting_order_and_applies_attributes(self) -> None:
        entrants = self.capture_entrants(self.grid)

        self.assertEqual(
            [item["driver_id"] for item in entrants], ["driver:2", "driver:1"]
        )
        self.assertEqual([item["grid_position"] for item in entrants], [1, 2])
        for item in entrants:
            self.assertIs(item["attributes"], self.attributes[item["driver_id"]])
            self.assertEqual(item["compound"], "MEDIUM")

    def test_reordered_grid_reaches_the_engine_as_starting_positions(self) -> None:
        reordered = reorder_grid(self.grid, ["driver:1", "driver:2"])

        entrants = self.capture_entrants(reordered)
        result = self.run_grid(RaceSetup(1, track_id="circuit:1"), grid=reordered)

        self.assertEqual(
            [(item["driver_id"], item["grid_position"]) for item in entrants],
            [("driver:1", 1), ("driver:2", 2)],
        )
        self.assertEqual(
            [(item["driver_id"], item["position"]) for item in result["starting_grid"]],
            [("driver:1", 1), ("driver:2", 2)],
        )

    def test_uses_calibrated_track_and_geometry_reference(self) -> None:
        result = self.run_grid()

        self.assertEqual(
            result["reference_lap_time_ms"],
            LAP_M / 1_000.0 * ASSUMED_REFERENCE_PACE_MS_PER_KM,
        )
        self.assertEqual(result["track_reference"]["model_track_id"], "circuit:1")
        self.assertEqual(result["track_reference"]["model_track_origin"], "calibrated")

    def test_uses_assumed_track_fallback_for_uncalibrated_track(self) -> None:
        result = self.run_grid(RaceSetup(1, track_id="circuit:999"))

        self.assertEqual(result["track_reference"]["requested_track_id"], "circuit:999")
        self.assertEqual(result["track_reference"]["model_track_id"], "__fallback__")
        self.assertEqual(result["track_reference"]["model_track_origin"], "assumed")

    def test_without_track_uses_nominal_lap_and_declares_assumption(self) -> None:
        result = self.run_grid(RaceSetup(1), lap_length_m=None)

        self.assertEqual(result["reference_lap_time_ms"], 90_000.0)
        reference = next(
            item for item in result["assumptions"] if item["kind"] == "reference_pace"
        )
        self.assertTrue(reference["used_nominal_lap_time_fallback"])
        self.assertEqual(reference["origin"], "assumed")

    def test_same_seed_reproduces_race_including_control_events(self) -> None:
        setup = RaceSetup(3, track_id="circuit:1")

        first = self.run_grid(setup, rng=SeededRandomSource(67202))
        repeated = self.run_grid(setup, rng=SeededRandomSource(67202))

        self.assertEqual(first, repeated)
        self.assertIn("race_control_events", first)
        self.assertIn("race_control_by_lap", first)
        self.assertEqual(len(first["race_control_by_lap"]), 3)

    def test_race_control_events_are_exposed_by_the_use_case(self) -> None:
        # O abandono so vira evento quando outro carro completa a volta, entao
        # o grid precisa de um segundo carro que siga em pista.
        result = self.run_grid(
            RaceSetup(3, track_id="circuit:1"),
            parameters=parameters(dnf_hazard_per_lap=0.35),
            rng=ScriptedFailureSource(),
        )

        self.assertTrue(result["race_control_events"])
        # No motor 2D o abandono sem disputa e mecanico; o "solo_crash" do motor
        # por volta nao existe mais.
        self.assertEqual(
            result["race_control_events"][0]["cause"]["kind"], "mechanical"
        )

    def test_start_stretch_uses_first_lap_weather_not_the_last(self) -> None:
        # Regressao: do grid ate a linha a volta calculada era 0 e o indice -1
        # buscava o estado de pista da ultima volta. Com chuva so no fim, a
        # largada era simulada molhada. A primeira volta tem de ser a mesma
        # com e sem chuva futura.
        grid = self.grid[:1]
        attributes = {grid[0].driver_id: self.attributes[grid[0].driver_id]}
        late_rain = (
            WeatherSegment(from_lap=5, to_lap=6, rain=RainLevel.HEAVY),
        )

        def first_lap(weather):
            result = self.run_grid(
                RaceSetup(6, track_id="circuit:1", weather=weather),
                grid=grid,
                attributes=attributes,
                race_control=None,
            )
            laps = result["speed_breakdown"]["cars"][grid[0].driver_id]["laps"]
            self.assertNotIn("0", laps)
            return result["history"][0]["cars"][0]["lap_time_ms"], laps["1"]

        dry_time, dry_lap = first_lap(())
        wet_time, wet_lap = first_lap(late_rain)
        self.assertEqual(wet_lap["weather_ms"], dry_lap["weather_ms"])
        self.assertEqual(wet_time, dry_time)

    def test_pace_attribute_changes_the_result(self) -> None:
        grid = (GridEntry("driver:1", "Piloto", "team:solid", "Solida"),)
        setup = RaceSetup(2, track_id="circuit:1")

        def total_time(pace_offset_pct: float) -> float:
            result = self.run_grid(
                setup,
                grid=grid,
                attributes={
                    "driver:1": attribute("driver:1", pace_offset_pct=pace_offset_pct)
                },
                rng=SeededRandomSource(55),
            )
            return result["classification"][0]["total_time_ms"]

        self.assertLess(total_time(-1.0), total_time(1.0))

    def _run_tournament_stage(self, tournament_seed: int, stage_index: int) -> dict:
        return self.run_grid(
            RaceSetup(
                2,
                track_id="circuit:1",
                tournament_seed=tournament_seed,
                stage_index=stage_index,
            ),
            parameters=parameters(dnf_hazard_per_lap=0.35),
            rng=SeededRandomSource(999),
        )

    def test_tournament_seed_reproduces_and_separates_2d_stages(self) -> None:
        first = self._run_tournament_stage(105, 0)
        repeated = self._run_tournament_stage(105, 0)
        different_seed = self._run_tournament_stage(106, 0)
        repeated_track_next_stage = self._run_tournament_stage(105, 1)

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, different_seed)
        self.assertNotEqual(first, repeated_track_next_stage)


if __name__ == "__main__":
    unittest.main()
