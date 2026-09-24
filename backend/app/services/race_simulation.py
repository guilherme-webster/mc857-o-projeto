from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

from app.config import DEFAULT_RACE_DB, MODEL_PARAMETERS, RACE_JSON
from fastapi import HTTPException, status

#: Semente padrao da simulacao exposta pela API. Mantida fixa para que duas
#: chamadas seguidas produzam o mesmo resultado; o cliente pode variar a semente
#: para explorar desfechos diferentes do mesmo cenario.
DEFAULT_SEED = 20260922

#: Plano de paradas do cenario padrao. Duas paradas e o padrao historico
#: dominante da era calibrada (43% das corridas de 2022-2024).
DEFAULT_STOPS = 2
DEFAULT_COMPOUNDS = ("MEDIUM", "HARD", "MEDIUM", "HARD")


def _total_laps(db_path) -> int:

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT MAX(lap_number) FROM laps").fetchone()
    finally:
        connection.close()
    return int(row[0]) if row and row[0] else 1


def _circuit_id(db_path) -> str | None:
    """Circuito da corrida carregada, usado para escolher os parametros de pista."""

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT circuit_id FROM races LIMIT 1").fetchone()
    finally:
        connection.close()
    return row[0] if row else None


def simulate_current_race(
    *, seed: int = DEFAULT_SEED, stops: int = DEFAULT_STOPS
) -> dict:
    """Execute a corrida carregada com o modelo calibrado e grave o retrato.

    A simulacao consome os parametros versionados de ``data/parameters``. Se o
    arquivo nao existir, a chamada falha com uma mensagem acionavel em vez de
    cair silenciosamente num modelo de ritmo constante: rodar com parametros
    diferentes dos publicados tornaria o resultado nao reproduzivel.
    """

    from app.loaders.loader import load_driver_parameters
    from f1_simulator.adapters.model_parameters_json import read_parameters
    from f1_simulator.domain.race_simulation import Entrant, simulate_detailed_race
    from f1_simulator.domain.random_source import SeededRandomSource
    from f1_simulator.domain.strategy import PlannedStopStrategy

    if not DEFAULT_RACE_DB.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Banco curado ({DEFAULT_RACE_DB.name}) nao encontrado. "
                "Rode POST /simulation/load antes de simular."
            ),
        )

    try:
        parameters = read_parameters(Path(MODEL_PARAMETERS))
    except (FileNotFoundError, KeyError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Parametros do modelo indisponiveis: {error}. "
                "Gere-os com scripts/calibrate_model.py."
            ),
        ) from error

    drivers = load_driver_parameters(DEFAULT_RACE_DB)
    track = parameters.track(_circuit_id(DEFAULT_RACE_DB) or "")
    total_laps = _total_laps(DEFAULT_RACE_DB)

    # Uma unica fonte aleatoria: primeiro escalona as janelas de parada (decisao
    # de cenario, antes da largada), depois conduz a corrida. A ordem fixa e o
    # que torna a semente reproduzivel.
    rng = SeededRandomSource(seed)
    entrants = [
        Entrant(
            driver_id=item.driver_id,
            name=item.name,
            reference_lap_time_ms=float(item.base_lap_time_ms),
            grid_position=item.grid_position if item.grid_position > 0 else 20,
            team_id=item.team_id,
            strategy=PlannedStopStrategy(
                stops,
                DEFAULT_COMPOUNDS,
                offset_laps=round(
                    rng.standard_normal() * parameters.pit_window_spread_laps
                ),
            ),
            starting_compound="MEDIUM",
            reliability_factor=parameters.reliability_factor(item.team_id),
        )
        for item in sorted(drivers, key=lambda d: d.driver_id)
        if item.base_lap_time_ms is not None
    ]

    if not entrants:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Nenhum piloto da corrida carregada tem ritmo de referencia "
                "derivavel das voltas historicas."
            ),
        )

    result = simulate_detailed_race(
        entrants,
        total_laps=total_laps,
        parameters=parameters,
        track=track,
        rng=rng,
    )
    # Proveniencia no proprio retrato: quem ler o JSON sabe com quais
    # parametros, semente e pista ele foi produzido.
    result["seed"] = seed
    result["stops_planned"] = stops
    result["track_name"] = track.name
    result["track_origin"] = track.origin

    _write_json_atomic(RACE_JSON, result)
    return result


def _write_json_atomic(destination, payload: dict) -> None:

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(name, destination)
    except Exception:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise
