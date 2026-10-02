from __future__ import annotations

from dataclasses import dataclass

from f1_simulator.application.ports.history import HistoryRepository


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    driver_id: str
    driver_name: str
    driver_code: str | None
    team_id: str
    team_name: str


def _full_name(given: object, family: object) -> str:
    parts = [str(part).strip() for part in (given, family) if part is not None]
    return " ".join(part for part in parts if part)


def list_entries(repository: HistoryRepository) -> tuple[CatalogEntry, ...]:
    drivers = {
        record["driver_id"]: (
            _full_name(record["given_name"], record["family_name"]),
            record["code"],
        )
        for record in repository.records("drivers")
    }
    teams = {record["team_id"]: record["name"] for record in repository.records("teams")}

    pairs = {
        (record["driver_id"], record["team_id"])
        for record in repository.records("race_results")
    }

    entries = [
        CatalogEntry(
            driver_id=driver_id,
            driver_name=drivers[driver_id][0],
            driver_code=drivers[driver_id][1],
            team_id=team_id,
            team_name=teams[team_id],
        )
        for driver_id, team_id in pairs
    ]
    entries.sort(key=lambda entry: (entry.driver_id, entry.team_id))
    return tuple(entries)
