"""Ponta a ponta do motor 2D (``simulate_2d_race``) na geometria real reduzida.

Roda corridas curtas (poucos carros e voltas) no circuito do fixture
``trotman_v128_tracks_2025``, sem rede. As corridas custosas sao simuladas uma
vez em ``setUpClass`` e compartilhadas; os testes so leem os resultados. As
invariantes vivem em ``tests/race_invariants.py`` para os testes de regressao
dos bugs #140 e #141 as reusarem.
"""

import json
import unittest

from f1_simulator.domain.race_simulation_2d import simulate_2d_race
from f1_simulator.domain.random_source import SeededRandomSource
from tests.geometry_support import attribute
from tests.model_support import parameters, track
from tests.race_invariants import (
    assert_classification_invariants,
    assert_effect_moves_only_with_stops,
    assert_fuel_never_increases,
    assert_history_invariants,
    assert_same_race,
    driver_ids,
    entrants,
    fuel_plan,
    real_geometry,
    stop_laps,
)

CARS = 4
PLAIN_LAPS = 5
LONG_LAPS = 12
# Probabilidade alta de falha mecanica por volta para forcar abandonos em
# poucas voltas; so este cenario usa, e a semente e fixa.
HAZARD = 0.25


class RaceSimulation2DTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geometry = real_geometry()
        cls.entries = entrants(CARS)
        cls.ids = driver_ids(cls.entries)
        cls.model = parameters()
        cls.plain = cls.run_plain(seed=1)
        cls.plain_again = cls.run_plain(seed=1)
        cls.other_seed = cls.run_plain(seed=2)
        cls.retirements = cls.run_plain(seed=3, mechanical_hazard_per_lap=HAZARD)
        cls.retirements_again = cls.run_plain(
            seed=3, mechanical_hazard_per_lap=HAZARD
        )
        cls.progress: list[tuple[int, int]] = []
        cls.long = cls.run_long(on_progress=lambda *a: cls.progress.append(a))
        cls.fuel_only = simulate_2d_race(
            cls.entries,
            cls.geometry,
            total_laps=PLAIN_LAPS,
            rng=SeededRandomSource(1),
            fuel=fuel_plan(cls.geometry),
        )

    @classmethod
    def run_plain(cls, *, seed, **kwargs):
        return simulate_2d_race(
            cls.entries,
            cls.geometry,
            total_laps=PLAIN_LAPS,
            rng=SeededRandomSource(seed),
            **kwargs,
        )

    @classmethod
    def run_long(cls, **kwargs):
        """Pneu, pit stop (heuristico) e combustivel ligados, corrida mais longa."""

        return simulate_2d_race(
            cls.entries,
            cls.geometry,
            total_laps=LONG_LAPS,
            rng=SeededRandomSource(1),
            compounds={c.name: c for c in cls.model.compounds},
            track_params=track(),
            model_parameters=cls.model,
            fuel=fuel_plan(cls.geometry),
            **kwargs,
        )

    def test_contact_rate_is_disclosed_as_assumed_and_versioned(self):
        contact = self.plain["assumptions"][0]["side_contact"]
        self.assertEqual(contact["origin"], "assumed")
        self.assertEqual(contact["parameter_version"], "spatial-contact-severity-assumed-v2")
        self.assertEqual(contact["risk_basis"], "one_consequence_per_physical_episode")
        self.assertEqual(contact["harmless_closing_ms"], 2.0)
        self.assertNotIn("base_rate_per_second", contact)

    # --- reprodutibilidade -------------------------------------------------

    def test_same_seed_and_inputs_give_identical_outputs(self):
        assert_same_race(self, self.plain, self.plain_again)
        assert_same_race(self, self.retirements, self.retirements_again)
        json.dumps(self.plain, allow_nan=False)

    def test_different_seeds_give_different_results(self):
        # Sem aleatoriedade explicita a corrida nao depende da semente; a falha
        # mecanica sorteada por volta e o que a torna observavel.
        other = self.run_plain(seed=4, mechanical_hazard_per_lap=HAZARD)
        self.assertNotEqual(
            (self.retirements["history"], self.retirements["classification"]),
            (other["history"], other["classification"]),
        )

    # --- invariantes -------------------------------------------------------

    def test_classification_and_history_invariants(self):
        for name, result, laps in (
            ("plain", self.plain, PLAIN_LAPS),
            ("other_seed", self.other_seed, PLAIN_LAPS),
            ("retirements", self.retirements, PLAIN_LAPS),
            ("long", self.long, LONG_LAPS),
        ):
            with self.subTest(race=name):
                self.assertEqual(result["total_laps"], laps)
                assert_classification_invariants(self, result, self.ids, laps)
                assert_history_invariants(self, result, self.ids, laps)

    def test_clean_race_has_everybody_finish(self):
        rows = self.plain["classification"]
        self.assertTrue(all(row["status"] == "RUNNING" for row in rows))
        self.assertEqual({row["laps_completed"] for row in rows}, {PLAIN_LAPS})

    def test_retirement_has_cause_and_lap(self):
        retired = [
            row
            for row in self.retirements["classification"]
            if row["status"] == "RETIRED"
        ]
        self.assertTrue(retired, "a semente de teste deve produzir abandonos")
        for row in retired:
            self.assertEqual(row["retirement_cause"], "MECHANICAL")
            self.assertLess(row["laps_completed"], PLAIN_LAPS)
        # O abandono aparece no history a partir de uma volta e nao some.
        for row in retired:
            statuses = [
                next(r for r in e["cars"] if r["driver_id"] == row["driver_id"])[
                    "status"
                ]
                for e in self.retirements["history"]
            ]
            first = statuses.index("RETIRED")
            self.assertEqual(statuses[first:], ["RETIRED"] * (len(statuses) - first))

    # --- efeitos opcionais -------------------------------------------------

    def test_without_model_track_and_compounds_there_are_no_stops(self):
        for result in (self.plain, self.fuel_only):
            self.assertEqual(result["pit_stop_events"], [])
            self.assertFalse(result["assumptions"][0]["pit_active"])
            self.assertTrue(
                all(row["stops_made"] == 0 for row in result["classification"])
            )
        # Parametros parciais (sem model_parameters) tambem nao abrem boxes.
        partial = simulate_2d_race(
            self.entries[:2],
            self.geometry,
            total_laps=3,
            rng=SeededRandomSource(1),
            compounds={c.name: c for c in self.model.compounds},
            track_params=track(),
        )
        self.assertEqual(partial["pit_stop_events"], [])

    def test_long_race_with_all_parameters_makes_a_stop(self):
        self.assertTrue(self.long["assumptions"][0]["pit_active"])
        self.assertTrue(self.long["pit_stop_events"])
        self.assertTrue(
            any(row["stops_made"] >= 1 for row in self.long["classification"])
        )
        for did in self.ids:
            self.assertTrue(stop_laps(self.long, did), did)

    def test_fuel_mass_only_decreases_without_refuelling(self):
        for result in (self.long, self.fuel_only):
            for did in self.ids:
                assert_fuel_never_increases(self, result, did)
        for result in (self.long, self.fuel_only):
            for did in self.ids:
                rows = [
                    next(r for r in e["cars"] if r["driver_id"] == did)["fuel_kg"]
                    for e in result["history"]
                ]
                self.assertEqual(rows, sorted(rows, reverse=True))
                self.assertLess(rows[-1], rows[0])

    def test_speed_effect_of_fuel_moves_only_one_way_without_stops(self):
        for did in self.ids:
            assert_effect_moves_only_with_stops(
                self, self.long, did, "fuel_ms", direction="nonincreasing"
            )

    def test_fuel_share_decreases_when_other_effects_are_absent(self):
        for did in self.ids:
            laps = self.fuel_only["speed_breakdown"]["cars"][did]["laps"]
            rows = [row for _, row in sorted(laps.items(), key=lambda item: int(item[0]))]
            shares = [row["delta_shares"]["fuel"] for row in rows]
            self.assertGreater(shares[0], shares[-1])
            for before, after in zip(shares, shares[1:]):
                self.assertLessEqual(after, before + 1e-6, did)

    def test_speed_effect_of_tyre_wear_only_grows_between_stops(self):
        for did in self.ids:
            assert_effect_moves_only_with_stops(
                self, self.long, did, "tyre_ms", direction="nondecreasing"
            )

    # --- progresso ---------------------------------------------------------

    def test_on_progress_is_called_once_per_lap_in_order(self):
        self.assertEqual(
            self.progress, [(lap, LONG_LAPS) for lap in range(1, LONG_LAPS + 1)]
        )


class LapPaceNoiseTest(unittest.TestCase):
    """Ruido de ritmo por volta escalado pelo ``consistency_factor`` (issue #139)."""

    LAPS = 3

    @classmethod
    def setUpClass(cls):
        cls.geometry = real_geometry()
        cls.model = parameters()

    def run_race(self, consistency: float | None, *, with_model: bool = True):
        entry = entrants(1)[0]
        if consistency is not None:
            entry["attributes"] = attribute(
                entry["driver_id"], consistency_factor=consistency
            )
        return simulate_2d_race(
            [entry],
            self.geometry,
            total_laps=self.LAPS,
            rng=SeededRandomSource(5),
            model_parameters=self.model if with_model else None,
            race_control=None,
        )

    @staticmethod
    def noise_by_lap(race) -> dict[str, float]:
        laps = race["speed_breakdown"]["cars"]["d1"]["laps"]
        return {lap: data["noise_ms"] for lap, data in laps.items()}

    def test_noise_scales_exactly_with_the_consistency_factor(self):
        # Mesmo piloto e mesma semente: o fluxo do ruido e o mesmo, so a
        # escala muda. E por aqui que o atributo atua no motor 2D.
        steady = self.noise_by_lap(self.run_race(0.5))
        erratic = self.noise_by_lap(self.run_race(1.5))
        self.assertTrue(any(value != 0.0 for value in steady.values()))
        for lap, value in steady.items():
            with self.subTest(lap=lap):
                self.assertAlmostEqual(erratic[lap], 3.0 * value, places=2)

    def test_noise_follows_the_calibrated_scale(self):
        # |z| <= 6 com folga: o desvio nao pode passar de alguns sigmas.
        limit = 6.0 * self.model.lap_noise_ms
        for value in self.noise_by_lap(self.run_race(1.0)).values():
            self.assertLess(abs(value), limit)

    def test_noise_changes_the_race_time(self):
        steady = self.run_race(0.5)["classification"][0]["total_time_ms"]
        erratic = self.run_race(1.5)["classification"][0]["total_time_ms"]
        self.assertNotEqual(steady, erratic)

    def test_without_model_parameters_there_is_no_noise(self):
        race = self.run_race(1.5, with_model=False)
        self.assertEqual(set(self.noise_by_lap(race).values()), {0.0})
        kinds = {item["kind"] for item in race["assumptions"]}
        self.assertNotIn("lap_pace_noise_2d", kinds)

    def test_noise_is_disclosed_as_heuristic_over_a_calibrated_scale(self):
        race = self.run_race(1.5)
        entry = next(
            item for item in race["assumptions"] if item["kind"] == "lap_pace_noise_2d"
        )
        self.assertEqual(entry["origin"], "heuristic")
        self.assertEqual(entry["lap_noise_origin"], "calibrated")
        self.assertEqual(entry["lap_noise_ms"], self.model.lap_noise_ms)
        self.assertEqual(entry["consistency_factor_by_driver"], {"d1": 1.5})
        self.assertEqual(race, self.run_race(1.5))


if __name__ == "__main__":
    unittest.main()
