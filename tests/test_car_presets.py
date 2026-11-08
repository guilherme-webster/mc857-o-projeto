"""Presets heuristicos de carro por equipe (ADR 0008) e o carro por piloto.

Cobre a conversao de ritmo em envelope fisico, a validacao do adaptador JSON,
o arquivo versionado de presets e o ponto exato que os dois motores usam para
derivar o tempo de volta por piloto: ``physics_for`` sobre o carro da equipe
seguido de ``GripLapTimes``. A corrida 2D minima confirma o encaminhamento do
novo parametro ate a classificacao final.
"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from datetime import date
from pathlib import Path

from f1_simulator.adapters.car_presets_json import (
    CarPresetError,
    load_car_preset_file,
)
from f1_simulator.application.car_presets import CarPreset
from f1_simulator.domain.driver_attributes import DriverAttributes
from f1_simulator.domain.race_simulation_2d import simulate_2d_race
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.speed_dynamics import (
    DEFAULT_CAR_PHYSICS,
    GripLapTimes,
    car_pace_to_physics,
    lap_time_ms,
    physics_for,
    steady_lap,
)
from f1_simulator.domain.track_geometry import (
    GeometryProvenance,
    TrackGeometry,
    TrackPoint,
)
from tests.test_track_space import _square

ROOT = Path(__file__).resolve().parents[1]
CAR_PRESETS = ROOT / "configs" / "cars" / "perfis-ficticios.json"

_PROV = GeometryProvenance(
    source_name="test",
    source_version="1",
    source_year=2025,
    generated_on=date(2025, 1, 1),
    upstream=None,
    upstream_data_license="CC0",
    artifact_sha256="a" * 64,
    manifest_sha256="b" * 64,
    transformation="synthetic",
)


def _circle(radius: float, n: int = 120) -> TrackGeometry:
    """Circulo fechado em metros (escala 1:1): curvatura constante e conhecida."""

    points, cum, prev = [], 0.0, None
    for i in range(n + 1):
        x = radius * math.cos(2 * math.pi * i / n)
        y = radius * math.sin(2 * math.pi * i / n)
        if prev is not None:
            cum += math.dist(prev, (x, y))
        points.append(TrackPoint(i, float(x), float(y), cum))
        prev = (x, y)
    return TrackGeometry("circuit:test", tuple(points), (), _PROV, _PROV)


def _attrs(**overrides) -> DriverAttributes:
    values = dict(
        pace_offset_pct=0.0,
        consistency_factor=1.0,
        tyre_management_factor=1.0,
        aggression=1.0,
        composure=1.0,
    )
    values.update(overrides)
    return DriverAttributes(
        driver_id="driver:test",
        archetype="balanced",
        sources={name: "manual" for name in values},
        **values,
    )


class CarPaceToPhysicsTest(unittest.TestCase):
    def test_neutral_returns_the_reference_car(self):
        self.assertEqual(car_pace_to_physics(0.0), DEFAULT_CAR_PHYSICS)

    def test_negative_is_faster_positive_is_slower(self):
        track = _circle(120.0)
        fast = car_pace_to_physics(-1.0)
        slow = car_pace_to_physics(1.0)
        self.assertGreater(fast.v_max_straight_kmh, DEFAULT_CAR_PHYSICS.v_max_straight_kmh)
        self.assertGreater(fast.grip_mu, DEFAULT_CAR_PHYSICS.grip_mu)
        self.assertLess(slow.v_max_straight_kmh, DEFAULT_CAR_PHYSICS.v_max_straight_kmh)
        ref = lap_time_ms(steady_lap(track, physics_for(None, DEFAULT_CAR_PHYSICS)))
        self.assertLess(lap_time_ms(steady_lap(track, physics_for(None, fast))), ref)
        self.assertGreater(lap_time_ms(steady_lap(track, physics_for(None, slow))), ref)

    def test_scales_v_max_grip_and_power_together_and_keeps_the_rest(self):
        car = car_pace_to_physics(-2.0)  # fator 1.02
        self.assertAlmostEqual(car.v_max_straight_kmh, DEFAULT_CAR_PHYSICS.v_max_straight_kmh * 1.02)
        self.assertAlmostEqual(car.grip_mu, DEFAULT_CAR_PHYSICS.grip_mu * 1.02)
        self.assertAlmostEqual(car.power_kw, DEFAULT_CAR_PHYSICS.power_kw * 1.02)
        # downforce, arrasto, massa e tracao permanecem do carro de referencia
        self.assertEqual(car.downforce_cla_m2, DEFAULT_CAR_PHYSICS.downforce_cla_m2)
        self.assertEqual(car.drag_cda_m2, DEFAULT_CAR_PHYSICS.drag_cda_m2)
        self.assertEqual(car.mass_kg, DEFAULT_CAR_PHYSICS.mass_kg)
        self.assertEqual(car.traction_share, DEFAULT_CAR_PHYSICS.traction_share)

    def test_rejects_non_finite_and_non_positive_factor(self):
        with self.assertRaises(ValueError):
            car_pace_to_physics(float("nan"))
        with self.assertRaises(ValueError):
            car_pace_to_physics(100.0)  # fator = 0
        with self.assertRaises(ValueError):
            car_pace_to_physics(True)  # bool nao e numero


class CarPresetTest(unittest.TestCase):
    def _preset(self, **overrides) -> CarPreset:
        defaults = dict(
            team_id="team:1",
            team_name="Equipe",
            pace_offset_pct=-0.5,
            characterization="ct",
            source_kind="heuristic",
            parameter_version="v1",
            rationale="r",
        )
        defaults.update(overrides)
        return CarPreset(**defaults)

    def test_valid_preset(self):
        preset = self._preset()
        self.assertEqual(preset.team_id, "team:1")
        self.assertEqual(preset.pace_offset_pct, -0.5)

    def test_rejects_empty_fields_and_non_heuristic(self):
        with self.assertRaises(ValueError):
            self._preset(team_id=" ")
        with self.assertRaises(ValueError):
            self._preset(team_name=" ")
        with self.assertRaises(ValueError):
            self._preset(characterization=" ")
        with self.assertRaises(ValueError):
            self._preset(parameter_version=" ")
        with self.assertRaises(ValueError):
            self._preset(rationale=" ")
        with self.assertRaises(ValueError):
            self._preset(source_kind="calibrated")
        with self.assertRaises(ValueError):
            self._preset(pace_offset_pct=float("inf"))


class CarPresetsJsonTest(unittest.TestCase):
    def test_loads_the_versioned_file_with_ten_teams(self):
        presets, disclaimer = load_car_preset_file(CAR_PRESETS)
        self.assertTrue(disclaimer)
        self.assertEqual(len(presets), 10)
        self.assertIn("team:9", presets)
        self.assertEqual(presets["team:9"].team_name, "Red Bull")
        self.assertEqual(presets["team:9"].source_kind, "heuristic")
        for preset in presets.values():
            self.assertLessEqual(abs(preset.pace_offset_pct), 5.0)

    def _write(self, payload) -> Path:
        path = Path(tempfile.mkdtemp()) / "cars.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _root(self, **overrides) -> dict:
        base = {
            "source_kind": "heuristic",
            "parameter_version": "v",
            "rationale": "r",
            "fictional_profiles": True,
            "disclaimer": "d",
        }
        base.update(overrides)
        return base

    def _team(self, **overrides) -> dict:
        base = {
            "team_id": "team:1",
            "team_name": "A",
            "pace_offset_pct": -1.0,
            "characterization": "c",
        }
        base.update(overrides)
        return base

    def test_rejects_unknown_root_keys(self):
        with self.assertRaises(CarPresetError):
            load_car_preset_file(self._write(self._root(extra=1, teams=[])))

    def test_rejects_non_heuristic_source_and_non_true_flag(self):
        with self.assertRaises(CarPresetError):
            load_car_preset_file(self._write(self._root(source_kind="calibrated", teams=[])))
        with self.assertRaises(CarPresetError):
            load_car_preset_file(self._write(self._root(fictional_profiles=False, teams=[])))

    def test_rejects_bad_team_id_and_out_of_range_pace(self):
        bad_id = self._root(teams=[self._team(team_id="redbull")])
        with self.assertRaises(CarPresetError):
            load_car_preset_file(self._write(bad_id))
        big_pace = self._root(teams=[self._team(pace_offset_pct=-99.0)])
        with self.assertRaises(CarPresetError):
            load_car_preset_file(self._write(big_pace))

    def test_rejects_duplicate_team_id(self):
        team = self._team()
        with self.assertRaises(CarPresetError):
            load_car_preset_file(self._write(self._root(teams=[team, team])))


class EngineSeamTest(unittest.TestCase):
    """O ponto exato que os dois motores usam para a volta base por piloto."""

    def test_per_team_car_orders_the_physical_lap(self):
        track = _circle(120.0)
        fast = car_pace_to_physics(-1.5)
        slow = car_pace_to_physics(1.5)
        t_fast = GripLapTimes(track, physics_for(None, fast)).lap_ms(1.0)
        t_ref = GripLapTimes(track, physics_for(None, DEFAULT_CAR_PHYSICS)).lap_ms(1.0)
        t_slow = GripLapTimes(track, physics_for(None, slow)).lap_ms(1.0)
        self.assertLess(t_fast, t_ref)
        self.assertLess(t_ref, t_slow)

    def test_driver_and_car_compose_without_breaking(self):
        track = _circle(120.0)
        quick_in_slow = physics_for(_attrs(pace_offset_pct=-0.5), car_pace_to_physics(1.5))
        slow_in_quick = physics_for(_attrs(pace_offset_pct=0.5), car_pace_to_physics(-1.5))
        GripLapTimes(track, quick_in_slow).lap_ms(1.0)
        GripLapTimes(track, slow_in_quick).lap_ms(1.0)


class TwoDEngineWiringTest(unittest.TestCase):
    def _entrant(self, driver_id, name, grid_position):
        return {
            "driver_id": driver_id,
            "name": name,
            "grid_position": grid_position,
            "aggression": 1.0,
            "compound": "MEDIUM",
        }

    def test_faster_car_wins_from_behind(self):
        geometry = _square()
        entrants = [
            self._entrant("slow", "Slow", 1),
            self._entrant("fast", "Fast", 2),
        ]
        result = simulate_2d_race(
            entrants,
            geometry,
            total_laps=3,
            rng=SeededRandomSource(7).spawn("2d-test"),
            base_physics_by_id={"fast": car_pace_to_physics(-4.0)},
            standing_start=False,
        )
        self.assertEqual(result["classification"][0]["driver_id"], "fast")
        self.assertLess(
            result["classification"][0]["total_time_ms"],
            result["classification"][1]["total_time_ms"],
        )

    def test_without_per_team_map_both_cars_finish(self):
        geometry = _square()
        entrants = [
            self._entrant("a", "A", 1),
            self._entrant("b", "B", 2),
        ]
        result = simulate_2d_race(
            entrants,
            geometry,
            total_laps=2,
            rng=SeededRandomSource(7).spawn("2d-test"),
            standing_start=False,
        )
        self.assertEqual(len(result["classification"]), 2)


if __name__ == "__main__":
    unittest.main()
