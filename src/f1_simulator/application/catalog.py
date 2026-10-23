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


@dataclass(frozen=True, slots=True)
class RaceEntry:
    race_id: str
    name: str
    season: int
    round_number: int
    circuit_id: str
    race_date: str
    start_time_utc: str | None


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


def list_races(repository: HistoryRepository) -> tuple[RaceEntry, ...]:
    races = [
        RaceEntry(
            race_id=record["race_id"],
            name=record["name"],
            season=record["season"],
            round_number=record["round_number"],
            circuit_id=record["circuit_id"],
            race_date=record["race_date"],
            start_time_utc=record["start_time_utc"],
        )
        for record in repository.records("races")
    ]
    races.sort(key=lambda race: (race.season, race.round_number))
    return tuple(races)


def starting_grid_pair_ids(
    repository: HistoryRepository, race_id: str
) -> tuple[str, ...]:
    """Pares ``piloto@equipe`` na ordem de largada de uma corrida historica.

    O formato do par e o de ``build_grid._pair_id``, para que o resultado
    alimente o modo manual sem traducao. Particularidades do Trotman:

    - ``grid_position`` 0 ou ausente indica largada do pit lane ou piloto sem
      posicao de grid; esses carros vao para o fim, na ordem de chegada
      (``classification_order``), em vez de ganharem a posicao zero;
    - corridas antigas tem o mesmo piloto mais de uma vez (carros
      compartilhados); vale a primeira entrada na ordem de largada, porque o
      grid nao repete piloto.
    """

    results = list(repository.records("race_results", race_id=race_id))
    if not results:
        raise ValueError(f"corrida sem resultados no historico: {race_id}")

    # ``HistoricalRecord`` so oferece indexacao, nao ``.get``.
    def starting_order(record) -> tuple:
        grid = record["grid_position"]
        without_grid = grid is None or grid <= 0
        order = record["classification_order"]
        return (
            without_grid,
            0 if without_grid else grid,
            order if order is not None else 10_000,
            record["driver_id"],
        )

    pair_ids: list[str] = []
    seen: set[str] = set()
    for record in sorted(results, key=starting_order):
        if record["driver_id"] in seen:
            continue
        seen.add(record["driver_id"])
        pair_ids.append(f"{record['driver_id']}@{record['team_id']}")
    return tuple(pair_ids)
