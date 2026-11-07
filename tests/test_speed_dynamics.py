"""Motor fisico de velocidade limitado por aderencia (ADR 0015).

Os testes sinteticos verificam a fisica onde a resposta e conhecida (circulo,
reta, formula da curva). Os testes com a geometria versionada verificam o
contrato que motiva o modelo: o carro de referencia reproduz as voltas
historicas, e o artefato calibrado e a constante do dominio nao divergem.
"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from f1_simulator.adapters.car_physics_json import (
    CarPhysicsParametersError,
    read_car_physics,
    write_car_physics,
)
from f1_simulator.adapters.datasets.mock_track_geometry import MockTrackDatasetAdapter
from f1_simulator.adapters.reference_laps_json import read_reference_laps
from f1_simulator.application.calibrate_car_physics import (
    evaluate_car_physics,
    fit_car_physics,
)
from f1_simulator.domain.driver_attributes import DriverAttributes
from f1_simulator.domain.speed_dynamics import (
    DEFAULT_CAR_PHYSICS,
    GRAVITY_MS2,
    MIN_CORNER_RADIUS_M,
    CarPhysics,
    lap_time_ms,
    physics_for,
    speed_ceiling,
    steady_lap,
    track_curvature_per_m,
)
from f1_simulator.domain.track_geometry import (
    GeometryProvenance,
    TrackGeometry,
    TrackPoint,
)
from f1_simulator.factories.track_geometry_factory import TrackGeometryFactory

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "trotman_v128_tracks_2025"
SOURCES = ROOT / "data" / "sources"
CAR_PHYSICS_ARTIFACT = ROOT / "data" / "parameters" / "car-physics-v1.json"
REFERENCE_LAPS = ROOT / "data" / "parameters" / "reference-laps-v1.json"
MONACO = "circuit:6"

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


def _geometry(xy):
    """Geometria fechada em metros (escala 1:1), a partir de vertices (x, y)."""

    points, cum, prev = [], 0.0, None
    for i, (x, y) in enumerate(xy):
        if prev is not None:
            cum += math.dist(prev, (x, y))
        points.append(TrackPoint(i, float(x), float(y), cum))
        prev = (x, y)
    return TrackGeometry("circuit:test", tuple(points), (), _PROV, _PROV)


def _circle(radius, n=120):
    return _geometry(
        [
            (radius * math.cos(2 * math.pi * k / n), radius * math.sin(2 * math.pi * k / n))
            for k in range(n + 1)
        ]
    )


def _stadium(straight_m=1000.0, radius=40.0, step=10.0):
    """Duas retas unidas por semicirculos: um traçado com freada e tracao."""

    xy = [(x, 0.0) for x in _steps(0.0, straight_m, step)]
    arc = int(math.pi * radius / step)
    for k in range(1, arc):
        a = -math.pi / 2 + math.pi * k / arc
        xy.append((straight_m + radius * math.cos(a), radius + radius * math.sin(a)))
    xy += [(x, 2 * radius) for x in _steps(straight_m, 0.0, -step)]
    for k in range(1, arc):
        a = math.pi / 2 + math.pi * k / arc
        xy.append((radius * math.cos(a), radius + radius * math.sin(a)))
    xy.append(xy[0])
    return _geometry(xy)


def _steps(start, stop, step):
    count = int(round(abs(stop - start) / abs(step)))
    return [start + i * step for i in range(count + 1)]


def _attributes(**overrides):
    values = dict(
        pace_offset_pct=0.0,
        consistency_factor=1.0,
        tyre_management_factor=1.0,
        aggression=1.0,
        composure=1.0,
    )
    values.update(overrides)
    return DriverAttributes(
        driver_id="driver:test",
        archetype="balanced",
        sources={name: "manual" for name in values},
        **values,
    )


def _fixture_tracks():
    adapter = MockTrackDatasetAdapter(
        FIXTURE / "track_points.csv",
        SOURCES / "fastf1-tracks-2025.json",
        FIXTURE / "pit_lane_points.csv",
        SOURCES / "fastf1-pit-lanes-2025.json",
    )
    references = read_reference_laps(REFERENCE_LAPS)
    return {
        circuit_id: (
            TrackGeometryFactory.build(adapter.load_geometry(circuit_id)),
            reference.reference_lap_time_ms,
        )
        for circuit_id, reference in references.items()
    }


class CurvatureTest(unittest.TestCase):
    def test_sampled_circle_recovers_its_radius(self):
        for radius in (30.0, 120.0, 400.0):
            curvature = track_curvature_per_m(_circle(radius))
            for value in curvature:
                self.assertAlmostEqual(1.0 / value, radius, delta=radius * 0.01)

    def test_scale_comes_from_the_official_lap_length(self):
        # Coordenadas normalizadas (circulo de raio 1) com a extensao de um
        # circulo de 100 m: a curvatura deve sair em metros, nao em unidades xy.
        unit = _circle(1.0)
        lap = 2 * math.pi * 100.0
        scaled = replace(
            unit,
            track_points=tuple(
                replace(p, cumulative_distance_m=p.cumulative_distance_m * 100.0)
                for p in unit.track_points
            ),
        )
        self.assertAlmostEqual(scaled.lap_length_m, lap, delta=lap * 0.01)
        self.assertAlmostEqual(1.0 / track_curvature_per_m(scaled)[0], 100.0, delta=1.0)

    def test_straights_are_flat_and_sharp_vertices_are_capped(self):
        curvature = track_curvature_per_m(_stadium())
        self.assertEqual(curvature[50], 0.0)
        square = _geometry([(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)])
        self.assertLessEqual(
            max(track_curvature_per_m(square)), 1.0 / MIN_CORNER_RADIUS_M + 1e-12
        )


class CarPhysicsTest(unittest.TestCase):
    def test_corner_speed_follows_grip_and_downforce(self):
        car = DEFAULT_CAR_PHYSICS
        radius = 20.0
        expected = math.sqrt(
            car.grip_mu * GRAVITY_MS2 / (1 / radius - car.grip_mu * car.aero_k_per_m)
        )
        self.assertAlmostEqual(car.corner_speed_ms(1 / radius), expected)
        # Curva aberta o bastante: o downforce sozinho a segura.
        self.assertEqual(car.corner_speed_ms(1 / 2000.0), car.v_max_ms)

    def test_braking_grows_with_speed_and_traction_fades_at_top_speed(self):
        car = DEFAULT_CAR_PHYSICS
        self.assertGreater(car.brake_limit_ms2(80.0), 2 * car.brake_limit_ms2(25.0))
        self.assertGreater(car.accel_limit_ms2(20.0), car.accel_limit_ms2(80.0))
        self.assertEqual(car.accel_limit_ms2(200.0), 0.0)

    def test_less_grip_is_slower_in_corners_but_not_on_the_straight(self):
        track = _stadium()
        dry = DEFAULT_CAR_PHYSICS
        wet = dry.with_grip(0.7)
        self.assertAlmostEqual(wet.grip_mu, dry.grip_mu * 0.7)
        _, dry_ceiling = speed_ceiling(track, dry)
        _, wet_ceiling = speed_ceiling(track, wet)
        self.assertLess(min(wet_ceiling), min(dry_ceiling))
        self.assertEqual(max(wet_ceiling), max(dry_ceiling))
        self.assertGreater(
            lap_time_ms(steady_lap(track, wet)), lap_time_ms(steady_lap(track, dry))
        )

    def test_rejects_invalid_envelopes(self):
        with self.assertRaises(ValueError):
            CarPhysics(grip_mu=0.0)
        with self.assertRaises(ValueError):
            CarPhysics(traction_share=1.5)
        with self.assertRaises(ValueError):
            DEFAULT_CAR_PHYSICS.with_grip(-1.0)


class PhysicsForTest(unittest.TestCase):
    def test_neutral_driver_keeps_the_reference_car(self):
        self.assertEqual(physics_for(None), DEFAULT_CAR_PHYSICS)
        self.assertEqual(physics_for(_attributes()), DEFAULT_CAR_PHYSICS)

    def test_attributes_keep_their_meaning(self):
        track = _stadium()
        neutral = lap_time_ms(steady_lap(track, physics_for(_attributes())))
        quick = physics_for(_attributes(pace_offset_pct=-0.5))
        calm = physics_for(_attributes(composure=1.2))
        bold = physics_for(_attributes(aggression=1.4))
        self.assertLess(lap_time_ms(steady_lap(track, quick)), neutral)
        self.assertGreater(calm.corner_grip_use, 1.0)
        self.assertGreater(bold.brake_grip_use, 1.0)
        self.assertEqual(bold.corner_grip_use, 1.0)


class CalibrationTest(unittest.TestCase):
    def test_fit_recovers_known_parameters(self):
        tracks = _fixture_tracks()
        truth = replace(DEFAULT_CAR_PHYSICS, grip_mu=1.5, downforce_cla_m2=4.0)
        chosen = {cid: tracks[cid][0] for cid in (MONACO, "circuit:14", "circuit:13")}
        synthetic = {
            cid: (geometry, lap_time_ms(steady_lap(geometry, truth)))
            for cid, geometry in chosen.items()
        }
        fit = fit_car_physics(
            synthetic,
            coarse_mu=(1.3, 1.5, 1.7),
            coarse_cla_m2=(3.0, 4.0, 5.0),
            fine_mu_step=0.1,
            fine_cla_step=0.5,
        )
        self.assertAlmostEqual(fit.physics.grip_mu, 1.5)
        self.assertAlmostEqual(fit.physics.downforce_cla_m2, 4.0)
        self.assertLess(fit.rms_log_error, 1e-9)

    def test_reference_car_reproduces_historical_laps(self):
        fit = evaluate_car_physics(_fixture_tracks(), DEFAULT_CAR_PHYSICS)
        self.assertLess(fit.rms_log_error, 0.06)
        self.assertAlmostEqual(fit.median_ratio, 1.0, delta=0.03)
        monaco = next(c for c in fit.circuits if c.circuit_id == MONACO)
        self.assertAlmostEqual(monaco.ratio, 1.0, delta=0.10)


class CarPhysicsArtifactTest(unittest.TestCase):
    def test_domain_default_mirrors_the_versioned_artifact(self):
        self.assertEqual(read_car_physics(CAR_PHYSICS_ARTIFACT), DEFAULT_CAR_PHYSICS)
        payload = json.loads(CAR_PHYSICS_ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(payload["origin"], "estimated")

    def test_roundtrip_and_strict_fields(self):
        fit = evaluate_car_physics(
            {MONACO: _fixture_tracks()[MONACO]}, DEFAULT_CAR_PHYSICS
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "car.json"
            write_car_physics(
                path, fit, parameter_version="t", rationale="r", sources={"s": "x"}
            )
            self.assertEqual(read_car_physics(path), DEFAULT_CAR_PHYSICS)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["typo"] = 1
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(CarPhysicsParametersError):
                read_car_physics(path)


if __name__ == "__main__":
    unittest.main()
