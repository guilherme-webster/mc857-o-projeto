from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from f1_simulator.adapters.persistence.sqlite_trotman_profiles import (
    ASSUMED_RAINFALL,
    UNKNOWN_COMPOUND,
    assess_trotman_races,
    races_before,
)
from f1_simulator.application.pace_profiles import (
    TROTMAN_PROFILE_CONFIG,
    PaceProfile,
    build_pace_profiles,
    reference_times_from_profiles,
)
from f1_simulator.domain.driver_profile import LapAssessment, PaceContext

SCHEMA = """
CREATE TABLE races (race_id TEXT PRIMARY KEY, season INTEGER, round_number INTEGER,
                    circuit_id TEXT, name TEXT);
CREATE TABLE race_results (race_id TEXT, driver_id TEXT, team_id TEXT);
CREATE TABLE pit_stops (race_id TEXT, driver_id TEXT, lap_number INTEGER);
CREATE TABLE laps (race_id TEXT, driver_id TEXT, lap_number INTEGER, lap_time_ms INTEGER);
"""


def build_database(path: Path, *, races: int = 4, drivers: int = 6) -> None:
    """Historico sintetico: cada piloto tem um ritmo proprio e estavel.

    O piloto ``driver:0`` e o mais rapido e ``driver:5`` o mais lento, por
    construcao. Um estimador que funcione precisa recuperar essa ordem.
    """

    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    for race in range(races):
        connection.execute(
            "INSERT INTO races VALUES (?,?,?,?,?)",
            (f"race:{race}", 2023, race + 1, f"circuit:{race % 2}", f"GP {race}"),
        )
        for driver in range(drivers):
            did = f"driver:{driver}"
            connection.execute(
                "INSERT INTO race_results VALUES (?,?,?)",
                (f"race:{race}", did, f"team:{driver // 2}"),
            )
            connection.execute(
                "INSERT INTO pit_stops VALUES (?,?,?)", (f"race:{race}", did, 20)
            )
            for lap in range(1, 41):
                base = 90_000 + driver * 400
                connection.execute(
                    "INSERT INTO laps VALUES (?,?,?,?)",
                    (f"race:{race}", did, lap, base + (lap % 3) * 20),
                )
    connection.commit()
    connection.close()


class TrotmanAssessmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.db = Path(self._dir.name) / "history.sqlite"
        build_database(self.db)

    def tearDown(self) -> None:
        self._dir.cleanup()

    def test_builds_assessments_the_issue40_estimator_accepts(self) -> None:
        assessments, drivers = assess_trotman_races(
            self.db, ("race:0", "race:1"), TROTMAN_PROFILE_CONFIG
        )
        self.assertTrue(assessments)
        self.assertEqual(len(drivers), 6)
        self.assertIsInstance(assessments[0], LapAssessment)
        included = [a for a in assessments if not a.exclusions]
        self.assertIsInstance(included[0].context, PaceContext)

    def test_missing_context_is_declared_not_invented(self) -> None:
        # O Trotman nao tem composto nem clima. O contexto precisa dizer isso
        # em vez de afirmar uma condicao que ninguem observou.
        assessments, _ = assess_trotman_races(
            self.db, ("race:0",), TROTMAN_PROFILE_CONFIG
        )
        context = next(a.context for a in assessments if a.context)
        self.assertEqual(context.compound, UNKNOWN_COMPOUND)
        self.assertEqual(context.rainfall, ASSUMED_RAINFALL)

    def test_excludes_first_pit_and_out_laps(self) -> None:
        assessments, _ = assess_trotman_races(
            self.db, ("race:0",), TROTMAN_PROFILE_CONFIG
        )
        by_lap = {
            (a.driver_id, a.lap_number): a.exclusions
            for a in assessments
            if a.driver_id == "driver:0"
        }
        self.assertIn("first_lap", by_lap[("driver:0", 1)])
        self.assertIn("pit_lap", by_lap[("driver:0", 20)])
        self.assertIn("out_lap", by_lap[("driver:0", 21)])
        self.assertEqual(by_lap[("driver:0", 15)], ())

    def test_tyre_age_resets_after_the_stop(self) -> None:
        assessments, _ = assess_trotman_races(
            self.db, ("race:0",), TROTMAN_PROFILE_CONFIG
        )
        contexts = {
            a.lap_number: a.context
            for a in assessments
            if a.driver_id == "driver:0" and a.context
        }
        # Volta 22 e a segunda do novo stint: idade 1, janela 0.
        self.assertEqual(contexts[22].tyre_age_window_start, 0)
        self.assertGreater(contexts[19].tyre_age_window_start, 0)

    def test_empty_race_list_returns_nothing(self) -> None:
        self.assertEqual(assess_trotman_races(self.db, (), TROTMAN_PROFILE_CONFIG), ((), ()))


class RacesBeforeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.db = Path(self._dir.name) / "history.sqlite"
        build_database(self.db)

    def tearDown(self) -> None:
        self._dir.cleanup()

    def test_excludes_the_race_itself_and_everything_after(self) -> None:
        # Este corte e o que torna o perfil fora da amostra. Sem ele o
        # experimento mediria memorizacao.
        prior = races_before(self.db, "race:2")
        self.assertEqual(prior, ("race:0", "race:1"))

    def test_first_race_has_no_history(self) -> None:
        self.assertEqual(races_before(self.db, "race:0"), ())

    def test_window_limits_how_far_back_it_reaches(self) -> None:
        self.assertEqual(races_before(self.db, "race:3", max_races=1), ("race:2",))

    def test_unknown_race_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            races_before(self.db, "race:404")


class BuildProfilesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.db = Path(self._dir.name) / "history.sqlite"
        build_database(self.db, races=5)

    def tearDown(self) -> None:
        self._dir.cleanup()

    def test_recovers_the_constructed_pace_order(self) -> None:
        assessments, drivers = assess_trotman_races(
            self.db, races_before(self.db, "race:4"), TROTMAN_PROFILE_CONFIG
        )
        profiles, _ = build_pace_profiles(assessments, drivers)
        self.assertTrue(profiles)
        ordered = sorted(profiles.values(), key=lambda p: p.pace_delta_pct)
        # driver:0 foi construido como o mais rapido do grid.
        self.assertEqual(ordered[0].driver_id, "driver:0")
        self.assertEqual(ordered[-1].driver_id, "driver:5")

    def test_empty_input_yields_no_profiles(self) -> None:
        self.assertEqual(build_pace_profiles((), ()), ({}, ()))


class ReferenceTimesTest(unittest.TestCase):
    def test_field_level_comes_from_the_weekend_and_order_from_the_profile(self) -> None:
        weekend = {"a": 90_000.0, "b": 92_000.0, "c": 94_000.0}
        profiles = {
            "a": PaceProfile("a", -2.0, 5, 200),
            "b": PaceProfile("b", 0.0, 5, 200),
            "c": PaceProfile("c", +2.0, 5, 200),
        }
        references, coverage = reference_times_from_profiles(weekend, profiles)
        # Nivel = mediana do campo (92.000); o perfil so desloca em torno dele.
        self.assertAlmostEqual(references["b"], 92_000.0, places=6)
        self.assertAlmostEqual(references["a"], 92_000.0 * 0.98, places=6)
        self.assertAlmostEqual(references["c"], 92_000.0 * 1.02, places=6)
        self.assertEqual(coverage.profiled, 3)
        self.assertEqual(coverage.fell_back, 0)

    def test_driver_without_profile_keeps_the_weekend_pace(self) -> None:
        # Substituir por um valor neutro faria o piloto parecer mediano em vez
        # de desconhecido, e distorceria a comparacao entre as fontes.
        weekend = {"a": 90_000.0, "b": 92_000.0}
        references, coverage = reference_times_from_profiles(
            weekend, {"a": PaceProfile("a", -1.0, 4, 100)}
        )
        self.assertEqual(references["b"], 92_000.0)
        self.assertEqual(coverage.profiled, 1)
        self.assertEqual(coverage.fell_back, 1)

    def test_absurd_offset_falls_back_instead_of_breaking_the_race(self) -> None:
        weekend = {"a": 90_000.0, "b": 90_000.0}
        references, _ = reference_times_from_profiles(
            weekend, {"a": PaceProfile("a", -250.0, 4, 100)}
        )
        self.assertEqual(references["a"], 90_000.0)

    def test_rejects_an_empty_field(self) -> None:
        with self.assertRaises(ValueError):
            reference_times_from_profiles({}, {})


if __name__ == "__main__":
    unittest.main()
