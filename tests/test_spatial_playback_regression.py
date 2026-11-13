"""Regressoes deterministicas da integracao espacial ate a reproducao HTTP."""

import unittest

from f1_simulator.domain.race_simulation_2d import _trajectories_2d
from f1_simulator.domain.speed_dynamics import CarPhysics
from f1_simulator.domain.track_space import (
    CarSpaceState,
    build_track_space,
    integrate_field,
)
from frontend.arcade.race_playback import CarTimeline
from tests.test_track_space import _rectangle_with_straight


class SpatialPlaybackRegressionTest(unittest.TestCase):
    def test_follower_gap_does_not_depend_on_driver_id(self):
        track = build_track_space(_rectangle_with_straight())
        physics = CarPhysics(v_max_straight_kmh=216)
        for leader, follower in (("a", "z"), ("z", "a")):
            with self.subTest(leader=leader):
                samples = integrate_field(
                    [CarSpaceState(leader, distance_m=100, speed_ms=60),
                     CarSpaceState(follower, distance_m=95, speed_ms=60)],
                    track, {leader: physics, follower: physics}, total_laps=1,
                    dt_s=0.2, max_steps=10, neutralized_lap=lambda _: True,
                )
                trajectories = _trajectories_2d(samples, [leader, follower], 1000)
                timelines = {
                    did: CarTimeline(did, did, (), False, trajectory=tuple(points))
                    for did, points in trajectories.items()
                }
                for t_ms in range(0, 2001, 25):
                    positions = {did: timeline.spatial_at(t_ms).distance_m
                                 for did, timeline in timelines.items()}
                    self.assertAlmostEqual(positions[leader] - positions[follower], 5.0)

    def test_blocked_follower_never_moves_backwards_in_playback(self):
        track = build_track_space(_rectangle_with_straight())
        physics = CarPhysics(v_max_straight_kmh=216)
        samples = integrate_field(
            [CarSpaceState("leader", distance_m=100, speed_ms=1),
             CarSpaceState("follower", distance_m=95, speed_ms=60)],
            track, {"leader": physics, "follower": physics}, total_laps=1,
            dt_s=0.2, max_steps=1, neutralized_lap=lambda _: True,
        )
        points = _trajectories_2d(samples, ["leader", "follower"], 1000)["follower"]
        self.assertEqual(len(points), 2)
        timeline = CarTimeline("follower", "follower", (), False, trajectory=tuple(points))
        positions = [timeline.spatial_at(t).distance_m for t in range(201)]
        self.assertAlmostEqual(positions[0], points[0][1])
        self.assertAlmostEqual(positions[-1], points[-1][1])
        self.assertEqual(positions, sorted(positions))
        self.assertTrue(all(points[0][1] <= p <= points[-1][1] for p in positions))

    def test_sampling_keeps_200ms_cadence_despite_float_rounding(self):
        track = build_track_space(_rectangle_with_straight())
        physics = CarPhysics(v_max_straight_kmh=216)
        samples = integrate_field(
            [CarSpaceState("a", distance_m=100, speed_ms=60)], track,
            {"a": physics}, total_laps=1, dt_s=0.2, max_steps=15,
        )
        points = _trajectories_2d(samples, ["a"], 1000)["a"]
        self.assertEqual([p[0] for p in points], list(range(0, 3001, 200)))

    def test_stationary_and_pit_segments_remain_stationary_and_linear(self):
        stationary = CarTimeline("a", "a", (), False, trajectory=(
            (0, 95, 0, 216, None), (200, 95, 0, 216, None),
        ))
        self.assertEqual(stationary.spatial_at(50).distance_m, 95)
        pit = CarTimeline("a", "a", (), False, trajectory=(
            (0, 95, 0, 216, 10), (200, 96, 0, 0, 20),
        ))
        self.assertAlmostEqual(pit.spatial_at(50).distance_m, 95.25)
        self.assertAlmostEqual(pit.spatial_at(50).pit_distance_m, 12.5)
        entering = CarTimeline("a", "a", (), False, trajectory=(
            (0, 95, 0, 216, None), (200, 96, 0, 0, 0),
        ))
        self.assertAlmostEqual(entering.spatial_at(50).distance_m, 95.25)
        self.assertIsNone(entering.spatial_at(50).pit_distance_m)

    def test_consistent_acceleration_keeps_cubic_interpolation(self):
        timeline = CarTimeline("a", "a", (), False, trajectory=(
            (0, 0, 0, 0, None), (1000, 10, 0, 72, None),
        ))
        self.assertAlmostEqual(timeline.spatial_at(500).distance_m, 2.5)
