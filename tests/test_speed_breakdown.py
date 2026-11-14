"""A parcela exibida depende do trecho e das demais condicoes da corrida."""

import unittest

from frontend.arcade.speed_breakdown import SpeedBreakdownReader


class SpeedBreakdownTyreTest(unittest.TestCase):
    def test_tyre_percentage_changes_with_corner_at_constant_wear(self):
        # Mesma volta e parcela de pneu: so muda o teto fisico do trecho.
        race = {
            "speed_breakdown": {"cars": {"a": {
                "v_max_kmh": 360,
                "laps": {"1": {"speed_scale": 0.9, "delta_shares": {
                    "tyre": 0.1, "fuel": 0, "weather": 0, "race_control": 0,
                }}},
            }}},
            "speed_profiles": {"a": [
                {"distance_m": 0, "speed_ms": 100},
                {"distance_m": 50, "speed_ms": 50},
                {"distance_m": 100, "speed_ms": 100},
            ]},
        }
        reader = SpeedBreakdownReader(race)
        straight = reader.at("a", distance_m=0, speed_kmh=324, lap=1)
        corner = reader.at("a", distance_m=50, speed_kmh=162, lap=1)
        self.assertAlmostEqual(straight.penalties["tyre"], 0.10)
        self.assertAlmostEqual(corner.penalties["tyre"], 0.05)
        for result in (straight, corner):
            self.assertAlmostEqual(
                result.effective + result.transient + result.corner
                + sum(result.penalties.values()), 1.0,
            )

    def test_same_tyre_time_has_different_speed_share_with_other_penalties(self):
        # O inverso do tempo e nao linear: mais tempo de clima/controle muda
        # a conversao do mesmo custo de pneu para fracao da velocidade.
        laps = {}
        for lap, weather in ((1, 0), (2, 10000)):
            base, tyre = 100000, 1000
            scale = base / (base + tyre + weather)
            unit = (1 - scale) / (tyre + weather)
            laps[str(lap)] = {"speed_scale": scale, "delta_shares": {
                "tyre": tyre * unit, "fuel": 0,
                "weather": weather * unit, "race_control": 0,
            }}
        reader = SpeedBreakdownReader({"speed_breakdown": {"cars": {
            "a": {"v_max_kmh": 360, "laps": laps},
        }}})
        dry = reader.at("a", distance_m=0, speed_kmh=300, lap=1)
        wet = reader.at("a", distance_m=0, speed_kmh=300, lap=2)
        self.assertGreater(dry.penalties["tyre"], wet.penalties["tyre"])
        self.assertAlmostEqual(dry.penalties["tyre"], 1000 / 101000)
        self.assertAlmostEqual(wet.penalties["tyre"], 1000 / 111000)

    def test_lap_pace_noise_is_its_own_slice(self):
        # Issue #139: o desvio de ritmo da volta (consistency_factor) entra na
        # soma; se o leitor o ignorasse, a parcela seria atribuida ao pneu.
        scale = 0.9
        race = {"speed_breakdown": {"cars": {"a": {
            "v_max_kmh": 360,
            "laps": {"1": {"speed_scale": scale, "delta_shares": {
                "tyre": 0.06, "fuel": 0, "weather": 0, "noise": 0.04,
                "race_control": 0,
            }}},
        }}}}
        result = SpeedBreakdownReader(race).at(
            "a", distance_m=0, speed_kmh=324, lap=1
        )
        self.assertAlmostEqual(result.penalties["noise"], 0.04)
        self.assertAlmostEqual(result.penalties["tyre"], 0.06)
        self.assertAlmostEqual(
            result.effective + result.transient + result.corner
            + sum(result.penalties.values()), 1.0,
        )

    def test_race_without_noise_share_reads_it_as_zero(self):
        # Corridas salvas antes do ruido por volta nao trazem a chave.
        race = {"speed_breakdown": {"cars": {"a": {
            "v_max_kmh": 360,
            "laps": {"1": {"speed_scale": 0.9, "delta_shares": {"tyre": 0.1}}},
        }}}}
        result = SpeedBreakdownReader(race).at(
            "a", distance_m=0, speed_kmh=324, lap=1
        )
        self.assertEqual(result.penalties["noise"], 0.0)
        self.assertAlmostEqual(result.penalties["tyre"], 0.1)


if __name__ == "__main__":
    unittest.main()
