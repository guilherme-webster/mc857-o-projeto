from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Literal

from f1_simulator.application.build_grid import GridEntry
from f1_simulator.application.car_presets import CarPreset
from f1_simulator.application.reference_laps import (
    METHOD_VERSION as REFERENCE_LAPS_METHOD_VERSION,
)
from f1_simulator.application.reference_laps import ReferenceLap
from f1_simulator.application.team_presets import TeamPreset
from f1_simulator.domain.driver_attributes import DriverAttributes
from f1_simulator.domain.fuel import (
    FuelModelParameters,
    FuelPlan,
)
from f1_simulator.domain.model_parameters import ASSUMED_WET_COMPOUNDS, ModelParameters
from f1_simulator.domain.race_control import (
    HEURISTIC_RACE_CONTROL,
    RaceControlParameters,
)
from f1_simulator.domain.random_source import (
    MAX_JSON_SAFE_SEED,
    RandomSource,
    derive_tournament_stage_random_source,
    uniform_index,
)
from f1_simulator.domain.speed_dynamics import (
    DEFAULT_CAR_PHYSICS,
    DRIVER_PHYSICS_GAINS_VERSION,
    CarPhysics,
    car_pace_to_physics,
)
from f1_simulator.domain.strategy import (
    DEFAULT_HEURISTIC_PIT_PARAMETERS,
    draw_weather_switch_bias,
)
from f1_simulator.domain.track_condition import (
    ASSUMED_TRACK_CONDITION,
    GRIP_LAP_TIME_EXPONENT,
    TrackState,
    simulate_track_conditions,
)
from f1_simulator.domain.track_geometry import TrackGeometry
from f1_simulator.domain.weather import (
    ASSUMED_WEATHER_PARAMETERS,
    RainLevel,
    WeatherSegment,
    expand_segments,
)
from f1_simulator.domain.wet_tyres import (
    ASSUMED_WET_TYRES,
    SLICK,
    best_tyre_class,
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
"""Parametros assumidos da referencia de ritmo do grid."""

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


def _setup_echo(setup: RaceSetup) -> dict:
    """Ecoe o setup da corrida; o motor 2D (ADR 0011) e o unico."""

    payload = {
        "total_laps": setup.total_laps,
        "track_id": setup.track_id,
        "weather": _weather_echo(setup),
        "engine": "2d",
    }
    if setup.tournament_seed is not None:
        payload["tournament_seed"] = setup.tournament_seed
        payload["stage_index"] = setup.stage_index
    return payload


def _strategy_offset(rng: RandomSource, driver_id: str) -> int:
    """Preferência por piloto em fluxo isolado, para o offset da estrategia."""

    amplitude = DEFAULT_HEURISTIC_PIT_PARAMETERS.driver_variation_amplitude_laps
    stream = rng.spawn(f"strategy:offset:{driver_id}")  # type: ignore[attr-defined]
    return (
        uniform_index(
            stream, f"strategy:offset:{driver_id}:uniform-index", 2 * amplitude + 1
        )
        - amplitude
    )


def _track_states(setup: RaceSetup, reference_lap_time_ms: float) -> tuple[TrackState, ...]:
    """Estado da pista em cada volta: agua, temperatura e borracha (ADR 0015).

    Calculado sempre, inclusive em corrida seca: a borracha evolui com o
    pelotao. A duracao da volta, que regula a secagem por minuto, e a volta de
    referencia do circuito; a precisao por carro nao importa para a pista.
    """

    conditions = (
        expand_segments(setup.weather, setup.total_laps)
        if setup.weather
        else (RainLevel.DRY,) * setup.total_laps
    )
    return simulate_track_conditions(
        conditions, lap_minutes=reference_lap_time_ms / 60_000.0
    )


def _starting_compound(track_states: tuple[TrackState, ...]) -> str:
    """Composto de largada: o de chuva se a primeira volta ja estiver molhada.

    O seco continua a hipotese uniforme (MEDIUM). Com chuva desde a largada,
    todos largam com o pneu que a agua prevista ao fim da volta 1 indica, como
    uma equipe que olha o radar antes da largada.
    """

    best = best_tyre_class(track_states[0].surface_water) if track_states else SLICK
    return "MEDIUM" if best == SLICK else best


def _weather_switch_bias(rng, driver_id: str, aggression: float) -> float:
    """Vies de troca por chuva do piloto, num fluxo proprio.

    O fluxo ``strategy:weather:<piloto>`` e derivado por rotulo, entao sortear
    aqui nao desloca o ruido da corrida nem as demais preferencias.
    """

    label = f"strategy:weather:{driver_id}"
    return draw_weather_switch_bias(aggression, rng.spawn(label), label)


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
    track_states,
    car_physics_by_driver,
    car_presets,
    car_preset_disclaimer,
    car_overrides_by_driver,
    pit_execution_by_driver,
    team_presets,
    team_preset_disclaimer,
    on_progress=None,
    check_cancelled=None,
) -> dict:
    """Execute o grid no motor 2D (ADR 0011) e monte o resultado da corrida."""

    from f1_simulator.domain.race_simulation_2d import simulate_2d_race

    compounds = {
        c.name: c for c in (*parameters.compounds, *ASSUMED_WET_COMPOUNDS)
    }
    starting_compound = _starting_compound(track_states)
    entrants = [
        {
            "driver_id": entry.driver_id,
            "name": entry.driver_name,
            "team_name": entry.team_name,
            "grid_position": position,
            "attributes": attributes[entry.driver_id],
            "aggression": attributes[entry.driver_id].aggression,
            "compound": starting_compound,
            "strategy_offset_laps": _strategy_offset(rng, entry.driver_id),
            "reference_lap_ms": reference_lap_time_ms,
            "weather_switch_bias": _weather_switch_bias(
                rng, entry.driver_id, attributes[entry.driver_id].aggression
            ),
        }
        for position, entry in enumerate(grid, start=1)
    ]
    reliability_by_id = {
        entry.driver_id: parameters.reliability_factor(entry.team_id) for entry in grid
    }
    result = simulate_2d_race(
        entrants,
        geometry,
        total_laps=setup.total_laps,
        rng=rng.spawn("race-2d"),  # type: ignore[attr-defined]
        compounds=compounds,
        track_params=track,
        model_parameters=parameters,
        fuel=fuel_plan,
        track_states=track_states,
        reliability_by_id=reliability_by_id,
        mechanical_hazard_per_lap=parameters.mechanical_hazard_per_lap(),
        race_control=race_control,
        base_physics_by_id=car_physics_by_driver,
        pit_execution_by_id=pit_execution_by_driver,
        on_progress=on_progress,
        check_cancelled=check_cancelled,
    )
    result["speed_profiles"] = _speed_profiles_by_driver(
        geometry, grid, attributes, car_physics_by_driver
    )
    result["setup"] = _setup_echo(setup)
    result["track_conditions"] = [state.as_dict() for state in track_states]
    result.setdefault("assumptions", []).extend(
        [_physical_lap_assumption(), _track_condition_assumption(setup)]
    )
    if car_physics_by_driver:
        result["assumptions"].append(
            _team_car_presets_assumption(
                grid, car_presets, car_preset_disclaimer, car_overrides_by_driver
            )
        )
    if pit_execution_by_driver:
        result["assumptions"].append(
            _team_execution_assumption(grid, team_presets, team_preset_disclaimer)
        )
    result["reference_lap_time_ms"] = reference_lap_time_ms
    result["track_reference"] = {
        "requested_track_id": setup.track_id,
        "model_track_id": track.circuit_id,
        "model_track_name": track.name,
        "model_track_origin": track.origin,
        "lap_length_m": geometry.lap_length_m,
    }
    return result


def _speed_profiles_by_driver(geometry, grid, attributes, car_physics_by_driver=None):
    """Perfil fisico de velocidade por piloto, para a tela mostrar carros distintos.

    O envelope de cada piloto tambem reflete o carro da sua equipe quando ha
    presets de carro, para que a velocidade desenhada coincida com a que
    efetivamente move o carro na pista.
    """

    from f1_simulator.domain.speed_dynamics import physics_for, steady_lap

    profiles = {}
    for entry in grid:
        base = (
            car_physics_by_driver.get(entry.driver_id)
            if car_physics_by_driver
            else None
        )
        physics = (
            physics_for(attributes.get(entry.driver_id), base)
            if base is not None
            else physics_for(attributes.get(entry.driver_id))
        )
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
    car_presets: Mapping[str, CarPreset] | None = None,
    car_preset_disclaimer: str | None = None,
    car_overrides_by_driver: Mapping[str, float] | None = None,
    team_presets: Mapping[str, TeamPreset] | None = None,
    team_preset_disclaimer: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    check_cancelled: Callable[[], None] | None = None,
) -> dict:
    """Execute o grid no motor 2D (ADR 0011) sem conhecer arquivo, HTTP ou banco.

    ``check_cancelled`` e um callback opcional que pode interromper a execucao
    por excecao, propagada ao chamador sem produzir um resultado parcial.

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
    da estrategia. O motor recebe outro fluxo, ``race-2d``; assim mudar a
    quantidade de sorteios da estrategia nao desloca ruido, incidentes ou
    controle de prova. ``RandomSource`` e o contrato aceito pelo nucleo, e a
    composition root injeta a implementacao semeada que tambem fornece
    ``spawn``.

    Com ``fuel_parameters`` cada carro carrega sua massa de combustivel
    (``domain/fuel.py``) em vez da penalidade linear por voltas restantes. O
    consumo por volta usa ``lap_length_m``; sem geometria, a extensao e
    derivada da referencia pela mesma hipotese de ritmo por km, e a origem fica
    declarada em ``fuel.lap_length_source``.

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
    # alimenta o motor. Sem seed de torneio, ``rng`` permanece intacto e
    # conserva exatamente o caminho legado ``grid_seed -> spawn('race')``.
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
    missing_attributes = [
        entry.driver_id for entry in grid if entry.driver_id not in attributes
    ]
    if missing_attributes:
        raise ValueError(f"attributes ausentes para pilotos: {missing_attributes}")

    if geometry is None:
        raise ValueError("o motor 2D exige geometria da pista")
    track_states = _track_states(setup, reference_lap_time_ms)
    car_physics_by_driver = _car_physics_by_driver(
        grid, car_presets, car_overrides_by_driver
    )
    pit_execution_by_driver = _pit_execution_by_driver(grid, team_presets)
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
        track_states=track_states,
        car_physics_by_driver=car_physics_by_driver,
        car_presets=car_presets,
        car_preset_disclaimer=car_preset_disclaimer,
        car_overrides_by_driver=car_overrides_by_driver,
        pit_execution_by_driver=pit_execution_by_driver,
        team_presets=team_presets,
        team_preset_disclaimer=team_preset_disclaimer,
        on_progress=on_progress,
        check_cancelled=check_cancelled,
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
    return result


def _car_physics_by_driver(
    grid: Sequence[GridEntry],
    car_presets: Mapping[str, CarPreset] | None,
    car_overrides_by_driver: Mapping[str, float] | None = None,
) -> dict[str, CarPhysics]:
    """Envelope fisico por piloto a partir dos presets de carro por equipe.

    Sem presets nem overrides, devolve ``{}`` e os motores usam o carro de
    referencia unico, preservando exatamente o comportamento (e os hashes) de
    antes. Equipes do grid sem preset ficam de fora e caem no carro de
    referencia: o mapa so traz quem tem caracterizacao propria.

    ``car_overrides_by_driver`` e o ritmo especifico de **um piloto** da equipe
    (upgrade que chega so a um carro, dano, especificacao), em pontos
    percentuais somados ao ritmo da equipe antes da conversao fisica. Ausente,
    os dois carros da equipe sao identicos. Um override para um piloto sem
    preset de equipe usa o carro de referencia como base (equipe neutra).
    """

    overrides = dict(car_overrides_by_driver or {})
    if not car_presets and not overrides:
        return {}
    by_team = (
        {team_id: preset.pace_offset_pct for team_id, preset in car_presets.items()}
        if car_presets
        else {}
    )
    result: dict[str, CarPhysics] = {}
    for entry in grid:
        has_team = entry.team_id in by_team
        has_override = entry.driver_id in overrides
        if not has_team and not has_override:
            continue
        team_pace = by_team.get(entry.team_id, 0.0)
        driver_pace = team_pace + overrides.get(entry.driver_id, 0.0)
        result[entry.driver_id] = car_pace_to_physics(driver_pace)
    return result


def _pit_execution_by_driver(
    grid: Sequence[GridEntry],
    team_presets: Mapping[str, TeamPreset] | None,
) -> dict[str, float]:
    """Fator de execucao de pit por piloto, a partir do preset da equipe.

    Sem presets, devolve ``{}`` e os motores usam o tempo de box neutro,
    preservando o comportamento anterior. Equipes sem preset ou fatores iguais
    a 1.0 ficam de fora: so entra quem muda o resultado, e os dois pilotos de
    uma equipe partilham o mesmo box (a execucao e da equipe, nao do piloto).
    """

    if not team_presets:
        return {}
    by_team = {
        team_id: preset.pit_execution_factor
        for team_id, preset in team_presets.items()
        if preset.pit_execution_factor != 1.0
    }
    return {
        entry.driver_id: by_team[entry.team_id]
        for entry in grid
        if entry.team_id in by_team
    }


def _team_car_presets_assumption(
    grid: Sequence[GridEntry],
    car_presets: Mapping[str, CarPreset] | None,
    disclaimer: str | None,
    car_overrides_by_driver: Mapping[str, float] | None = None,
) -> dict:
    """Origem heuristica dos carros por equipe (ADR 0008), para os dois motores.

    ``mapped`` traz o ritmo da equipe e, quando ha variacao por piloto, o
    ritmo efetivo de cada carro (equipe + override).
    """

    presets = car_presets or {}
    overrides = dict(car_overrides_by_driver or {})
    if not presets and not overrides:
        raise AssertionError("a assumption de carro exige presets ou overrides")
    teams_in_grid = {entry.team_id: entry.team_name for entry in grid}
    mapped = []
    for team_id in sorted(teams_in_grid):
        preset = presets.get(team_id)
        team_pace = preset.pace_offset_pct if preset is not None else 0.0
        drivers_here = sorted(
            entry.driver_id for entry in grid if entry.team_id == team_id
        )
        if preset is None and not any(d in overrides for d in drivers_here):
            continue
        mapped.append(
            {
                "team_id": team_id,
                "team_name": teams_in_grid[team_id],
                "team_pace_offset_pct": team_pace,
                "has_preset": preset is not None,
                "drivers": [
                    {
                        "driver_id": driver_id,
                        "driver_override_pct": overrides.get(driver_id, 0.0),
                        "effective_pace_offset_pct": team_pace
                        + overrides.get(driver_id, 0.0),
                    }
                    for driver_id in drivers_here
                ],
            }
        )
    unmapped = [
        {"team_id": team_id, "team_name": name}
        for team_id, name in sorted(teams_in_grid.items())
        if team_id not in presets
        and not any(
            entry.team_id == team_id and entry.driver_id in overrides
            for entry in grid
        )
    ]
    if presets:
        sample = next(iter(presets.values()))
        parameter_version = sample.parameter_version
        rationale = sample.rationale
    else:
        parameter_version = "driver-car-override-only-v1"
        rationale = (
            "Variacao de carro por piloto sem preset de equipe: o ritmo do "
            "carro de cada piloto e o override aplicado ao carro de referencia."
        )
    return {
        "kind": "team_car_presets",
        "origin": "heuristic",
        "parameter_version": parameter_version,
        "rationale": rationale,
        "disclaimer": disclaimer,
        "method": (
            "car_pace_to_physics: factor = 1 - (team + override)/100 escala "
            "v_max_straight_kmh, grip_mu e power_kw do carro de referencia"
        ),
        "mapped": mapped,
        "unmapped_teams": unmapped,
        "applies_to": (
            "2d: movimento por fisica; detailed: volta base quando ha "
            "geometria (producao). Sem geometria, o motor detalhado usa a "
            "volta de referencia historica e o carro por equipe nao altera o "
            "ritmo base."
        ),
    }


def _team_execution_assumption(
    grid: Sequence[GridEntry],
    team_presets: Mapping[str, TeamPreset] | None,
    disclaimer: str | None,
) -> dict:
    """Origem heuristica da execucao de pit por equipe (ADR 0008).

    Declara explicitamente que confiabilidade mecanica (abandono) continua
    calibrada em ``model-v1.json`` e nao e tocada por esta heuristica.
    """

    if not team_presets:
        raise AssertionError("a assumption de execucao exige presets de equipe")
    teams_in_grid = {entry.team_id: entry.team_name for entry in grid}
    mapped = [
        {
            "team_id": team_id,
            "team_name": preset.team_name,
            "pit_execution_factor": preset.pit_execution_factor,
            "drivers": sorted(
                entry.driver_id for entry in grid if entry.team_id == team_id
            ),
        }
        for team_id, preset in sorted(team_presets.items())
        if team_id in teams_in_grid
    ]
    sample = next(iter(team_presets.values()))
    return {
        "kind": "team_execution_presets",
        "origin": "heuristic",
        "parameter_version": sample.parameter_version,
        "rationale": sample.rationale,
        "disclaimer": disclaimer,
        "method": (
            "pit_execution_factor multiplica o tempo de parada: detailed, a "
            "perda de boxes (track.pit_loss_ms) da troca de pneus; 2d, o "
            "service_time_s. O tempo de abastecer nao escala."
        ),
        "mapped": mapped,
        "mechanical_reliability": (
            "nao modelada aqui: abandono por quebra continua calibrado em "
            "model-v1.json (team_reliability.hazard_factor)"
        ),
    }


def _physical_lap_assumption() -> dict:
    """Origem do tempo de volta fisico (ADR 0015)."""

    car = DEFAULT_CAR_PHYSICS
    return {
        "kind": "physical_lap_time",
        "origin": "estimated",
        "parameter_version": "car-physics-v1",
        "estimated": {
            "grip_mu": car.grip_mu,
            "downforce_cla_m2": car.downforce_cla_m2,
        },
        "assumed": {
            "v_max_straight_kmh": car.v_max_straight_kmh,
            "drag_cda_m2": car.drag_cda_m2,
            "mass_kg": car.mass_kg,
            "power_kw": car.power_kw,
            "traction_share": car.traction_share,
        },
        # Os ganhos que traduzem atributos de piloto em envelope fisico sao
        # heuristicos (ADR 0008) e mudam o resultado sem mudar o carro: a
        # versao vai junto para a corrida salva ser auditavel (issue #139).
        "driver_attribute_gains": {
            "origin": "heuristic",
            "parameter_version": DRIVER_PHYSICS_GAINS_VERSION,
        },
        "rationale": (
            "ADR 0015: velocidade de curva limitada por aderencia e downforce, "
            "com raio em metros; grip_mu e downforce_cla_m2 ajustados para o "
            "piloto neutro reproduzir a volta de referencia historica "
            "(data/parameters/car-physics-v1.json). Substitui a volta de "
            "referencia como base do tempo de volta."
        ),
    }


def _track_condition_assumption(setup: RaceSetup) -> dict:
    """Hipoteses de clima e de estado da pista que entraram na corrida."""

    condition = ASSUMED_TRACK_CONDITION
    return {
        "kind": "track_condition",
        "segments": _weather_echo(setup),
        "evolution": {
            "source_kind": ASSUMED_WEATHER_PARAMETERS.source_kind,
            "parameter_version": ASSUMED_WEATHER_PARAMETERS.parameter_version,
            "rationale": ASSUMED_WEATHER_PARAMETERS.rationale,
        },
        "grip": {
            "damp_water": condition.damp_water,
            "damp_grip": condition.damp_grip,
            "saturated_grip": condition.saturated_grip,
            "initial_rubber": condition.initial_rubber,
            "green_track_grip_loss": condition.green_track_grip_loss,
            "dry_track_temp_c": condition.dry_track_temp_c,
            "no_geometry_lap_time_exponent": GRIP_LAP_TIME_EXPONENT,
            "source_kind": condition.source_kind,
            "parameter_version": condition.parameter_version,
            "rationale": condition.rationale,
        },
        "wet_tyres": {
            "slick_curve": [list(point) for point in ASSUMED_WET_TYRES.slick_curve],
            "intermediate_curve": [
                list(point) for point in ASSUMED_WET_TYRES.intermediate_curve
            ],
            "wet_curve": [list(point) for point in ASSUMED_WET_TYRES.wet_curve],
            "switch_horizon_laps": ASSUMED_WET_TYRES.switch_horizon_laps,
            "source_kind": ASSUMED_WET_TYRES.source_kind,
            "parameter_version": ASSUMED_WET_TYRES.parameter_version,
            "rationale": ASSUMED_WET_TYRES.rationale,
        },
    }

