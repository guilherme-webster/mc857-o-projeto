"""Motor 2D de pista (ADR 0011): geometria em faixa, integracao sub-volta,
exclusao espacial, ultrapassagem emergente e colisao.

Os tempos de volta validam a ponte com o motor por distancia do ADR 0010; os
demais testes exercem a fisica espacial em geometrias sinteticas simples, onde o
comportamento esperado e conhecido de antemao.
"""

from __future__ import annotations

import math
import unittest
from datetime import date

from f1_simulator.domain.random_source import SeededRandomSource
from f1_simulator.domain.race_simulation_2d import (
    GRID_ROW_SPACING_M,
    _grid_coordinates,
)
from f1_simulator.domain.speed_dynamics import (
    CarPhysics,
    lap_time_ms,
    steady_lap,
)
from f1_simulator.domain.track_geometry import (
    GeometryProvenance,
    TrackGeometry,
    TrackPoint,
)
from f1_simulator.domain.track_space import (
    ASSUMED_CAR_LENGTH_M,
    CarSpaceState,
    build_track_space,
    integrate_field,
    integrate_single_car,
    lap_time_ms_2d,
)

_PROV = GeometryProvenance(
    source_name="test",
    source_version="1",
    source_year=2025,
    generated_on=date(2025, 1, 1),
    upstream=None,
    upstream_data_license="CC0",
    artifact_sha256="a" * 64,
    manifest_sha256="b" * 64,
    transformation="synthetic",
)


def _geometry_from_corners(corners):
    """TrackGeometry a partir de uma lista fechada de vertices (x, y)."""

    points = []
    cum = 0.0
    prev = None
    for i, (x, y) in enumerate(corners):
        if prev is not None:
            cum += ((x - prev[0]) ** 2 + (y - prev[1]) ** 2) ** 0.5
        points.append(TrackPoint(i, float(x), float(y), cum))
        prev = (x, y)
    return TrackGeometry("circuit:test", tuple(points), (), _PROV, _PROV)


def _square(side=100.0):
    return _geometry_from_corners(
        [(0, 0), (side, 0), (side, side), (0, side), (0, 0)]
    )


def _circle(radius=318.3, n=120):
    corners = []
    for k in range(n + 1):
        a = 2 * math.pi * k / n
        corners.append((radius * math.cos(a), radius * math.sin(a)))
    return _geometry_from_corners(corners)


def _rectangle_with_straight(straight_m=2000.0, width=100.0, step=10.0):
    """Retangulo com uma reta longa densamente amostrada."""

    corners = []
    n = int(straight_m / step)
    for i in range(n + 1):
        corners.append((i * step, 0.0))
    for i in range(1, int(width / step) + 1):
        corners.append((straight_m, i * step))
    for i in range(1, n + 1):
        corners.append((straight_m - i * step, width))
    for i in range(1, int(width / step) + 1):
        corners.append((0.0, width - i * step))
    return _geometry_from_corners(corners)


class TrackSpaceGeometryTest(unittest.TestCase):
    def test_center_lies_on_centerline(self):
        sp = build_track_space(_square(), width_m=12.0)
        x, y = sp.position(50.0, 0.0)
        self.assertAlmostEqual(x, 50.0, places=5)
        self.assertAlmostEqual(y, 0.0, places=5)

    def test_lateral_offset_leaves_centerline(self):
        sp = build_track_space(_square(), width_m=12.0)
        center = sp.position(50.0, 0.0)
        offset = sp.position(50.0, 6.0)
        moved = (offset[0] - center[0]) ** 2 + (offset[1] - center[1]) ** 2
        self.assertGreater(moved, 0.0)

    def test_usable_width_excludes_car_body(self):
        sp = build_track_space(_square(), width_m=12.0)
        bounds = sp.bounds
        self.assertAlmostEqual(bounds.usable_m, 6.0 - 1.0)

    def test_clamp_keeps_car_on_track(self):
        sp = build_track_space(_square(), width_m=12.0)
        car = CarSpaceState("d", lateral_m=99.0)
        car.clamp_lateral(sp.bounds)
        self.assertLessEqual(abs(car.lateral_m), sp.bounds.usable_m + 1e-9)

    def test_rejects_non_positive_width(self):
        with self.assertRaises(ValueError):
            build_track_space(_square(), width_m=0.0)

    def test_starting_grid_uses_two_cars_per_row_on_opposite_sides(self):
        p1 = _grid_coordinates(1, 20, 5.0)
        p2 = _grid_coordinates(2, 20, 5.0)
        p3 = _grid_coordinates(3, 20, 5.0)
        p4 = _grid_coordinates(4, 20, 5.0)
        p19 = _grid_coordinates(19, 20, 5.0)
        p20 = _grid_coordinates(20, 20, 5.0)

        self.assertEqual(p1[0], p2[0])
        self.assertEqual(p3[0], p4[0])
        self.assertEqual(p1[0] - p3[0], GRID_ROW_SPACING_M)
        self.assertEqual(p19[0], p20[0])
        self.assertEqual(p19[0], 0.0)
        self.assertEqual(p1[1], -p2[1])
        self.assertEqual(p3[1], -p4[1])


class SingleCarIntegratorTest(unittest.TestCase):
    def test_lap_time_matches_distance_engine(self):
        geo = _circle()
        phys = CarPhysics()
        expected = lap_time_ms(steady_lap(geo, phys))
        for dt in (0.1, 0.05, 0.02):
            samples = integrate_single_car(geo, phys, dt_s=dt)
            got = lap_time_ms_2d(samples, geo.lap_length_m)
            self.assertAlmostEqual(got, expected, delta=expected * 0.01)

    def test_completes_one_lap(self):
        geo = _circle()
        samples = integrate_single_car(geo, CarPhysics(), dt_s=0.05)
        self.assertGreaterEqual(samples[-1].distance_m, geo.lap_length_m)

    def test_rejects_non_positive_step(self):
        with self.assertRaises(ValueError):
            integrate_single_car(_circle(), CarPhysics(), dt_s=0.0)


class SpatialExclusionTest(unittest.TestCase):
    def test_same_lane_keeps_car_length_gap_on_straight(self):
        # Carros identicos colados na mesma faixa: o de tras nunca e mais rapido
        # (nao desvia nem passa), entao so a exclusao espacial atua. Na reta,
        # sem frenagem, a folga se mantem em um comprimento de carro. (Na entrada
        # de curva o integrador discreto pode encolher a folga por um ou dois
        # passos -- limitacao documentada no motor.)
        sp = build_track_space(_rectangle_with_straight(straight_m=2000.0), width_m=12.0)
        same = CarPhysics(v_max_straight_kmh=230, v_min_corner_kmh=120)
        cars = [
            CarSpaceState("a", distance_m=25, lateral_m=0.0, speed_ms=60),
            CarSpaceState("b", distance_m=20, lateral_m=0.0, speed_ms=60),
        ]
        res = integrate_field(
            cars, sp, {"a": same, "b": same}, total_laps=1, dt_s=0.05
        )
        # So os instantes na reta (ambos antes do fim da reta em 2000m).
        straight = [
            s for s in res
            if all({c.driver_id: c for c in s.cars}[d].distance_m < 1900.0
                   for d in ("a", "b"))
        ]
        min_gap = min(
            ({c.driver_id: c for c in s.cars}["a"].distance_m
             - {c.driver_id: c for c in s.cars}["b"].distance_m)
            for s in straight
        )
        # Tolerancia de discretizacao: o avanco por passo deixa uma margem de
        # alguns centimetros em torno da folga de um comprimento de carro.
        self.assertGreaterEqual(min_gap, ASSUMED_CAR_LENGTH_M - 0.15)

    def test_bodies_never_overlap_grossly(self):
        # Mesmo na frenagem, a folga nunca deve indicar sobreposicao total dos
        # corpos (folga centro-a-centro >= metade de um comprimento de carro).
        sp = build_track_space(_rectangle_with_straight(straight_m=2000.0), width_m=12.0)
        same = CarPhysics(v_max_straight_kmh=230, v_min_corner_kmh=120)
        cars = [
            CarSpaceState("a", distance_m=25, lateral_m=0.0, speed_ms=60),
            CarSpaceState("b", distance_m=20, lateral_m=0.0, speed_ms=60),
        ]
        res = integrate_field(
            cars, sp, {"a": same, "b": same}, total_laps=1, dt_s=0.05
        )
        race = sp.lap_length_m
        min_gap = min(
            ({c.driver_id: c for c in s.cars}["a"].distance_m
             - {c.driver_id: c for c in s.cars}["b"].distance_m)
            for s in res
            if all(c.distance_m < race for c in s.cars)
        )
        self.assertGreater(min_gap, ASSUMED_CAR_LENGTH_M / 2.0)

    def test_different_lanes_do_not_block(self):
        sp = build_track_space(_rectangle_with_straight(), width_m=12.0)
        fast = CarPhysics(v_max_straight_kmh=330, v_min_corner_kmh=120)
        slow = CarPhysics(v_max_straight_kmh=230, v_min_corner_kmh=120)
        cars = [
            CarSpaceState("a_slow", distance_m=40, lateral_m=4.0, speed_ms=60),
            CarSpaceState("b_fast", distance_m=20, lateral_m=-4.0, speed_ms=60),
        ]
        res = integrate_field(
            cars,
            sp,
            {"a_slow": slow, "b_fast": fast},
            total_laps=1,
            dt_s=0.05,
        )
        final = {c.driver_id: c for c in res[-1].cars}
        self.assertGreater(
            final["b_fast"].distance_m, final["a_slow"].distance_m
        )


class EmergentOvertakeTest(unittest.TestCase):
    def test_faster_car_changes_lane_and_passes(self):
        sp = build_track_space(
            _rectangle_with_straight(straight_m=5000.0), width_m=12.0
        )
        fast = CarPhysics(v_max_straight_kmh=330, v_min_corner_kmh=120)
        slow = CarPhysics(v_max_straight_kmh=200, v_min_corner_kmh=120)
        cars = [
            CarSpaceState("a_slow", distance_m=40, lateral_m=0.0, speed_ms=55),
            CarSpaceState("b_fast", distance_m=20, lateral_m=0.0, speed_ms=55),
        ]
        res = integrate_field(
            cars,
            sp,
            {"a_slow": slow, "b_fast": fast},
            total_laps=1,
            dt_s=0.05,
            aggression_by_id={"b_fast": 1.3},
        )
        max_lateral = max(
            abs({c.driver_id: c for c in s.cars}["b_fast"].lateral_m) for s in res
        )
        final = {c.driver_id: c for c in res[-1].cars}
        self.assertGreater(max_lateral, 0.5)  # desviou
        self.assertGreater(  # e passou
            final["b_fast"].distance_m, final["a_slow"].distance_m
        )

    def test_equal_speed_cars_hold_station_on_straight(self):
        # Numa reta, dois carros identicos partindo espacados mantem o gap:
        # nao ha razao para desviar nem para alcancar.
        sp = build_track_space(
            _rectangle_with_straight(straight_m=5000.0), width_m=12.0
        )
        same = CarPhysics(v_max_straight_kmh=240, v_min_corner_kmh=120)
        cars = [
            CarSpaceState("a", distance_m=40, lateral_m=0.0, speed_ms=60),
            CarSpaceState("b", distance_m=20, lateral_m=0.0, speed_ms=60),
        ]
        res = integrate_field(
            cars, sp, {"a": same, "b": same}, total_laps=1, dt_s=0.05
        )
        # Enquanto na reta (distancia < 5000m), b nao deve desviar.
        on_straight = [
            s for s in res
            if {c.driver_id: c for c in s.cars}["b"].distance_m < 4000.0
        ]
        max_lateral = max(
            abs({c.driver_id: c for c in s.cars}["b"].lateral_m) for s in on_straight
        )
        self.assertLess(max_lateral, 0.01)


class CollisionTest(unittest.TestCase):
    def _forced_rubbing_cars(self):
        # Dois carros emparelhados, corpos sobrepostos lateralmente (folga < 0).
        return [
            CarSpaceState("a", distance_m=100.0, lateral_m=0.0),
            CarSpaceState("b", distance_m=100.0, lateral_m=1.0),
        ]

    def test_no_rng_means_no_collision(self):
        sp = build_track_space(_rectangle_with_straight(), width_m=12.0)
        same = CarPhysics(v_max_straight_kmh=250, v_min_corner_kmh=130)
        cars = self._forced_rubbing_cars()
        res = integrate_field(
            cars, sp, {"a": same, "b": same}, total_laps=1, dt_s=0.05
        )
        self.assertFalse(any(c.retired for c in res[-1].cars))

    def test_sustained_rubbing_can_cause_contact(self):
        from f1_simulator.domain.track_space import _resolve_collisions

        hits = 0
        for seed in range(100):
            a = CarSpaceState("a", distance_m=100.0, lateral_m=0.0)
            b = CarSpaceState("b", distance_m=100.0, lateral_m=1.0)
            rng = SeededRandomSource(seed).spawn("x")
            for _ in range(20):  # 1 s de rocamento a dt=0.05
                if a.retired or b.retired:
                    break
                _resolve_collisions([a, b], 1e9, {"a": 1.0, "b": 1.0}, rng, 0.05)
            if a.retired or b.retired:
                hits += 1
        self.assertGreater(hits, 0)
        self.assertLess(hits, 100)

    def test_aggression_raises_contact_rate(self):
        from f1_simulator.domain.track_space import _resolve_collisions

        def crashes(aggression):
            hits = 0
            for seed in range(100):
                a = CarSpaceState("a", distance_m=100.0, lateral_m=0.0)
                b = CarSpaceState("b", distance_m=100.0, lateral_m=1.0)
                rng = SeededRandomSource(seed).spawn("x")
                for _ in range(20):
                    if a.retired or b.retired:
                        break
                    _resolve_collisions(
                        [a, b], 1e9, {"a": aggression, "b": aggression}, rng, 0.05
                    )
                if a.retired or b.retired:
                    hits += 1
            return hits

        self.assertGreater(crashes(3.0), crashes(1.0))

    def test_collision_reproducible_by_seed(self):
        sp = build_track_space(_rectangle_with_straight(), width_m=12.0)
        fast = CarPhysics(v_max_straight_kmh=330, v_min_corner_kmh=140)
        slow = CarPhysics(v_max_straight_kmh=250, v_min_corner_kmh=130)

        def run():
            cars = [
                CarSpaceState("a", distance_m=15, lateral_m=0.0, speed_ms=60),
                CarSpaceState("c", distance_m=0, lateral_m=0.0, speed_ms=60),
            ]
            rng = SeededRandomSource(7).spawn("race")
            res = integrate_field(
                cars,
                sp,
                {"a": slow, "c": fast},
                total_laps=3,
                dt_s=0.05,
                aggression_by_id={"c": 3.0},
                rng=rng,
            )
            return sorted(c.driver_id for c in res[-1].cars if c.retired)

        self.assertEqual(run(), run())


if __name__ == "__main__":
    unittest.main()
