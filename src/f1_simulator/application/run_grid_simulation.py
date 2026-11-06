from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Literal

from f1_simulator.application.build_grid import GridEntry
from f1_simulator.application.reference_laps import (
    METHOD_VERSION as REFERENCE_LAPS_METHOD_VERSION,
)
from f1_simulator.application.reference_laps import ReferenceLap
from f1_simulator.domain.driver_attributes import DriverAttributes
from f1_simulator.domain.fuel import (
    FuelModelParameters,
    FuelPlan,
)
from f1_simulator.domain.model_parameters import ModelParameters
from f1_simulator.domain.race_control import (
    HEURISTIC_RACE_CONTROL,
    RaceControlParameters,
)
from f1_simulator.domain.random_source import (
    MAX_JSON_SAFE_SEED,
    RandomSource,
    derive_tournament_stage_random_source,
)
from f1_simulator.domain.track_geometry import TrackGeometry
from f1_simulator.domain.weather import (
    ASSUMED_WEATHER_EFFECT,
    ASSUMED_WEATHER_PARAMETERS,
    WeatherSegment,
    expand_segments,
    simulate_weather,
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

#: Volta de referencia nominal (ms), ultima reserva quando nao ha pista nem
#: comprimento. No motor 2D so entra no eco de ``assumptions``, porque o 2D
#: exige geometria e nao chega a simular sem pista.
NOMINAL_LAP_TIME_MS = 90_000.0


@dataclass(frozen=True, slots=True)
class RaceSetup:
    total_laps: int
    track_id: str | None = None
    weather: tuple[WeatherSegment, ...] = ()
    tournament_seed: int | None = None
    stage_index: int = 0

    def __post_init__(self) -> None:
        if type(self.total_laps) is not int or self.total_laps <= 0:
            raise ValueError("total_laps must be a positive integer")
        if not isinstance(self.weather, tuple):
            raise ValueError("weather must be a tuple of WeatherSegment")
        if self.tournament_seed is not None and (
            type(self.tournament_seed) is not int
            or not 0 <= self.tournament_seed <= MAX_JSON_SAFE_SEED
        ):
            raise ValueError(
                f"tournament_seed deve estar entre 0 e {MAX_JSON_SAFE_SEED}"
            )
        if type(self.stage_index) is not int or self.stage_index < 0:
            raise ValueError("stage_index deve ser um inteiro maior ou igual a zero")


def _weather_echo(setup: RaceSetup) -> list[dict]:
    return [
        {"from_lap": s.from_lap, "to_lap": s.to_lap, "rain": s.rain.value}
        for s in setup.weather
    ]


def _setup_echo(setup: RaceSetup, engine: str = "detailed") -> dict:
    """Ecoe o contrato novo sem alterar a representacao de corridas legadas.

    ``engine`` so aparece fora do padrao: corridas do motor detalhado mantem o
    eco de antes, e uma corrida 2D declara o motor que a produziu (conferido ao
    salvar um torneio).
    """

    payload = {
        "total_laps": setup.total_laps,
        "track_id": setup.track_id,
        "weather": _weather_echo(setup),
    }
    if engine != "detailed":
        payload["engine"] = engine
    if setup.tournament_seed is not None:
        payload["tournament_seed"] = setup.tournament_seed
        payload["stage_index"] = setup.stage_index
    return payload


def _run_2d(
    grid,
    attributes,
    setup,
    *,
    parameters,
    geometry,
    track,
    rng,
    fuel_plan,
    reference_lap_time_ms,
    race_control,
) -> dict:
    """Execute o grid no motor 2D (ADR 0011) e complete o resultado como o detalhado."""

    from f1_simulator.domain.race_simulation_2d import simulate_2d_race
    from f1_simulator.domain.weather import expand_segments, simulate_weather

    compounds = {c.name: c for c in parameters.compounds}
    entrants = [
        {
            "driver_id": entry.driver_id,
            "name": entry.driver_name,
            "grid_position": position,
            "attributes": attributes[entry.driver_id],
            "aggression": attributes[entry.driver_id].aggression,
            "compound": "MEDIUM",
        }
        for position, entry in enumerate(grid, start=1)
    ]
    reliability_by_id = {
        entry.driver_id: parameters.reliability_factor(entry.team_id) for entry in grid
    }
    lap_surface_water = None
    if setup.weather:
        lap_weather = simulate_weather(expand_segments(setup.weather, setup.total_laps))
        lap_surface_water = [item.state.surface_water for item in lap_weather]

    result = simulate_2d_race(
        entrants,
        geometry,
        total_laps=setup.total_laps,
        rng=rng.spawn("race-2d"),  # type: ignore[attr-defined]
        compounds=compounds,
        track_params=track,
        model_parameters=parameters,
        fuel=fuel_plan,
        lap_surface_water=lap_surface_water,
        reliability_by_id=reliability_by_id,
        mechanical_hazard_per_lap=parameters.mechanical_hazard_per_lap(),
        race_control=race_control,
    )
    result["speed_profiles"] = _speed_profiles_by_driver(geometry, grid, attributes)
    result["setup"] = _setup_echo(setup, engine="2d")
    result["reference_lap_time_ms"] = reference_lap_time_ms
    result["track_reference"] = {
        "requested_track_id": setup.track_id,
        "model_track_id": track.circuit_id,
        "model_track_name": track.name,
        "model_track_origin": track.origin,
        "lap_length_m": geometry.lap_length_m,
    }
    return result


def _speed_profiles_by_driver(geometry, grid, attributes):
    """Perfil fisico de velocidade por piloto, para a tela mostrar carros distintos."""

    from f1_simulator.domain.speed_dynamics import physics_for, steady_lap

    profiles = {}
    for entry in grid:
        physics = physics_for(attributes.get(entry.driver_id))
        samples = steady_lap(geometry, physics)
        profiles[entry.driver_id] = [
            {"distance_m": s.distance_m, "speed_ms": s.speed_ms, "time_s": s.time_s}
            for s in samples
        ]
    return profiles


def run_grid_simulation(
    grid: Sequence[GridEntry],
    attributes: dict[str, DriverAttributes],
    setup: RaceSetup,
    *,
    parameters: ModelParameters,
    lap_length_m: float | None,
    rng: RandomSource,
    reference_pace_ms_per_km: float = ASSUMED_REFERENCE_PACE_MS_PER_KM,
    race_control: RaceControlParameters | None = HEURISTIC_RACE_CONTROL,
    reference_lap: ReferenceLap | None = None,
    geometry: TrackGeometry | None = None,
    fuel_parameters: FuelModelParameters | None = None,
    pit_entry_fraction: float | None = None,
) -> dict:
    """Execute o grid no motor 2D (ADR 0011) sem conhecer arquivo, HTTP ou banco.

    O motor 2D e o unico da corrida: a posicao x,y evolui por passos de tempo e
    ultrapassagem e colisao emergem da fisica espacial. Este caso de uso prepara
    o cenario compartilhado (volta de referencia, plano de combustivel, pista) e
    delega a simulacao a ``_run_2d``. O motor detalhado por volta foi aposentado.

    A ordem recebida em ``grid`` e a ordem de largada, começando em um. Quando
    ``setup.track_id`` existe em ``parameters.tracks``, seus parametros
    calibrados sao usados; qualquer ID ausente (inclusive ``None``) usa
    ``parameters.fallback_track``, cuja origem ``assumed`` torna a substituicao
    auditavel em ``track_reference``.

    A volta de referencia vem, em ordem de preferencia:

    1. de ``reference_lap``, a tabela historica por circuito
       (``application/reference_laps.py``), quando o circuito tem entrada;
    2. de ``lap_length_m`` vezes a hipotese em ms/km, quando ha pista mas nao
       ha entrada na tabela;
    3. de ``NOMINAL_LAP_TIME_MS`` do nucleo simples, quando nao ha pista.

    A origem efetivamente usada e declarada em ``assumptions``, em vez de
    transformar ausencia em zero ou esconder qual valor entrou na corrida.

    Cada piloto recebe um fluxo derivado exclusivamente para o offset inteiro
    da estrategia. O motor recebe outro fluxo, ``detailed-race``; assim mudar a
    quantidade de sorteios da estrategia nao desloca ruido, incidentes ou
    controle de prova. ``RandomSource`` e o contrato aceito pelo nucleo, e a
    composition root injeta a implementacao semeada que tambem fornece
    ``spawn``.

    Com ``fuel_parameters`` cada carro carrega sua massa de combustivel
    (``domain/fuel.py``) em vez da penalidade linear por voltas restantes. O
    consumo por volta usa ``lap_length_m``; sem geometria, a extensao e
    derivada da referencia pela mesma hipotese de ritmo por km, e a origem fica
    declarada em ``fuel.lap_length_source``.

    Com reabastecimento permitido, cada carro recebe as perdas das suas
    paradas antes da largada: a perda de boxes do circuito mais o
    deslocamento real da equipe (``fuel_parameters.refuel_stops``), com uma
    variacao por parada sorteada no fluxo ``refuel:stops:<piloto>``. Fluxo
    proprio, como o da estrategia, para nao deslocar o ruido da corrida.

    Nesse modo cada piloto tambem recebe preferencias de combustivel
    (``draw_fuel_traits``, fluxo ``strategy:fuel:<piloto>``) a partir da sua
    agressividade, e a carga de largada passa a ser escolhida pela propria
    estrategia: o primeiro stint do plano de paradas, nao a corrida inteira.
    ``pit_entry_fraction`` e a posicao da entrada dos boxes na volta, tirada
    da geometria do pit lane; ``None`` supoe a entrada na linha.
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

    # O caso de uso, e nao o adaptador HTTP nem o frontend, define qual fluxo
    # alimenta ambos os motores. Sem seed de torneio, ``rng`` permanece intacto
    # e conserva exatamente o caminho legado ``grid_seed -> spawn('race')``.
    if setup.tournament_seed is not None:
        rng = derive_tournament_stage_random_source(
            setup.tournament_seed, setup.stage_index
        )

    known_track_ids = {candidate.circuit_id for candidate in parameters.tracks}
    track = (
        parameters.track(setup.track_id)
        if setup.track_id is not None and setup.track_id in known_track_ids
        else parameters.fallback_track
    )
    if reference_lap is not None and reference_lap.circuit_id != setup.track_id:
        raise ValueError(
            f"reference_lap de {reference_lap.circuit_id} nao corresponde a "
            f"pista {setup.track_id}"
        )
    if reference_lap is not None:
        reference_lap_time_ms = reference_lap.reference_lap_time_ms
        reference_source = "historical_median"
    elif lap_length_m is not None:
        reference_lap_time_ms = lap_length_m / 1_000.0 * reference_pace_ms_per_km
        reference_source = "assumed_pace_per_km"
    else:
        reference_lap_time_ms = NOMINAL_LAP_TIME_MS
        reference_source = "nominal_lap_time"

    fuel_plan = None
    if fuel_parameters is not None:
        fuel_plan = FuelPlan(
            parameters=fuel_parameters,
            reference_lap_ms=reference_lap_time_ms,
            lap_length_km=(
                lap_length_m / 1_000.0
                if lap_length_m is not None
                else reference_lap_time_ms / reference_pace_ms_per_km
            ),
            lap_length_source=(
                "track_geometry" if lap_length_m is not None else "reference_pace"
            ),
            pit_entry_fraction=(
                1.0 if pit_entry_fraction is None else float(pit_entry_fraction)
            ),
        )
    refuel_mode = fuel_plan is not None and fuel_plan.parameters.refuelling_allowed

    missing_attributes = [
        entry.driver_id for entry in grid if entry.driver_id not in attributes
    ]
    if missing_attributes:
        raise ValueError(f"attributes ausentes para pilotos: {missing_attributes}")

    if geometry is None:
        raise ValueError("o motor 2D exige geometria da pista")
    result = _run_2d(
        grid,
        attributes,
        setup,
        parameters=parameters,
        geometry=geometry,
        track=track,
        rng=rng,
        fuel_plan=fuel_plan,
        reference_lap_time_ms=reference_lap_time_ms,
        race_control=race_control,
    )
    result["assumptions"] = [
        *result.get("assumptions", []),
        {
            "kind": "reference_pace",
            "reference_source": reference_source,
            "reference_lap_time_ms": reference_lap_time_ms,
            "historical_reference": (
                {
                    "method_version": REFERENCE_LAPS_METHOD_VERSION,
                    "races": reference_lap.races,
                    "seasons": list(reference_lap.seasons),
                }
                if reference_lap is not None
                else None
            ),
            **asdict(
                ReferencePaceParameters(pace_ms_per_km=float(reference_pace_ms_per_km))
            ),
            "used_nominal_lap_time_fallback": reference_source == "nominal_lap_time",
            "nominal_lap_time_ms": (
                NOMINAL_LAP_TIME_MS if reference_source == "nominal_lap_time" else None
            ),
        },
    ]
    if setup.weather:
        result["assumptions"].append(
            {
                "kind": "weather",
                "segments": _weather_echo(setup),
                "evolution": {
                    "source_kind": ASSUMED_WEATHER_PARAMETERS.source_kind,
                    "parameter_version": ASSUMED_WEATHER_PARAMETERS.parameter_version,
                    "rationale": ASSUMED_WEATHER_PARAMETERS.rationale,
                },
                "effect": {
                    "wet_penalty_pct_max": ASSUMED_WEATHER_EFFECT.wet_penalty_pct_max,
                    "source_kind": ASSUMED_WEATHER_EFFECT.source_kind,
                    "parameter_version": ASSUMED_WEATHER_EFFECT.parameter_version,
                    "rationale": ASSUMED_WEATHER_EFFECT.rationale,
                },
            }
        )
    return result



