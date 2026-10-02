from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from f1_simulator.application.catalog import CatalogEntry
from f1_simulator.domain.random_source import RandomSource, uniform_index

SelectionMode = Literal["manual", "random"]


@dataclass(frozen=True, slots=True)
class GridEntry:
    driver_id: str
    driver_name: str
    team_id: str
    team_name: str


def _pair_id(driver_id: str, team_id: str) -> str:
    return f"{driver_id}@{team_id}"


def build_grid(
    size: int,
    pool: Sequence[CatalogEntry],
    *,
    mode: SelectionMode,
    manual_pair_ids: Sequence[str] = (),
    rng: RandomSource | None = None,
) -> tuple[GridEntry, ...]:
    if type(size) is not int or size <= 0:
        raise ValueError("size deve ser um inteiro positivo")
    if mode not in ("manual", "random"):
        raise ValueError("mode deve ser 'manual' ou 'random'")
    if mode == "random" and rng is None:
        raise ValueError("modo aleatorio exige um rng injetado")
    if rng is not None and mode != "random":
        raise ValueError(
            "rng informado sem modo aleatorio: o sorteio seria ignorado em silencio"
        )

    index = {_pair_id(entry.driver_id, entry.team_id): entry for entry in pool}
    if len(index) != len(pool):
        raise ValueError("pool contem pares duplicados")

    chosen = _select(size, index, mode, manual_pair_ids, rng)

    drivers_seen: set[str] = set()
    for entry in chosen:
        if entry.driver_id in drivers_seen:
            raise ValueError(f"piloto repetido no grid: {entry.driver_id}")
        drivers_seen.add(entry.driver_id)

    return tuple(
        GridEntry(
            driver_id=entry.driver_id,
            driver_name=entry.driver_name,
            team_id=entry.team_id,
            team_name=entry.team_name,
        )
        for entry in chosen
    )


def _select(
    size: int,
    index: dict[str, CatalogEntry],
    mode: SelectionMode,
    manual_pair_ids: Sequence[str],
    rng: RandomSource | None,
) -> list[CatalogEntry]:
    if mode == "manual":
        chosen_ids = tuple(manual_pair_ids)
        if len(chosen_ids) != size:
            raise ValueError(
                f"manual exige exatamente {size} pares; recebi {len(chosen_ids)}"
            )
        if len(set(chosen_ids)) != len(chosen_ids):
            raise ValueError("pares nao podem repetir no grid")
        unknown = [pair_id for pair_id in chosen_ids if pair_id not in index]
        if unknown:
            raise ValueError(f"par fora do catalogo: {unknown}")
        return [index[pair_id] for pair_id in chosen_ids]

    # Sem reposicao por piloto: sorteia pares e descarta quem repetir piloto.
    distinct_drivers = len({entry.driver_id for entry in index.values()})
    if size > distinct_drivers:
        raise ValueError(
            f"nao ha pilotos suficientes para {size} sem repeticao "
            f"(catalogo tem {distinct_drivers})"
        )
    assert rng is not None
    source = rng.spawn("grid:pairs")
    remaining = sorted(index)
    chosen: list[CatalogEntry] = []
    drivers_seen: set[str] = set()
    attempt = 0
    while len(chosen) < size:
        if not remaining:
            raise ValueError("pares insuficientes para completar o grid sem repetir piloto")
        picked = uniform_index(source, f"grid:pair:{attempt}", len(remaining))
        entry = index[remaining.pop(picked)]
        attempt += 1
        if entry.driver_id in drivers_seen:
            continue
        drivers_seen.add(entry.driver_id)
        chosen.append(entry)
    return chosen
