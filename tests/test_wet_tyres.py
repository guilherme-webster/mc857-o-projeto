"""Pneus de chuva: aderencia por agua, desgaste, risco e decisao (issue #120)."""

from __future__ import annotations

import unittest

from f1_simulator.application.build_grid import GridEntry
from f1_simulator.application.run_grid_simulation import (
    RaceSetup,
    run_grid_simulation,
)
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.strategy import (
    HeuristicPitStrategy,
    StrategyState,
    draw_weather_switch_bias,
)
from f1_simulator.domain.track_condition import water_grip_factor
from f1_simulator.domain.tyres import TyreSet
from f1_simulator.domain.weather import RainLevel, WeatherSegment
from f1_simulator.domain.wet_tyres import (
    INTERMEDIATE,
    SLICK,
    WET,
    WET_COMPOUNDS,
    absolute_grip,
    best_tyre_class,
    contact_multiplier,
    crash_multiplier,
    relative_grip,
    wear_factor,
)
from tests.geometry_support import attribute
from tests.model_support import parameters, track
from tests.test_track_condition import _fixture_geometry


class WetTyreGripTest(unittest.TestCase):
    def test_each_tyre_owns_its_water_range(self):
        self.assertEqual(best_tyre_class(0.0), SLICK)
        self.assertEqual(best_tyre_class(0.2), INTERMEDIATE)
        self.assertEqual(best_tyre_class(0.8), WET)

    def test_the_right_tyre_pays_nothing_and_the_wrong_one_pays_a_lot(self):
        for water in (0.0, 0.2, 0.3, 0.8, 1.0):
            best = best_tyre_class(water)
            compound = "MEDIUM" if best == SLICK else best
            self.assertEqual(relative_grip(compound, water), 1.0)
        self.assertLess(relative_grip("SOFT", 1.0), 0.6)
        self.assertLess(relative_grip(WET, 0.0), 0.9)

    def test_curves_meet_the_track_anchors(self):
        # Com o pneu adequado, a aderencia e a ancora da pista (ADR 0015).
        self.assertAlmostEqual(absolute_grip(INTERMEDIATE, 0.3), water_grip_factor(0.3))
        self.assertAlmostEqual(absolute_grip(WET, 1.0), water_grip_factor(1.0))

    def test_wet_tyres_overheat_on_a_drying_track(self):
        self.assertEqual(wear_factor("MEDIUM", 0.0), 1.0)
        self.assertEqual(wear_factor(INTERMEDIATE, 0.5), 1.0)
        self.assertGreater(wear_factor(WET, 0.0), wear_factor(INTERMEDIATE, 0.0))
        self.assertGreater(wear_factor(INTERMEDIATE, 0.02), 1.0)

    def test_risk_grows_with_water_and_the_wrong_tyre(self):
        self.assertEqual(crash_multiplier("MEDIUM", 0.0), 1.0)
        self.assertEqual(contact_multiplier(0.0), 1.0)
        right = crash_multiplier(WET, 0.9)
        wrong = crash_multiplier("MEDIUM", 0.9)
        self.assertGreater(right, 1.0)
        self.assertGreater(wrong, right)
        self.assertLess(crash_multiplier(WET, 0.9, wet_skill=1.3), right)


def _state(compound, water, *, lap=20, used=(), free=False, pit_loss_factor=1.0):
    return StrategyState(
        lap_number=lap,
        total_laps=50,
        tyre=TyreSet(compound, 5),
        stops_made=0,
        compounds_used=used,
        free_tyre_change=free,
        pit_loss_factor=pit_loss_factor,
        surface_water=water,
    )


class WeatherStrategyTest(unittest.TestCase):
    def setUp(self):
        self.strategy = HeuristicPitStrategy(parameters(), track())

    def test_slicks_in_heavy_rain_pit_for_wets(self):
        decision = self.strategy.decide(_state("MEDIUM", 0.8))
        self.assertTrue(decision.pit)
        self.assertEqual(decision.compound, WET)

    def test_wets_on_a_dry_track_go_back_to_slicks(self):
        decision = self.strategy.decide(_state(WET, 0.0))
        self.assertTrue(decision.pit)
        self.assertNotIn(decision.compound, WET_COMPOUNDS)

    def test_right_tyre_stays_out(self):
        self.assertFalse(self.strategy.decide(_state(INTERMEDIATE, 0.25)).pit)

    def test_bias_separates_the_gambler_from_the_cautious(self):
        # Garoa leve: o slick ainda e quase o melhor; quem aposta fica na pista.
        water = 0.09
        cautious = HeuristicPitStrategy(parameters(), track(), weather_switch_bias=0.5)
        gambler = HeuristicPitStrategy(parameters(), track(), weather_switch_bias=2.0)
        self.assertTrue(cautious.decide(_state("MEDIUM", water)).pit)
        self.assertFalse(gambler.decide(_state("MEDIUM", water)).pit)

    def test_red_flag_change_always_takes_the_right_tyre(self):
        decision = self.strategy.decide(_state("MEDIUM", 0.12, free=True))
        self.assertTrue(decision.pit)
        self.assertEqual(decision.compound, INTERMEDIATE)

    def test_wet_tyres_lift_the_two_compound_rule(self):
        # Na ultima volta regular, quem so usou MEDIUM e obrigado a parar;
        # quem ja usou intermediario, nao.
        last_regular = 50 - 3
        forced = self.strategy.decide(_state("MEDIUM", 0.0, lap=last_regular))
        free = self.strategy.decide(
            _state("MEDIUM", 0.0, lap=last_regular, used=(INTERMEDIATE,))
        )
        self.assertTrue(forced.pit)
        self.assertFalse(free.pit)

    def test_without_water_the_legacy_contract_holds(self):
        legacy = StrategyState(20, 50, TyreSet("MEDIUM", 5), 0)
        self.assertFalse(self.strategy.decide(legacy).pit)

    def test_switch_bias_is_drawn_from_aggression_and_seed(self):
        draws = [
            draw_weather_switch_bias(aggression, SeededRandomSource(1), "t")
            for aggression in (0.7, 1.0, 1.4)
        ]
        self.assertEqual(draws, sorted(draws))
        self.assertTrue(all(0.5 <= value <= 2.0 for value in draws))


class WetRaceTest(unittest.TestCase):
    def _race(self, weather, laps=30, seed=3):
        geometry = _fixture_geometry("circuit:6")
        grid = tuple(GridEntry(f"driver:{i}", f"P{i}", "team:1", "Team") for i in range(6))
        attributes = {entry.driver_id: attribute(entry.driver_id) for entry in grid}
        return run_grid_simulation(
            grid,
            attributes,
            RaceSetup(total_laps=laps, track_id="circuit:6", weather=weather),
            parameters=parameters(),
            lap_length_m=geometry.lap_length_m,
            rng=SeededRandomSource(seed),
            geometry=geometry,
            race_control=None,
        )

    @staticmethod
    def _compounds(result):
        return {car["compound"] for row in result["history"] for car in row["cars"]}

    def test_rain_mid_race_puts_the_field_on_wet_tyres(self):
        result = self._race((WeatherSegment(8, 20, RainLevel.HEAVY),))
        self.assertTrue(self._compounds(result) & set(WET_COMPOUNDS))

    def test_a_wet_start_uses_wet_tyres_from_the_grid(self):
        result = self._race((WeatherSegment(1, 30, RainLevel.HEAVY),))
        self.assertIn(result["starting_grid"][0]["compound"], WET_COMPOUNDS)
        kinds = {a["kind"]: a for a in result["assumptions"]}
        self.assertIn("wet_tyres", kinds["track_condition"])

    def test_a_dry_race_never_sees_wet_tyres(self):
        self.assertFalse(self._compounds(self._race(())) & set(WET_COMPOUNDS))


if __name__ == "__main__":
    unittest.main()
