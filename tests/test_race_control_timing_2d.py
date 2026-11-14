"""SC de cinco voltas deve afetar o lider e o restante na mesma volta."""

import unittest
from unittest.mock import patch

from f1_simulator.adapters.driver_presets_json import load_driver_presets
from f1_simulator.domain import race_simulation_2d
from f1_simulator.domain.race_control import (
    HEURISTIC_RACE_CONTROL,
    SC,
    VSC,
    Incident,
    RaceControlState,
    effects,
)
from f1_simulator.domain.random_source import SeededRandomSource
from tests.geometry_support import attribute, fixture_geometry
from tests.race_invariants import entrants


def _forced_step(state, incidents, rng, params, lap):
    """Ative SC nas voltas 2–6; nenhum evento aleatorio altera o experimento."""

    if lap <= 5:
        return RaceControlState(
            status=SC,
            laps_remaining=6 - lap,
            cause=Incident(1, "contact", ("test",)),
        ), []
    return RaceControlState(), []


class RaceControlTiming2DTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        presets = list(
            load_driver_presets("configs/drivers/perfis-ficticios.json").values()
        )[:20]
        entries = []
        for pos, preset in enumerate(presets, 1):
            attrs = attribute(preset.driver_id, **preset.values)
            entries.append(
                {
                    "driver_id": preset.driver_id,
                    "name": preset.driver_name,
                    "grid_position": pos,
                    "attributes": attrs,
                    "aggression": attrs.aggression,
                }
            )
        with patch.object(race_simulation_2d, "step", _forced_step):
            cls.race = race_simulation_2d.simulate_2d_race(
                entries,
                fixture_geometry(),
                total_laps=8,
                rng=SeededRandomSource(2),
                dt_s=0.2,
            )

    def test_leader_and_other_active_cars_use_the_status_of_each_lap(self):
        race = self.race
        status_by_lap = {
            row["lap"]: row["status"] for row in race["race_control_by_lap"]
        }
        self.assertEqual(
            [status_by_lap[lap] for lap in range(2, 8)], ["SC"] * 5 + ["GREEN"]
        )
        sc_factor = effects(
            RaceControlState(
                status=SC, laps_remaining=1, cause=Incident(1, "contact", ("test",))
            ),
            HEURISTIC_RACE_CONTROL,
        ).lap_time_factor
        cars = race["speed_breakdown"]["cars"]
        for lap in range(1, 9):
            expected = sc_factor if 2 <= lap <= 6 else 1.0
            # Inclui o lider ao cruzar a linha e todos os demais com dados da volta.
            leader = race["history"][lap - 1]["cars"][0]["driver_id"]
            self.assertEqual(cars[leader]["laps"][str(lap)]["control_factor"], expected)
            seen = [
                car["laps"][str(lap)]["control_factor"]
                for car in cars.values()
                if str(lap) in car["laps"]
            ]
            self.assertGreater(len(seen), 1)
            self.assertTrue(all(factor == expected for factor in seen), (lap, seen))

    def test_forced_safety_car_does_not_give_leader_a_free_lap(self):
        first, second = self.race["history"][1]["cars"][:2]
        gap_s = (second["total_time_ms"] - first["total_time_ms"]) / 1000
        # No mesmo cenario antes da correcao o intervalo era 40,22 s.
        self.assertLess(gap_s, 20.0)

    def test_green_without_incidents_matches_disabled_control(self):
        original = race_simulation_2d.integrate_field

        def no_contact(*args, **kwargs):
            kwargs["rng"] = None
            return original(*args, **kwargs)

        with patch.object(race_simulation_2d, "integrate_field", no_contact):
            green = race_simulation_2d.simulate_2d_race(
                entrants(4),
                fixture_geometry(),
                total_laps=3,
                rng=SeededRandomSource(2),
                dt_s=0.2,
            )
            disabled = race_simulation_2d.simulate_2d_race(
                entrants(4),
                fixture_geometry(),
                total_laps=3,
                rng=SeededRandomSource(2),
                dt_s=0.2,
                race_control=None,
            )
        self.assertEqual(green["history"], disabled["history"])
        self.assertEqual(green["trajectories_2d"], disabled["trajectories_2d"])

    def test_virtual_safety_car_is_applied_and_removed_for_each_car(self):
        cause = Incident(1, "mechanical", ("test",))

        def vsc_step(state, incidents, rng, params, lap):
            if lap <= 2:
                return RaceControlState(status=VSC, laps_remaining=1, cause=cause), []
            return RaceControlState(), []

        with patch.object(race_simulation_2d, "step", vsc_step):
            race = race_simulation_2d.simulate_2d_race(
                entrants(4),
                fixture_geometry(),
                total_laps=4,
                rng=SeededRandomSource(2),
                dt_s=0.2,
            )
        vsc = effects(RaceControlState(status=VSC, laps_remaining=1, cause=cause))
        for car in race["speed_breakdown"]["cars"].values():
            for lap, expected in (
                (1, 1.0),
                (2, vsc.lap_time_factor),
                (3, vsc.lap_time_factor),
                (4, 1.0),
            ):
                self.assertEqual(car["laps"][str(lap)]["control_factor"], expected)


if __name__ == "__main__":
    unittest.main()
