"""Nucleo da simulacao de corrida, em dois niveis.

``simulate_detailed_race`` -- o modelo do motor calibrado (issue #40), com
combustivel (linear por voltas restantes, ou massa por carro quando um
``FuelPlan`` e informado), pneus por composto, trafego, paradas, disputas de posicao, abandono
e ruido, descrito em ``domain/lap_time.py`` e ``domain/disputes.py``. Consome
parametros versionados e uma fonte aleatoria injetada; a mesma semente reproduz
a mesma corrida.

Fronteiras (ADR 0002 / AGENTS.md): o core e a fonte de verdade da classificacao
e nao conhece Arcade, FastAPI, SQLite nem formatos de dados. A aleatoriedade e
sempre injetada (nunca ha sorteio global nem semente escolhida aqui). Tempos em
milissegundos.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from math import floor
from typing import Literal

from f1_simulator.domain.attribute_effects import (
    DETAILED_TYRE_MANAGEMENT,
    adjusted_reference_ms,
    attributes_assumption,
    consistency_scale,
    detailed_degradation_factor,
)
from f1_simulator.domain.disputes import (
    DEFAULT_DISPUTE_HEURISTICS,
    DisputeHeuristics,
    DisputeProfile,
    resolve_disputes,
)
from f1_simulator.domain.driver_attributes import DriverAttributes
from f1_simulator.domain.fuel import FuelLap, FuelPlan, RefuelStops, fuel_lap
from f1_simulator.domain.lap_time import compute_lap_time
from f1_simulator.domain.model_parameters import ModelParameters, TrackParameters
from f1_simulator.domain.race_control import (
    SC,
    VSC,
    Incident,
    RaceControlParameters,
    RaceControlState,
    effects,
    solo_crash_probability,
    step,
)
from f1_simulator.domain.random_source import RandomSource
from f1_simulator.domain.speed_dynamics import (
    ASSUMED_CAR_PHYSICS,
    CarPhysics,
    lap_time_ms,
    physics_for,
    steady_lap,
)
from f1_simulator.domain.strategy import (
    FuelStatus,
    PitDecision,
    StrategyState,
    TyreStrategy,
)
from f1_simulator.domain.track_geometry import TrackGeometry
from f1_simulator.domain.tyres import TyreSet
from f1_simulator.domain.weather import (
    ASSUMED_WEATHER_EFFECT,
    WeatherEffectParameters,
    weather_penalty_ms,
)

RUNNING = "RUNNING"
RETIRED = "RETIRED"

#: Causa do abandono. Separar as duas importa porque elas tem origens
#: diferentes no modelo: a mecanica e um risco por volta da equipe, o
#: contato so pode surgir de uma disputa de posicao.
MECHANICAL = "MECHANICAL"
CONTACT = "CONTACT"
CRASH = "CRASH"
#: O tanque esvaziou antes da bandeirada. So existe com o modelo de massa de
#: combustivel e so acontece quando a carga nao cobre a corrida (corrida alem
#: do alcance de 110 kg ou carga de largada reduzida de proposito).
FUEL = "FUEL"

#: Volta de referencia nominal assumida (ms), usada pelo motor detalhado como
#: ultima reserva quando a corrida nao tem pista nem comprimento informados.
NOMINAL_LAP_TIME_MS = 90_000.0


# --------------------------------------------------------------------------
# Modelo detalhado
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Entrant:
    """Inscricao completa de um carro no cenario detalhado.

    ``reference_lap_time_ms`` e a volta limpa de referencia (pneu novo,
    combustivel baixo, ar livre) -- a mesma condicao assumida pelas penalidades
    de ``domain/lap_time.py``. ``reliability_factor`` multiplica o risco base de
    abandono: 1.0 e o carro medio da era calibrada.

    ``start_fuel_kg`` e a carga de largada, usada apenas quando a corrida
    recebe um ``FuelPlan``. ``None`` usa a carga planejada pelo plano (corrida
    inteira mais a reserva); um valor menor representa a estrategia de largar
    leve e economizar depois.

    ``refuel_stops`` e a perda de tempo de cada parada de reabastecimento
    deste carro, sorteada antes da corrida a partir do tempo de parada real
    da equipe. ``None`` usa a perda de boxes do circuito. So vale quando o
    plano permite reabastecer.
    """

    driver_id: str
    name: str
    reference_lap_time_ms: float
    grid_position: int
    strategy: TyreStrategy
    starting_compound: str
    team_id: str | None = None
    reliability_factor: float = 1.0
    start_fuel_kg: float | None = None
    refuel_stops: RefuelStops | None = None

    def __post_init__(self) -> None:
        if self.reference_lap_time_ms <= 0:
            raise ValueError(
                f"reference_lap_time_ms deve ser positivo para {self.driver_id}"
            )
        if self.grid_position < 1:
            raise ValueError(f"grid_position deve ser positivo para {self.driver_id}")
        if self.reliability_factor < 0:
            raise ValueError("reliability_factor nao pode ser negativo")
        if self.start_fuel_kg is not None and (
            isinstance(self.start_fuel_kg, bool)
            or not isinstance(self.start_fuel_kg, (int, float))
            or not self.start_fuel_kg >= 0
        ):
            raise ValueError(f"start_fuel_kg invalido para {self.driver_id}")


@dataclass(slots=True)
class CarState:
    """Estado mutavel de um carro ao longo da corrida.

    E o unico objeto mutavel do nucleo. Ele existe porque a corrida e um
    processo com estado; os parametros e o retrato entregue a interface
    permanecem imutaveis.
    """

    driver_id: str
    name: str
    total_time_ms: float
    laps_completed: int = 0
    tyre: TyreSet = field(default_factory=lambda: TyreSet("MEDIUM"))
    stops_made: int = 0
    status: str = RUNNING
    retired_on_lap: int | None = None
    retirement_cause: str | None = None
    #: Voltas em que o carro terminou preso atras de outro. Distingue um
    #: carro lento de um carro rapido que nao conseguiu passar.
    blocked_laps: int = 0
    #: Massa de combustivel (kg) ao fim da ultima volta. ``None`` quando a
    #: corrida usa o combustivel linear legado, que nao tem estado por carro;
    #: nesse caso o retrato nao ganha campos novos.
    fuel_kg: float | None = None
    #: Voltas em que o carro precisou economizar (lift-and-coast).
    fuel_saving_laps: int = 0
    #: Paradas so de reabastecimento. Separadas de ``stops_made`` porque a
    #: estrategia de pneus conta apenas as suas proprias paradas.
    refuels_made: int = 0


def _detailed_classification(states: list[CarState]) -> list[dict]:
    """Ordene pela regra de classificacao da corrida, nao pelo relogio puro.

    Mais voltas completadas vem sempre a frente; entre iguais, menor tempo
    acumulado. Carros abandonados ficam atras de todos os que seguem na pista,
    e entre si sao ordenados por voltas completadas -- que e a convencao usada
    na classificacao oficial e no ``classification_order`` do dataset.
    """

    ordered = sorted(
        states,
        key=lambda s: (
            s.status == RETIRED,
            -s.laps_completed,
            s.total_time_ms,
            s.driver_id,
        ),
    )
    rows = [
        {
            "position": index,
            "driver_id": state.driver_id,
            "name": state.name,
            "total_time_ms": round(state.total_time_ms, 1),
            # ``lap_time_ms`` e o tempo medio por volta ate aqui, e nao um ritmo
            # constante. A visualizacao Arcade nao o usa mais: ela reproduz a
            # corrida pelos ``total_time_ms`` de cada retrato
            # (``frontend/arcade/race_playback.py``). O campo permanece no
            # contrato para corridas salvas e outros consumidores.
            "lap_time_ms": round(state.total_time_ms / state.laps_completed, 1)
            if state.laps_completed
            else 0.0,
            "laps_completed": state.laps_completed,
            "status": state.status,
            "compound": state.tyre.compound,
            "tyre_age_laps": state.tyre.age_laps,
            "stops_made": state.stops_made,
            "retirement_cause": state.retirement_cause,
            "blocked_laps": state.blocked_laps,
        }
        for index, state in enumerate(ordered, start=1)
    ]
    # Campos de combustivel apenas com o modelo de massa: o retrato legado e
    # parte do hash de reproducao e nao pode ganhar chaves.
    for row, state in zip(rows, ordered):
        if state.fuel_kg is not None:
            row["fuel_kg"] = round(state.fuel_kg, 3)
            row["fuel_saving_laps"] = state.fuel_saving_laps
            row["refuels_made"] = state.refuels_made
    return rows


def simulate_detailed_race(
    entrants: tuple[Entrant, ...] | list[Entrant],
    *,
    total_laps: int,
    parameters: ModelParameters,
    track: TrackParameters,
    rng: RandomSource,
    collect_breakdowns: bool = False,
    resolve_position_disputes: bool = True,
    attributes: Mapping[str, DriverAttributes] | None = None,
    dispute_model: Literal["legacy", "pressure"] = "legacy",
    dispute_heuristics: DisputeHeuristics = DEFAULT_DISPUTE_HEURISTICS,
    race_control: RaceControlParameters | None = None,
    lap_surface_water: Sequence[float] | None = None,
    weather_effect: WeatherEffectParameters = ASSUMED_WEATHER_EFFECT,
    geometry: TrackGeometry | None = None,
    car_physics: CarPhysics = ASSUMED_CAR_PHYSICS,
    fuel: FuelPlan | None = None,
) -> dict:
    """Simule uma corrida detalhada, com extensoes opt-in e caminho neutro fiel.

    Sem ``attributes``, modelo de pressao ou ``race_control``, a chamada e
    encaminhada ao laco legado sem mudar sua estrutura, aritmetica ou ordem de
    sorteios. Essa separacao deliberada protege a reproducibilidade do motor
    calibrado: defaults novos nao podem alterar nem o ultimo bit dos resultados
    historicos usados nos backtests.

    Quando algum recurso novo esta ativo, atributos ajustam referencia, ruido e
    degradacao; o modelo de pressao recebe perfis de disputa; e o controle de
    prova modifica tempo, paradas, disputas e incidentes volta a volta. Todos os
    sorteios adicionais existem exclusivamente nesse caminho opt-in.

    ``fuel`` liga o modelo de massa de combustivel (``domain/fuel.py``): cada
    carro carrega sua massa, queima uma volta de combustivel por volta (menos
    sob SC/VSC/vermelha), economiza quando falta e abandona com causa ``FUEL``
    se o tanque esvaziar. Se o plano permite reabastecer, toda parada troca
    pneus e reabastece, e a estrategia de cada piloto decide quando parar e
    quanto colocar (``StrategyState.fuel``). O modelo nao sorteia nada, entao
    a sequencia aleatoria so muda se um carro ficar sem combustivel sob
    controle de prova (o carro parado vira um incidente).
    """

    if dispute_model not in ("legacy", "pressure"):
        raise ValueError("dispute_model deve ser 'legacy' ou 'pressure'")
    enhanced = (
        attributes is not None
        or dispute_model == "pressure"
        or race_control is not None
        or lap_surface_water is not None
        or geometry is not None
        or fuel is not None
    )
    if not enhanced:
        return _simulate_detailed_race_legacy(
            entrants,
            total_laps=total_laps,
            parameters=parameters,
            track=track,
            rng=rng,
            collect_breakdowns=collect_breakdowns,
            resolve_position_disputes=resolve_position_disputes,
        )
    return _simulate_detailed_race_enhanced(
        entrants,
        total_laps=total_laps,
        parameters=parameters,
        track=track,
        rng=rng,
        collect_breakdowns=collect_breakdowns,
        resolve_position_disputes=resolve_position_disputes,
        attributes=attributes,
        dispute_model=dispute_model,
        dispute_heuristics=dispute_heuristics,
        race_control=race_control,
        lap_surface_water=lap_surface_water,
        weather_effect=weather_effect,
        geometry=geometry,
        car_physics=car_physics,
        fuel=fuel,
    )


def _simulate_detailed_race_legacy(
    entrants: tuple[Entrant, ...] | list[Entrant],
    *,
    total_laps: int,
    parameters: ModelParameters,
    track: TrackParameters,
    rng: RandomSource,
    collect_breakdowns: bool = False,
    resolve_position_disputes: bool = True,
) -> dict:
    """Simule a corrida com o modelo completo e retorne retrato por volta.

    Ordem de cada volta, fixa para garantir reprodutibilidade:

    1. o intervalo para o carro da frente e medido no **inicio** da volta, pela
       classificacao vigente, de modo que o resultado nao dependa da ordem em
       que os carros sao iterados;
    2. a politica decide parar ou seguir, usando o estado do fim da volta
       anterior;
    3. o tempo da volta e montado por ``compute_lap_time``, ja incluindo a perda
       de boxes quando houver parada;
    4. o pneu envelhece, ou e trocado por um jogo novo se houve parada;
    5. o risco de abandono e sorteado.

    A fonte aleatoria e consumida na mesma ordem para todos os carros, sempre em
    ordem de ``driver_id``, para que a semente reproduza a corrida exatamente.
    """

    if total_laps <= 0:
        raise ValueError("total_laps deve ser positivo")

    seen: set[str] = set()
    for entrant in entrants:
        if entrant.driver_id in seen:
            raise ValueError(f"driver_id duplicado: {entrant.driver_id}")
        seen.add(entrant.driver_id)
        parameters.compound(entrant.starting_compound)

    # Ordem canonica de consumo da fonte aleatoria.
    ordered_entrants = sorted(entrants, key=lambda e: e.driver_id)
    by_id = {e.driver_id: e for e in ordered_entrants}

    states: dict[str, CarState] = {
        e.driver_id: CarState(
            driver_id=e.driver_id,
            name=e.name,
            # A posicao de largada vira atraso inicial de relogio: quem larga
            # atras ja comeca a corrida devendo tempo ao lider.
            total_time_ms=parameters.grid_penalty_ms_per_position
            * (e.grid_position - 1),
            tyre=TyreSet(e.starting_compound),
        )
        for e in ordered_entrants
    }

    breakdowns: list[dict] = []
    history: list[dict] = []

    for lap in range(1, total_laps + 1):
        running = [s for s in states.values() if s.status == RUNNING]
        if not running:
            break

        # (1) intervalos medidos antes de qualquer carro avancar
        standing = sorted(running, key=lambda s: (s.total_time_ms, s.driver_id))
        gaps: dict[str, float | None] = {standing[0].driver_id: None}
        for ahead, behind in zip(standing, standing[1:]):
            gaps[behind.driver_id] = behind.total_time_ms - ahead.total_time_ms

        # (2) tempos propostos, sem commit: a disputa pode altera-los
        proposals: dict[str, tuple[float, bool, str | None]] = {}
        for state in (s for s in states.values() if s.status == RUNNING):
            entrant = by_id[state.driver_id]

            decision = entrant.strategy.decide(
                StrategyState(
                    lap_number=lap,
                    total_laps=total_laps,
                    tyre=state.tyre,
                    stops_made=state.stops_made,
                )
            )
            breakdown = compute_lap_time(
                reference_ms=entrant.reference_lap_time_ms,
                parameters=parameters,
                track=track,
                tyre=state.tyre,
                lap_number=lap,
                total_laps=total_laps,
                gap_ahead_ms=gaps.get(state.driver_id),
                pitting=decision.pit,
                rng=rng,
            )
            proposals[state.driver_id] = (
                state.total_time_ms + breakdown.total_ms,
                decision.pit,
                decision.compound,
            )

            if collect_breakdowns:
                breakdowns.append(
                    {
                        "lap": lap,
                        "driver_id": state.driver_id,
                        "reference_ms": round(breakdown.reference_ms, 1),
                        "fuel_ms": round(breakdown.fuel_ms, 1),
                        "tyre_ms": round(breakdown.tyre_ms, 1),
                        "traffic_ms": round(breakdown.traffic_ms, 1),
                        "pit_ms": round(breakdown.pit_ms, 1),
                        "noise_ms": round(breakdown.noise_ms, 1),
                        "total_ms": round(breakdown.total_ms, 1),
                    }
                )

        # (3) disputas: bloqueio, ultrapassagem e contato. Um carro nos boxes
        #     nao esta disputando posicao em pista, entao fica de fora e sua
        #     perda de tempo nao e confundida com um bloqueio.
        contenders = [
            (state.driver_id, state.total_time_ms, proposals[state.driver_id][0])
            for state in states.values()
            if state.status == RUNNING and not proposals[state.driver_id][1]
        ]
        # Desligar a disputa precisa pular a funcao inteira, e nao apenas
        # zerar seus parametros: com espacamento zero o sorteio de
        # ultrapassagem continuaria acontecendo e uma passagem negada ainda
        # prenderia o carro atras. A ablacao tem de ser uma ablacao.
        outcomes = {}
        if resolve_position_disputes:
            outcomes = {
                outcome.driver_id: outcome
                for outcome in resolve_disputes(
                    contenders, parameters=parameters, track=track, rng=rng
                )
            }

        # (4) commit do tempo, do pneu e dos abandonos
        for state in (s for s in states.values() if s.status == RUNNING):
            entrant = by_id[state.driver_id]
            proposed_end, pitting, compound = proposals[state.driver_id]
            outcome = outcomes.get(state.driver_id)

            state.total_time_ms = outcome.end_time_ms if outcome else proposed_end
            state.laps_completed += 1
            if outcome and outcome.blocked_by:
                state.blocked_laps += 1

            if pitting:
                state.tyre = TyreSet(compound, 0)
                state.stops_made += 1
            else:
                state.tyre = state.tyre.aged()

            # Contato durante a disputa: um desfecho da briga, nao um sorteio
            # solto. A falha mecanica e sorteada a parte, sempre, para manter a
            # sequencia aleatoria identica independentemente do desfecho.
            draw = rng.uniform01()
            hazard = parameters.mechanical_hazard_per_lap() * entrant.reliability_factor
            retired = draw < hazard or (outcome is not None and outcome.collided)
            if retired and lap < total_laps:
                state.status = RETIRED
                state.retired_on_lap = lap
                state.retirement_cause = (
                    CONTACT if outcome and outcome.collided else MECHANICAL
                )

        history.append(
            {"lap": lap, "cars": _detailed_classification(list(states.values()))}
        )

    classification = history[-1]["cars"] if history else []
    result = {
        "total_laps": total_laps,
        "parameters_version": parameters.version,
        "circuit_id": track.circuit_id,
        "history": history,
        "classification": classification,
    }
    if collect_breakdowns:
        result["breakdowns"] = breakdowns
    return result


def _simulate_detailed_race_enhanced(
    entrants: tuple[Entrant, ...] | list[Entrant],
    *,
    total_laps: int,
    parameters: ModelParameters,
    track: TrackParameters,
    rng: RandomSource,
    collect_breakdowns: bool,
    resolve_position_disputes: bool,
    attributes: Mapping[str, DriverAttributes] | None,
    dispute_model: Literal["legacy", "pressure"],
    dispute_heuristics: DisputeHeuristics,
    race_control: RaceControlParameters | None,
    lap_surface_water: Sequence[float] | None = None,
    weather_effect: WeatherEffectParameters = ASSUMED_WEATHER_EFFECT,
    geometry: TrackGeometry | None = None,
    car_physics: CarPhysics = ASSUMED_CAR_PHYSICS,
    fuel: FuelPlan | None = None,
) -> dict:
    """Execute a composicao opt-in de atributos, disputas e controle de prova.

    A ordem de consumo aleatorio por volta e parte do contrato reproduzivel:

    1. ruido de volta, em ``driver_id`` crescente;
    2. disputas, na ordem fisica do inicio da volta;
    3. somente com controle de prova ativo, acidente individual por carro em
       ``driver_id`` crescente e depois falha mecanica na mesma ordem;
    4. respostas do controle de prova, que :func:`race_control.step` reordena
       canonicamente por tipo e IDs.

    Sem controle de prova, o unico sorteio posterior as disputas continua sendo
    o abandono mecanico legado, sem rotulo. Assim atributos isolados nao criam
    fontes novas de acaso.

    Com ``fuel``, a massa de cada carro e consumida em todas as voltas, apos a
    decisao de parada e antes do tempo da volta. Pane seca e verificada depois
    dos sorteios de abandono e nao consome aleatoriedade.

    Reabastecimento: a queima da volta e calculada antes da decisao e
    entregue a estrategia junto com a massa a bordo. Uma parada decidida vira
    a volta de entrada: soma a perda de parada propria do carro mais o tempo
    de abastecer alem da troca de pneus, sai das disputas e, no commit, recebe
    pneus novos e o combustivel decidido (``PitDecision.refuel_kg``; ``None``
    enche para terminar). Estrategias que nao olham o combustivel ficam
    protegidas por uma rede de seguranca: se o carro nao chegaria a proxima
    entrada dos boxes, o motor o chama para os boxes com o mesmo composto.
    """

    ordered_entrants, by_id, used_attributes = _prepare_enhanced_race(
        entrants, total_laps, parameters, attributes
    )
    # Com geometria, o tempo-base da volta emerge da fisica (ADR 0010) e
    # substitui a volta de referencia escalar como fonte do tempo. Cada carro
    # tem seu envelope, derivado dos atributos, entao o tempo fisico difere por
    # piloto. As penalidades aditivas e o ruido seguem somando por cima,
    # preservando pit, disputa, clima e a ordem de consumo do rng.
    physical_lap_ms_by_id: dict[str, float] = {}
    if geometry is not None:
        for entrant in ordered_entrants:
            physics = physics_for(used_attributes.get(entrant.driver_id), car_physics)
            physical_lap_ms_by_id[entrant.driver_id] = lap_time_ms(
                steady_lap(geometry, physics)
            )
    profiles = {
        driver_id: DisputeProfile(
            aggression=item.aggression,
            composure=item.composure,
            consistency_factor=item.consistency_factor,
        )
        for driver_id, item in used_attributes.items()
    }

    states: dict[str, CarState] = {
        entrant.driver_id: CarState(
            driver_id=entrant.driver_id,
            name=entrant.name,
            total_time_ms=(
                parameters.grid_penalty_ms_per_position * (entrant.grid_position - 1)
            ),
            tyre=TyreSet(entrant.starting_compound),
        )
        for entrant in ordered_entrants
    }
    compounds_used = {
        entrant.driver_id: [entrant.starting_compound] for entrant in ordered_entrants
    }
    start_fuel: dict[str, float] = {}
    refuel_events: list[dict] = []
    if fuel is not None:
        for entrant in ordered_entrants:
            load = (
                fuel.start_fuel_kg(total_laps)
                if entrant.start_fuel_kg is None
                else float(entrant.start_fuel_kg)
            )
            fuel.validate_start_fuel(load, entrant.driver_id)
            start_fuel[entrant.driver_id] = load
            states[entrant.driver_id].fuel_kg = load

    control_state = RaceControlState()
    control_events: list[dict[str, object]] = []
    control_by_lap: list[dict[str, object]] = []
    breakdowns: list[dict] = []
    history: list[dict] = []

    for lap in range(1, total_laps + 1):
        running = sorted(
            (state for state in states.values() if state.status == RUNNING),
            key=lambda state: state.driver_id,
        )
        if not running:
            break

        lap_effects = (
            effects(control_state, race_control)
            if race_control
            else effects(control_state)
        )
        control_by_lap.append(
            {
                "lap": lap,
                "status": control_state.status.value,
                "restart_lap": control_state.restart_lap,
            }
        )

        standing = sorted(
            running, key=lambda state: (state.total_time_ms, state.driver_id)
        )
        start_order = tuple(state.driver_id for state in standing)
        gaps: dict[str, float | None] = {standing[0].driver_id: None}
        for ahead, behind in zip(standing, standing[1:]):
            gaps[behind.driver_id] = behind.total_time_ms - ahead.total_time_ms

        # O quarto item indica troca gratuita sob vermelha. Nela o jogo novo
        # estreia nesta propria volta e nao representa passagem pelo pit lane.
        proposals: dict[str, tuple[float, bool, str | None, bool]] = {}
        fuel_laps: dict[str, FuelLap] = {}
        # Paradas com reabastecimento ligado: (kg, perda aplicada ms, quem
        # decidiu). Toda parada nesse modo troca pneus e pode abastecer.
        refuelling: dict[str, tuple[float, float, str]] = {}
        for state in running:
            entrant = by_id[state.driver_id]
            driver_attributes = used_attributes.get(state.driver_id)
            neutralization = (
                control_state.status.value
                if control_state.status in (SC, VSC)
                else None
            )
            lap_fuel: FuelLap | None = None
            fuel_status: FuelStatus | None = None
            refuel_mode = fuel is not None and fuel.parameters.refuelling_allowed
            if fuel is not None:
                assert state.fuel_kg is not None
                # A queima depende so do estado da pista, nao da decisao: e
                # calculada antes para o piloto decidir sabendo quanto sobra.
                lap_fuel = fuel_lap(
                    fuel,
                    fuel_kg=state.fuel_kg,
                    laps_remaining=total_laps - lap + 1,
                    status=control_state.status.value,
                )
                fuel_laps[state.driver_id] = lap_fuel
                if refuel_mode:
                    fuel_status = FuelStatus(
                        plan=fuel,
                        fuel_kg=state.fuel_kg,
                        lap_burn_kg=lap_fuel.burn_kg,
                        stop_loss_ms=(
                            entrant.refuel_stops.mean_ms
                            if entrant.refuel_stops is not None
                            else track.pit_loss_ms
                        ),
                    )
            decision = entrant.strategy.decide(
                StrategyState(
                    lap_number=lap,
                    total_laps=total_laps,
                    tyre=state.tyre,
                    stops_made=state.stops_made,
                    neutralization=neutralization,
                    pit_loss_factor=lap_effects.pit_loss_factor,
                    compounds_used=tuple(compounds_used[state.driver_id]),
                    free_tyre_change=lap_effects.free_tyre_change,
                    fuel=fuel_status,
                )
            )
            # Rede de seguranca: a estrategia nao olhou o combustivel e o carro
            # nao chegaria a proxima entrada dos boxes. Vale tambem para quem
            # nao completaria a volta inteira: ele ainda pode chegar a entrada
            # desta volta, que e mais curta (ver abaixo).
            boxed_by_engine = (
                refuel_mode
                and not decision.pit
                and lap_fuel is not None
                and fuel.must_pit(lap_fuel.end_kg, lap, total_laps)
            )
            if boxed_by_engine:
                decision = PitDecision(True, state.tyre.compound)
            free_change = decision.pit and lap_effects.free_tyre_change
            lap_tyre = (
                TyreSet(decision.compound, 0)
                if free_change and decision.compound is not None
                else state.tyre
            )
            lap_reference_ms = (
                physical_lap_ms_by_id[state.driver_id]
                if physical_lap_ms_by_id
                else adjusted_reference_ms(
                    entrant.reference_lap_time_ms, driver_attributes
                )
            )
            surface_water = (
                lap_surface_water[lap - 1]
                if lap_surface_water is not None and lap - 1 < len(lap_surface_water)
                else 0.0
            )
            lap_weather_ms = (
                weather_penalty_ms(lap_reference_ms, surface_water, weather_effect)
                if surface_water > 0.0
                else 0.0
            )
            in_pit_lane = decision.pit and not free_change
            if refuel_mode and in_pit_lane and lap_fuel is not None:
                assert fuel is not None and state.fuel_kg is not None
                # A volta de entrada so queima ate a entrada dos boxes; no pit
                # lane, a 80 km/h, o consumo e desprezivel. E a mesma distancia
                # que ``must_pit`` exigiu para a decisao.
                lap_fuel = fuel_lap(
                    fuel,
                    fuel_kg=state.fuel_kg,
                    laps_remaining=total_laps - lap + 1,
                    status=control_state.status.value,
                    distance_fraction=min(1.0, fuel.pit_entry_fraction),
                )
                fuel_laps[state.driver_id] = lap_fuel
            fill_kg = 0.0
            stop_ms = None
            if refuel_mode and decision.pit:
                assert fuel is not None and lap_fuel is not None
                wanted_kg = (
                    decision.refuel_kg
                    if decision.refuel_kg is not None
                    else fuel.refuel_target_kg(total_laps - lap) - lap_fuel.end_kg
                )
                fill_kg = min(
                    max(0.0, wanted_kg),
                    fuel.parameters.max_fuel_kg - lap_fuel.end_kg,
                )
                if in_pit_lane:
                    base_ms = (
                        entrant.refuel_stops.loss_ms(state.stops_made)
                        if entrant.refuel_stops is not None
                        else track.pit_loss_ms
                    )
                    stop_ms = base_ms + fuel.stationary_extra_ms(fill_kg)
            breakdown = compute_lap_time(
                reference_ms=lap_reference_ms,
                parameters=parameters,
                track=track,
                tyre=lap_tyre,
                lap_number=lap,
                total_laps=total_laps,
                gap_ahead_ms=gaps.get(state.driver_id),
                pitting=in_pit_lane,
                rng=rng,
                noise_scale=consistency_scale(driver_attributes),
                degradation_factor=detailed_degradation_factor(driver_attributes),
                pit_loss_factor=lap_effects.pit_loss_factor,
                lap_time_factor=lap_effects.lap_time_factor,
                lap_time_loss_ms=lap_effects.lap_time_loss_ms,
                weather_ms=lap_weather_ms,
                noise_label=(f"detailed-race:lap:{lap}:{state.driver_id}:lap-noise"),
                fuel_ms=lap_fuel.fuel_ms if lap_fuel is not None else None,
                pit_ms=stop_ms,
            )
            if refuel_mode and decision.pit:
                refuelling[state.driver_id] = (
                    fill_kg,
                    breakdown.pit_ms,
                    "engine" if boxed_by_engine else "strategy",
                )
            proposals[state.driver_id] = (
                state.total_time_ms + breakdown.total_ms,
                in_pit_lane,
                decision.compound,
                free_change,
            )

            if collect_breakdowns:
                row = {
                    "lap": lap,
                    "driver_id": state.driver_id,
                    "reference_ms": round(breakdown.reference_ms, 1),
                    "fuel_ms": round(breakdown.fuel_ms, 1),
                    "tyre_ms": round(breakdown.tyre_ms, 1),
                    "traffic_ms": round(breakdown.traffic_ms, 1),
                    "weather_ms": round(breakdown.weather_ms, 1),
                    "pit_ms": round(breakdown.pit_ms, 1),
                    "noise_ms": round(breakdown.noise_ms, 1),
                    "lap_time_factor": breakdown.lap_time_factor,
                    "lap_time_loss_ms": breakdown.lap_time_loss_ms,
                    "total_ms": round(breakdown.total_ms, 1),
                }
                if lap_fuel is not None:
                    row["fuel_start_kg"] = round(lap_fuel.start_kg, 3)
                    row["fuel_burn_kg"] = round(lap_fuel.burn_kg, 4)
                    row["fuel_saved_kg"] = round(lap_fuel.saved_kg, 4)
                    row["fuel_saving_ms"] = round(lap_fuel.saving_ms, 1)
                    row["refuel_kg"] = round(fill_kg, 3)
                breakdowns.append(row)

        # Quem esta nos boxes, para pneu ou combustivel, nao disputa posicao.
        contenders = [
            (state.driver_id, state.total_time_ms, proposals[state.driver_id][0])
            for state in running
            if not proposals[state.driver_id][1]
        ]
        outcomes = {}
        disputes_enabled = resolve_position_disputes and lap_effects.disputes_enabled
        if disputes_enabled:
            derived_laps = None
            if race_control is not None or dispute_model == "pressure":
                derived_laps = _laps_completed_from_elapsed_time(
                    contenders,
                    states,
                    by_id,
                    used_attributes,
                    physical_lap_ms_by_id or None,
                )
            outcomes = {
                outcome.driver_id: outcome
                for outcome in resolve_disputes(
                    contenders,
                    parameters=parameters,
                    track=track,
                    rng=rng,
                    model=dispute_model,
                    profiles=profiles,
                    heuristics=dispute_heuristics,
                    laps_completed=derived_laps,
                    overtake_factor=lap_effects.overtake_factor,
                    contact_factor=lap_effects.contact_factor,
                )
            }

        for state in running:
            proposed_end, pitting, compound, free_change = proposals[state.driver_id]
            outcome = outcomes.get(state.driver_id)
            state.total_time_ms = outcome.end_time_ms if outcome else proposed_end
            state.laps_completed += 1
            if outcome and outcome.blocked_by:
                state.blocked_laps += 1

            if free_change:
                assert compound is not None
                # O jogo foi montado antes da volta de bandeira vermelha e,
                # portanto, termina a volta com uma volta de uso.
                state.tyre = TyreSet(compound, 1)
                _append_compound(compounds_used[state.driver_id], compound)
            elif pitting:
                assert compound is not None
                state.tyre = TyreSet(compound, 0)
                state.stops_made += 1
                _append_compound(compounds_used[state.driver_id], compound)
            else:
                state.tyre = state.tyre.aged()

            lap_fuel = fuel_laps.get(state.driver_id)
            if lap_fuel is not None:
                assert fuel is not None
                state.fuel_kg = lap_fuel.end_kg
                if lap_fuel.saved_kg > 0.0:
                    state.fuel_saving_laps += 1
                stop = refuelling.get(state.driver_id)
                if stop is not None and stop[0] > 0.0:
                    fill_kg, stop_ms, decided_by = stop
                    refuel_events.append(
                        {
                            "lap": lap,
                            "driver_id": state.driver_id,
                            "fuel_before_kg": round(lap_fuel.end_kg, 3),
                            "added_kg": round(fill_kg, 3),
                            "stop_ms": round(stop_ms, 1),
                            "compound": compound,
                            "decided_by": decided_by,
                        }
                    )
                    state.fuel_kg = lap_fuel.end_kg + fill_kg
                    state.refuels_made += 1

        if lap_effects.freeze_order:
            _freeze_order(states, start_order, parameters.minimum_gap_ms)

        incidents: list[Incident] = []
        if race_control is None:
            # Compatibilidade do caminho opt-in sem controle: mesmo sorteio
            # mecanico, sem rotulo, depois das disputas.
            for state in running:
                entrant = by_id[state.driver_id]
                outcome = outcomes.get(state.driver_id)
                draw = rng.uniform01()
                hazard = (
                    parameters.mechanical_hazard_per_lap() * entrant.reliability_factor
                )
                retired = draw < hazard or (outcome is not None and outcome.collided)
                if retired and lap < total_laps:
                    state.status = RETIRED
                    state.retired_on_lap = lap
                    state.retirement_cause = (
                        CONTACT if outcome and outcome.collided else MECHANICAL
                    )
            # Pane seca depois do sorteio mecanico: nao desloca a sequencia
            # aleatoria e nao sobrescreve uma causa ja atribuida.
            for state in running:
                lap_fuel = fuel_laps.get(state.driver_id)
                if (
                    lap_fuel is not None
                    and lap_fuel.ran_dry
                    and state.status == RUNNING
                    and lap < total_laps
                ):
                    state.status = RETIRED
                    state.retired_on_lap = lap
                    state.retirement_cause = FUEL
        else:
            retirement_causes: dict[str, str] = {}
            contact_pairs = _contact_pairs(contenders, outcomes)
            for first_id, second_id in contact_pairs:
                incidents.append(Incident(lap, "contact", (first_id, second_id)))
            for state in running:
                outcome = outcomes.get(state.driver_id)
                if outcome is not None and outcome.collided:
                    retirement_causes[state.driver_id] = CONTACT

            solo_probability = solo_crash_probability(lap, lap_effects, race_control)
            for state in running:
                draw = rng.uniform01(
                    f"race-control:lap:{lap}:{state.driver_id}:solo-crash"
                )
                if draw < solo_probability:
                    incidents.append(Incident(lap, "solo_crash", (state.driver_id,)))
                    retirement_causes.setdefault(state.driver_id, CRASH)

            for state in running:
                entrant = by_id[state.driver_id]
                draw = rng.uniform01(
                    f"race-control:lap:{lap}:{state.driver_id}:mechanical"
                )
                hazard = (
                    parameters.mechanical_hazard_per_lap() * entrant.reliability_factor
                )
                if draw < hazard:
                    incidents.append(Incident(lap, "mechanical", (state.driver_id,)))
                    retirement_causes.setdefault(state.driver_id, MECHANICAL)

            # Carro sem combustivel para na pista como uma quebra: vira
            # incidente "mechanical" para o controle de prova poder neutralizar.
            for state in running:
                lap_fuel = fuel_laps.get(state.driver_id)
                if (
                    lap_fuel is not None
                    and lap_fuel.ran_dry
                    and lap < total_laps
                    and state.driver_id not in retirement_causes
                ):
                    incidents.append(Incident(lap, "mechanical", (state.driver_id,)))
                    retirement_causes[state.driver_id] = FUEL

            for driver_id, cause in retirement_causes.items():
                state = states[driver_id]
                state.status = RETIRED
                state.retired_on_lap = lap
                state.retirement_cause = cause

            control_state, lap_events = step(
                control_state, incidents, rng, race_control, lap
            )
            control_events.extend(lap_events)

        if lap_effects.compress_field:
            _compress_running_field(states, parameters.minimum_gap_ms)

        history.append(
            {"lap": lap, "cars": _detailed_classification(list(states.values()))}
        )

    classification = history[-1]["cars"] if history else []
    result: dict = {
        "total_laps": total_laps,
        "parameters_version": parameters.version,
        "circuit_id": track.circuit_id,
        "history": history,
        "classification": classification,
        "race_control_events": control_events,
        "race_control_by_lap": control_by_lap,
        "assumptions": _detailed_assumptions(
            used_attributes,
            dispute_model,
            dispute_heuristics,
            race_control,
            fuel,
        ),
    }
    if fuel is not None:
        result["fuel"] = _fuel_summary(fuel, total_laps, start_fuel)
        result["fuel"]["refuel_stops"] = refuel_events
    if collect_breakdowns:
        result["breakdowns"] = breakdowns
    return result


def _prepare_enhanced_race(
    entrants: tuple[Entrant, ...] | list[Entrant],
    total_laps: int,
    parameters: ModelParameters,
    attributes: Mapping[str, DriverAttributes] | None,
) -> tuple[list[Entrant], dict[str, Entrant], dict[str, DriverAttributes]]:
    """Valide o cenario antes do primeiro sorteio e normalize seus mapas."""

    if total_laps <= 0:
        raise ValueError("total_laps deve ser positivo")
    seen: set[str] = set()
    for entrant in entrants:
        if entrant.driver_id in seen:
            raise ValueError(f"driver_id duplicado: {entrant.driver_id}")
        seen.add(entrant.driver_id)
        parameters.compound(entrant.starting_compound)

    used_attributes: dict[str, DriverAttributes] = {}
    if attributes is not None:
        unknown = sorted(set(attributes).difference(seen))
        if unknown:
            raise ValueError(f"attributes contem driver_id desconhecido: {unknown}")
        for driver_id, item in attributes.items():
            if not isinstance(item, DriverAttributes):
                raise ValueError(f"attributes[{driver_id!r}] deve ser DriverAttributes")
            if item.driver_id != driver_id:
                raise ValueError(
                    f"attributes[{driver_id!r}] pertence a {item.driver_id!r}"
                )
            used_attributes[driver_id] = item

    ordered = sorted(entrants, key=lambda entrant: entrant.driver_id)
    return ordered, {entrant.driver_id: entrant for entrant in ordered}, used_attributes


def _laps_completed_from_elapsed_time(
    contenders: list[tuple[str, float, float]],
    states: Mapping[str, CarState],
    entrants: Mapping[str, Entrant],
    attributes: Mapping[str, DriverAttributes],
    physical_lap_ms_by_id: Mapping[str, float] | None = None,
) -> dict[str, int]:
    """Derive voltas relativas do relogio para aplicar a bandeira azul.

    O motor discreto incrementa ``CarState.laps_completed`` igualmente para
    todos os carros ativos, portanto esse contador nao revela retardatarios.
    Aqui um carro e considerado ``N`` voltas atras quando seu tempo acumulado
    excede o do lider em ``N`` vezes a volta de referencia ajustada do lider.
    Isso e uma aproximacao temporal deliberada: sob SC a compressao apaga as
    diferencas e, consequentemente, desdobra retardatarios de forma implicita.
    """

    if not contenders:
        return {}
    leader_id, leader_time_ms, _ = min(contenders, key=lambda row: (row[1], row[0]))
    leader_reference_ms = (
        physical_lap_ms_by_id[leader_id]
        if physical_lap_ms_by_id is not None
        else adjusted_reference_ms(
            entrants[leader_id].reference_lap_time_ms, attributes.get(leader_id)
        )
    )
    leader_laps = states[leader_id].laps_completed
    result: dict[str, int] = {}
    for driver_id, start_time_ms, _ in contenders:
        deficit_laps = floor(
            max(0.0, start_time_ms - leader_time_ms) / leader_reference_ms
        )
        result[driver_id] = max(0, leader_laps - deficit_laps)
    return result


def _append_compound(compounds: list[str], compound: str) -> None:
    """Registre uma troca sem duplicar a permanencia no mesmo composto."""

    if compounds[-1] != compound:
        compounds.append(compound)


def _contact_pairs(
    contenders: list[tuple[str, float, float]],
    outcomes: Mapping[str, object],
) -> tuple[tuple[str, str], ...]:
    """Reconstrua pares de contato inclusive para o desfecho legado.

    O modelo pressure informa ``contact_with`` nos dois resultados. O contrato
    legado informa apenas que o atacante abandonou; nesse caso o defensor e o
    carro imediatamente a frente na ordem do inicio da volta.
    """

    ordered_ids = [
        row[0] for row in sorted(contenders, key=lambda row: (row[1], row[0]))
    ]
    ahead_by_id = {behind: ahead for ahead, behind in zip(ordered_ids, ordered_ids[1:])}
    pairs: set[tuple[str, str]] = set()
    for driver_id, outcome in outcomes.items():
        if not getattr(outcome, "collided", False):
            continue
        other_id = getattr(outcome, "contact_with", None)
        if other_id is None:
            other_id = ahead_by_id.get(driver_id)
        if other_id is not None:
            pairs.add(tuple(sorted((driver_id, other_id))))
    return tuple(sorted(pairs))


def _freeze_order(
    states: Mapping[str, CarState],
    start_order: tuple[str, ...],
    minimum_gap_ms: float,
) -> None:
    """Impeca trocas durante a vermelha sem apagar os intervalos existentes."""

    previous_time_ms: float | None = None
    for driver_id in start_order:
        state = states[driver_id]
        if state.status != RUNNING:
            continue
        if previous_time_ms is not None:
            state.total_time_ms = max(
                state.total_time_ms, previous_time_ms + minimum_gap_ms
            )
        previous_time_ms = state.total_time_ms


def _compress_running_field(
    states: Mapping[str, CarState], minimum_gap_ms: float
) -> None:
    """Agrupe o pelotao como um SC, apagando diferencas acumuladas.

    A ordem e calculada depois das paradas e abandonos da volta, portanto quem
    perdeu tempo nos boxes ja ocupa sua nova posicao. Em seguida cada carro em
    pista recebe ``tempo_lider + k * minimum_gap_ms``. Isso apaga os intervalos
    como o agrupamento real sob SC; como o modelo nao guarda distancia fisica,
    retardatarios se desdobram implicitamente nessa reescrita.
    """

    running = sorted(
        (state for state in states.values() if state.status == RUNNING),
        key=lambda state: (state.total_time_ms, state.driver_id),
    )
    if not running:
        return
    leader_time_ms = running[0].total_time_ms
    for offset, state in enumerate(running):
        state.total_time_ms = leader_time_ms + offset * minimum_gap_ms


def _detailed_assumptions(
    attributes: Mapping[str, DriverAttributes],
    dispute_model: Literal["legacy", "pressure"],
    dispute_heuristics: DisputeHeuristics,
    race_control: RaceControlParameters | None,
    fuel: FuelPlan | None = None,
) -> list[dict]:
    """Exponha somente heuristicas e atributos realmente ativados."""

    assumptions = [
        attributes_assumption(attributes[driver_id]) for driver_id in sorted(attributes)
    ]
    if attributes:
        assumptions.append(
            {
                "kind": "detailed_tyre_management",
                **{
                    item.name: getattr(DETAILED_TYRE_MANAGEMENT, item.name)
                    for item in fields(DETAILED_TYRE_MANAGEMENT)
                },
            }
        )
    if dispute_model == "pressure":
        assumptions.append(
            {
                "kind": "dispute_heuristics",
                **{
                    item.name: getattr(dispute_heuristics, item.name)
                    for item in fields(dispute_heuristics)
                },
            }
        )
    if race_control is not None:
        assumptions.append(
            {
                "kind": "race_control",
                **{
                    item.name: getattr(race_control, item.name)
                    for item in fields(race_control)
                },
            }
        )
    if fuel is not None:
        parameters = fuel.parameters
        assumptions.append(
            {
                "kind": "fuel",
                "parameter_version": parameters.version,
                "calibrated": {
                    "lap_time_fraction_per_fuel_km": (
                        parameters.lap_time_fraction_per_fuel_km
                    ),
                    "origin": parameters.origin,
                    "seasons": list(parameters.provenance.seasons),
                },
                "regulation": {"max_fuel_kg": parameters.max_fuel_kg},
                "assumed": {
                    "burn_kg_per_km": parameters.burn_kg_per_km,
                    "finish_reserve_kg": parameters.finish_reserve_kg,
                    "vsc_burn_factor": parameters.vsc_burn_factor,
                    "sc_burn_factor": parameters.sc_burn_factor,
                    "red_flag_burn_factor": parameters.red_flag_burn_factor,
                    "lift_coast_max_saving_fraction": (
                        parameters.lift_coast_max_saving_fraction
                    ),
                    "lift_coast_ms_per_kg_saved": (
                        parameters.lift_coast_ms_per_kg_saved
                    ),
                },
                "lap_length_source": fuel.lap_length_source,
                "scenario": {
                    "refuelling_allowed": parameters.refuelling_allowed,
                    "origin": "assumed",
                },
                "refuel_stops": _refuel_stops_assumption(parameters.refuel_stops),
            }
        )
    return assumptions


def _refuel_stops_assumption(stops) -> dict | None:
    """Origem do tempo de parada por equipe, quando calibrado."""

    if stops is None:
        return None
    return {
        "origin": stops.origin,
        "seasons": list(stops.provenance.seasons),
        "persistence": stops.persistence,
        "stop_sigma_ms": stops.stop_sigma_ms,
        "stop_skew": stops.stop_skew,
        "teams": len(stops.team_offsets),
    }


def _fuel_summary(
    fuel: FuelPlan, total_laps: int, start_fuel: Mapping[str, float]
) -> dict:
    """Numeros do plano de combustivel para a interface e para auditoria."""

    return {
        "burn_kg_per_lap": round(fuel.burn_kg_per_lap, 4),
        "ms_per_kg": round(fuel.ms_per_kg, 2),
        "lap_length_km": round(fuel.lap_length_km, 3),
        "lap_length_source": fuel.lap_length_source,
        "reference_lap_ms": fuel.reference_lap_ms,
        "max_fuel_kg": fuel.parameters.max_fuel_kg,
        "finish_reserve_kg": fuel.parameters.finish_reserve_kg,
        "range_laps_at_max_fuel": round(fuel.range_laps_at_max_fuel, 1),
        "race_exceeds_fuel_range": total_laps > fuel.range_laps_at_max_fuel,
        "refuelling_allowed": fuel.parameters.refuelling_allowed,
        "start_fuel_kg": {
            driver_id: round(load, 3) for driver_id, load in sorted(start_fuel.items())
        },
    }
