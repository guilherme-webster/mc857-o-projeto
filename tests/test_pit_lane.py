"""Percurso dos boxes: relógio, progresso de corrida, serviço e reprodução."""

from dataclasses import replace
import json
from pathlib import Path
import unittest

from frontend.arcade.race_playback import RacePlayback
from f1_simulator.adapters.datasets.mock_track_geometry import MockTrackDatasetAdapter
from f1_simulator.domain.pit_lane import (
    PitLaneParameters,
    PitLaneState,
    PitStopRequest,
    build_pit_lane,
)
from f1_simulator.domain.race_simulation_2d import simulate_2d_race
from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.speed_dynamics import CarPhysics
from f1_simulator.domain.strategy import NoStopStrategy, PlannedStopStrategy
from f1_simulator.domain.track_geometry import PitLanePoint
from f1_simulator.domain.track_space import (
    CarSpaceState,
    build_track_space,
    integrate_field,
)
from f1_simulator.factories.track_geometry_factory import TrackGeometryFactory
from tests.model_support import parameters, track
from tests.test_track_space import _square


def pit_geometry():
    """Boxes de 360 m a 440 m na volta de 400 m: cruzam a linha uma vez."""

    xy = ((0, 40), (-10, 35), (-10, 0), (0, -10), (40, 0))
    return replace(
        _square(),
        pit_lane_points=tuple(
            PitLanePoint(i, x, y, i / (len(xy) - 1), i == 2)
            for i, (x, y) in enumerate(xy)
        ),
    )


class PitLaneMotionTest(unittest.TestCase):
    def test_all_existing_layouts_have_a_usable_open_lane(self):
        root = Path(__file__).resolve().parents[1]
        fixture = root / "tests/fixtures/trotman_v128_tracks_2025"
        manifest = root / "data/sources/fastf1-tracks-2025.json"
        adapter = MockTrackDatasetAdapter(
            fixture / "track_points.csv",
            manifest,
            fixture / "pit_lane_points.csv",
            root / "data/sources/fastf1-pit-lanes-2025.json",
        )
        events = json.loads(manifest.read_text(encoding="utf-8"))["source"]["events"]
        for event in events:
            with self.subTest(circuit=event["circuit_id"]):
                geometry = TrackGeometryFactory.build(
                    adapter.load_geometry("circuit:" + event["circuit_id"])
                )
                lane = build_pit_lane(geometry)
                self.assertGreater(lane.length_m, lane.service_distance_m)
                self.assertGreater(lane.service_distance_m, 0)
                self.assertLess(
                    lane.exit_distance_m - lane.entry_distance_m, geometry.lap_length_m
                )

    def test_projection_wraps_exit_and_maps_progress_without_adding_a_lap(self):
        path = build_pit_lane(pit_geometry())
        self.assertAlmostEqual(path.entry_distance_m, 360)
        self.assertAlmostEqual(path.exit_distance_m, 440)
        self.assertAlmostEqual(path.race_distance(760, path.length_m), 840)
        self.assertEqual(path.position(0), (0, 40))
        self.assertEqual(path.position(path.length_m), (40, 0))

    def test_movement_stops_at_service_and_finishes_two_laps(self):
        geo = pit_geometry()
        path = build_pit_lane(geo)
        car = CarSpaceState("a", distance_m=340, pit_request=PitStopRequest(360, 2.5))
        events = []
        crossings = []
        samples = integrate_field(
            [car],
            build_track_space(geo),
            {"a": CarPhysics()},
            total_laps=2,
            pit_lane=path,
            on_pit_event=lambda c, kind, t: events.append((kind, t)),
            on_lap_complete=lambda c, lap: crossings.append(lap),
        )
        self.assertEqual(
            [e[0] for e in events],
            ["entry", "service_started", "service_completed", "exit"],
        )
        self.assertAlmostEqual(events[2][1] - events[1][1], 2.5, places=6)
        self.assertEqual(crossings, [1, 2])
        self.assertIsNone(car.pit_state)
        positions = [s.cars[0].distance_m for s in samples]
        self.assertEqual(positions, sorted(positions))
        pit_samples = [s.cars[0] for s in samples if s.cars[0].pit_state is not None]
        self.assertTrue(pit_samples)
        self.assertLessEqual(max(c.speed_ms * 3.6 for c in pit_samples), 80.000001)
        stationary = [c for c in pit_samples if c.pit_state.service_remaining_s > 0]
        self.assertGreater(len(stationary), 40)
        self.assertTrue(all(c.speed_ms == 0 for c in stationary))
        self.assertAlmostEqual(
            min(c.distance_m for c in stationary), max(c.distance_m for c in stationary)
        )

    def test_rejects_missing_or_ambiguous_service_and_invalid_speed(self):
        with self.assertRaises(ValueError):
            build_pit_lane(_square())
        geo = pit_geometry()
        with self.assertRaises(ValueError):
            build_pit_lane(
                replace(
                    geo,
                    pit_lane_points=tuple(
                        replace(p, is_service_point=True) for p in geo.pit_lane_points
                    ),
                )
            )
        for value in (0, -1, float("nan"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                PitLaneParameters(speed_limit_kmh=value)

    def test_two_cars_queue_and_do_not_block_main_track(self):
        geo = pit_geometry()
        path = build_pit_lane(geo)
        cars = [
            CarSpaceState("a", distance_m=350, pit_request=PitStopRequest(360, 2.5)),
            CarSpaceState("b", distance_m=340, pit_request=PitStopRequest(360, 2.5)),
            CarSpaceState("c", distance_m=320),
        ]
        events = []
        samples = integrate_field(
            cars,
            build_track_space(geo),
            {c.driver_id: CarPhysics() for c in cars},
            total_laps=2,
            pit_lane=path,
            on_pit_event=lambda c, kind, t: events.append((c.driver_id, kind, t)),
        )
        times = {(did, kind): t for did, kind, t in events}
        self.assertLessEqual(
            times["a", "service_completed"], times["b", "service_started"]
        )
        self.assertEqual(sum(kind == "exit" for _, kind, _ in events), 2)
        for sample in samples:
            in_lane = sorted(
                c.pit_state.path_distance_m for c in sample.cars if c.pit_state
            )
            if len(in_lane) == 2:
                self.assertGreaterEqual(in_lane[1] - in_lane[0], 4.999)
        # Enquanto o primeiro está parado, o carro na pista principal passa
        # pela projeção do seu progresso sem ser preso pela exclusão espacial.
        self.assertTrue(
            any(
                sample.cars[0].pit_state
                and sample.cars[0].speed_ms == 0
                and sample.cars[2].distance_m > sample.cars[0].distance_m
                for sample in samples
            )
        )

    def test_exit_waits_for_a_gap_and_then_rejoins(self):
        geo = pit_geometry()
        path = build_pit_lane(geo)
        exiting = CarSpaceState(
            "a",
            distance_m=440,
            pit_request=PitStopRequest(360, 2.5),
            pit_state=PitLaneState(path.length_m, serviced=True),
        )
        traffic = CarSpaceState("b", distance_m=441, speed_ms=20)
        cars = [exiting, traffic]
        kwargs = dict(total_laps=2, pit_lane=path, max_steps=1)
        physics = {c.driver_id: CarPhysics() for c in cars}
        integrate_field(cars, build_track_space(geo), physics, **kwargs)
        self.assertIsNotNone(exiting.pit_state)
        self.assertEqual(exiting.speed_ms, 0)
        traffic.distance_m = 500
        integrate_field(cars, build_track_space(geo), physics, **kwargs)
        self.assertIsNone(exiting.pit_state)
        self.assertIsNone(exiting.pit_request)
        self.assertEqual(exiting.distance_m, 440)


def run_pit_race(*, loss=20_000, service=2.5, stop=True):
    model = parameters()
    return simulate_2d_race(
        [
            {
                "driver_id": "a",
                "name": "A",
                "grid_position": 1,
                "strategy": PlannedStopStrategy(1, ("HARD",))
                if stop
                else NoStopStrategy(),
            }
        ],
        pit_geometry(),
        total_laps=4,
        rng=SeededRandomSource(1),
        compounds={c.name: c for c in model.compounds},
        track_params=track(pit_loss_ms=loss),
        model_parameters=model,
        race_control=None,
        pit_parameters=PitLaneParameters(service_time_s=service),
    )


class SpatialPitRaceTest(unittest.TestCase):
    def test_service_changes_tyres_and_old_loss_is_not_charged(self):
        result = run_pit_race()
        self.assertEqual(result, run_pit_race())
        json.dumps(result, allow_nan=False)
        final = result["classification"][0]
        self.assertEqual(final["laps_completed"], 4)
        self.assertEqual(final["stops_made"], 1)
        self.assertEqual(final["compound"], "HARD")
        self.assertEqual(result["history"], run_pit_race(loss=1_000_000)["history"])
        # Mudar apenas o serviço muda o relógio pelo mesmo valor, sem uma
        # segunda perda de boxes escondida no fator de velocidade da volta.
        longer = run_pit_race(service=5.5)
        self.assertAlmostEqual(
            longer["classification"][0]["total_time_ms"] - final["total_time_ms"],
            3000,
            delta=60,
        )

    def test_frontend_reads_exact_stopped_progress_and_pit_interval(self):
        result = run_pit_race()
        playback = RacePlayback(result)
        car = playback.car("a")
        events = {e["type"]: e for e in result["pit_stop_events"]}
        start = events["service_started"]["time_ms"] + 200
        end = events["service_completed"]["time_ms"] - 200
        self.assertAlmostEqual(car.laps_at(start), car.laps_at(end), places=4)
        self.assertEqual(car.spatial_at(start).speed_kmh, 0)
        self.assertTrue(car.in_pit_lap_at(start))
        self.assertFalse(car.in_pit_lap_at(events["entry"]["time_ms"] - 200))
        self.assertFalse(car.in_pit_lap_at(events["exit"]["time_ms"] + 200))
        self.assertEqual(car.tyre_at(start).compound, "MEDIUM")
        self.assertEqual(
            car.tyre_at(events["service_completed"]["time_ms"] + 200).compound, "HARD"
        )
        self.assertEqual(playback.standings(playback.duration_ms)[0].position, 1)

    def test_no_stop_has_no_lane_visits(self):
        result = run_pit_race(stop=False)
        self.assertFalse(result["pit_stop_events"])
        self.assertTrue(all(p[4] is None for p in result["trajectories_2d"]["a"]))

    def test_live_order_uses_stopped_progress_and_agrees_with_final_classification(
        self,
    ):
        model = parameters()
        result = simulate_2d_race(
            [
                {
                    "driver_id": "a",
                    "name": "A",
                    "grid_position": 1,
                    "strategy": PlannedStopStrategy(1, ("HARD",)),
                },
                {
                    "driver_id": "b",
                    "name": "B",
                    "grid_position": 2,
                    "strategy": NoStopStrategy(),
                },
            ],
            pit_geometry(),
            total_laps=4,
            rng=SeededRandomSource(1),
            compounds={c.name: c for c in model.compounds},
            track_params=track(),
            model_parameters=model,
            race_control=None,
        )
        playback = RacePlayback(result)
        for event in result["pit_stop_events"]:
            t = event["time_ms"] + 20
            rows = playback.standings(t)
            progress = [playback.car(row.driver_id).laps_at(t) for row in rows]
            self.assertEqual(progress, sorted(progress, reverse=True))
        self.assertEqual(
            [row.driver_id for row in playback.standings(playback.duration_ms)],
            [row["driver_id"] for row in result["classification"]],
        )

    def test_old_four_field_trajectories_remain_readable(self):
        result = run_pit_race(stop=False)
        result["trajectories_2d"] = {
            "a": [p[:4] for p in result["trajectories_2d"]["a"]]
        }
        result.pop("pit_lane_2d")
        playback = RacePlayback(result)
        self.assertIsNone(playback.car("a").spatial_at(1000).pit_distance_m)
        self.assertFalse(playback.car("a").in_pit_lap_at(1000))
        self.assertEqual(playback.car("a").laps_at(playback.duration_ms), 4)


if __name__ == "__main__":
    unittest.main()
