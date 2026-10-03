from __future__ import annotations

import unittest

from f1_simulator.domain.race_simulation import (
    RETIRED,
    RUNNING,
    Entrant,
    simulate_detailed_race,
)
from f1_simulator.domain.random_source import FrozenRandomSource, SeededRandomSource
from f1_simulator.domain.strategy import (
    NoStopStrategy,
    PitDecision,
    PlannedStopStrategy,
    StrategyState,
    TyreLifeStrategy,
)
from f1_simulator.domain.tyres import TyreSet
from tests.model_support import parameters, track


def field(count: int, *, stops: int = 1, spread: bool = False) -> list[Entrant]:
    """Grid sintetico com ritmos separados o suficiente para nao empatar."""

    return [
        Entrant(
            driver_id=f"driver:{index}",
            name=f"Piloto {index}",
            reference_lap_time_ms=90_000.0 + index * 300,
            grid_position=index + 1,
            strategy=PlannedStopStrategy(
                stops, ("MEDIUM", "HARD", "MEDIUM", "HARD"),
                offset_laps=index if spread else 0,
            ),
            starting_compound="MEDIUM",
        )
        for index in range(count)
    ]


class ReproducibilityTest(unittest.TestCase):
    """A mesma semente precisa reproduzir a corrida inteira, nao so o final."""

    def test_same_seed_same_race(self) -> None:
        def run() -> dict:
            return simulate_detailed_race(
                field(8),
                total_laps=30,
                parameters=parameters(),
                track=track(),
                rng=SeededRandomSource(2026),
            )

        self.assertEqual(run(), run())

    def test_different_seed_changes_the_race(self) -> None:
        def run(seed: int) -> dict:
            return simulate_detailed_race(
                field(8),
                total_laps=30,
                parameters=parameters(),
                track=track(),
                rng=SeededRandomSource(seed),
            )

        self.assertNotEqual(run(1), run(2))

    def test_result_is_independent_of_entrant_order(self) -> None:
        entrants = field(8)
        forward = simulate_detailed_race(
            entrants,
            total_laps=25,
            parameters=parameters(),
            track=track(),
            rng=SeededRandomSource(99),
        )
        backward = simulate_detailed_race(
            list(reversed(entrants)),
            total_laps=25,
            parameters=parameters(),
            track=track(),
            rng=SeededRandomSource(99),
        )
        self.assertEqual(forward, backward)


class InvariantTest(unittest.TestCase):
    """Propriedades que toda corrida precisa respeitar, com ou sem sorte."""

    def _race(self, seed: int = 4, laps: int = 40, hazard: float = 0.02) -> dict:
        return simulate_detailed_race(
            field(10, stops=2),
            total_laps=laps,
            parameters=parameters(dnf_hazard_per_lap=hazard),
            track=track(),
            rng=SeededRandomSource(seed),
        )

    def test_positions_are_unique_and_contiguous(self) -> None:
        result = self._race()
        for lap in result["history"]:
            positions = [car["position"] for car in lap["cars"]]
            self.assertEqual(positions, list(range(1, len(positions) + 1)))

    def test_total_time_never_decreases(self) -> None:
        result = self._race()
        seen: dict[str, float] = {}
        for lap in result["history"]:
            for car in lap["cars"]:
                previous = seen.get(car["driver_id"], 0.0)
                self.assertGreaterEqual(car["total_time_ms"], previous)
                seen[car["driver_id"]] = car["total_time_ms"]

    def test_a_retired_car_never_returns(self) -> None:
        result = self._race()
        retired: set[str] = set()
        for lap in result["history"]:
            for car in lap["cars"]:
                if car["driver_id"] in retired:
                    self.assertEqual(car["status"], RETIRED)
                if car["status"] == RETIRED:
                    retired.add(car["driver_id"])

    def test_active_car_count_never_increases(self) -> None:
        result = self._race()
        running = [
            sum(1 for car in lap["cars"] if car["status"] == RUNNING)
            for lap in result["history"]
        ]
        self.assertEqual(running, sorted(running, reverse=True))

    def test_laps_completed_never_decreases(self) -> None:
        result = self._race()
        seen: dict[str, int] = {}
        for lap in result["history"]:
            for car in lap["cars"]:
                previous = seen.get(car["driver_id"], 0)
                self.assertGreaterEqual(car["laps_completed"], previous)
                seen[car["driver_id"]] = car["laps_completed"]

    def test_retired_cars_are_classified_behind_runners(self) -> None:
        result = self._race()
        final = result["classification"]
        statuses = [car["status"] for car in final]
        if RETIRED in statuses:
            first_retired = statuses.index(RETIRED)
            self.assertNotIn(RUNNING, statuses[first_retired:])

    def test_no_retirement_when_hazard_is_zero(self) -> None:
        result = self._race(hazard=0.0)
        self.assertTrue(
            all(car["status"] == RUNNING for car in result["classification"])
        )


class ModelledEffectsTest(unittest.TestCase):
    """Cada parcela nova precisa mudar o resultado de forma observavel."""

    def test_grid_position_delays_the_start(self) -> None:
        result = simulate_detailed_race(
            field(5),
            total_laps=1,
            parameters=parameters(dnf_hazard_per_lap=0.0),
            track=track(),
            rng=FrozenRandomSource(),
        )
        cars = {c["driver_id"]: c for c in result["classification"]}
        # Ritmos iguais a parte, quem larga atras acumula o atraso do grid.
        self.assertLess(
            cars["driver:0"]["total_time_ms"], cars["driver:4"]["total_time_ms"]
        )

    def test_pit_stops_actually_happen_and_are_counted(self) -> None:
        result = simulate_detailed_race(
            field(4, stops=2),
            total_laps=60,
            parameters=parameters(dnf_hazard_per_lap=0.0),
            track=track(),
            rng=FrozenRandomSource(),
        )
        self.assertTrue(
            all(car["stops_made"] == 2 for car in result["classification"])
        )

    def test_pitting_resets_tyre_age(self) -> None:
        result = simulate_detailed_race(
            field(2, stops=1),
            total_laps=40,
            parameters=parameters(dnf_hazard_per_lap=0.0),
            track=track(),
            rng=FrozenRandomSource(),
        )
        ages = [
            car["tyre_age_laps"]
            for lap in result["history"]
            for car in lap["cars"]
            if car["driver_id"] == "driver:0"
        ]
        # Houve ao menos uma queda de idade: o jogo foi trocado.
        self.assertTrue(any(b < a for a, b in zip(ages, ages[1:])))

    def test_staggered_stops_change_the_order(self) -> None:
        # Se todos param na mesma volta a perda de boxes e um deslocamento
        # comum e nao muda nada; escalonar precisa produzir outra corrida.
        common = dict(
            total_laps=50,
            parameters=parameters(dnf_hazard_per_lap=0.0),
            track=track(),
        )
        together = simulate_detailed_race(
            field(8, stops=2, spread=False), rng=FrozenRandomSource(), **common
        )
        staggered = simulate_detailed_race(
            field(8, stops=2, spread=True), rng=FrozenRandomSource(), **common
        )
        self.assertNotEqual(
            [c["total_time_ms"] for c in together["classification"]],
            [c["total_time_ms"] for c in staggered["classification"]],
        )

    def test_breakdowns_are_collected_on_request(self) -> None:
        result = simulate_detailed_race(
            field(3),
            total_laps=5,
            parameters=parameters(dnf_hazard_per_lap=0.0),
            track=track(),
            rng=FrozenRandomSource(),
            collect_breakdowns=True,
        )
        self.assertEqual(len(result["breakdowns"]), 15)
        self.assertIn("fuel_ms", result["breakdowns"][0])

    def test_snapshot_keeps_the_field_the_arcade_view_reads(self) -> None:
        # frontend/arcade/track_view.py interpola a posicao com lap_time_ms.
        result = simulate_detailed_race(
            field(3),
            total_laps=5,
            parameters=parameters(dnf_hazard_per_lap=0.0),
            track=track(),
            rng=FrozenRandomSource(),
        )
        for car in result["classification"]:
            self.assertIn("lap_time_ms", car)
            self.assertGreater(car["lap_time_ms"], 0)

    def test_parameters_version_travels_with_the_result(self) -> None:
        result = simulate_detailed_race(
            field(2),
            total_laps=3,
            parameters=parameters(),
            track=track(),
            rng=FrozenRandomSource(),
        )
        self.assertEqual(result["parameters_version"], "teste-v1")
        self.assertEqual(result["circuit_id"], "circuit:1")


class ValidationTest(unittest.TestCase):
    def test_rejects_duplicate_driver(self) -> None:
        entrants = field(2)
        entrants[1] = Entrant(
            driver_id="driver:0",
            name="Clone",
            reference_lap_time_ms=90_000.0,
            grid_position=2,
            strategy=NoStopStrategy(),
            starting_compound="MEDIUM",
        )
        with self.assertRaises(ValueError):
            simulate_detailed_race(
                entrants,
                total_laps=5,
                parameters=parameters(),
                track=track(),
                rng=FrozenRandomSource(),
            )

    def test_rejects_non_positive_total_laps(self) -> None:
        with self.assertRaises(ValueError):
            simulate_detailed_race(
                field(2),
                total_laps=0,
                parameters=parameters(),
                track=track(),
                rng=FrozenRandomSource(),
            )

    def test_rejects_unknown_starting_compound_before_the_race(self) -> None:
        entrants = [
            Entrant(
                driver_id="driver:0",
                name="A",
                reference_lap_time_ms=90_000.0,
                grid_position=1,
                strategy=NoStopStrategy(),
                starting_compound="WET",
            )
        ]
        with self.assertRaises(KeyError):
            simulate_detailed_race(
                entrants,
                total_laps=5,
                parameters=parameters(),
                track=track(),
                rng=FrozenRandomSource(),
            )

    def test_rejects_invalid_entrant(self) -> None:
        with self.assertRaises(ValueError):
            Entrant("d", "A", 0.0, 1, NoStopStrategy(), "MEDIUM")
        with self.assertRaises(ValueError):
            Entrant("d", "A", 90_000.0, 0, NoStopStrategy(), "MEDIUM")


class StrategyTest(unittest.TestCase):
    def test_pit_decision_requires_a_compound(self) -> None:
        with self.assertRaises(ValueError):
            PitDecision(True)

    def test_planned_strategy_splits_the_race(self) -> None:
        strategy = PlannedStopStrategy(1, ("HARD",))
        state = lambda lap, stops: StrategyState(  # noqa: E731
            lap, 40, TyreSet("MEDIUM", lap), stops
        )
        self.assertFalse(strategy.decide(state(10, 0)).pit)
        self.assertTrue(strategy.decide(state(20, 0)).pit)
        # Depois de cumprir o plano, nao para mais.
        self.assertFalse(strategy.decide(state(39, 1)).pit)

    def test_planned_strategy_never_pits_on_the_last_lap(self) -> None:
        strategy = PlannedStopStrategy(1, ("HARD",), offset_laps=100)
        decision = strategy.decide(
            StrategyState(40, 40, TyreSet("MEDIUM", 40), 0)
        )
        self.assertFalse(decision.pit)

    def test_planned_strategy_rejects_missing_compounds(self) -> None:
        with self.assertRaises(ValueError):
            PlannedStopStrategy(3, ("HARD",))

    def test_tyre_life_strategy_reacts_to_age(self) -> None:
        model = parameters()
        strategy = TyreLifeStrategy(model, "HARD")
        young = StrategyState(10, 50, TyreSet("MEDIUM", 5), 0)
        old = StrategyState(30, 50, TyreSet("MEDIUM", 25), 0)
        self.assertFalse(strategy.decide(young).pit)
        self.assertTrue(strategy.decide(old).pit)

    def test_tyre_life_strategy_validates_compound_up_front(self) -> None:
        with self.assertRaises(KeyError):
            TyreLifeStrategy(parameters(), "WET")

    def test_no_stop_strategy_never_pits(self) -> None:
        strategy = NoStopStrategy()
        self.assertFalse(
            strategy.decide(StrategyState(40, 50, TyreSet("SOFT", 40), 0)).pit
        )


if __name__ == "__main__":
    unittest.main()
