from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Literal

from f1_simulator.application.build_grid import GridEntry
from f1_simulator.domain.attribute_effects import detailed_degradation_factor
from f1_simulator.domain.driver_attributes import DriverAttributes
from f1_simulator.domain.model_parameters import ModelParameters
from f1_simulator.domain.race_control import (
    HEURISTIC_RACE_CONTROL,
    RaceControlParameters,
)
from f1_simulator.domain.race_simulation import (
    ASSUMED_LAP_VARIABILITY,
    NOMINAL_LAP_TIME_MS,
    Competitor,
    Entrant,
    simulate_detailed_race,
    simulate_race,
)
from f1_simulator.domain.random_source import RandomSource, uniform_index
from f1_simulator.domain.strategy import (
    DEFAULT_HEURISTIC_PIT_PARAMETERS,
    HeuristicPitStrategy,
)


_REFERENCE_PACE_RATIONALE = (
    "Hipotese de composicao, nao calibrada: 17 s/km representa somente a "
    "ordem de grandeza do ritmo de corrida da Formula 1 moderna e converte o "
    "comprimento da geometria em uma volta de referencia plausivel."
)


@dataclass(frozen=True, slots=True)
class ReferencePaceParameters:
    """Hipotese versionada que converte comprimento de pista em tempo de volta.

    O valor nao foi estimado do historico e, por isso, carrega origem
    ``assumed``. Mantê-lo em um objeto de parametros impede que o coeficiente
    heuristico fique escondido na montagem dos ``Entrant`` e permite expor a
    mesma proveniencia na resposta do caso de uso.
    """

    pace_ms_per_km: float
    origin: Literal["assumed"] = "assumed"
    parameter_version: str = "assumed-grid-reference-pace-v1"
    rationale: str = _REFERENCE_PACE_RATIONALE

    def __post_init__(self) -> None:
        if (
            isinstance(self.pace_ms_per_km, bool)
            or not isinstance(self.pace_ms_per_km, (int, float))
            or not isfinite(self.pace_ms_per_km)
            or self.pace_ms_per_km <= 0
        ):
            raise ValueError("pace_ms_per_km deve ser positivo e finito")
        if self.origin != "assumed":
            raise ValueError("origin deve ser 'assumed'")
        for name in ("parameter_version", "rationale"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} deve ser texto nao vazio")


ASSUMED_REFERENCE_PACE = ReferencePaceParameters(pace_ms_per_km=17_000.0)
"""Parametros assumidos da referencia de ritmo usada pelo grid detalhado."""

ASSUMED_REFERENCE_PACE_MS_PER_KM = ASSUMED_REFERENCE_PACE.pace_ms_per_km
"""Ritmo assumido de 17 s/km, apenas como ordem de grandeza da F1 moderna."""


@dataclass(frozen=True, slots=True)
class RaceSetup:
    total_laps: int
    track_id: str | None = None
    weather: str | None = None

    def __post_init__(self) -> None:
        if type(self.total_laps) is not int or self.total_laps <= 0:
            raise ValueError("total_laps must be a positive integer")


def run_grid_simulation(
    grid: Sequence[GridEntry],
    attributes: dict[str, DriverAttributes],
    setup: RaceSetup,
    rng: RandomSource | None = None,
) -> dict:
    competitors = tuple(
        Competitor(
            driver_id=entry.driver_id,
            name=entry.driver_name,
            attributes=attributes[entry.driver_id],
        )
        for entry in grid
    )
    result = simulate_race(
        competitors,
        setup.total_laps,
        variability=ASSUMED_LAP_VARIABILITY if rng is not None else None,
        rng=rng,
    )
    result["setup"] = {
        "total_laps": setup.total_laps,
        "track_id": setup.track_id,
        "weather": setup.weather,
    }
    return result


def run_detailed_grid_simulation(
    grid: Sequence[GridEntry],
    attributes: dict[str, DriverAttributes],
    setup: RaceSetup,
    *,
    parameters: ModelParameters,
    lap_length_m: float | None,
    rng: RandomSource,
    reference_pace_ms_per_km: float = ASSUMED_REFERENCE_PACE_MS_PER_KM,
    race_control: RaceControlParameters | None = HEURISTIC_RACE_CONTROL,
    dispute_model: Literal["legacy", "pressure"] = "pressure",
) -> dict:
    """Execute o grid no motor detalhado sem conhecer arquivo, HTTP ou banco.

    A ordem recebida em ``grid`` e a ordem de largada, começando em um. Quando
    ``setup.track_id`` existe em ``parameters.tracks``, seus parametros
    calibrados sao usados; qualquer ID ausente (inclusive ``None``) usa
    ``parameters.fallback_track``, cuja origem ``assumed`` torna a substituicao
    auditavel em ``track_reference``.

    ``lap_length_m`` converte a hipotese em ms/km para uma volta de referencia.
    Sem pista, o caso de uso reutiliza ``NOMINAL_LAP_TIME_MS`` do nucleo simples
    e declara o fallback na resposta, em vez de transformar ausencia em zero.

    Cada piloto recebe um fluxo derivado exclusivamente para o offset inteiro
    da estrategia. O motor recebe outro fluxo, ``detailed-race``; assim mudar a
    quantidade de sorteios da estrategia nao desloca ruido, incidentes ou
    controle de prova. ``RandomSource`` e o contrato aceito pelo nucleo, e a
    composition root injeta a implementacao semeada que tambem fornece
    ``spawn``.
    """

    if (
        isinstance(reference_pace_ms_per_km, bool)
        or not isinstance(reference_pace_ms_per_km, (int, float))
        or not isfinite(reference_pace_ms_per_km)
        or reference_pace_ms_per_km <= 0
    ):
        raise ValueError("reference_pace_ms_per_km deve ser positivo e finito")
    if lap_length_m is not None and (
        isinstance(lap_length_m, bool)
        or not isinstance(lap_length_m, (int, float))
        or not isfinite(lap_length_m)
        or lap_length_m <= 0
    ):
        raise ValueError("lap_length_m deve ser positivo e finito quando informado")

    known_track_ids = {candidate.circuit_id for candidate in parameters.tracks}
    track = (
        parameters.track(setup.track_id)
        if setup.track_id is not None and setup.track_id in known_track_ids
        else parameters.fallback_track
    )
    reference_lap_time_ms = (
        lap_length_m / 1_000.0 * reference_pace_ms_per_km
        if lap_length_m is not None
        else NOMINAL_LAP_TIME_MS
    )

    missing_attributes = [
        entry.driver_id for entry in grid if entry.driver_id not in attributes
    ]
    if missing_attributes:
        raise ValueError(f"attributes ausentes para pilotos: {missing_attributes}")

    amplitude = DEFAULT_HEURISTIC_PIT_PARAMETERS.driver_variation_amplitude_laps
    known_team_ids = {
        candidate.team_id for candidate in parameters.team_reliability
    }
    entrants = []
    reliability_fallbacks = []
    for grid_position, entry in enumerate(grid, start=1):
        driver_attributes = attributes[entry.driver_id]
        # O intervalo inclusivo [-amplitude, +amplitude] tem largura impar; o
        # deslocamento posterior devolve exatamente o offset inteiro esperado.
        strategy_rng = rng.spawn(  # type: ignore[attr-defined]
            f"strategy:offset:{entry.driver_id}"
        )
        offset_laps = uniform_index(
            strategy_rng,
            f"strategy:offset:{entry.driver_id}:uniform-index",
            2 * amplitude + 1,
        ) - amplitude
        team_is_modeled = entry.team_id in known_team_ids
        reliability_factor = (
            parameters.reliability_factor(entry.team_id)
            if team_is_modeled
            else 1.0
        )
        if not team_is_modeled:
            reliability_fallbacks.append(
                {
                    "driver_id": entry.driver_id,
                    "team_id": entry.team_id,
                    "reliability_factor": 1.0,
                }
            )
        entrants.append(
            Entrant(
                driver_id=entry.driver_id,
                name=entry.driver_name,
                reference_lap_time_ms=reference_lap_time_ms,
                grid_position=grid_position,
                strategy=HeuristicPitStrategy(
                    parameters,
                    track,
                    # O mesmo multiplicador que o motor aplica ao desgaste, para
                    # a decisao de parar enxergar o pneu que o carro tera.
                    tyre_management_factor=detailed_degradation_factor(
                        driver_attributes
                    ),
                    offset_laps=offset_laps,
                ),
                starting_compound="MEDIUM",
                team_id=entry.team_id,
                reliability_factor=reliability_factor,
            )
        )

    result = simulate_detailed_race(
        entrants,
        total_laps=setup.total_laps,
        parameters=parameters,
        track=track,
        rng=rng.spawn("detailed-race"),  # type: ignore[attr-defined]
        attributes=attributes,
        dispute_model=dispute_model,
        race_control=race_control,
    )
    result["setup"] = {
        "total_laps": setup.total_laps,
        "track_id": setup.track_id,
        "weather": setup.weather,
    }
    result["reference_lap_time_ms"] = reference_lap_time_ms
    result["track_reference"] = {
        "requested_track_id": setup.track_id,
        "model_track_id": track.circuit_id,
        "model_track_name": track.name,
        "model_track_origin": track.origin,
        "lap_length_m": lap_length_m,
    }
    result["assumptions"] = [
        *result.get("assumptions", []),
        {
            "kind": "reference_pace",
            **asdict(
                ReferencePaceParameters(
                    pace_ms_per_km=float(reference_pace_ms_per_km)
                )
            ),
            "used_nominal_lap_time_fallback": lap_length_m is None,
            "nominal_lap_time_ms": (
                NOMINAL_LAP_TIME_MS if lap_length_m is None else None
            ),
        },
        {
            "kind": "starting_compound",
            "compound": "MEDIUM",
            "origin": "assumed",
            "parameter_version": "assumed-grid-starting-compound-v1",
            "rationale": (
                "Hipotese uniforme para ligar o grid ao modelo de pneus; o "
                "catalogo atual nao informa o composto de largada."
            ),
        },
        {
            "kind": "pit_strategy",
            **asdict(DEFAULT_HEURISTIC_PIT_PARAMETERS),
        },
    ]
    if reliability_fallbacks:
        result["assumptions"].append(
            {
                "kind": "team_reliability_fallback",
                "origin": "assumed",
                "parameter_version": "model-team-reliability-fallback-v1",
                "rationale": (
                    "IDs de equipe sem correspondencia exata no modelo usam "
                    "o fator neutro 1.0, sem inferencia por nome."
                ),
                "entries": reliability_fallbacks,
            }
        )
    return result
