"""Presets heuristicos de equipe (execucao de pit) e carro por piloto.

Cobre a terceira heuristica (ADR 0008): o adaptador JSON de equipe, o arquivo
versionado, a ligacao do fator de execucao ao tempo de pit nos dois motores,
e a variacao de carro por piloto (override sobre o ritmo da equipe). A
confiabilidade mecanica calibrada nao e tocada por nenhuma dessas pecas.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from f1_simulator.adapters.car_presets_json import (
    CarPresetError,
    load_car_preset_file_with_overrides,
)
from f1_simulator.adapters.team_presets_json import (
    TeamPresetError,
    load_team_preset_file,
)
from f1_simulator.application.team_presets import TeamPreset
from f1_simulator.domain.pit_lane import PitLaneParameters
from f1_simulator.domain.race_simulation_2d import simulate_2d_race
from f1_simulator.domain.random_source import SeededRandomSource
from tests.test_pit_lane import pit_geometry

ROOT = Path(__file__).resolve().parents[1]
CAR_PRESETS = ROOT / "configs" / "cars" / "perfis-ficticios.json"
TEAM_PRESETS = ROOT / "configs" / "teams" / "perfis-ficticios.json"


class TeamPresetTest(unittest.TestCase):
    def _preset(self, **overrides) -> TeamPreset:
        defaults = dict(
            team_id="team:1",
            team_name="Equipe",
            pit_execution_factor=1.1,
            characterization="ct",
            source_kind="heuristic",
            parameter_version="v1",
            rationale="r",
        )
        defaults.update(overrides)
        return TeamPreset(**defaults)

    def test_valid_and_invalid(self):
        self.assertEqual(self._preset().pit_execution_factor, 1.1)
        with self.assertRaises(ValueError):
            self._preset(pit_execution_factor=0.0)
        with self.assertRaises(ValueError):
            self._preset(pit_execution_factor=float("inf"))
        with self.assertRaises(ValueError):
            self._preset(source_kind="calibrated")
        with self.assertRaises(ValueError):
            self._preset(team_id=" ")


class TeamPresetsJsonTest(unittest.TestCase):
    def test_loads_versioned_file(self):
        presets, disclaimer = load_team_preset_file(TEAM_PRESETS)
        self.assertTrue(disclaimer)
        self.assertEqual(len(presets), 10)
        # Ferrari desorganizada perde tempo; Red Bull ganha.
        self.assertGreater(presets["team:6"].pit_execution_factor, 1.0)
        self.assertLess(presets["team:9"].pit_execution_factor, 1.0)

    def _write(self, payload) -> Path:
        path = Path(tempfile.mkdtemp()) / "teams.json"
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
            "pit_execution_factor": 1.1,
            "characterization": "c",
        }
        base.update(overrides)
        return base

    def test_rejects_out_of_range_factor(self):
        with self.assertRaises(TeamPresetError):
            load_team_preset_file(
                self._write(self._root(teams=[self._team(pit_execution_factor=2.0)]))
            )

    def test_rejects_unknown_keys_and_duplicate_team(self):
        with self.assertRaises(TeamPresetError):
            load_team_preset_file(
                self._write(self._root(teams=[self._team(extra=1)]))
            )
        team = self._team()
        with self.assertRaises(TeamPresetError):
            load_team_preset_file(self._write(self._root(teams=[team, team])))


class CarOverridesJsonTest(unittest.TestCase):
    def test_production_file_carries_per_driver_overrides(self):
        presets, _disclaimer, overrides = load_car_preset_file_with_overrides(
            CAR_PRESETS
        )
        self.assertEqual(len(presets), 10)
        # Red Bull tem override por piloto no arquivo versionado.
        self.assertIn("driver:830", overrides)
        self.assertIn("driver:815", overrides)
        self.assertLess(overrides["driver:830"], overrides["driver:815"])

    def _car_root(self, teams) -> dict:
        return {
            "source_kind": "heuristic",
            "parameter_version": "v",
            "rationale": "r",
            "fictional_profiles": True,
            "disclaimer": "d",
            "teams": teams,
        }

    def _write(self, payload) -> Path:
        path = Path(tempfile.mkdtemp()) / "cars.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_overrides_optional_and_validated(self):
        # Sem o campo: nenhum override.
        base = self._car_root(
            [{"team_id": "team:1", "team_name": "A", "pace_offset_pct": -1.0, "characterization": "c"}]
        )
        _p, _d, overrides = load_car_preset_file_with_overrides(self._write(base))
        self.assertEqual(overrides, {})
        # Com o campo: id canonico e faixa validados.
        bad = self._car_root(
            [
                {
                    "team_id": "team:1",
                    "team_name": "A",
                    "pace_offset_pct": -1.0,
                    "characterization": "c",
                    "driver_overrides": {"max": -0.2},
                }
            ]
        )
        with self.assertRaises(CarPresetError):
            load_car_preset_file_with_overrides(self._write(bad))

    def test_same_driver_in_two_teams_is_rejected(self):
        payload = self._car_root(
            [
                {
                    "team_id": "team:1",
                    "team_name": "A",
                    "pace_offset_pct": -1.0,
                    "characterization": "c",
                    "driver_overrides": {"driver:1": -0.2},
                },
                {
                    "team_id": "team:2",
                    "team_name": "B",
                    "pace_offset_pct": 1.0,
                    "characterization": "c",
                    "driver_overrides": {"driver:1": 0.2},
                },
            ]
        )
        with self.assertRaises(CarPresetError):
            load_car_preset_file_with_overrides(self._write(payload))


class PitExecutionWiringTest(unittest.TestCase):
    """A execucao de equipe escala o tempo de servico no motor 2D."""

    def _entrant(self, driver_id, grid_position):
        return {
            "driver_id": driver_id,
            "name": driver_id,
            "grid_position": grid_position,
            "aggression": 1.0,
            "compound": "MEDIUM",
        }

    def test_slow_box_costs_more_time_on_a_forced_stop(self):
        from f1_simulator.domain.model_parameters import ASSUMED_WET_COMPOUNDS
        from f1_simulator.domain.strategy import PlannedStopStrategy
        from tests.model_support import parameters
        from tests.model_support import track as track_params

        geometry = pit_geometry()
        model = parameters()
        compounds = {c.name: c for c in (*model.compounds, *ASSUMED_WET_COMPOUNDS)}

        def run(execution):
            entrant = self._entrant("a", 1)
            # Estrategia explicita de uma parada: garante a visita ao box para
            # que o fator de execucao tenha efeito observavel.
            entrant["strategy"] = PlannedStopStrategy(1, ("SOFT",))
            return simulate_2d_race(
                [entrant],
                geometry,
                total_laps=6,
                rng=SeededRandomSource(3).spawn("2d"),
                compounds=compounds,
                track_params=track_params(),
                model_parameters=model,
                pit_execution_by_id={"a": execution},
                standing_start=False,
                pit_parameters=PitLaneParameters(service_time_s=3.0),
            )

        fast = run(0.5)
        slow = run(1.5)
        self.assertGreaterEqual(fast["classification"][0]["stops_made"], 1)
        self.assertGreater(
            slow["classification"][0]["total_time_ms"],
            fast["classification"][0]["total_time_ms"],
        )


if __name__ == "__main__":
    unittest.main()
