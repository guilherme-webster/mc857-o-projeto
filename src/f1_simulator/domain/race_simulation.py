"""Nucleo da simulacao de corrida, em dois niveis.

``simulate_race`` -- o nucleo simples. Por padrao e deterministico: cada carro
percorre todas as voltas a um tempo de volta constante e a posicao emerge do
tempo acumulado. Fontes de variacao opcionais, DESLIGADAS a menos que o chamador
as peca (PRD ``nao-determinismo-pneus-assumidos``): desgaste linear de pneu
(``tyre_plan``), ruido por volta (``variability`` + ``rng``) e atributos de
piloto (``Competitor.attributes``). Esses parametros sao HIPOTESES assumidas e
rotuladas (``source_kind``); o resultado ativo sempre carrega ``assumptions``.
Ele tambem serve de **linha de base** no backtest: um modelo mais complexo
precisa vencer o ritmo constante para se justificar.

``simulate_detailed_race`` -- o modelo do motor calibrado (issue #40), com
combustivel, pneus por composto, trafego, paradas, disputas de posicao, abandono
e ruido, descrito em ``domain/lap_time.py`` e ``domain/disputes.py``. Consome
parametros versionados e uma fonte aleatoria injetada; a mesma semente reproduz
a mesma corrida.

Fronteiras (ADR 0002 / AGENTS.md): o core e a fonte de verdade da classificacao
e nao conhece Arcade, FastAPI, SQLite nem formatos de dados. A aleatoriedade e
sempre injetada (nunca ha sorteio global nem semente escolhida aqui). Tempos em
milissegundos.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from math import floor, isfinite
from typing import Literal

from f1_simulator.domain.attribute_effects import (
    adjusted_reference_ms,
    adjusted_tyre_effect_ms,
    attributes_assumption,
    consistency_scale,
)
from f1_simulator.domain.disputes import (
    DEFAULT_DISPUTE_HEURISTICS,
    DisputeHeuristics,
    DisputeProfile,
    resolve_disputes,
)
from f1_simulator.domain.driver_attributes import DriverAttributes
# O motor detalhado usa a decomposicao de ``lap_time.py``; ela nao e importada
# pelo nome porque este modulo ja define o ``LapTimeBreakdown`` do nucleo simples.
from f1_simulator.domain.lap_time import compute_lap_time
from f1_simulator.domain.model_parameters import ModelParameters, TrackParameters
from f1_simulator.domain.random_source import (
    RandomSource,
    truncated_standard_normal,
)
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
from f1_simulator.domain.strategy import StrategyState, TyreStrategy
from f1_simulator.domain.tyres import (
    ASSUMED_DRY_TYRES,
    TyreModelParameters,
    TyreSet,
    TyreState,
    tyre_effect_ms,
    tyre_parameters_for,
)


NOMINAL_LAP_TIME_MS = 90_000.0
"""Assumed nominal lap reference, in ms, modulated by driver attributes."""

RUNNING = "RUNNING"
RETIRED = "RETIRED"

#: Causa do abandono. Separar as duas importa porque elas tem origens
#: diferentes no modelo: a mecanica e um risco por volta da equipe, o
#: contato so pode surgir de uma disputa de posicao.
MECHANICAL = "MECHANICAL"
CONTACT = "CONTACT"
CRASH = "CRASH"


@dataclass(frozen=True, slots=True)
class Competitor:
    driver_id: str
    name: str
    lap_time_ms: float | None = None
    attributes: DriverAttributes | None = None

    @property
    def reference_lap_time_ms(self) -> float:
        return self.lap_time_ms if self.lap_time_ms is not None else NOMINAL_LAP_TIME_MS


@dataclass(frozen=True, slots=True)
class LapPosition:
    """Estado classificatorio de um carro ao fim de uma volta."""

    position: int
    driver_id: str
    name: str
    total_time_ms: float


@dataclass(frozen=True, slots=True)
class LapTimeBreakdown:
    """Decomposicao do tempo de uma volta, em milissegundos.

    ``reference_ms`` e o ritmo do competidor no ponto de ancoragem. Os outros
    dois componentes valem ``None`` quando a corrida NAO os modela: um efeito
    nao modelado nao e o mesmo que um efeito medido igual a zero, e o
    AGENTS.md proibe preencher ausencia com zero. O tempo da volta soma apenas
    os componentes presentes.
    """

    reference_ms: float
    tyre_effect_ms: float | None
    noise_ms: float | None

    @property
    def lap_time_ms(self) -> float:
        """Some referencia, efeito de pneu e ruido (componentes ausentes valem 0)."""

        total = self.reference_ms
        if self.tyre_effect_ms is not None:
            total += self.tyre_effect_ms
        if self.noise_ms is not None:
            total += self.noise_ms
        return total


@dataclass(frozen=True, slots=True)
class LapVariabilityAssumption:
    """Ruido por volta assumido: dispersao proporcional ao tempo de referencia.

    ``sigma_pct_of_reference`` e o desvio padrao do ruido, em percentual do
    tempo de referencia da volta. ``truncation_sigmas`` limita o sorteio a
    +/- esse numero de desvios (regra documentada e parametrizada, nao um clamp
    escondido). Nao e uma medida calibrada: o MAD dos perfis de pilotos mede
    dispersao observada e NAO pode ser convertido em ruido de simulacao.
    """

    sigma_pct_of_reference: float
    truncation_sigmas: float
    source_kind: Literal["assumed", "estimated"]
    parameter_version: str
    rationale: str

    def __post_init__(self) -> None:
        for name in ("sigma_pct_of_reference", "truncation_sigmas"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name} deve ser positivo e finito")
        for name in ("source_kind", "parameter_version", "rationale"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} deve ser uma string nao vazia")
        if self.source_kind not in ("assumed", "estimated"):
            raise ValueError("source_kind deve ser 'assumed' ou 'estimated'")


ASSUMED_LAP_VARIABILITY = LapVariabilityAssumption(
    sigma_pct_of_reference=0.2,
    truncation_sigmas=3.0,
    source_kind="assumed",
    parameter_version="assumed-lap-noise-v1",
    rationale=(
        "Hipotese assumida, nao calibrada: 0,2% do tempo de referencia, truncada "
        "em 3 desvios. O MAD dos perfis de pilotos mede dispersao observada e "
        "nao pode ser convertido em ruido de simulacao."
    ),
)


def simulate_race(
    competitors: tuple[Competitor, ...] | list[Competitor],
    total_laps: int,
    *,
    tyre_plan: Mapping[str, str] | None = None,
    variability: LapVariabilityAssumption | None = None,
    rng: RandomSource | None = None,
    tyre_catalogue: tuple[TyreModelParameters, ...] = ASSUMED_DRY_TYRES,
) -> dict:
    """Simule ``total_laps`` voltas e retorne as posicoes por volta.

    **Modo padrao** (sem ``tyre_plan`` nem ``variability``): a cada volta, cada
    carro soma seu ``lap_time_ms`` constante ao tempo total, e os carros sao
    ordenados pelo tempo acumulado (menor tempo = frente). O resultado e
    deterministico e independe da ordem de entrada dos competidores; empates de
    tempo sao desempatados por ``driver_id`` para ser reproduzivel.

    **Modo com modelo** (qualquer um dos dois opcionais ativo):

    * ``tyre_plan`` mapeia ``driver_id -> composto``, um composto por corrida e
      SEM pit stop. Deve cobrir TODOS os competidores e nenhum ``driver_id``
      desconhecido (ausencia nunca vira efeito zero). A idade do pneu na volta
      ``k`` e ``k - 1`` (a primeira volta tem idade zero, convencao de
      :mod:`f1_simulator.domain.tyres`). Idade fora da faixa de suporte levanta
      ``ValueError``; nao ha clamp nem extrapolacao.
    * ``variability`` exige ``rng`` e vice-versa: um ``rng`` sem ``variability``
      seria ignorado em silencio, o que esconderia um erro de configuracao.
      O ruido da volta e ``sigma_pct/100 * referencia * z``, com ``z`` normal
      padrao truncada. Para a saida nao depender da ordem de entrada, os sorteios
      seguem voltas crescentes e, dentro de cada volta, ``driver_id`` crescente,
      com a ``label`` ``lap:<volta>:<driver_id>`` (o ``driver_id`` canonico ja
      carrega o prefixo ``driver:``, entao nao ha prefixo repetido).

    Retorna um dicionario pronto para transporte JSON::

        {
            "total_laps": int,
            "history": [
                {"lap": int, "cars": [
                    {"position", "driver_id", "name", "total_time_ms",
                     "lap_time_ms"[, "breakdown"]}, ...
                ]},
                ...
            ],
            "classification": [ ...mesma forma dos cars da ultima volta... ],
            "assumptions": [...],   # somente quando um modelo esta ativo
        }

    No modo padrao a estrutura e exatamente a original (sem ``breakdown`` nem
    ``assumptions``, ``lap_time_ms`` inalterado). No modo com modelo,
    ``lap_time_ms`` e o tempo REAL da volta arredondado a 0,1 ms, tal como
    ``total_time_ms``, e ``breakdown`` traz ``reference_ms``, ``tyre_effect_ms``
    e ``noise_ms`` sem arredondar (``None`` para o que nao foi modelado).
    ``assumptions`` lista, de forma ordenada, os parametros usados com seu
    ``source_kind`` para que nada assumido seja lido como calibrado.

    A aritmetica e em ``float`` (decisao D1 do PRD): a unificacao de precisao com
    ``Decimal`` fica para quando os perfis entrarem no motor.

    ``total_laps`` deve ser positivo. Uma lista vazia de competidores produz um
    historico com voltas sem carros, o que mantem o contrato simples e explicito.
    """

    if total_laps <= 0:
        raise ValueError("total_laps deve ser positivo")

    seen: set[str] = set()
    for competitor in competitors:
        if competitor.reference_lap_time_ms <= 0:
            raise ValueError(
                f"reference lap time must be positive for {competitor.driver_id}"
            )
        if competitor.driver_id in seen:
            raise ValueError(f"duplicate driver_id: {competitor.driver_id}")
        seen.add(competitor.driver_id)

    if variability is not None and rng is None:
        raise ValueError("variability exige um rng injetado")
    if rng is not None and variability is None:
        raise ValueError(
            "rng informado sem variability: o sorteio seria ignorado em silencio"
        )

    tyre_parameters = _resolve_tyre_parameters(
        competitors, tyre_plan, tyre_catalogue, total_laps
    )
    has_attributes = any(c.attributes is not None for c in competitors)
    model_active = (
        tyre_plan is not None or variability is not None or has_attributes
    )

    totals: dict[str, float] = {c.driver_id: 0.0 for c in competitors}

    # Ordem canonica dos sorteios: independe da ordem de entrada dos competidores.
    draw_order = sorted(competitors, key=lambda c: c.driver_id)

    history = []
    for lap in range(1, total_laps + 1):
        lap_times: dict[str, float] = {}
        breakdowns: dict[str, LapTimeBreakdown] = {}
        for competitor in draw_order:
            if model_active:
                breakdown = _lap_breakdown(
                    competitor,
                    lap,
                    tyre_parameters.get(competitor.driver_id),
                    variability,
                    rng,
                )
                lap_time = breakdown.lap_time_ms
                if not isfinite(lap_time) or lap_time <= 0:
                    raise ValueError(
                        f"tempo de volta nao positivo ou invalido para "
                        f"{competitor.driver_id} na volta {lap}: {lap_time}"
                    )
                breakdowns[competitor.driver_id] = breakdown
            else:
                lap_time = competitor.reference_lap_time_ms
            lap_times[competitor.driver_id] = lap_time
            totals[competitor.driver_id] += lap_time
        history.append(
            {
                "lap": lap,
                "cars": _classify(
                    competitors, totals, lap_times, breakdowns, model_active
                ),
            }
        )

    classification = history[-1]["cars"] if history else []
    result: dict = {
        "total_laps": total_laps,
        "history": history,
        "classification": classification,
    }
    if model_active:
        result["assumptions"] = _assumptions(
            tyre_parameters, variability, competitors
        )
    return result


def _resolve_tyre_parameters(
    competitors: tuple[Competitor, ...] | list[Competitor],
    tyre_plan: Mapping[str, str] | None,
    catalogue: tuple[TyreModelParameters, ...],
    total_laps: int,
) -> dict[str, TyreModelParameters]:
    """Valide o plano de pneus e resolva os parametros de cada competidor.

    Falha cedo, antes de qualquer volta: plano incompleto, ``driver_id``
    desconhecido, composto fora do catalogo ou corrida mais longa que o suporte
    do pneu. Sem plano, devolve um mapa vazio (nenhum pneu e modelado).
    """

    if tyre_plan is None:
        return {}

    known_ids = {c.driver_id for c in competitors}
    planned_ids = set(tyre_plan)
    unknown = sorted(planned_ids - known_ids)
    if unknown:
        raise ValueError(f"tyre_plan com driver_id desconhecido: {unknown}")
    missing = sorted(known_ids - planned_ids)
    if missing:
        raise ValueError(
            f"tyre_plan deve cobrir todos os competidores; faltam: {missing}"
        )

    resolved: dict[str, TyreModelParameters] = {}
    for driver_id in sorted(known_ids):
        parameters = tyre_parameters_for(tyre_plan[driver_id], catalogue)
        # Sem pit stop, a idade cresce ate total_laps - 1: precisa caber no suporte.
        if total_laps - 1 > parameters.max_age_laps:
            raise ValueError(
                f"corrida de {total_laps} voltas excede o suporte do pneu "
                f"{parameters.compound} para {driver_id} "
                f"(idade maxima {parameters.max_age_laps})"
            )
        resolved[driver_id] = parameters
    return resolved


def _lap_breakdown(
    competitor: Competitor,
    lap: int,
    tyre_parameters: TyreModelParameters | None,
    variability: LapVariabilityAssumption | None,
    rng: RandomSource | None,
) -> LapTimeBreakdown:
    """Componha o tempo de uma volta; o que nao e modelado permanece ``None``."""

    attributes = competitor.attributes
    reference = adjusted_reference_ms(competitor.reference_lap_time_ms, attributes)

    tyre_effect: float | None = None
    if tyre_parameters is not None:
        state = TyreState(tyre_parameters.compound, lap - 1)
        tyre_effect = adjusted_tyre_effect_ms(
            tyre_effect_ms(tyre_parameters, state), attributes
        )

    noise: float | None = None
    if variability is not None and rng is not None:
        z = truncated_standard_normal(
            rng,
            f"lap:{lap}:{competitor.driver_id}",
            variability.truncation_sigmas,
        )
        noise = (
            variability.sigma_pct_of_reference / 100.0
            * reference
            * consistency_scale(attributes)
            * z
        )

    return LapTimeBreakdown(reference, tyre_effect, noise)


def _assumptions(
    tyre_parameters: Mapping[str, TyreModelParameters],
    variability: LapVariabilityAssumption | None,
    competitors: tuple[Competitor, ...] | list[Competitor],
) -> list[dict]:
    """Liste, em ordem deterministica, os parametros assumidos realmente usados."""

    items: list[dict] = []
    by_compound = {p.compound: p for p in tyre_parameters.values()}
    for compound in sorted(by_compound):
        parameters = by_compound[compound]
        items.append(
            {
                "kind": "tyre",
                "compound": parameters.compound,
                "source_kind": parameters.source_kind,
                "parameter_version": parameters.parameter_version,
                "rationale": parameters.rationale,
                "anchor_age_laps": parameters.anchor_age_laps,
                "min_age_laps": parameters.min_age_laps,
                "max_age_laps": parameters.max_age_laps,
                "linear_ms_per_lap": parameters.linear_ms_per_lap,
            }
        )
    if variability is not None:
        items.append(
            {
                "kind": "lap_variability",
                "source_kind": variability.source_kind,
                "parameter_version": variability.parameter_version,
                "rationale": variability.rationale,
                "sigma_pct_of_reference": variability.sigma_pct_of_reference,
                "truncation_sigmas": variability.truncation_sigmas,
            }
        )
    for competitor in sorted(competitors, key=lambda c: c.driver_id):
        if competitor.attributes is not None:
            items.append(attributes_assumption(competitor.attributes))
    return items


def _classify(
    competitors: tuple[Competitor, ...] | list[Competitor],
    totals: dict[str, float],
    lap_times: dict[str, float],
    breakdowns: dict[str, LapTimeBreakdown],
    model_active: bool,
) -> list[dict]:
    """Ordene por tempo acumulado (desempate por driver_id) e atribua posicoes.

    No modo padrao, ``lap_time_ms`` e o valor original do competidor, sem
    arredondar; no modo com modelo, e o tempo real da volta a 0,1 ms.
    """

    ordered = sorted(
        competitors, key=lambda c: (totals[c.driver_id], c.driver_id)
    )
    cars = []
    for index, competitor in enumerate(ordered, start=1):
        lap_time = lap_times[competitor.driver_id]
        car = {
            "position": index,
            "driver_id": competitor.driver_id,
            "name": competitor.name,
            "total_time_ms": round(totals[competitor.driver_id], 1),
            "lap_time_ms": round(lap_time, 1) if model_active else lap_time,
        }
        if model_active:
            breakdown = breakdowns[competitor.driver_id]
            car["breakdown"] = {
                "reference_ms": breakdown.reference_ms,
                "tyre_effect_ms": breakdown.tyre_effect_ms,
                "noise_ms": breakdown.noise_ms,
            }
        cars.append(car)
    return cars


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
    attributes: Mapping[str, DriverAttributes] | None = None,
    dispute_model: Literal["legacy", "pressure"] = "legacy",
    dispute_heuristics: DisputeHeuristics = DEFAULT_DISPUTE_HEURISTICS,
    race_control: RaceControlParameters | None = None,
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
    """

    if dispute_model not in ("legacy", "pressure"):
        raise ValueError("dispute_model deve ser 'legacy' ou 'pressure'")
    enhanced = (
        attributes is not None
        or dispute_model == "pressure"
        or race_control is not None
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
    """

    ordered_entrants, by_id, used_attributes = _prepare_enhanced_race(
        entrants, total_laps, parameters, attributes
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
                parameters.grid_penalty_ms_per_position
                * (entrant.grid_position - 1)
            ),
            tyre=TyreSet(entrant.starting_compound),
        )
        for entrant in ordered_entrants
    }
    compounds_used = {
        entrant.driver_id: [entrant.starting_compound]
        for entrant in ordered_entrants
    }

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
        for state in running:
            entrant = by_id[state.driver_id]
            driver_attributes = used_attributes.get(state.driver_id)
            neutralization = (
                control_state.status.value
                if control_state.status in (SC, VSC)
                else None
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
                )
            )
            free_change = decision.pit and lap_effects.free_tyre_change
            lap_tyre = (
                TyreSet(decision.compound, 0)
                if free_change and decision.compound is not None
                else state.tyre
            )
            breakdown = compute_lap_time(
                reference_ms=adjusted_reference_ms(
                    entrant.reference_lap_time_ms, driver_attributes
                ),
                parameters=parameters,
                track=track,
                tyre=lap_tyre,
                lap_number=lap,
                total_laps=total_laps,
                gap_ahead_ms=gaps.get(state.driver_id),
                pitting=decision.pit and not free_change,
                rng=rng,
                noise_scale=consistency_scale(driver_attributes),
                degradation_factor=(
                    driver_attributes.tyre_management_factor
                    if driver_attributes is not None
                    else 1.0
                ),
                pit_loss_factor=lap_effects.pit_loss_factor,
                lap_time_factor=lap_effects.lap_time_factor,
                lap_time_loss_ms=lap_effects.lap_time_loss_ms,
                noise_label=(
                    f"detailed-race:lap:{lap}:{state.driver_id}:lap-noise"
                ),
            )
            proposals[state.driver_id] = (
                state.total_time_ms + breakdown.total_ms,
                decision.pit and not free_change,
                decision.compound,
                free_change,
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
                        "lap_time_factor": breakdown.lap_time_factor,
                        "lap_time_loss_ms": breakdown.lap_time_loss_ms,
                        "total_ms": round(breakdown.total_ms, 1),
                    }
                )

        contenders = [
            (state.driver_id, state.total_time_ms, proposals[state.driver_id][0])
            for state in running
            if not proposals[state.driver_id][1]
        ]
        outcomes = {}
        disputes_enabled = (
            resolve_position_disputes and lap_effects.disputes_enabled
        )
        if disputes_enabled:
            derived_laps = None
            if race_control is not None or dispute_model == "pressure":
                derived_laps = _laps_completed_from_elapsed_time(
                    contenders, states, by_id, used_attributes
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
                    parameters.mechanical_hazard_per_lap()
                    * entrant.reliability_factor
                )
                retired = draw < hazard or (
                    outcome is not None and outcome.collided
                )
                if retired and lap < total_laps:
                    state.status = RETIRED
                    state.retired_on_lap = lap
                    state.retirement_cause = (
                        CONTACT if outcome and outcome.collided else MECHANICAL
                    )
        else:
            retirement_causes: dict[str, str] = {}
            contact_pairs = _contact_pairs(contenders, outcomes)
            for first_id, second_id in contact_pairs:
                incidents.append(
                    Incident(lap, "contact", (first_id, second_id))
                )
            for state in running:
                outcome = outcomes.get(state.driver_id)
                if outcome is not None and outcome.collided:
                    retirement_causes[state.driver_id] = CONTACT

            solo_probability = solo_crash_probability(
                lap, lap_effects, race_control
            )
            for state in running:
                draw = rng.uniform01(
                    f"race-control:lap:{lap}:{state.driver_id}:solo-crash"
                )
                if draw < solo_probability:
                    incidents.append(
                        Incident(lap, "solo_crash", (state.driver_id,))
                    )
                    retirement_causes.setdefault(state.driver_id, CRASH)

            for state in running:
                entrant = by_id[state.driver_id]
                draw = rng.uniform01(
                    f"race-control:lap:{lap}:{state.driver_id}:mechanical"
                )
                hazard = (
                    parameters.mechanical_hazard_per_lap()
                    * entrant.reliability_factor
                )
                if draw < hazard:
                    incidents.append(
                        Incident(lap, "mechanical", (state.driver_id,))
                    )
                    retirement_causes.setdefault(state.driver_id, MECHANICAL)

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
        ),
    }
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
                raise ValueError(
                    f"attributes[{driver_id!r}] deve ser DriverAttributes"
                )
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
    leader_id, leader_time_ms, _ = min(
        contenders, key=lambda row: (row[1], row[0])
    )
    leader_reference_ms = adjusted_reference_ms(
        entrants[leader_id].reference_lap_time_ms, attributes.get(leader_id)
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
    ahead_by_id = {
        behind: ahead for ahead, behind in zip(ordered_ids, ordered_ids[1:])
    }
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
) -> list[dict]:
    """Exponha somente heuristicas e atributos realmente ativados."""

    assumptions = [
        attributes_assumption(attributes[driver_id])
        for driver_id in sorted(attributes)
    ]
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
    return assumptions
