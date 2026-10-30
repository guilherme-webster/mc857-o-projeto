"""Leva o plano montado nas telas de configuracao ate o backend, sem Arcade.

O ``SimulationPlan`` e dado de apresentacao (rotulos em portugues, clima por
volta, regras do torneio). Este modulo o traduz para o contrato de
``POST /catalog/grid/run``, garante que exista um grid e roda cada etapa em
ordem. Nao ha threads aqui: a ``ParametersView`` chama ``launch_plan`` fora do
laco do Arcade e recebe o progresso por callback.

Politica de grid desta etapa (a tela de grid e pilotos ainda nao existe):

- se o backend ja tem um grid atual, ele e reutilizado, de modo que um grid
  montado ou editado por outra via e respeitado;
- se nao ha grid (404) ou ele esta num formato antigo (409), cria-se um grid
  aleatorio de ``DEFAULT_GRID_SIZE`` pilotos, com semente escolhida pelo
  backend e registrada no resultado.

Opcoes da tela que o motor ainda nao suporta (intervalo de voltas da sessao,
largada lancada) nao sao descartadas em silencio: viram avisos no resultado.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from frontend.arcade import track_client
from frontend.arcade.configuration_state import (
    WEATHER_MODE_OPTIONS,
    PlannedRace,
    SimulationPlan,
    TournamentRules,
)

DEFAULT_GRID_SIZE = 20

# Rotulo da tela -> ``RainLevel`` do dominio (``domain/weather.py``).
WEATHER_TO_RAIN = {
    "Seco": "dry",
    "Chuva leve": "light_rain",
    "Chuva intensa": "heavy_rain",
}
_ALL_DRY = WEATHER_MODE_OPTIONS[1]


class RaceClient(Protocol):
    """Operacoes do backend usadas aqui; ``track_client`` as implementa."""

    def fetch_current_grid(self) -> dict | None: ...

    def build_grid(self, size: int) -> dict: ...

    def run_grid(self, setup: dict) -> dict: ...

    def fetch_track(self, circuit_id: str) -> dict: ...


class GridOutdatedError(Exception):
    """O grid salvo no backend precisa ser montado de novo (HTTP 409)."""


@dataclass(frozen=True, slots=True)
class LaunchedRace:
    """Uma etapa simulada, com a geometria necessaria para a TrackView."""

    planned: PlannedRace
    race: dict
    track: dict


@dataclass(frozen=True, slots=True)
class LaunchOutcome:
    races: tuple[LaunchedRace, ...]
    grid_note: str
    warnings: tuple[str, ...]
    rules: TournamentRules = TournamentRules()


def run_setup(
    planned: PlannedRace,
    rules: TournamentRules,
    *,
    tournament_seed: int | None = None,
    stage_index: int = 0,
) -> dict:
    """``setup`` do ``POST /catalog/grid/run`` para uma etapa.

    O clima vai como faixas contiguas, inclusive as secas, para que o
    resultado ecoe exatamente o que foi pedido. Com a regra "Seco em todas" a
    etapa inteira e seca, independentemente do clima configurado nela.
    """

    configuration = planned.configuration
    if rules.weather_mode == _ALL_DRY:
        weather = [
            {"from_lap": 1, "to_lap": configuration.laps, "rain": "dry"},
        ]
    else:
        weather = [
            {
                "from_lap": item.start_lap,
                "to_lap": item.end_lap,
                "rain": WEATHER_TO_RAIN[item.weather],
            }
            for item in configuration.weather_schedule.ranges()
        ]
    setup = {
        "total_laps": configuration.laps,
        "track_id": planned.circuit_id,
        "weather": weather,
    }
    if tournament_seed is not None:
        setup["tournament_seed"] = tournament_seed
        setup["stage_index"] = stage_index
    return setup


def unsupported_options(planned: PlannedRace) -> tuple[str, ...]:
    """Avisos para opcoes da etapa que o motor ainda ignora."""

    session = planned.session
    if session is None:
        return ()
    warnings = []
    laps = planned.configuration.laps
    if (session.first_lap, session.last_lap) != (1, laps):
        warnings.append(
            f"{planned.name}: intervalo de voltas {session.first_lap}-"
            f"{session.last_lap} ainda não é suportado; simulando 1-{laps}."
        )
    if session.start_mode != "Parada":
        warnings.append(
            f"{planned.name}: largada {session.start_mode.lower()} ainda não é "
            "suportada; simulando largada parada."
        )
    return tuple(warnings)


def launch_plan(
    plan: SimulationPlan,
    client: RaceClient,
    progress: Callable[[str], None] = lambda message: None,
) -> LaunchOutcome:
    """Garanta um grid e rode as etapas na ordem do plano.

    Erros do backend propagam para quem chamou, com a mensagem original; as
    etapas ja rodadas continuam salvas no backend.
    """

    progress("Conferindo o grid no backend…")
    grid_note = _ensure_grid(client)

    total = len(plan.races)
    launched = []
    warnings: list[str] = []
    for stage_index, planned in enumerate(plan.races):
        warnings.extend(unsupported_options(planned))
        progress(f"Simulando etapa {stage_index + 1}/{total}: {planned.name}…")
        race = client.run_grid(
            run_setup(
                planned,
                plan.rules,
                tournament_seed=plan.tournament_seed,
                stage_index=stage_index,
            )
        )
        track = client.fetch_track(planned.circuit_id)
        launched.append(LaunchedRace(planned, race, track))
    return LaunchOutcome(tuple(launched), grid_note, tuple(warnings), plan.rules)


def _ensure_grid(client: RaceClient) -> str:
    try:
        grid = client.fetch_current_grid()
    except GridOutdatedError:
        grid = None
        reason = "grid salvo em formato antigo"
    else:
        reason = "nenhum grid no backend"
    if grid is not None:
        return f"grid atual do backend ({grid['size']} pilotos, semente {grid['seed']})"
    created = client.build_grid(DEFAULT_GRID_SIZE)
    return (
        f"{reason}: grid aleatório criado ({created['size']} pilotos, "
        f"semente {created['seed']})"
    )


class HttpRaceClient:
    """``RaceClient`` sobre ``track_client``, o adaptador HTTP do frontend."""

    def fetch_current_grid(self) -> dict | None:
        try:
            return track_client.fetch_current_grid()
        except track_client.BackendError as error:
            if error.status == 409:
                raise GridOutdatedError(error.detail) from error
            raise

    def build_grid(self, size: int) -> dict:
        return track_client.build_grid(size)

    def run_grid(self, setup: dict) -> dict:
        return track_client.run_grid(setup)

    def fetch_track(self, circuit_id: str) -> dict:
        return track_client.fetch_track(circuit_id)
