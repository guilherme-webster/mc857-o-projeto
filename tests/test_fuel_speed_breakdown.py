"""Contrato das parcelas de velocidade apresentadas durante a reproducao."""

import unittest

from frontend.arcade.speed_breakdown import SpeedBreakdownReader


class SpeedBreakdownTest(unittest.TestCase):
    def test_fuel_percentage_changes_with_local_corner_ceiling(self):
        # A penalidade do motor e a mesma na volta inteira. A fatia apresentada
        # e relativa a velocidade maxima, logo diminui quando a curva reduz o
        # teto local e volta a crescer na reta, sem qualquer reabastecimento.
        race = {
            "speed_breakdown": {"cars": {"driver": {
                "v_max_kmh": 360,
                "laps": {"1": {"speed_scale": 0.9, "delta_shares": {"fuel": 0.1}}},
            }}},
            "speed_profiles": {"driver": [
                {"distance_m": 0, "speed_ms": 100},
                {"distance_m": 100, "speed_ms": 50},
                {"distance_m": 200, "speed_ms": 100},
            ]},
        }
        reader = SpeedBreakdownReader(race)
        samples = [
            reader.at("driver", distance_m=d, speed_kmh=0, lap=1)
            for d in (0, 100, 199.999)
        ]
        for sample in samples:
            self.assertIsNotNone(sample)
            self.assertAlmostEqual(
                sample.effective + sample.transient + sample.corner
                + sum(sample.penalties.values()), 1.0
            )
        self.assertAlmostEqual(samples[0].penalties["fuel"], 0.1)
        self.assertAlmostEqual(samples[1].penalties["fuel"], 0.05)
        self.assertGreater(samples[2].penalties["fuel"], samples[1].penalties["fuel"])


if __name__ == "__main__":
    unittest.main()
