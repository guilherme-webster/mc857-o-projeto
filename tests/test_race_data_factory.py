from __future__ import annotations

import unittest
from datetime import date, time

from f1_simulator.application.race_data_dto import NormalizedRaceData
from f1_simulator.factories.race_data_factory import (
    RaceDataFactory,
    RaceDataValidationError,
)


def normalized_race_data() -> NormalizedRaceData:
    return NormalizedRaceData(
        source_name="example/source",
        source_version=1,
        source_sha256=None,
        circuit={
            "external_id": "18",
            "name": "Example Circuit",
            "location": "Example City",
            "country": "Brazil",
            "latitude_deg": -23.7,
            "longitude_deg": -46.7,
            "altitude_m": None,
        },
        race={
            "external_id": "1141",
            "circuit_external_id": "18",
            "season": 2024,
            "round_number": 21,
            "name": "Example Grand Prix",
            "race_date": date(2024, 11, 3),
            "start_time_utc": time(17, 0),
        },
        drivers=(
            {
                "external_id": "830",
                "code": "VER",
                "given_name": "Max",
                "family_name": "Verstappen",
            },
        ),
        teams=({"external_id": "9", "name": "Red Bull"},),
        entries=(
            {
                "driver_external_id": "830",
                "team_external_id": "9",
                "grid_position": 17,
                "finish_position": 1,
                "classification_order": 1,
                "laps_completed": 69,
                "elapsed_time_ms": 7_614_430,
                "status": "Finished",
            },
        ),
        laps=(
            {
                "driver_external_id": "830",
                "lap_number": 1,
                "lap_time_ms": 99_161,
                "position": 11,
            },
        ),
        pit_stops=(),
    )


class RaceDataFactoryTest(unittest.TestCase):
    def test_builds_domain_objects_from_normalized_data(self) -> None:
        result = RaceDataFactory.create(normalized_race_data())

        self.assertEqual(result.race.race_id, "race:1141")
        self.assertEqual(result.circuit.circuit_id, "circuit:18")
        self.assertEqual(result.entries[0].driver_id, "driver:830")
        self.assertEqual(result.laps[0].lap_time_ms, 99_161)
        self.assertIsNone(result.circuit.altitude_m)

    def test_rejects_race_that_references_another_circuit(self) -> None:
        normalized = normalized_race_data()
        normalized.race["circuit_external_id"] = "99"

        with self.assertRaisesRegex(RaceDataValidationError, "different circuit"):
            RaceDataFactory.create(normalized)

    def test_rejects_orphan_driver_reference(self) -> None:
        normalized = normalized_race_data()
        normalized.entries[0]["driver_external_id"] = "999"

        with self.assertRaisesRegex(RaceDataValidationError, "orphan reference"):
            RaceDataFactory.create(normalized)


if __name__ == "__main__":
    unittest.main()
