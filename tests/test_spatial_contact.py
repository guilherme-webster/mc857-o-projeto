"""Contato físico, episódios e gravidade independem da taxa de quadros."""

import unittest

from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.spatial_contact import ContactTracker, contact_consequence
from f1_simulator.domain.track_space import (
    CarSpaceState,
    _limit_projected_motion,
    _projected_rectangle,
    _rectangles_overlap,
    _resolve_collisions,
    build_track_space,
)
from tests.test_track_space import _rectangle_with_straight


class ContactConsequencesTest(unittest.TestCase):
    def test_low_relative_speed_touch_never_retires_even_at_racing_speed(self):
        for seed in range(20):
            outcome = contact_consequence(1.0, 3.0, SeededRandomSource(seed), "touch")
            self.assertEqual(outcome.kind, "touch")
            self.assertFalse(outcome.retires)
            self.assertEqual(outcome.damage_fraction, 0)

    def test_severe_impacts_can_damage_or_retire_and_are_reproducible(self):
        outcomes = [contact_consequence(15.0, 1.0, SeededRandomSource(s), "impact") for s in range(40)]
        self.assertTrue(any(o.retires for o in outcomes))
        self.assertTrue(any(not o.retires for o in outcomes))
        self.assertTrue(all(o.damage_fraction > 0 for o in outcomes))
        self.assertEqual(outcomes, [contact_consequence(15.0, 1.0, SeededRandomSource(s), "impact")
                                   for s in range(40)])

    def test_proximity_and_long_exposure_are_not_impacts(self):
        cars = [CarSpaceState("a", distance_m=100, speed_ms=80),
                CarSpaceState("b", distance_m=100, lateral_m=2.2, speed_ms=80)]
        events = []
        tracker = ContactTracker()
        for _ in range(100):
            _resolve_collisions(cars, 10000, {}, SeededRandomSource(1), .2,
                                tracker=tracker, events=events)
        self.assertFalse(events)
        self.assertFalse(any(c.retired for c in cars))

    def test_one_touch_per_episode_and_reentry_creates_another(self):
        cars = [CarSpaceState("a", distance_m=100, speed_ms=80),
                CarSpaceState("b", distance_m=100, lateral_m=1.9, speed_ms=80)]
        tracker = ContactTracker()
        events = []
        for _ in range(100):
            _resolve_collisions(cars, 10000, {}, SeededRandomSource(1), .1,
                                tracker=tracker, events=events)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["kind"], "touch")
        self.assertFalse(any(c.retired for c in cars))
        cars[1].lateral_m = 5
        _resolve_collisions(cars, 10000, {}, None, .1, tracker=tracker, events=events)
        cars[1].lateral_m = 1.9
        _resolve_collisions(cars, 10000, {}, None, .1, tracker=tracker, events=events)
        self.assertEqual([e["episode"] for e in events], [1, 2])

    def test_positional_corrections_do_not_fabricate_impact_velocity(self):
        track = build_track_space(_rectangle_with_straight())
        cars = [CarSpaceState("a", distance_m=100, speed_ms=80),
                CarSpaceState("b", distance_m=104, speed_ms=80)]
        previous = {"a": CarSpaceState("a", distance_m=95, speed_ms=80),
                    "b": CarSpaceState("b", distance_m=102, speed_ms=80)}
        events = []
        _resolve_collisions(cars, 10000, {}, SeededRandomSource(1), .2,
                            track=track, previous=previous, events=events)
        self.assertEqual(events[0]["closing_speed_ms"], 0)
        self.assertEqual(events[0]["kind"], "touch")
        self.assertFalse(any(c.retired for c in cars))


class SweptBodyTest(unittest.TestCase):
    def setUp(self):
        self.track = build_track_space(_rectangle_with_straight())

    def test_monaco_field_does_not_get_stuck_behind_stopped_cars(self):
        from scripts.analyze_spatial_contacts import run_case

        result = run_case("circuit:6", 2, 10, 5, 0.2, 2, 50)
        self.assertEqual(result["unfinished_drivers"], [])
        self.assertEqual(result["backward_distance_samples"], 0)

    def test_cannot_jump_through_body_with_both_ends_free(self):
        moving = CarSpaceState("a", distance_m=70, speed_ms=100)
        other = CarSpaceState("b", distance_m=100)
        distance, lateral, hits = _limit_projected_motion(
            self.track, moving, 70, 0, 130, 0, [moving, other], 10000)
        self.assertEqual(hits, {"b"})
        self.assertLess(distance, 100)
        moving.distance_m, moving.lateral_m = distance, lateral
        self.assertFalse(_rectangles_overlap(
            moving, _projected_rectangle(self.track, moving, distance),
            other, _projected_rectangle(self.track, other, other.distance_m)))

    def test_lateral_block_does_not_stop_clear_longitudinal_lane(self):
        moving = CarSpaceState("a", distance_m=90, lateral_m=-3)
        other = CarSpaceState("b", distance_m=100, lateral_m=0)
        distance, lateral, _ = _limit_projected_motion(
            self.track, moving, 90, -3, 110, 3, [moving, other], 10000)
        self.assertEqual(distance, 110)
        self.assertEqual(lateral, -3)



if __name__ == "__main__":
    unittest.main()
