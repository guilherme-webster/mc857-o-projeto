"""Estado da tela de pilotos e grid, sem janela nem backend."""

from __future__ import annotations

import unittest

from frontend.arcade.grid_editor import (
    RANDOM_GRID_SIZE,
    GridDraft,
    GridSource,
    format_value,
    grid_sources,
    parse_grid_size,
)


def grid_payload() -> dict:
    return {
        "size": 2,
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
            },
            {
                "driver_id": "driver:844",
                "driver_name": "Charles Leclerc",
                "team_id": "team:6",
                "team_name": "Ferrari",
                "attributes": {
                    "archetype": "balanced",
                    "pace_offset_pct": -0.25,
                    "consistency_factor": 1.05,
                    "tyre_management_factor": 0.95,
                    "aggression": 1.10,
                    "composure": 1.15,
                    "sources": {
                        "pace_offset_pct": "generated",
                        "consistency_factor": "generated",
                        "tyre_management_factor": "generated",
                        "aggression": "generated",
                        "composure": "generated",
                    },
                },
                "profile": None,
            },
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
        self.draft.move("driver:844", -1)
        self.draft.discard()
        self.assertEqual(self.draft.value("driver:830", "aggression"), 1.48)
        self.assertEqual(
            [entry["driver_id"] for entry in self.draft.entries],
            ["driver:830", "driver:844"],
        )
        self.assertFalse(self.draft.has_changes)
        self.assertEqual(self.draft.patch(), {})

    def test_move_updates_pending_order_and_displayed_positions(self) -> None:
        self.assertTrue(self.draft.move("driver:844", -1))

        self.assertEqual(
            [entry["driver_id"] for entry in self.draft.entries],
            ["driver:844", "driver:830"],
        )
        self.assertTrue(self.draft.has_changes)

    def test_move_does_not_cross_top_or_bottom_limits(self) -> None:
        self.assertFalse(self.draft.move("driver:830", -1))
        self.assertFalse(self.draft.move("driver:844", 1))
        self.assertFalse(self.draft.has_changes)

    def test_patch_includes_order_and_overrides_only_when_pending(self) -> None:
        self.draft.move("driver:844", -1)
        self.draft.step("driver:830", "aggression", 1)

        self.assertEqual(
            self.draft.patch(),
            {
                "overrides": [{"driver_id": "driver:830", "aggression": 1.53}],
                "order": ["driver:844", "driver:830"],
            },
        )

    def test_handles_null_car_attributes_gracefully(self) -> None:
        payload = grid_payload()
        payload["grid"][0]["attributes"]["v_max_kmh"] = None
        payload["grid"][0]["attributes"]["a_max_ms2"] = None
        draft = GridDraft(payload)
        self.assertEqual(draft.value("driver:830", "v_max_kmh"), 338.0)
        self.assertEqual(draft.value("driver:830", "a_max_ms2"), 14.1)

    def test_rejects_payload_without_grid(self) -> None:
        with self.assertRaises(ValueError):
            GridDraft({"seed": 1})


class RosterDraftTest(unittest.TestCase):
    def setUp(self) -> None:
        self.draft = GridDraft(grid_payload())
        self.newcomer = {
            "driver_id": "driver:999",
            "driver_name": "Novato",
            "team_id": "team:6",
            "team_name": "Ferrari",
        }

    def test_added_driver_is_pending_and_sent_as_pair_with_full_order(self) -> None:
        self.assertIsNone(self.draft.add_pair(self.newcomer))

        entry = self.draft.entries[-1]
        self.assertEqual(entry["driver_id"], "driver:999")
        self.assertIsNone(self.draft.value("driver:999", "aggression"))
        self.assertEqual(self.draft.source("driver:999", "aggression"), "pending")
        self.assertTrue(self.draft.has_changes)
        self.assertEqual(
            self.draft.patch(),
            {
                "add": ["driver:999@team:6"],
                "order": ["driver:830", "driver:844", "driver:999"],
            },
        )

    def test_pending_driver_cannot_be_edited(self) -> None:
        self.draft.add_pair(self.newcomer)
        self.assertIsNone(self.draft.step("driver:999", "aggression", 1))
        self.assertEqual(self.draft.overrides(), [])

    def test_adding_a_driver_already_in_the_grid_is_refused(self) -> None:
        duplicate = dict(self.newcomer, driver_id="driver:844")
        self.assertIn("já está no grid", self.draft.add_pair(duplicate))

    def test_removing_a_driver_drops_its_edits_and_is_sent_by_id(self) -> None:
        self.draft.step("driver:830", "aggression", 1)
        self.assertIsNone(self.draft.remove_driver("driver:830"))

        self.assertEqual(self.draft.overrides(), [])
        self.assertEqual(
            self.draft.patch(),
            {"remove": ["driver:830"], "order": ["driver:844"]},
        )

    def test_remove_then_readd_with_another_team_sends_both(self) -> None:
        self.draft.remove_driver("driver:830")
        readded = dict(
            self.newcomer, driver_id="driver:830", team_id="team:6", team_name="Ferrari"
        )
        self.assertIsNone(self.draft.add_pair(readded))

        self.assertEqual(self.draft.entries[-1]["team_name"], "Ferrari")
        self.assertEqual(
            self.draft.patch(),
            {
                "remove": ["driver:830"],
                "add": ["driver:830@team:6"],
                "order": ["driver:844", "driver:830"],
            },
        )

    def test_removing_a_pending_driver_just_forgets_it(self) -> None:
        self.draft.add_pair(self.newcomer)
        self.assertIsNone(self.draft.remove_driver("driver:999"))
        self.assertFalse(self.draft.has_changes)
        self.assertEqual(self.draft.patch(), {})

    def test_grid_keeps_between_one_and_forty_drivers(self) -> None:
        self.assertIsNone(self.draft.remove_driver("driver:830"))
        self.assertIn("ao menos um", self.draft.remove_driver("driver:844"))

        for index in range(40):
            self.draft.discard()
            self.draft.remove_driver("driver:844")
            self.draft.add_pair(self.newcomer | {"driver_id": f"d{index}"})
        self.assertEqual(len(self.draft.entries), 2)
        for index in range(38):
            self.draft.add_pair(self.newcomer | {"driver_id": f"e{index}"})
        self.assertIn("máximo 40", self.draft.add_pair(self.newcomer | {"driver_id": "x"}))

    def test_discard_restores_the_loaded_roster(self) -> None:
        self.draft.remove_driver("driver:830")
        self.draft.add_pair(self.newcomer)
        self.draft.discard()

        self.assertFalse(self.draft.has_changes)
        self.assertEqual(self.draft.patch(), {})
        self.assertEqual(
            [entry["driver_id"] for entry in self.draft.entries],
            ["driver:830", "driver:844"],
        )


class GridSourcesTest(unittest.TestCase):
    def test_random_first_then_season_races_in_round_order(self) -> None:
        payload = {
            "races": [
                {"race_id": "race:2", "name": "B", "season": 2024, "round_number": 2},
                {"race_id": "race:9", "name": "Z", "season": 2023, "round_number": 1},
                {"race_id": "race:1", "name": "A", "season": 2024, "round_number": 1},
            ]
        }
        sources = grid_sources(payload)
        self.assertEqual([s.mode for s in sources], ["random", "race", "race", "race"])
        # Cronologico: temporada 2023 antes de 2024; dentro de 2024, rodada 1 e 2.
        self.assertEqual(
            [s.race_id for s in sources[1:]], ["race:9", "race:1", "race:2"]
        )
        self.assertEqual([s.season for s in sources[1:]], [2023, 2024, 2024])
        self.assertEqual(
            sources[0].request(), {"mode": "random", "size": RANDOM_GRID_SIZE}
        )
        self.assertEqual(
            sources[0].request(105),
            {"mode": "random", "size": RANDOM_GRID_SIZE, "seed": 105},
        )
        self.assertEqual(sources[1].request(), {"mode": "race", "race_id": "race:9"})

    def test_races_after_the_last_one_with_results_are_hidden(self) -> None:
        payload = {
            "races": [
                {"race_id": "race:1180", "name": "Dutch", "season": 2026, "round_number": 12},
                {"race_id": "race:1181", "name": "Italian", "season": 2026, "round_number": 13},
            ]
        }
        sources = grid_sources(payload)
        self.assertEqual([s.race_id for s in sources[1:]], ["race:1180"])

    def test_without_history_only_random_is_offered(self) -> None:
        self.assertEqual(len(grid_sources(None)), 1)


class GridSizeTest(unittest.TestCase):
    def test_accepts_whole_numbers_from_one_to_forty(self) -> None:
        self.assertEqual(parse_grid_size("1"), 1)
        self.assertEqual(parse_grid_size(" 40 "), 40)
        self.assertEqual(parse_grid_size("20"), 20)

    def test_rejects_out_of_range_and_non_numeric_text(self) -> None:
        for text in ("0", "41", "", "-3", "2a", "1.5"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_grid_size(text)

    def test_random_request_carries_the_chosen_size(self) -> None:
        source = GridSource("Aleatório", "random")
        self.assertEqual(source.request(7, 12), {"mode": "random", "size": 12, "seed": 7})


class FormatValueTest(unittest.TestCase):
    def test_pace_has_explicit_sign(self) -> None:
        self.assertEqual(format_value("pace_offset_pct", 0.1), "+0.10")
        self.assertEqual(format_value("aggression", 1.234), "1.23")


if __name__ == "__main__":
    unittest.main()
