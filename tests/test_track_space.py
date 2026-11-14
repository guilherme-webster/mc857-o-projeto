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


def _finish_time(samples, driver_id, race_distance_m):
    """Primeiro instante em que o carro completa ``race_distance_m``.

    Comparar a distancia final nao serve: depois da bandeirada os dois carros
    param de avancar, e a diferenca vira so o quanto cada um passou da linha no
    ultimo passo.
    """

    for sample in samples:
        car = {c.driver_id: c for c in sample.cars}[driver_id]
        if car.distance_m >= race_distance_m:
            return sample.time_s
    return float("inf")


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

    def test_interpolated_normal_preserves_offset_in_metres(self):
        from f1_simulator.domain.track_space import _projected_rectangle

        sp = build_track_space(_square(), width_m=12.0)
        car = CarSpaceState("d", lateral_m=3.0)
        for distance in (25.0, 50.0, 75.0):
            center = sp.position(distance, 0.0)
            offset = sp.position(distance, 3.0)
            self.assertAlmostEqual(math.dist(center, offset) / sp.xy_per_metre, 3.0)
            x, y, _, _ = _projected_rectangle(sp, car, distance)
            self.assertAlmostEqual(offset[0], x * sp.xy_per_metre)
            self.assertAlmostEqual(offset[1], y * sp.xy_per_metre)

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
    def test_lapped_cars_remain_separate_including_under_neutralization(self):
        sp = build_track_space(_square(200), width_m=12.0)
        physics = CarPhysics()
        for dt in (0.1, 0.2, 0.4):
            for neutralized in (False, True):
                with self.subTest(dt=dt, neutralized=neutralized):
                    cars = [
                        CarSpaceState("leader", distance_m=sp.lap_length_m + 5,
                                      speed_ms=40),
                        CarSpaceState("lapped", distance_m=20, speed_ms=30),
                    ]
                    samples = integrate_field(
                        cars, sp, {c.driver_id: physics for c in cars},
                        total_laps=3, dt_s=dt, max_steps=10000,
                        neutralized_lap=(lambda lap: True) if neutralized else None,
                    )
                    self.assertTrue(all(c.distance_m >= 3 * sp.lap_length_m
                                        for c in samples[-1].cars))
                    for sample in samples:
                        a, b = sample.cars
                        if a.distance_m >= 3 * sp.lap_length_m or b.distance_m >= 3 * sp.lap_length_m:
                            continue
                        gap = abs((a.distance_m - b.distance_m + sp.lap_length_m / 2)
                                  % sp.lap_length_m - sp.lap_length_m / 2)
                        lateral = abs(a.lateral_m - b.lateral_m)
                        self.assertTrue(gap >= 5 - 1e-8 or lateral >= 2 - 1e-8,
                                        (dt, neutralized, sample.time_s, gap, lateral))

    def test_lateral_move_cannot_cross_an_adjacent_car(self):
        from f1_simulator.domain.track_space import _limit_lateral_move, _rubbing

        a = CarSpaceState("a", distance_m=805, lateral_m=3.0)
        b = CarSpaceState("b", distance_m=5, lateral_m=0.0)
        a.lateral_m = _limit_lateral_move(a, 0.9, [a, b], 2400, 800)
        self.assertAlmostEqual(a.lateral_m, 2.3)
        self.assertFalse(_rubbing(a, b, 800))
        # Quem ja esta dentro da margem nao se move para mais perto nem salta.
        a.lateral_m = 2.1
        self.assertAlmostEqual(_limit_lateral_move(a, 0.9, [a, b], 2400, 800), 2.1)
        self.assertAlmostEqual(_limit_lateral_move(a, 3.0, [a, b], 2400, 800), 3.0)
        # Erro numerico no limite longitudinal nao gera roçamento numa fila.
        a.distance_m = 810 - 1e-10
        a.lateral_m = 0.0
        self.assertFalse(_rubbing(a, b, 800))

    def test_monaco_seed_three_keeps_exclusion_when_contacts_occur(self):
        from dataclasses import replace
        from itertools import combinations
        from unittest.mock import patch

        from f1_simulator.adapters.driver_presets_json import load_driver_presets
        from f1_simulator.domain import race_simulation_2d
        from tests.geometry_support import attribute, fixture_geometry

        presets = list(load_driver_presets("configs/drivers/perfis-ficticios.json").values())[:20]
        entries = []
        for i, preset in enumerate(presets, 1):
            attrs = attribute(preset.driver_id, **preset.values)
            entries.append({"driver_id": preset.driver_id, "name": preset.driver_name,
                            "grid_position": i, "attributes": attrs,
                            "aggression": attrs.aggression})
        geometry = fixture_geometry()
        original = race_simulation_2d.integrate_field
        contacts_are_geometric = []
        def check_samples(*args, **kwargs):
            from f1_simulator.domain.track_space import (
                ASSUMED_RUBBING_MARGIN_M,
                _projected_rectangle,
                _rectangles_overlap,
            )

            samples = original(*args, **kwargs)
            track = args[1]
            for before, after in zip(samples, samples[1:]):
                previous = {c.driver_id: c for c in before.cars}
                for car in after.cars:
                    if not car.retired or previous[car.driver_id].retired:
                        continue
                    pose = _projected_rectangle(track, car, car.distance_m)
                    # O motor sorteia contato dentro da margem lateral de
                    # rocamento, antes de os retangulos necessariamente se
                    # atravessarem. Cada meia-largura recebe metade da margem;
                    # o comprimento permanece fisico para nao aceitar fila.
                    contact_car = replace(car, width_m=car.width_m + ASSUMED_RUBBING_MARGIN_M)
                    contacts_are_geometric.append(any(
                        other.driver_id != car.driver_id and not other.retired
                        and _rectangles_overlap(
                            contact_car, pose,
                            replace(other, width_m=other.width_m + ASSUMED_RUBBING_MARGIN_M),
                            _projected_rectangle(track, other, other.distance_m),
                        ) for other in after.cars
                    ))
            for sample in samples:
                cars = [c for c in sample.cars if not c.retired and c.pit_state is None
                        and c.distance_m < geometry.lap_length_m]
                for a, b in combinations(cars, 2):
                    gap = abs((a.distance_m - b.distance_m + geometry.lap_length_m / 2)
                              % geometry.lap_length_m - geometry.lap_length_m / 2)
                    lateral = abs(a.lateral_m - b.lateral_m)
                    self.assertTrue(gap >= 5 - 1e-7 or lateral >= 2 - 1e-7,
                                    (sample.time_s, a.driver_id, b.driver_id, gap, lateral))
            return samples

        with patch.object(race_simulation_2d, "integrate_field", check_samples):
            race = race_simulation_2d.simulate_2d_race(
                entries, geometry, total_laps=1, rng=SeededRandomSource(3), dt_s=0.2
            )
        self.assertTrue(race["contact_events_2d"])
        self.assertTrue(all(contacts_are_geometric))

    def test_projected_advance_respects_compressed_monaco_segment(self):
        from f1_simulator.domain.track_space import (
            _limit_projected_advance,
            _projected_rectangle,
            _rectangles_overlap,
        )
        from tests.geometry_support import fixture_geometry

        track = build_track_space(fixture_geometry())
        leader = CarSpaceState("leader", distance_m=1002.512)
        follower = CarSpaceState("follower", distance_m=980.0)
        proposed = 997.512
        leader_pose = _projected_rectangle(track, leader, leader.distance_m)
        self.assertTrue(_rectangles_overlap(
            follower, _projected_rectangle(track, follower, proposed), leader, leader_pose
        ))
        limit = _limit_projected_advance(track, follower, leader, proposed)
        self.assertGreater(limit, follower.distance_m)
        self.assertLess(limit, proposed)
        self.assertFalse(_rectangles_overlap(
            follower, _projected_rectangle(track, follower, limit), leader, leader_pose
        ))
        # O estado nao e deslocado e faixas separadas continuam disponiveis.
        self.assertEqual(follower.distance_m, 980.0)
        follower.lateral_m = 8.0
        self.assertEqual(_limit_projected_advance(track, follower, leader, proposed), proposed)

    def test_same_lane_keeps_car_length_gap_on_straight(self):
        # Carros identicos colados na mesma faixa: o de tras nunca e mais rapido
        # (nao desvia nem passa), entao so a exclusao espacial atua. Na reta,
        # sem frenagem, a folga se mantem em um comprimento de carro. (Na entrada
        # de curva o integrador discreto pode encolher a folga por um ou dois
        # passos -- limitacao documentada no motor.)
        sp = build_track_space(_rectangle_with_straight(straight_m=2000.0), width_m=12.0)
        same = CarPhysics(v_max_straight_kmh=230)
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
        # Mesmo na frenagem, dois corpos na mesma faixa nunca se sobrepoem por
        # inteiro (folga centro-a-centro >= metade de um comprimento de carro).
        # Na freada forte o de tras pode sair da esteira e emparelhar por fora
        # (tentativa de ultrapassagem): lado a lado nao e sobreposicao, entao so
        # contam os instantes em que as faixas se cruzam.
        sp = build_track_space(_rectangle_with_straight(straight_m=2000.0), width_m=12.0)
        same = CarPhysics(v_max_straight_kmh=230)
        cars = [
            CarSpaceState("a", distance_m=25, lateral_m=0.0, speed_ms=60),
            CarSpaceState("b", distance_m=20, lateral_m=0.0, speed_ms=60),
        ]
        res = integrate_field(
            cars, sp, {"a": same, "b": same}, total_laps=1, dt_s=0.05
        )
        race = sp.lap_length_m
        gaps = []
        for s in res:
            by_id = {c.driver_id: c for c in s.cars}
            a, b = by_id["a"], by_id["b"]
            same_lane = abs(a.lateral_m - b.lateral_m) < (a.width_m + b.width_m) / 2
            if same_lane and a.distance_m < race and b.distance_m < race:
                gaps.append(a.distance_m - b.distance_m)
        self.assertTrue(gaps)
        self.assertGreater(min(gaps), ASSUMED_CAR_LENGTH_M / 2.0)

    def test_different_lanes_do_not_block(self):
        sp = build_track_space(_rectangle_with_straight(), width_m=12.0)
        fast = CarPhysics(v_max_straight_kmh=330)
        slow = CarPhysics(v_max_straight_kmh=230)
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
        # Faixas separadas: o rapido nao fica preso e cruza a linha primeiro.
        self.assertLess(
            _finish_time(res, "b_fast", sp.lap_length_m),
            _finish_time(res, "a_slow", sp.lap_length_m),
        )


class EmergentOvertakeTest(unittest.TestCase):
    def test_predictive_corridor_detects_fast_rear_and_allows_nonclosing_car(self):
        from f1_simulator.domain.track_space import _side_is_clear

        car = CarSpaceState("car", distance_m=100, speed_ms=40)
        rear = CarSpaceState("rear", distance_m=94, lateral_m=2.4, speed_ms=80)
        self.assertFalse(_side_is_clear(car, 2.4, [car, rear], 800, 800))
        rear.speed_ms = 40
        self.assertTrue(_side_is_clear(car, 2.4, [car, rear], 800, 800))
        rear.speed_ms = 80
        rear.distance_m = 54  # Nao alcança a manobra curta.
        self.assertTrue(_side_is_clear(car, 2.4, [car, rear], 800, 800))

    def test_predictive_corridor_wraps_finish_and_checks_crossed_lane(self):
        from f1_simulator.domain.track_space import _side_is_clear

        car = CarSpaceState("car", distance_m=802, lateral_m=-3, speed_ms=40)
        rear = CarSpaceState("rear", distance_m=796, lateral_m=0, speed_ms=80)
        self.assertFalse(_side_is_clear(car, 3, [car, rear], 2400, 800))

    def test_fast_rear_rejects_candidate_and_uses_other_side(self):
        from f1_simulator.domain.track_space import _lane_decision

        car = CarSpaceState("car", distance_m=100, speed_ms=40, speed_scale=1.0)
        leader = CarSpaceState("leader", distance_m=110, speed_ms=40)
        rear = CarSpaceState("rear", distance_m=94, lateral_m=2.4, speed_ms=80)
        cars = [car, leader, rear]
        ceilings = {c.driver_id: ([0.0, 800.0], [40.0, 40.0]) for c in cars}
        ceilings["car"] = ([0.0, 800.0], [60.0, 60.0])
        self.assertLess(_lane_decision(car, {c.driver_id: c for c in cars}, cars,
                                       ceilings, 800, 5, 1.0, 800), 0.0)
        self.assertEqual(car.overtaking, "leader")

    def test_blocked_follower_plans_pass_from_free_track_ceiling(self):
        from f1_simulator.domain.track_space import _lane_decision

        leader = CarSpaceState("leader", distance_m=40, speed_ms=40)
        follower = CarSpaceState("follower", distance_m=30, speed_ms=40)
        cars = [follower, leader]
        by_id = {c.driver_id: c for c in cars}
        ceilings = {"follower": ([0.0, 800.0], [60.0, 60.0]),
                    "leader": ([0.0, 800.0], [40.0, 40.0])}
        target = _lane_decision(follower, by_id, cars, ceilings, 800, 5, 1.0, 800)
        self.assertGreater(target, 0.0)
        self.assertEqual(follower.overtaking, "leader")
        follower.speed_ms = 35
        self.assertGreater(_lane_decision(follower, by_id, cars, ceilings,
                                          800, 5, 1.0, 800), 0.0)
        self.assertEqual(follower.overtaking, "leader")

    def test_blocked_follower_waits_when_both_sides_are_occupied(self):
        from f1_simulator.domain.track_space import _lane_decision

        cars = [CarSpaceState("follower", distance_m=30, speed_ms=40),
                CarSpaceState("leader", distance_m=40, speed_ms=40),
                CarSpaceState("left", distance_m=30, lateral_m=2.4),
                CarSpaceState("right", distance_m=30, lateral_m=-2.4)]
        ceilings = {c.driver_id: ([0.0, 800.0], [40.0, 40.0]) for c in cars}
        ceilings["follower"] = ([0.0, 800.0], [60.0, 60.0])
        target = _lane_decision(cars[0], {c.driver_id: c for c in cars}, cars,
                                ceilings, 800, 5, 1.0, 800)
        self.assertEqual(target, 0.0)
        self.assertIsNone(cars[0].overtaking)

    def test_equal_free_track_ceiling_does_not_start_pass(self):
        from f1_simulator.domain.track_space import _lane_decision

        leader = CarSpaceState("leader", distance_m=40, speed_ms=40)
        follower = CarSpaceState("follower", distance_m=30, speed_ms=40)
        cars = [follower, leader]
        ceilings = {c.driver_id: ([0.0, 800.0], [60.0, 60.0]) for c in cars}
        target = _lane_decision(follower, {c.driver_id: c for c in cars}, cars,
                                ceilings, 800, 5, 1.0, 800)
        self.assertEqual(target, 0.0)
        self.assertIsNone(follower.overtaking)

    def test_equal_ceiling_leader_queued_behind_third_car_can_be_passed(self):
        from f1_simulator.domain.track_space import _lane_decision

        cars = [CarSpaceState("follower", distance_m=30, speed_ms=40),
                CarSpaceState("leader", distance_m=40, speed_ms=40),
                CarSpaceState("obstruction", distance_m=45, speed_ms=40)]
        ceilings = {c.driver_id: ([0.0, 800.0], [60.0, 60.0]) for c in cars}
        target = _lane_decision(cars[0], {c.driver_id: c for c in cars}, cars,
                                ceilings, 800, 5, 1.0, 800)
        self.assertGreater(target, 0.0)
        self.assertEqual(cars[0].overtaking, "leader")

    def test_curve_without_obstruction_does_not_create_passing_advantage(self):
        from f1_simulator.domain.track_space import _lane_decision

        cars = [CarSpaceState("follower", distance_m=30, speed_ms=40),
                CarSpaceState("leader", distance_m=40, speed_ms=35)]
        ceilings = {c.driver_id: ([0.0, 30.0, 40.0, 800.0], [60.0, 45.0, 35.0, 35.0])
                    for c in cars}
        target = _lane_decision(cars[0], {c.driver_id: c for c in cars}, cars,
                                ceilings, 800, 5, 1.0, 800)
        self.assertEqual(target, 0.0)
        self.assertIsNone(cars[0].overtaking)

    def test_return_keeps_clearance_from_car_alongside(self):
        from f1_simulator.domain.track_space import _safe_center

        passing = CarSpaceState("passing", distance_m=110, lateral_m=2.4)
        other = CarSpaceState("other", distance_m=108, lateral_m=0)
        target = _safe_center(passing, [passing, other], 800, 5, 800)
        self.assertAlmostEqual(target, 2.3)
        other.distance_m = 104
        self.assertEqual(_safe_center(passing, [passing, other], 800, 5, 800), 0.0)

    def test_three_car_field_produces_persistent_passes(self):
        sp = build_track_space(_rectangle_with_straight(straight_m=1000), width_m=12)
        physics = CarPhysics(v_max_straight_kmh=260)
        cars = [
            CarSpaceState("slow", distance_m=80, speed_ms=45, speed_scale=0.7),
            CarSpaceState("mid", distance_m=55, speed_ms=48, speed_scale=0.85),
            CarSpaceState("fast", distance_m=30, speed_ms=50, speed_scale=1.0),
        ]
        samples = integrate_field(
            cars, sp, {c.driver_id: physics for c in cars},
            total_laps=1, dt_s=0.2, max_steps=5000,
        )
        states = [{c.driver_id: c for c in sample.cars} for sample in samples]
        for attacker, leader in (("fast", "mid"), ("fast", "slow"), ("mid", "slow")):
            gaps = [state[attacker].distance_m - state[leader].distance_m for state in states]
            self.assertTrue(all(gap <= -5.0 for gap in gaps[:5]))
            # Cinco amostras consecutivas com um corpo de folga evitam
            # classificar uma simples oscilacao instantanea como passagem.
            self.assertTrue(any(all(gap >= 5.0 for gap in gaps[i:i + 5])
                                for i in range(len(gaps) - 4)))
            self.assertGreater(max(abs(s[attacker].lateral_m) for s in states), 0.5)

    def test_slower_speed_scale_triggers_overtake_with_same_physics(self):
        sp = build_track_space(_rectangle_with_straight(straight_m=1000), width_m=12)
        physics = CarPhysics(v_max_straight_kmh=260)
        cars = [
            CarSpaceState("slow", distance_m=40, speed_ms=45, speed_scale=0.8),
            CarSpaceState("fast", distance_m=20, speed_ms=50, speed_scale=1.0),
        ]
        samples = integrate_field(
            cars, sp, {c.driver_id: physics for c in cars},
            total_laps=1, dt_s=0.2, max_steps=5000,
        )
        self.assertGreater(max(abs(next(c for c in s.cars if c.driver_id == "fast").lateral_m)
                               for s in samples), 0.5)
        self.assertLess(_finish_time(samples, "fast", sp.lap_length_m),
                        _finish_time(samples, "slow", sp.lap_length_m))

    def test_faster_car_changes_lane_and_passes(self):
        sp = build_track_space(
            _rectangle_with_straight(straight_m=5000.0), width_m=12.0
        )
        fast = CarPhysics(v_max_straight_kmh=330)
        slow = CarPhysics(v_max_straight_kmh=200)
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
        self.assertGreater(max_lateral, 0.5)  # desviou
        self.assertLess(  # e passou: cruza a linha antes de quem largou na frente
            _finish_time(res, "b_fast", sp.lap_length_m),
            _finish_time(res, "a_slow", sp.lap_length_m),
        )

    def test_equal_speed_cars_hold_station_on_straight(self):
        # Numa reta, dois carros identicos partindo espacados mantem o gap:
        # nao ha razao para desviar nem para alcancar.
        sp = build_track_space(
            _rectangle_with_straight(straight_m=5000.0), width_m=12.0
        )
        same = CarPhysics(v_max_straight_kmh=240)
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
    def test_lapped_cars_can_still_touch_in_the_rubbing_margin(self):
        from f1_simulator.domain.track_space import _resolve_collisions

        cars = [CarSpaceState("a", distance_m=802, lateral_m=0),
                CarSpaceState("b", distance_m=1, lateral_m=2.2)]
        _resolve_collisions(cars, 2400, {}, SeededRandomSource(1), 100,
                            lap_length_m=800)
        # A margem lateral e espaco de planejamento, nao encontro dos corpos.
        self.assertEqual(sum(c.retired for c in cars), 0)

    def _forced_rubbing_cars(self):
        # Dois carros emparelhados, corpos sobrepostos lateralmente (folga < 0).
        return [
            CarSpaceState("a", distance_m=100.0, lateral_m=0.0),
            CarSpaceState("b", distance_m=100.0, lateral_m=1.0),
        ]

    def test_no_rng_means_no_collision(self):
        sp = build_track_space(_rectangle_with_straight(), width_m=12.0)
        same = CarPhysics(v_max_straight_kmh=250)
        cars = self._forced_rubbing_cars()
        res = integrate_field(
            cars, sp, {"a": same, "b": same}, total_laps=1, dt_s=0.05
        )
        self.assertFalse(any(c.retired for c in res[-1].cars))

    def test_sustained_rubbing_can_cause_contact(self):
        from f1_simulator.domain.spatial_contact import ContactTracker
        from f1_simulator.domain.track_space import _resolve_collisions

        hits = 0
        for seed in range(100):
            a = CarSpaceState("a", distance_m=100.0, lateral_m=0.0)
            b = CarSpaceState("b", distance_m=100.0, lateral_m=1.0)
            rng = SeededRandomSource(seed).spawn("x")
            events = []
            tracker = ContactTracker()
            for _ in range(20):  # 1 s de rocamento a dt=0.05
                if a.retired or b.retired:
                    break
                _resolve_collisions([a, b], 1e9, {"a": 1.0, "b": 1.0}, rng, 0.05,
                                    events=events, tracker=tracker)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["kind"], "touch")
            if a.retired or b.retired:
                hits += 1
        self.assertEqual(hits, 0)

    def test_aggression_raises_contact_rate(self):
        from f1_simulator.domain.track_space import _resolve_collisions

        def crashes(aggression):
            hits = 0
            for seed in range(100):
                a = CarSpaceState("a", distance_m=100.0, speed_ms=28)
                b = CarSpaceState("b", distance_m=104.0, speed_ms=20)
                rng = SeededRandomSource(seed).spawn("x")
                _resolve_collisions(
                    [a, b], 1e9, {"a": aggression, "b": aggression}, rng, 0.05
                )
                if a.retired or b.retired:
                    hits += 1
            return hits

        self.assertGreater(crashes(3.0), crashes(1.0))

    def test_collision_reproducible_by_seed(self):
        sp = build_track_space(_rectangle_with_straight(), width_m=12.0)
        fast = CarPhysics(v_max_straight_kmh=330)
        slow = CarPhysics(v_max_straight_kmh=250)

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
