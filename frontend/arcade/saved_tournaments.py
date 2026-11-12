"""Salvar, reabrir e reexecutar torneios, sem Arcade (#109, ADR 0013).

O backend guarda o torneio como JSON (``/tournaments``). Este modulo traduz nos
dois sentidos entre esse registro e os objetos da apresentacao:

- ``save_request``: ``TournamentSession`` -> corpo de ``POST /tournaments``;
- ``reopen``: registro -> ``LaunchOutcome`` com as corridas salvas, sem chamar
  ``/catalog/grid/run``;
- ``rerun``: restaura o grid congelado e reenvia o ``setup`` salvo de cada
  etapa, na ordem, pelo mesmo caminho de uma simulacao nova.

``plan`` e ``rules`` sao a forma da tela (rotulos em portugues): o backend os
guarda sem interpretar, e so este modulo os reconstroi.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Protocol

from frontend.arcade import track_client
from frontend.arcade.configuration_state import (
    ConfigurationFormData,
    PlannedRace,
    SessionConfiguration,
    SimulationPlan,
    TournamentRules,
    WeatherSchedule,
)
from frontend.arcade.race_launcher import (
    LaunchCancelled,
    LaunchedRace,
    LaunchOutcome,
    LaunchProgress,
    run_setup,
)
from frontend.arcade.tournament_session import TournamentSession


class TournamentClient(Protocol):
    """Operacoes do backend usadas aqui; ``track_client`` as implementa."""

    def restore_grid(self, tournament_id: str) -> dict: ...

    def run_grid(
        self, setup: dict, on_lap: Callable[[int, int], None] = lambda lap, total: None
    ) -> dict: ...

    def fetch_track(self, circuit_id: str) -> dict: ...


def save_request(session: TournamentSession, name: str | None = None) -> dict:
    """Corpo de ``POST /tournaments`` para um torneio recem-simulado.

    O ``setup`` de cada etapa e recalculado por ``run_setup`` com a mesma seed
    e o mesmo indice usados no lancamento; como a funcao e pura, ele e
    identico ao corpo que produziu a corrida, e o backend confere isso contra
    o resultado.
    """

    return {
        "name": (name or session.rules.name).strip(),
        "rules": asdict(session.rules),
        "tournament_seed": session.tournament_seed,
        "stages": [
            {
                "name": launched.planned.name,
                "circuit_id": launched.planned.circuit_id,
                "plan": _plan_payload(launched.planned),
                "setup": run_setup(
                    launched.planned,
                    session.rules,
                    tournament_seed=session.tournament_seed,
                    stage_index=index,
                ),
                "race": launched.race,
            }
            for index, launched in enumerate(session.races)
        ],
    }


def reopen(
    record: dict, fetch_track: Callable[[str], dict] = track_client.fetch_track
) -> LaunchOutcome:
    """Torneio salvo pronto para exibir, usando so as corridas guardadas.

    A geometria da pista nao vai no registro (e grande e ja e servida pelo
    backend); ela e buscada por etapa, sem simular nada.
    """

    rules = _rules(record)
    races = tuple(
        LaunchedRace(_planned(stage), stage["race"], fetch_track(stage["circuit_id"]))
        for stage in record["stages"]
    )
    return LaunchOutcome(
        races,
        _note(record, "reaberto sem simular"),
        (),
        rules,
        record.get("tournament_seed"),
    )


def plan_from_record(record: dict) -> SimulationPlan:
    """Plano de exibicao de um torneio salvo, para a tela de carregamento.

    A ``SimulationLoadingView`` desenha o grid, a etapa em foco e o clima a
    partir de um ``SimulationPlan``. Aqui ele e so a descricao do que sera
    reexecutado: quem manda no que vai ao backend e o ``setup`` salvo de cada
    etapa (ver ``rerun``), nunca este plano.
    """

    return SimulationPlan(
        tuple(_planned(stage) for stage in record["stages"]),
        _rules(record),
        record.get("tournament_seed"),
    )


def rerun(
    record: dict,
    client: TournamentClient,
    progress: Callable[[str], None] = lambda message: None,
    *,
    stage_progress: Callable[[LaunchProgress], None] = lambda item: None,
    cancelled: Callable[[], bool] = lambda: False,
) -> LaunchOutcome:
    """Restaure o grid congelado e rode cada etapa de novo com o setup salvo.

    O grid e restaurado uma vez, antes da primeira etapa: o ``setup`` nao
    carrega o grid, entao rodar sem restaurar usaria o grid atual do backend.

    ``progress`` recebe frases de status; ``stage_progress`` recebe o mesmo
    estado estruturado (etapa e volta) que ``launch_plan`` publica, para a tela
    de carregamento. ``cancelled`` e consultado antes de cada etapa: se
    disparar, levanta ``LaunchCancelled``. A etapa em curso nao e interrompida
    (o backend ja a recebeu) e o grid ja restaurado continua sendo o atual.
    """

    restoring = "Restaurando o grid salvo…"
    progress(restoring)
    stage_progress(LaunchProgress(restoring))
    client.restore_grid(record["id"])
    rules = _rules(record)
    total = len(record["stages"])
    races = []
    for index, stage in enumerate(record["stages"]):
        if cancelled():
            raise LaunchCancelled()
        planned = _planned(stage)
        laps = planned.configuration.laps
        message = f"Reexecutando etapa {index + 1}/{total}: {stage['name']}…"
        progress(message)
        stage_progress(
            LaunchProgress(
                message,
                stage_index=index + 1,
                total_stages=total,
                stage_name=stage["name"],
                laps=laps,
            )
        )

        def on_lap(
            lap: int, laps_total: int, _index: int = index, _stage: dict = stage
        ) -> None:
            stage_progress(
                LaunchProgress(
                    f"Reexecutando etapa {_index + 1}/{total}: {_stage['name']} — "
                    f"volta {lap}/{laps_total}",
                    stage_index=_index + 1,
                    total_stages=total,
                    stage_name=_stage["name"],
                    lap=lap,
                    laps=laps_total,
                )
            )

        # O setup salvo e reenviado intacto: e ele (com a semente do torneio e
        # o indice da etapa) que faz a reexecucao reproduzir a corrida salva.
        race = client.run_grid(stage["setup"], on_lap)
        races.append(LaunchedRace(planned, race, client.fetch_track(stage["circuit_id"])))
    return LaunchOutcome(
        tuple(races),
        _note(record, "reexecutado com o grid salvo"),
        (),
        rules,
        record.get("tournament_seed"),
    )


def rerun_runner(
    record: dict, client: TournamentClient
) -> Callable[[SimulationPlan, Callable[[LaunchProgress], None], Callable[[], bool]], LaunchOutcome]:
    """Runner no formato da ``SimulationLoadingView`` para reexecutar ``record``.

    O ``plan`` recebido e ignorado de proposito: a tela o usa so para desenhar;
    o que roda sao os ``setup`` do registro.
    """

    def runner(plan, progress, cancelled):
        del plan
        return rerun(record, client, stage_progress=progress, cancelled=cancelled)

    return runner


def session_from_outcome(outcome: LaunchOutcome) -> TournamentSession:
    """``TournamentSession`` de um torneio reaberto ou reexecutado."""

    notices = (outcome.grid_note, *outcome.warnings)
    return TournamentSession(
        outcome.races, outcome.rules, notices, outcome.tournament_seed
    )


class HttpTournamentClient:
    """``TournamentClient`` sobre ``track_client``, o adaptador HTTP do frontend."""

    def restore_grid(self, tournament_id: str) -> dict:
        return track_client.restore_tournament_grid(tournament_id)

    def run_grid(
        self, setup: dict, on_lap: Callable[[int, int], None] = lambda lap, total: None
    ) -> dict:
        # SSE por volta; cai no POST sincrono se o backend nao tem a rota (404).
        return track_client.run_grid_stream(setup, on_progress=on_lap)

    def fetch_track(self, circuit_id: str) -> dict:
        return track_client.fetch_track(circuit_id)


def _plan_payload(planned: PlannedRace) -> dict:
    configuration = planned.configuration
    session = planned.session
    return {
        "preset": configuration.preset,
        "laps": configuration.laps,
        "weather_by_lap": list(configuration.weather_schedule.by_lap),
        "session": None if session is None else asdict(session),
    }


def _planned(stage: dict) -> PlannedRace:
    plan = stage["plan"]
    configuration = ConfigurationFormData(
        preset=plan["preset"],
        laps=plan["laps"],
        weather_schedule=WeatherSchedule(tuple(plan["weather_by_lap"])),
    )
    session = plan.get("session")
    return PlannedRace(
        stage["circuit_id"],
        stage["name"],
        configuration,
        None if session is None else SessionConfiguration(**session),
    )


def _rules(record: dict) -> TournamentRules:
    return TournamentRules(**record["rules"])


def _note(record: dict, action: str) -> str:
    seed = record.get("tournament_seed")
    seed_text = "sem seed de torneio" if seed is None else f"seed {seed}"
    return (
        f"Torneio salvo “{record['name']}” {action} "
        f"(grid congelado, semente do grid {record['grid']['seed']}, {seed_text})"
    )
