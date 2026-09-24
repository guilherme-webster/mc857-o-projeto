"""Nucleo da simulacao de corrida.

Este modulo expoe dois niveis, deliberadamente:

``simulate_race`` -- a fatia original, deterministica e de ritmo constante. Cada
carro percorre todas as voltas com o mesmo ``lap_time_ms`` e a classificacao
emerge do tempo acumulado. Ela permanece porque e o contrato mais simples
possivel e serve de **linha de base** contra a qual o modelo rico e comparado no
backtest: um modelo mais complexo precisa vencer o ritmo constante para se
justificar.

``simulate_detailed_race`` -- o modelo com combustivel, pneus, trafego, paradas,
abandono e ruido, descrito em ``domain/lap_time.py``. Consome parametros
versionados e uma fonte aleatoria injetada; a mesma semente reproduz a mesma
corrida.

Fronteiras (ADR 0002 / AGENTS.md): o core e a fonte de verdade da classificacao
e nao conhece Arcade, FastAPI, SQLite nem formatos de dados. Tempos em
milissegundos.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from f1_simulator.domain.disputes import resolve_disputes
from f1_simulator.domain.lap_time import LapTimeBreakdown, compute_lap_time
from f1_simulator.domain.model_parameters import ModelParameters, TrackParameters
from f1_simulator.domain.random_source import RandomSource
from f1_simulator.domain.strategy import StrategyState, TyreStrategy
from f1_simulator.domain.tyres import TyreSet

RUNNING = "RUNNING"
RETIRED = "RETIRED"

#: Causa do abandono. Separar as duas importa porque elas tem origens
#: diferentes no modelo: a mecanica e um risco por volta da equipe, o
#: contato so pode surgir de uma disputa de posicao.
MECHANICAL = "MECHANICAL"
CONTACT = "CONTACT"


@dataclass(frozen=True, slots=True)
class Competitor:
    """Um participante e seu unico atributo nesta fatia: o ritmo constante.

    ``lap_time_ms`` e o tempo de volta constante do carro, em milissegundos.
    Deve ser estritamente positivo; pilotos sem ritmo derivavel do ETL nao
    entram na simulacao e devem ser filtrados antes de chegar aqui.
    """

    driver_id: str
    name: str
    lap_time_ms: float


def simulate_race(
    competitors: tuple[Competitor, ...] | list[Competitor],
    total_laps: int,
) -> dict:
    """Simule ``total_laps`` voltas e retorne as posicoes por volta.

    A cada volta, cada carro soma seu ``lap_time_ms`` constante ao tempo total,
    e os carros sao ordenados pelo tempo acumulado (menor tempo = frente). O
    resultado e determinístico e independe da ordem de entrada dos competidores;
    empates de tempo sao desempatados por ``driver_id`` para ser reproduzivel.

    Retorna um dicionario pronto para transporte JSON::

        {
            "total_laps": int,
            "history": [
                {"lap": int, "cars": [
                    {"position", "driver_id", "name", "total_time_ms"}, ...
                ]},
                ...
            ],
            "classification": [ ...mesma forma dos cars da ultima volta... ],
        }

    ``total_laps`` deve ser positivo. Uma lista vazia de competidores produz um
    historico com voltas sem carros, o que mantem o contrato simples e explicito.
    """

    if total_laps <= 0:
        raise ValueError("total_laps deve ser positivo")

    seen: set[str] = set()
    for competitor in competitors:
        if competitor.lap_time_ms <= 0:
            raise ValueError(
                f"lap_time_ms deve ser positivo para {competitor.driver_id}"
            )
        if competitor.driver_id in seen:
            raise ValueError(f"driver_id duplicado: {competitor.driver_id}")
        seen.add(competitor.driver_id)

    totals: dict[str, float] = {c.driver_id: 0.0 for c in competitors}

    history = []
    for lap in range(1, total_laps + 1):
        for competitor in competitors:
            totals[competitor.driver_id] += competitor.lap_time_ms
        history.append({"lap": lap, "cars": _classify(competitors, totals)})

    classification = history[-1]["cars"] if history else []
    return {
        "total_laps": total_laps,
        "history": history,
        "classification": classification,
    }


def _classify(
    competitors: tuple[Competitor, ...] | list[Competitor],
    totals: dict[str, float],
) -> list[dict]:
    """Ordene por tempo acumulado (desempate por driver_id) e atribua posicoes."""

    ordered = sorted(
        competitors, key=lambda c: (totals[c.driver_id], c.driver_id)
    )
    return [
        {
            "position": index,
            "driver_id": competitor.driver_id,
            "name": competitor.name,
            "total_time_ms": round(totals[competitor.driver_id], 1),
            "lap_time_ms": competitor.lap_time_ms,
        }
        for index, competitor in enumerate(ordered, start=1)
    ]


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
    """

    driver_id: str
    name: str
    reference_lap_time_ms: float
    grid_position: int
    strategy: TyreStrategy
    starting_compound: str
    team_id: str | None = None
    reliability_factor: float = 1.0

    def __post_init__(self) -> None:
        if self.reference_lap_time_ms <= 0:
            raise ValueError(
                f"reference_lap_time_ms deve ser positivo para {self.driver_id}"
            )
        if self.grid_position < 1:
            raise ValueError(
                f"grid_position deve ser positivo para {self.driver_id}"
            )
        if self.reliability_factor < 0:
            raise ValueError("reliability_factor nao pode ser negativo")


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
    return [
        {
            "position": index,
            "driver_id": state.driver_id,
            "name": state.name,
            "total_time_ms": round(state.total_time_ms, 1),
            # ``lap_time_ms`` e o tempo medio por volta ate aqui, e nao um ritmo
            # constante. O campo permanece no retrato porque a visualizacao
            # Arcade o usa para interpolar a posicao do carro na pista; mantendo
            # o nome, a interface existente continua funcionando e passa a
            # refletir o modelo novo sem alteracao alguma no frontend.
            "lap_time_ms": round(
                state.total_time_ms / state.laps_completed, 1
            )
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


def simulate_detailed_race(
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
