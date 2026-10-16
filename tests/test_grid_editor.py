"""Estado da tela de pilotos e grid, sem janela nem backend."""

from __future__ import annotations

import unittest

from frontend.arcade.grid_editor import (
    RANDOM_GRID_SIZE,
    GridDraft,
    format_value,
    grid_sources,
)


def grid_payload() -> dict:
    return {
        "size": 1,
        "seed": 8,
        "profiles_disclaimer": "Caracterizacoes ficticias.",
        "grid": [
            {
                "driver_id": "driver:830",
                "driver_name": "Max Verstappen",
                "team_id": "team:9",
                "team_name": "Red Bull",
                "attributes": {
                    "archetype": "aggressive",
                    "pace_offset_pct": -0.58,
                    "consistency_factor": 1.37,
                    "tyre_management_factor": 1.18,
                    "aggression": 1.48,
                    "composure": 0.10,
                    "sources": {
                        "pace_offset_pct": "preset",
                        "consistency_factor": "generated",
                        "tyre_management_factor": "generated",
                        "aggression": "preset",
                        "composure": "preset",
                    },
                },
                "profile": {"characterization": "x", "parameter_version": "v1"},
            }
        ],
    }


class GridDraftTest(unittest.TestCase):
    def setUp(self) -> None:
        self.draft = GridDraft(grid_payload())

    def test_reads_values_sources_and_metadata(self) -> None:
        self.assertEqual(self.draft.value("driver:830", "aggression"), 1.48)
        self.assertEqual(self.draft.source("driver:830", "aggression"), "preset")
        self.assertEqual(self.draft.seed, 8)
        self.assertEqual(self.draft.disclaimer, "Caracterizacoes ficticias.")
        self.assertFalse(self.draft.has_changes)

    def test_step_marks_the_field_as_manual_and_builds_the_patch(self) -> None:
        self.assertEqual(self.draft.step("driver:830", "aggression", 2), 1.58)
        self.assertEqual(self.draft.source("driver:830", "aggression"), "manual")
        self.assertEqual(
            self.draft.overrides(), [{"driver_id": "driver:830", "aggression": 1.58}]
        )

    def test_returning_to_the_original_value_is_not_an_edit(self) -> None:
        self.draft.step("driver:830", "aggression", 1)
        self.draft.step("driver:830", "aggression", -1)
        self.assertFalse(self.draft.has_changes)
        self.assertEqual(self.draft.source("driver:830", "aggression"), "preset")
        self.assertEqual(self.draft.overrides(), [])

    def test_factors_stay_positive_but_pace_can_go_negative(self) -> None:
        self.assertEqual(self.draft.step("driver:830", "composure", -5), 0.05)
        self.assertLess(self.draft.step("driver:830", "pace_offset_pct", -10), -1.0)

    def test_discard_drops_pending_edits(self) -> None:
        self.draft.step("driver:830", "aggression", 1)
        self.draft.discard()
        self.assertEqual(self.draft.value("driver:830", "aggression"), 1.48)

    def test_rejects_payload_without_grid(self) -> None:
        with self.assertRaises(ValueError):
            GridDraft({"seed": 1})


class GridSourcesTest(unittest.TestCase):
    def test_random_first_then_season_races_in_round_order(self) -> None:
        payload = {
            "races": [
                {"race_id": "race:2", "name": "B", "season": 2024, "round_number": 2},
                {"race_id": "race:9", "name": "Z", "season": 2023, "round_number": 1},
                {"race_id": "race:1", "name": "A", "season": 2024, "round_number": 1},
            ]
        }
        sources = grid_sources(payload, 2024)
        self.assertEqual([s.mode for s in sources], ["random", "race", "race"])
        self.assertEqual([s.race_id for s in sources[1:]], ["race:1", "race:2"])
        self.assertEqual(
            sources[0].request(), {"mode": "random", "size": RANDOM_GRID_SIZE}
        )
        self.assertEqual(sources[1].request(), {"mode": "race", "race_id": "race:1"})

    def test_without_history_only_random_is_offered(self) -> None:
        self.assertEqual(len(grid_sources(None, 2024)), 1)


class FormatValueTest(unittest.TestCase):
    def test_pace_has_explicit_sign(self) -> None:
        self.assertEqual(format_value("pace_offset_pct", 0.1), "+0.10")
        self.assertEqual(format_value("aggression", 1.234), "1.23")


if __name__ == "__main__":
    unittest.main()
