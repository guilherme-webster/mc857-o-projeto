"""Dano so aparece na decomposicao depois do instante do contato."""

import unittest

from frontend.arcade.race_control_feed import RaceControlFeed
from frontend.arcade.speed_breakdown import SpeedBreakdownReader


class ContactPlaybackTest(unittest.TestCase):
    def test_touch_is_shown_at_its_timestamp_without_a_retirement(self):
        feed = RaceControlFeed({"contact_events_2d": [
            {"lap": 1, "time_ms": 1000, "driver_ids": ["a", "b"], "kind": "touch"},
        ]}, {"a": "A", "b": "B"})
        self.assertEqual(feed.entries_through(0, 999), [])
        self.assertEqual([e.text for e in feed.entries_through(0, 1000)], ["Toque leve: A x B"])

    def test_damage_is_not_backdated_or_hidden_as_braking(self):
        race = {
            "speed_breakdown": {"cars": {"a": {"v_max_kmh": 360,
                "laps": {"1": {"speed_scale": 1.0, "delta_shares": {}}}}}},
            "contact_model": {"maximum_speed_loss": 0.15},
            "contact_events_2d": [{"time_ms": 1000, "damage_by_driver": {"a": 0.4}}],
        }
        reader = SpeedBreakdownReader(race)
        before = reader.at("a", distance_m=0, speed_kmh=360, lap=1, t_ms=999)
        after = reader.at("a", distance_m=0, speed_kmh=338.4, lap=1, t_ms=1000)
        self.assertEqual(before.penalties["damage"], 0)
        self.assertAlmostEqual(after.penalties["damage"], 0.06)
        self.assertAlmostEqual(after.transient, 0)
        self.assertAlmostEqual(after.effective + after.corner + after.transient
                               + sum(after.penalties.values()), 1)


if __name__ == "__main__":
    unittest.main()
