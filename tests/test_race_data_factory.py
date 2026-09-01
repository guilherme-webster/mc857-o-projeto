from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date, time

from f1_simulator.application.race_data_dto import NormalizedRaceData
from f1_simulator.domain.race_data import (
    Circuit,
    Driver,
    Lap,
    PitStop,
    Race,
    RaceData,
    RaceEntry,
    SourceId,
    Team,
)
from f1_simulator.factories.race_data_factory import (
    RaceDataFactory,
    RaceDataValidationError,
)


def normalized_race_data() -> NormalizedRaceData:
    return NormalizedRaceData(
        source_name=" example/source ",
        source_version=1,
        source_sha256="A" * 64,
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
        pit_stops=(
            {
                "driver_external_id": "830",
                "stop_number": 1,
                "lap_number": 26,
                "duration_ms": 24_381,
            },
        ),
    )


class RaceDataFactoryTest(unittest.TestCase):
    def test_builds_domain_objects_from_normalized_data(self) -> None:
        result = RaceDataFactory.create(normalized_race_data())

        # Comparing the full aggregate protects every normalized field and its
        # unit, not only the handful of identifiers used by downstream tests.
        self.assertEqual(
            result,
            RaceData(
                source_name="example/source",
                source_version=1,
                source_sha256="a" * 64,
                circuit=Circuit(
                    circuit_id="circuit:18",
                    name="Example Circuit",
                    location="Example City",
                    country="Brazil",
                    latitude_deg=-23.7,
                    longitude_deg=-46.7,
                    altitude_m=None,
                ),
                race=Race(
                    race_id="race:1141",
                    circuit_id="circuit:18",
                    season=2024,
                    round_number=21,
                    name="Example Grand Prix",
                    race_date=date(2024, 11, 3),
                    start_time_utc=time(17, 0),
                ),
                drivers=(
                    Driver(
                        driver_id="driver:830",
                        code="VER",
                        given_name="Max",
                        family_name="Verstappen",
                    ),
                ),
                teams=(Team(team_id="team:9", name="Red Bull"),),
                entries=(
                    RaceEntry(
                        race_id="race:1141",
                        driver_id="driver:830",
                        team_id="team:9",
                        grid_position=17,
                        finish_position=1,
                        classification_order=1,
                        laps_completed=69,
                        elapsed_time_ms=7_614_430,
                        status="Finished",
                    ),
                ),
                laps=(
                    Lap(
                        race_id="race:1141",
                        driver_id="driver:830",
                        lap_number=1,
                        lap_time_ms=99_161,
                        position=11,
                    ),
                ),
                pit_stops=(
                    PitStop(
                        race_id="race:1141",
                        driver_id="driver:830",
                        stop_number=1,
                        lap_number=26,
                        duration_ms=24_381,
                    ),
                ),
                source_ids=(
                    SourceId(
                        entity_type="circuit",
                        source_name="example/source",
                        external_id="18",
                        canonical_id="circuit:18",
                    ),
                    SourceId(
                        entity_type="race",
                        source_name="example/source",
                        external_id="1141",
                        canonical_id="race:1141",
                    ),
                    SourceId(
                        entity_type="driver",
                        source_name="example/source",
                        external_id="830",
                        canonical_id="driver:830",
                    ),
                    SourceId(
                        entity_type="team",
                        source_name="example/source",
                        external_id="9",
                        canonical_id="team:9",
                    ),
                ),
            ),
        )

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

    def test_rejects_invalid_source_metadata(self) -> None:
        invalid_cases = (
            ("source_name", "", "source_name must be non-empty text"),
            ("source_version", 0, "source_version must be positive"),
            ("source_sha256", "not-a-sha256", "source_sha256"),
        )

        for field, value, expected_message in invalid_cases:
            with self.subTest(field=field):
                normalized = replace(normalized_race_data(), **{field: value})
                with self.assertRaisesRegex(RaceDataValidationError, expected_message):
                    RaceDataFactory.create(normalized)

    def test_rejects_values_outside_domain_ranges(self) -> None:
        invalid_cases = (
            ("circuit", "latitude_deg", 91, "latitude_deg"),
            ("circuit", "longitude_deg", -181, "longitude_deg"),
            ("entries", "grid_position", -1, "grid_position"),
            ("laps", "lap_time_ms", 0, "lap_time_ms"),
            ("pit_stops", "duration_ms", 0, "duration_ms"),
        )

        for section, field, value, expected_message in invalid_cases:
            with self.subTest(section=section, field=field):
                normalized = normalized_race_data()
                rows = getattr(normalized, section)
                row = rows if section == "circuit" else rows[0]
                row[field] = value
                with self.assertRaisesRegex(RaceDataValidationError, expected_message):
                    RaceDataFactory.create(normalized)

    def test_rejects_an_unrepresented_team(self) -> None:
        normalized = normalized_race_data()
        normalized = replace(
            normalized,
            teams=normalized.teams + ({"external_id": "131", "name": "Unused Team"},),
        )

        with self.assertRaisesRegex(RaceDataValidationError, "teams and race entries"):
            RaceDataFactory.create(normalized)

    def test_rejects_race_without_entries(self) -> None:
        normalized = replace(
            normalized_race_data(),
            drivers=(),
            teams=(),
            entries=(),
            laps=(),
            pit_stops=(),
        )

        with self.assertRaisesRegex(RaceDataValidationError, "at least one entry"):
            RaceDataFactory.create(normalized)


if __name__ == "__main__":
    unittest.main()
