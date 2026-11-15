"""Estado do seletor de pilotos do grid, sem janela nem backend."""

from __future__ import annotations

import unittest

from frontend.arcade.grid_picker import PairPicker, pair_id


def entry(driver_id: str, name: str, team_id: str, team: str) -> dict:
    return {
        "driver_id": driver_id,
        "driver_name": name,
        "team_id": team_id,
        "team_name": team,
    }


CATALOG = (
    entry("driver:1", "Ayrton Senna", "team:1", "McLaren"),
    entry("driver:2", "Alain Prost", "team:1", "McLaren"),
    entry("driver:2", "Alain Prost", "team:2", "Williams"),
    entry("driver:3", "Nigel Mansell", "team:2", "Williams"),
)


class PairPickerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.picker = PairPicker(entries=CATALOG, in_grid=frozenset({"driver:3"}), room=3)

    def test_search_matches_driver_or_team_name_case_insensitively(self) -> None:
        self.picker.set_query("williams")
        self.assertEqual([pair_id(e) for e in self.picker.visible()],
                         ["driver:2@team:2", "driver:3@team:2"])
        self.picker.set_query("  SENNA ")
        self.assertEqual([e["driver_name"] for e in self.picker.visible()],
                         ["Ayrton Senna"])

    def test_search_resets_scroll(self) -> None:
        self.picker.scroll = 2
        self.picker.set_query("a")
        self.assertEqual(self.picker.scroll, 0)

    def test_driver_already_in_grid_cannot_be_chosen(self) -> None:
        self.assertEqual(self.picker.toggle(CATALOG[3]), "Nigel Mansell: já está no grid")
        self.assertEqual(self.picker.selected, [])

    def test_one_team_per_driver_in_the_same_selection(self) -> None:
        self.assertIsNone(self.picker.toggle(CATALOG[1]))
        self.assertEqual(
            self.picker.toggle(CATALOG[2]),
            "Alain Prost: já escolhido com outra equipe",
        )

    def test_selection_is_limited_to_the_remaining_room(self) -> None:
        self.assertIsNone(self.picker.toggle(CATALOG[0]))
        self.assertIsNone(self.picker.toggle(CATALOG[1]))
        self.assertIsNone(self.picker.toggle(entry("driver:9", "X", "team:9", "Y")))
        self.assertIn("máximo 3", self.picker.toggle(entry("driver:10", "Z", "team:9", "Y")))
        self.picker.room = 0
        self.assertIn("limite", self.picker.toggle(entry("driver:11", "W", "team:9", "Y")))

    def test_toggling_a_selected_pair_deselects_it(self) -> None:
        self.picker.toggle(CATALOG[0])
        self.assertIsNone(self.picker.toggle(CATALOG[0]))
        self.assertEqual(self.picker.selected, [])

    def test_selected_entries_keep_the_order_of_choice(self) -> None:
        self.picker.toggle(CATALOG[1])
        self.picker.toggle(CATALOG[0])
        self.assertEqual(
            [e["driver_name"] for e in self.picker.selected_entries()],
            ["Alain Prost", "Ayrton Senna"],
        )


if __name__ == "__main__":
    unittest.main()
