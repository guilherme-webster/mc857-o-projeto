"""Contratos do diagnóstico espacial, com amostras artificiais determinísticas."""

import unittest

from f1_simulator.domain.track_space import (
    CarSpaceState,
    FieldSample,
    build_track_space,
)
from scripts.analyze_spatial_contacts import analyze_samples, run_case
from tests.geometry_support import small_geometry


class SpatialContactAnalysisTest(unittest.TestCase):
    def test_samples_measure_persistence_overlap_braking_and_monotonicity(self):
        track = build_track_space(small_geometry())

        def sample(t, a, b, speed):
            return FieldSample(t, (CarSpaceState("a", a, speed_ms=speed),
                                   CarSpaceState("b", b, speed_ms=10)))

        samples = [sample(0, 20, 10, 100), sample(1, 19, 21, 20),
                   sample(2, 18, 22, 20), sample(3, 17, 23, 20)]
        result = analyze_samples(samples, track, 2, 2, 50)
        self.assertEqual(result["persistent_overtake_count"], 1)
        self.assertEqual(result["persistent_overtakes"][0]["ahead"], "b")
        self.assertGreater(result["sat_overlap_pair_samples"], 0)
        self.assertEqual(result["sat_distinct_pairs"], 1)
        self.assertEqual(result["abnormal_braking_samples"], 1)
        self.assertEqual(result["backward_distance_samples"], 3)
        self.assertEqual(result["max_backward_distance_m"], 1)

    def test_seed_repeats_entire_report_except_runtime(self):
        first = run_case("circuit:6", 1, 4, 1, 0.2, 2, 50)
        second = run_case("circuit:6", 1, 4, 1, 0.2, 2, 50)
        first.pop("runtime_s")
        second.pop("runtime_s")
        self.assertEqual(first, second)
        self.assertGreater(first["samples"], 1)


if __name__ == "__main__":
    unittest.main()
