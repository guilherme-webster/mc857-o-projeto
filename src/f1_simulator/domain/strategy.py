"""Politica de pneus e paradas (padrao Strategy, plano secao 5.2).

A interface e a prevista no plano: ``decide(state) -> PitDecision``. Manter a
decisao atras de uma porta permite rodar o mesmo cenario com politicas
diferentes sem alterar o motor, que e exatamente o caso de uso citado na tabela
de padroes do plano.

Nenhuma implementacao aqui le banco, consulta HTTP ou sorteia numero: a decisao
e uma funcao pura do estado visivel da corrida.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil, floor, isfinite
from typing import Literal, Protocol

from f1_simulator.domain.fuel import FuelPlan
from f1_simulator.domain.model_parameters import ModelParameters, TrackParameters
from f1_simulator.domain.random_source import RandomSource
from f1_simulator.domain.tyres import TyreSet, tyre_penalty_ms
from f1_simulator.domain.wet_tyres import (
    ASSUMED_WET_TYRES,
    SLICK,
    WET_COMPOUNDS,
    WetTyreParameters,
    best_tyre_class,
    relative_grip,
    tyre_class,
    wet_compound_used,
)


_DEFAULT_DRY_COMPOUNDS = ("SOFT", "MEDIUM", "HARD")

#: Tolerancia de ponto flutuante para comparar massas de combustivel (kg).
_KG_TOLERANCE = 1e-9
_HEURISTIC_PIT_RATIONALE = (
    "Hipotese heuristica, nao calibrada: compara a degradacao acumulada ate o "
    "fim com a perda de boxes, aproveita neutralizacoes e preserva a regra de "
    "dois compostos secos."
)


@dataclass(frozen=True, slots=True)
class PitDecision:
    """Resultado da politica para a volta corrente.

    ``pit`` falso mantem o jogo atual e ignora ``compound``. ``pit`` verdadeiro
    exige um composto de destino, porque parar sem trocar pneu nao e um cenario
    que este modelo represente.

    ``refuel_kg`` e quanto combustivel colocar nesta parada, quando o
    reabastecimento esta ligado. ``None`` deixa o motor encher para terminar
    a corrida (estrategias que nao olham o combustivel); ``0.0`` e uma parada
    so de pneus porque o tanque ja cobre o resto.
    """

    pit: bool
    compound: str | None = None
    refuel_kg: float | None = None

    def __post_init__(self) -> None:
        if self.pit and not self.compound:
            raise ValueError("uma parada precisa declarar o composto de destino")
        if self.refuel_kg is not None:
            if not self.pit:
                raise ValueError("refuel_kg so faz sentido numa parada")
            if (
                isinstance(self.refuel_kg, bool)
                or not isinstance(self.refuel_kg, (int, float))
                or not isfinite(self.refuel_kg)
                or self.refuel_kg < 0
            ):
                raise ValueError("refuel_kg deve ser nao negativo e finito")


@dataclass(frozen=True, slots=True)
class FuelStatus:
    """O que o piloto sabe do combustivel ao decidir a volta.

    So e entregue a estrategia quando o reabastecimento esta ligado; sem ele
    o combustivel nao e uma decisao de parada. ``fuel_kg`` e a massa no
    inicio da volta e ``lap_burn_kg`` a queima desta volta, ja com o estado
    da pista (SC queima menos). ``stop_loss_ms`` e a perda media de uma parada
    *deste* carro (perda do circuito mais o deslocamento da equipe), com a
    troca de pneus incluida; o tempo de abastecer alem disso vem do plano.
    """

    plan: FuelPlan
    fuel_kg: float
    lap_burn_kg: float
    stop_loss_ms: float

    def __post_init__(self) -> None:
        if not isinstance(self.plan, FuelPlan):
            raise ValueError("plan deve ser FuelPlan")
        for name in ("fuel_kg", "lap_burn_kg", "stop_loss_ms"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{name} deve ser nao negativo e finito")

    @property
    def end_kg(self) -> float:
        """Massa ao fim desta volta, se ela for completada."""

        return max(0.0, self.fuel_kg - self.lap_burn_kg)


@dataclass(frozen=True, slots=True)
class FuelStrategyTraits:
    """Como um piloto (e sua equipe) trata o combustivel; heuristica.

    ``margin_laps`` e a folga, em voltas verdes, que o piloto quer ter ao
    chegar aos boxes: quem e cauteloso para antes, quem arrisca chega quase
    vazio. ``stop_cost_bias`` multiplica a perda das paradas *futuras* ao
    escolher quantas fazer: abaixo de 1 o piloto prefere mais paradas e carro
    leve, acima de 1 prefere menos paradas e tanque cheio. ``stint_shift``
    encurta (negativo) ou alonga (positivo) o proximo stint planejado, como
    fracao do stint igual: quem gosta de undercut para cedo, quem prefere
    overcut estica. E isso que tira todos os carros da mesma volta de parada.
    Os valores sao sorteados por piloto pela composicao do cenario; nao sao
    medidos.
    """

    margin_laps: float
    stop_cost_bias: float
    stint_shift: float = 0.0
    origin: Literal["heuristic"] = "heuristic"
    parameter_version: str = "heuristic-fuel-strategy-v1"

    def __post_init__(self) -> None:
        for name, low, high in (
            ("margin_laps", 0.0, 2.0),
            ("stop_cost_bias", 0.1, 3.0),
            ("stint_shift", -0.5, 0.5),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or not low <= value <= high
            ):
                raise ValueError(f"{name} deve estar em [{low}, {high}]")
        if self.origin != "heuristic":
            raise ValueError("origin deve ser 'heuristic'")


NEUTRAL_FUEL_TRAITS = FuelStrategyTraits(margin_laps=0.5, stop_cost_bias=1.0)
"""Piloto medio: meia volta de folga e custo de parada sem vies."""


@dataclass(frozen=True, slots=True)
class FuelTraitHeuristics:
    """Como a agressividade do piloto e o acaso viram ``FuelStrategyTraits``.

    ``margin = base - por_agressividade * (agressividade - 1) + ruido * z1``,
    ``vies = 1 - por_agressividade * (agressividade - 1) + ruido * z2`` e
    ``desvio = -por_agressividade * (agressividade - 1) + ruido * z3``,
    limitados a faixas plausiveis. O piloto agressivo chega mais vazio,
    prefere carro leve com mais paradas e para mais cedo; o ruido faz dois
    pilotos com o mesmo perfil decidirem diferente. A folga nunca fica abaixo
    de ``margin_floor_laps``: nem o piloto mais ousado chega aos boxes seco.
    Hipotese do grupo, nao calibrada.
    """

    margin_base_laps: float = 0.5
    margin_per_aggression_laps: float = 0.5
    margin_noise_laps: float = 0.2
    margin_floor_laps: float = 0.2
    bias_per_aggression: float = 0.5
    bias_noise: float = 0.15
    shift_per_aggression: float = 0.2
    shift_noise: float = 0.12
    origin: Literal["heuristic"] = "heuristic"
    parameter_version: str = "heuristic-fuel-traits-v1"


DEFAULT_FUEL_TRAIT_HEURISTICS = FuelTraitHeuristics()


def draw_fuel_traits(
    aggression: float,
    rng: RandomSource,
    label: str,
    heuristics: FuelTraitHeuristics = DEFAULT_FUEL_TRAIT_HEURISTICS,
) -> FuelStrategyTraits:
    """Sorteie as preferencias de combustivel de um piloto (tres sorteios)."""

    deviation = aggression - 1.0
    margin = (
        heuristics.margin_base_laps
        - heuristics.margin_per_aggression_laps * deviation
        + heuristics.margin_noise_laps * rng.standard_normal(f"{label}:margin")
    )
    bias = (
        1.0
        - heuristics.bias_per_aggression * deviation
        + heuristics.bias_noise * rng.standard_normal(f"{label}:stop-bias")
    )
    shift = (
        -heuristics.shift_per_aggression * deviation
        + heuristics.shift_noise * rng.standard_normal(f"{label}:stint-shift")
    )
    return FuelStrategyTraits(
        margin_laps=min(1.5, max(heuristics.margin_floor_laps, margin)),
        stop_cost_bias=min(1.5, max(0.5, bias)),
        stint_shift=min(0.3, max(-0.3, shift)),
    )


#: Quanto a agressividade e o acaso mudam o vies de troca por chuva (#120).
WEATHER_SWITCH_BIAS_PER_AGGRESSION = 0.6
WEATHER_SWITCH_BIAS_NOISE = 0.2


def draw_weather_switch_bias(
    aggression: float, rng: RandomSource, label: str
) -> float:
    """Sorteie o vies de troca por chuva de um piloto (um sorteio).

    Multiplica o custo da parada na comparacao com a perda do pneu errado:
    acima de 1 o piloto aposta e fica mais tempo com o pneu atual (slick na
    garoa, intermediario na pista secando); abaixo de 1 troca cedo. O
    agressivo aposta mais; o ruido separa pilotos do mesmo perfil. Heuristica,
    nao calibrada.
    """

    bias = (
        1.0
        + WEATHER_SWITCH_BIAS_PER_AGGRESSION * (aggression - 1.0)
        + WEATHER_SWITCH_BIAS_NOISE * rng.standard_normal(f"{label}:switch-bias")
    )
    return min(2.0, max(0.5, bias))


@dataclass(frozen=True, slots=True)
class StrategyState:
    """Estado visivel a politica antes de decidir a volta ``lap_number``.

    Deliberadamente estreito: a politica ve o proprio carro e o relogio da
    corrida, nao a classificacao inteira. Ampliar isso exigiria um caso de uso
    concreto (por exemplo, reagir a um undercut), ainda fora do MVP.

    ``tyre.age_laps`` conta voltas concluidas antes da decisao. Numa parada
    normal, a volta decidida e a entrada dos boxes e o jogo novo estreia na
    proxima; numa troca gratuita de bandeira vermelha, ele pode estrear ja na
    volta decidida. Essa distincao e necessaria para a fatia que integrar a
    estrategia ao controle de corrida nao cobrar uma parada ficticia.
    """

    lap_number: int
    total_laps: int
    tyre: TyreSet
    stops_made: int
    neutralization: str | None = None
    pit_loss_factor: float = 1.0
    compounds_used: tuple[str, ...] = ()
    free_tyre_change: bool = False
    fuel: FuelStatus | None = None
    tyre_wear_laps: float | None = None

    @property
    def effective_tyre_age(self) -> float:
        """Desgaste acumulado no 2D; idade em voltas no caminho por volta."""

        return self.tyre.age_laps if self.tyre_wear_laps is None else self.tyre_wear_laps

    #: Agua na pista (0-1) prevista para a volta decidida (o radar da
    #: equipe); ``None`` desliga a decisao por clima (contrato anterior).
    surface_water: float | None = None

    def __post_init__(self) -> None:
        """Valide somente o contexto novo, preservando o contrato legado.

        ``lap_number``, ``total_laps`` e ``stops_made`` nao eram validados por
        este objeto antes desta extensao. Mudar agora a faixa aceita por eles
        alteraria, sem necessidade, as tres estrategias preexistentes.
        """

        if self.neutralization not in (None, "SC", "VSC"):
            raise ValueError("neutralization deve ser None, 'SC' ou 'VSC'")
        if (
            isinstance(self.pit_loss_factor, bool)
            or not isinstance(self.pit_loss_factor, (int, float))
            or not isfinite(self.pit_loss_factor)
            or self.pit_loss_factor < 0
        ):
            raise ValueError("pit_loss_factor deve ser nao negativo e finito")
        if any(
            not isinstance(compound, str) or not compound
            for compound in self.compounds_used
        ):
            raise ValueError("compounds_used deve conter nomes nao vazios")
        if type(self.free_tyre_change) is not bool:
            raise ValueError("free_tyre_change deve ser bool")
        if self.fuel is not None and not isinstance(self.fuel, FuelStatus):
            raise ValueError("fuel deve ser FuelStatus")
        if self.tyre_wear_laps is not None and (
            isinstance(self.tyre_wear_laps, bool)
            or not isinstance(self.tyre_wear_laps, (int, float))
            or not isfinite(self.tyre_wear_laps)
            or self.tyre_wear_laps < 0
        ):
            raise ValueError("tyre_wear_laps deve ser finito e não negativo")
        if self.surface_water is not None and (
            isinstance(self.surface_water, bool)
            or not isinstance(self.surface_water, (int, float))
            or not isfinite(self.surface_water)
            or not 0.0 <= self.surface_water <= 1.0
        ):
            raise ValueError("surface_water deve estar em [0, 1]")


@dataclass(frozen=True, slots=True)
class HeuristicPitParameters:
    """Coeficientes assumidos da politica economica de paradas.

    ``decision_margin_ms`` evita trocar por uma vantagem marginal, sensivel a
    arredondamentos e a efeitos que o modelo ainda nao representa.
    ``opportunistic_remaining_life_fraction`` define quanta vida tipica pode
    restar para uma parada oportunista sob SC/VSC. As ultimas
    ``final_laps_without_pit`` voltas formam uma zona sem parada normal; o mesmo
    valor e o excesso sobre a vida tipica que caracteriza a excecao de
    seguranca. ``driver_variation_amplitude_laps`` limita o offset inteiro que
    a fatia de composicao pode sortear fora desta classe.

    Todos os coeficientes sao heuristicas explicitamente versionadas. Nenhum
    valor deste objeto deve ser apresentado como estimativa do Trotman ou do
    FastF1.
    """

    decision_margin_ms: float
    opportunistic_remaining_life_fraction: float
    final_laps_without_pit: int
    driver_variation_amplitude_laps: int
    origin: Literal["heuristic"] = "heuristic"
    parameter_version: str = "heuristic-pit-v1"
    rationale: str = _HEURISTIC_PIT_RATIONALE

    def __post_init__(self) -> None:
        if (
            isinstance(self.decision_margin_ms, bool)
            or not isinstance(self.decision_margin_ms, (int, float))
            or not isfinite(self.decision_margin_ms)
            or self.decision_margin_ms < 0
        ):
            raise ValueError("decision_margin_ms deve ser nao negativo e finito")
        fraction = self.opportunistic_remaining_life_fraction
        if (
            isinstance(fraction, bool)
            or not isinstance(fraction, (int, float))
            or not isfinite(fraction)
            or not 0.0 <= fraction <= 1.0
        ):
            raise ValueError(
                "opportunistic_remaining_life_fraction deve estar em [0, 1]"
            )
        for name in (
            "final_laps_without_pit",
            "driver_variation_amplitude_laps",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} deve ser um inteiro nao negativo")
        if self.origin != "heuristic":
            raise ValueError("origin deve ser 'heuristic'")
        for name in ("parameter_version", "rationale"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} deve ser uma string nao vazia")


DEFAULT_HEURISTIC_PIT_PARAMETERS = HeuristicPitParameters(
    decision_margin_ms=1_500.0,
    opportunistic_remaining_life_fraction=0.25,
    final_laps_without_pit=3,
    driver_variation_amplitude_laps=2,
)


@dataclass(frozen=True, slots=True)
class SpatialPitPlanningParameters:
    """Planeje a troca obrigatória por desgaste, antes do último prazo comum.

    O orçamento equivale à fração da corrida em voltas neutras de carga. O
    desgaste real determina quando o carro o atinge; a preferência individual
    usa o offset já existente, sorteado na composição. Não força voltas únicas:
    carros com decisões semelhantes ainda podem parar juntos, como sob SC.
    """

    compulsory_change_fraction: float = 0.5
    origin: Literal["heuristic"] = "heuristic"
    parameter_version: str = "spatial-pit-planning-v1"

    def __post_init__(self) -> None:
        value = self.compulsory_change_fraction
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or not 0 < value < 1
        ):
            raise ValueError("compulsory_change_fraction deve estar em (0, 1)")
        if (
            self.origin != "heuristic"
            or not isinstance(self.parameter_version, str)
            or not self.parameter_version.strip()
        ):
            raise ValueError("planejamento dos boxes exige origem heurística e versão")

    def wear_target(self, total_laps: int) -> float:
        """Orçamento antes da volta de entrada, sem antecipar o desgaste dela."""

        if type(total_laps) is not int or total_laps < 1:
            raise ValueError("total_laps deve ser positivo")
        return max(0.0, total_laps * self.compulsory_change_fraction - 1.0)
"""Hipotese padrao versionada para a estrategia; nao e calibracao empirica."""


class TyreStrategy(Protocol):
    """Porta de decisao de parada consumida pelo motor."""

    def decide(self, state: StrategyState) -> PitDecision:
        """Decida parar ou seguir na volta ``state.lap_number``."""
        ...


class NoStopStrategy:
    """Nunca para. Util para isolar o efeito de pneu/combustivel nos testes."""

    __slots__ = ()

    def decide(self, state: StrategyState) -> PitDecision:
        return PitDecision(False)


class PlannedStopStrategy:
    """Divide a corrida em stints de comprimento aproximadamente igual.

    Com ``stops=2`` numa corrida de 60 voltas, as paradas caem por volta das
    voltas 20 e 40. E a politica mais simples que reproduz o padrao historico
    dominante (uma a tres paradas) sem precisar do dado de composto, que o
    Trotman nao fornece.

    A ultima volta nunca recebe parada: trocar pneu para cruzar a linha nao faz
    sentido e distorceria a comparacao de tempo total.

    ``offset_laps`` desloca a janela deste carro. Ele e essencial, e nao um
    detalhe: com todos os carros parando na mesma volta, a perda de boxes vira
    um deslocamento comum e nao muda posicao alguma. Equipes reais escalonam
    as paradas, e o historico mostra desvio tipico de cerca de seis voltas.
    """

    __slots__ = ("_compounds", "_offset_laps", "_stops")

    def __init__(
        self,
        stops: int,
        compounds: tuple[str, ...],
        offset_laps: int = 0,
    ) -> None:
        if stops < 0:
            raise ValueError("stops nao pode ser negativo")
        if stops and len(compounds) < stops:
            raise ValueError(
                f"{stops} paradas exigem ao menos {stops} compostos, "
                f"recebido {len(compounds)}"
            )
        self._stops = stops
        self._compounds = compounds
        self._offset_laps = offset_laps

    def decide(self, state: StrategyState) -> PitDecision:
        if self._stops == 0 or state.stops_made >= self._stops:
            return PitDecision(False)
        if state.lap_number >= state.total_laps:
            return PitDecision(False)
        window = state.total_laps / (self._stops + 1)
        target = round(window * (state.stops_made + 1)) + self._offset_laps
        target = max(2, min(target, state.total_laps - 1))
        if state.lap_number >= target:
            return PitDecision(True, self._compounds[state.stops_made])
        return PitDecision(False)


class TyreLifeStrategy:
    """Para quando o jogo atinge a vida tipica do composto.

    Reage ao estado do pneu em vez de seguir um calendario fixo, o que a torna
    sensivel a ``tyre_severity`` do circuito. Respeita ``max_stops`` para nao
    degenerar numa corrida de paradas infinitas caso a vida tipica seja curta.
    """

    __slots__ = ("_max_stops", "_next_compound", "_parameters")

    def __init__(
        self,
        parameters: ModelParameters,
        next_compound: str,
        max_stops: int = 3,
    ) -> None:
        parameters.compound(next_compound)  # valida cedo, nao na volta 40
        self._parameters = parameters
        self._next_compound = next_compound
        self._max_stops = max_stops

    def decide(self, state: StrategyState) -> PitDecision:
        if state.stops_made >= self._max_stops:
            return PitDecision(False)
        if state.lap_number >= state.total_laps:
            return PitDecision(False)
        life = self._parameters.compound(state.tyre.compound).typical_stint_laps
        if state.effective_tyre_age >= life:
            return PitDecision(True, self._next_compound)
        return PitDecision(False)


class HeuristicPitStrategy:
    """Decida paradas secas pelo custo acumulado de pneus ate o fim.

    A regra economica compara dois cenarios de uma unica decisao: continuar com
    o jogo atual ate a bandeirada ou fazer uma parada agora e terminar com um
    jogo novo. Numa parada normal, a volta corrente e a volta de entrada e ainda
    usa o pneu antigo, exatamente como ``simulate_2d_race``; o jogo novo
    passa a valer na volta seguinte. Uma troca gratuita por bandeira vermelha
    disponibiliza o jogo novo imediatamente e nao soma perda de boxes.

    ``dry_compounds`` e uma preferencia ordenada do mais macio ao mais duro. O
    primeiro composto cuja vida tipica cobre o restante e escolhido; se nenhum
    cobre, vence o de maior vida tipica. Enquanto a regra de dois compostos nao
    tiver sido cumprida, o composto corrente e excluido dessa escolha.

    ``tyre_management_factor`` multiplica somente a degradacao, nunca o
    ``pace_offset_ms`` intrinseco do composto. Valores maiores que 1 antecipam
    a parada; valores menores a adiam. ``offset_laps`` desloca a idade observada
    apenas para a decisao (positivo adia, negativo antecipa) e deve ter sido
    sorteado pelo consumidor dentro da amplitude declarada. Assim, ``decide``
    nao consome aleatoriedade e e deterministico para o mesmo estado.

    ``compulsory_wear_target_laps`` permite ao 2D planejar a troca obrigatória
    por exposição acumulada antes do prazo final. ``None`` mantém a política
    por volta; o orçamento não altera o desgaste real nem exige voltas únicas.

    Nas ultimas voltas configuradas, uma parada normal e recusada. A excecao de
    seguranca ocorre quando o jogo ja ultrapassou sua vida tipica por mais que
    toda essa janela: usar o proprio tamanho da janela evita esconder outro
    limiar heuristico fora do objeto de parametros.

    Com reabastecimento (``state.fuel`` presente), pneus e combustivel viram
    uma decisao so, porque toda parada faz as duas coisas:

    - se o tanque ja cobre ate a bandeirada, vale a regra de pneus acima e a
      parada, se houver, nao reabastece;
    - se o carro nao chegaria a proxima entrada dos boxes com a folga do
      piloto (``FuelStrategyTraits.margin_laps``), ele para agora;
    - senao, compara parar agora com parar na ultima volta possivel. Cada
      cenario soma, ate o fim: desgaste do pneu atual, peso do combustivel
      carregado, a parada (perda do carro x fator do SC/VSC, mais o tempo de
      abastecer alem da troca de pneus) e o resto da corrida planejado por
      ``_plan_rest``. Para agora se isso for mais barato pela margem de
      decisao. Sob SC/VSC a parada fica mais barata e a comparacao tende a
      antecipa-la, sem regra separada.

    ``_plan_rest`` escolhe quantos stints fazer no resto da corrida (o minimo
    que o tanque permite, ate duas paradas a mais), com stints iguais, e dai
    saem o composto e quanto abastecer agora. O vies de custo de parada do
    piloto entra so nessa escolha: e ele que separa quem prefere carro leve e
    mais paradas de quem prefere tanque cheio.
    """

    __slots__ = (
        "_dry_compounds",
        "_fuel_traits",
        "_heuristics",
        "_offset_laps",
        "_parameters",
        "_reference_lap_ms",
        "_track",
        "_tyre_management_factor",
        "_compulsory_wear_target_laps",
        "_weather_switch_bias",
        "_wet_tyres",
    )

    def __init__(
        self,
        parameters: ModelParameters,
        track: TrackParameters,
        heuristics: HeuristicPitParameters = DEFAULT_HEURISTIC_PIT_PARAMETERS,
        tyre_management_factor: float = 1.0,
        offset_laps: int = 0,
        dry_compounds: Sequence[str] = _DEFAULT_DRY_COMPOUNDS,
        fuel_traits: FuelStrategyTraits = NEUTRAL_FUEL_TRAITS,
        compulsory_wear_target_laps: float | None = None,
        *,
        wet_tyres: WetTyreParameters = ASSUMED_WET_TYRES,
        reference_lap_ms: float = 90_000.0,
        weather_switch_bias: float = 1.0,
    ) -> None:
        """Construa uma politica pura e valide todo o catalogo antes da corrida.

        ``reference_lap_ms`` converte a perda de aderencia do pneu errado em
        tempo por volta na decisao por clima; ``weather_switch_bias`` e o vies
        do piloto (:func:`draw_weather_switch_bias`).
        """

        if (
            isinstance(tyre_management_factor, bool)
            or not isinstance(tyre_management_factor, (int, float))
            or not isfinite(tyre_management_factor)
            or tyre_management_factor <= 0
        ):
            raise ValueError("tyre_management_factor deve ser positivo e finito")
        if type(offset_laps) is not int:
            raise ValueError("offset_laps deve ser um inteiro verdadeiro")
        if abs(offset_laps) > heuristics.driver_variation_amplitude_laps:
            raise ValueError(
                "offset_laps excede driver_variation_amplitude_laps"
            )

        if isinstance(dry_compounds, str):
            raise ValueError("dry_compounds deve ser uma sequencia de nomes")
        compounds = tuple(dry_compounds)
        if len(compounds) < 2:
            raise ValueError("dry_compounds deve conter ao menos dois compostos")
        if any(
            not isinstance(compound, str) or not compound
            for compound in compounds
        ):
            raise ValueError("dry_compounds deve conter nomes nao vazios")
        if len(set(compounds)) != len(compounds):
            raise ValueError("dry_compounds nao pode conter duplicatas")
        for compound in compounds:
            parameters.compound(compound)
        if not isinstance(fuel_traits, FuelStrategyTraits):
            raise ValueError("fuel_traits deve ser FuelStrategyTraits")
        if compulsory_wear_target_laps is not None and (
            isinstance(compulsory_wear_target_laps, bool)
            or not isinstance(compulsory_wear_target_laps, (int, float))
            or not isfinite(compulsory_wear_target_laps)
            or compulsory_wear_target_laps < 0
        ):
            raise ValueError("compulsory_wear_target_laps deve ser finito e não negativo")
        for name, value in (
            ("reference_lap_ms", reference_lap_ms),
            ("weather_switch_bias", weather_switch_bias),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name} deve ser positivo e finito")
        if set(compounds) & set(WET_COMPOUNDS):
            raise ValueError("dry_compounds nao pode conter pneus de chuva")
        for compound in WET_COMPOUNDS:
            parameters.compound(compound)

        self._parameters = parameters
        self._track = track
        self._heuristics = heuristics
        self._tyre_management_factor = float(tyre_management_factor)
        self._offset_laps = offset_laps
        self._dry_compounds = compounds
        self._fuel_traits = fuel_traits
        self._compulsory_wear_target_laps = compulsory_wear_target_laps
        self._wet_tyres = wet_tyres
        self._reference_lap_ms = float(reference_lap_ms)
        self._weather_switch_bias = float(weather_switch_bias)

    def decide(self, state: StrategyState) -> PitDecision:
        """Decida a parada sem sortear nem manter estado interno mutavel.

        Com ``state.surface_water``, o clima vem primeiro: se o pneu montado
        nao e o melhor para a agua atual e a perda prevista paga a parada, o
        carro para para o composto certo (:meth:`_weather_switch`). Paradas
        por desgaste ou combustivel com a pista molhada montam o pneu de chuva
        indicado, e nao um slick. Com pneu de chuva montado, nao ha parada por
        desgaste: a vida tipica cobre o que resta de uma fase molhada.
        """

        known = (*self._dry_compounds, *WET_COMPOUNDS)
        if state.tyre.compound not in known:
            raise ValueError(
                f"composto atual {state.tyre.compound!r} nao pertence a "
                "dry_compounds nem aos pneus de chuva"
            )
        unknown_used = sorted(set(state.compounds_used).difference(known))
        if unknown_used:
            raise ValueError(
                f"compounds_used contem compostos fora de dry_compounds: "
                f"{unknown_used}"
            )
        if state.lap_number >= state.total_laps:
            return PitDecision(False)
        wet_class = None
        if state.surface_water is not None:
            switch = self._weather_switch(state)
            if switch is not None:
                return switch
            best = best_tyre_class(state.surface_water, self._wet_tyres)
            wet_class = None if best == SLICK else best
        if state.fuel is not None:
            decision = self._decide_with_fuel(state, state.fuel)
        elif state.tyre.compound in WET_COMPOUNDS:
            decision = PitDecision(False)
        else:
            decision = self._decide_tyres(state)
        if decision.pit and wet_class is not None and decision.compound != wet_class:
            decision = PitDecision(True, wet_class, decision.refuel_kg)
        return decision

    def _needs_second_compound(self, state: StrategyState) -> bool:
        """Regra de dois compostos secos, suspensa se houve pneu de chuva."""

        used = (*state.compounds_used, state.tyre.compound)
        if wet_compound_used(used):
            return False
        return len(frozenset(used)) < 2

    def _weather_switch(self, state: StrategyState) -> PitDecision | None:
        """Pare para o composto da agua atual quando a perda paga a parada.

        A perda por volta do pneu errado vem da aderencia relativa
        (``relative_grip``) pela sensibilidade da pista mediana
        (``aderencia ** -0,6``), vezes a volta de referencia. A decisao supoe
        que a condicao dura ``switch_horizon_laps`` voltas (ou o que resta) e
        compara com a perda de boxes do circuito, barateada por SC/VSC e
        multiplicada pelo vies do piloto. Troca gratuita (vermelha) sempre
        compensa.
        """

        assert state.surface_water is not None
        water = state.surface_water
        best = best_tyre_class(water, self._wet_tyres)
        if tyre_class(state.tyre.compound) == best:
            return None
        remaining = state.total_laps - state.lap_number
        if remaining < 1:
            return None
        if best == SLICK:
            target = self._next_compound(remaining, state.tyre.compound, False)
        else:
            target = best
        if state.free_tyre_change:
            return PitDecision(True, target)
        grip = relative_grip(state.tyre.compound, water, self._wet_tyres)
        loss_per_lap_ms = self._reference_lap_ms * (grip ** -0.6 - 1.0)
        horizon = min(remaining, self._wet_tyres.switch_horizon_laps)
        stop_cost_ms = (
            self._track.pit_loss_ms * state.pit_loss_factor * self._weather_switch_bias
        )
        if loss_per_lap_ms * horizon > stop_cost_ms:
            return PitDecision(True, target)
        return None

    def _decide_tyres(self, state: StrategyState) -> PitDecision:
        """Regra so de pneus: e o comportamento sem reabastecimento."""

        needs_second_compound = self._needs_second_compound(state)
        remaining_after_current = state.total_laps - state.lap_number
        next_compound = self._next_compound(
            remaining_after_current, state.tyre.compound, needs_second_compound
        )

        # A volta imediatamente anterior a zona sem paradas e a ultima chance
        # deterministica de cumprir a regra de dois compostos secos.
        last_regular_pit_lap = min(
            state.total_laps - 1,
            state.total_laps - self._heuristics.final_laps_without_pit,
        )
        if needs_second_compound and state.lap_number == last_regular_pit_lap:
            return PitDecision(True, next_compound)

        decision_age_laps = max(0, state.effective_tyre_age - self._offset_laps)
        if state.free_tyre_change:
            if self._free_change_is_convenient(
                state, decision_age_laps, next_compound
            ):
                return PitDecision(True, next_compound)
            return PitDecision(False)

        in_final_no_pit_window = (
            remaining_after_current
            < self._heuristics.final_laps_without_pit
        )
        if in_final_no_pit_window and not self._is_extreme_overlife(
            state, decision_age_laps
        ):
            return PitDecision(False)

        # No 2D, planejar o composto obrigatório por exposição real evita
        # que todos aguardem o mesmo prazo final apesar de desgastes distintos.
        # None preserva exatamente a política do motor por volta.
        if (
            needs_second_compound
            and self._compulsory_wear_target_laps is not None
            and decision_age_laps >= self._compulsory_wear_target_laps
        ):
            return PitDecision(True, next_compound)

        if state.neutralization in ("SC", "VSC") and self._is_opportunistic(
            state, decision_age_laps
        ):
            return PitDecision(True, next_compound)

        if self._old_tyre_cost_ms(state, decision_age_laps) > (
            self._normal_stop_cost_ms(state, decision_age_laps, next_compound)
            + self._heuristics.decision_margin_ms
        ):
            return PitDecision(True, next_compound)
        return PitDecision(False)

    def _next_compound(
        self,
        remaining_after_current: int,
        current_compound: str,
        needs_second_compound: bool,
    ) -> str:
        """Escolha macio no sprint final e duro quando o horizonte for longo."""

        candidates = tuple(
            compound
            for compound in self._dry_compounds
            if not needs_second_compound or compound != current_compound
        )
        for compound in candidates:
            if (
                self._parameters.compound(compound).typical_stint_laps
                >= remaining_after_current
            ):
                return compound
        return max(
            candidates,
            key=lambda compound: self._parameters.compound(
                compound
            ).typical_stint_laps,
        )

    def _adjusted_tyre_penalty_ms(self, compound: str, age_laps: float) -> float:
        """Aplique gestao a degradacao sem distorcer o ritmo do composto novo."""

        compound_parameters = self._parameters.compound(compound)
        raw_penalty_ms = tyre_penalty_ms(
            TyreSet(compound, 0), compound_parameters, self._track, wear_laps=age_laps
        )
        degradation_ms = raw_penalty_ms - compound_parameters.pace_offset_ms
        return (
            compound_parameters.pace_offset_ms
            + degradation_ms * self._tyre_management_factor
        )

    def _old_tyre_cost_ms(
        self, state: StrategyState, decision_age_laps: float
    ) -> float:
        remaining_including_current = state.total_laps - state.lap_number + 1
        return sum(
            self._adjusted_tyre_penalty_ms(
                state.tyre.compound, decision_age_laps + age_delta
            )
            for age_delta in range(remaining_including_current)
        )

    def _normal_stop_cost_ms(
        self,
        state: StrategyState,
        decision_age_laps: float,
        next_compound: str,
    ) -> float:
        """Some volta de entrada, perda de boxes e voltas do jogo novo."""

        current_lap_ms = self._adjusted_tyre_penalty_ms(
            state.tyre.compound, decision_age_laps
        )
        new_tyre_ms = sum(
            self._adjusted_tyre_penalty_ms(next_compound, age_laps)
            for age_laps in range(state.total_laps - state.lap_number)
        )
        pit_loss_ms = self._track.pit_loss_ms * state.pit_loss_factor
        return current_lap_ms + new_tyre_ms + pit_loss_ms

    def _free_change_is_convenient(
        self,
        state: StrategyState,
        decision_age_laps: float,
        next_compound: str,
    ) -> bool:
        """Compare a troca de bandeira vermelha, efetiva antes da proxima volta."""

        remaining_including_current = state.total_laps - state.lap_number + 1
        new_tyre_ms = sum(
            self._adjusted_tyre_penalty_ms(next_compound, age_laps)
            for age_laps in range(remaining_including_current)
        )
        return self._old_tyre_cost_ms(state, decision_age_laps) > (
            new_tyre_ms + self._heuristics.decision_margin_ms
        )

    def _is_opportunistic(
        self, state: StrategyState, decision_age_laps: float
    ) -> bool:
        life_laps = self._parameters.compound(
            state.tyre.compound
        ).typical_stint_laps
        remaining_life_laps = life_laps - decision_age_laps
        return remaining_life_laps <= (
            life_laps
            * self._heuristics.opportunistic_remaining_life_fraction
        )

    def _is_extreme_overlife(
        self, state: StrategyState, decision_age_laps: float
    ) -> bool:
        life_laps = self._parameters.compound(
            state.tyre.compound
        ).typical_stint_laps
        return decision_age_laps > (
            life_laps + self._heuristics.final_laps_without_pit
        )

    # ------------------------------------------------------------------
    # Pneus e combustivel juntos (reabastecimento ligado)
    # ------------------------------------------------------------------

    def plan_start_fuel_kg(
        self,
        plan: FuelPlan,
        total_laps: int,
        starting_compound: str,
        stop_loss_ms: float,
    ) -> float:
        """Carga de largada que o piloto escolhe: a do primeiro stint planejado.

        Com reabastecimento, largar com a corrida inteira no tanque so vale se
        o peso extra custar menos que as paradas evitadas; o mesmo planejador
        das paradas decide isso, com o composto de largada fixo e a regra de
        dois compostos ainda por cumprir.
        """

        status = FuelStatus(plan, 0.0, 0.0, stop_loss_ms)
        _, load_kg, _ = self._plan_rest(
            status,
            0.0,
            total_laps,
            starting_compound,
            needs_second=True,
            first_compound=starting_compound,
        )
        return load_kg

    def _decide_with_fuel(
        self, state: StrategyState, fuel: FuelStatus
    ) -> PitDecision:
        """Decida parada e abastecimento juntos; veja a docstring da classe."""

        plan = fuel.plan
        burn_kg = plan.burn_kg_per_lap
        end_kg = fuel.end_kg
        laps_after = state.total_laps - state.lap_number
        reserve_kg = plan.parameters.finish_reserve_kg
        margin_kg = self._fuel_traits.margin_laps * burn_kg
        needs_second = self._needs_second_compound(state)

        # O tanque ja cobre ate a bandeirada: so o pneu decide, e uma parada
        # eventual nao abastece.
        if end_kg - reserve_kg >= burn_kg * laps_after - _KG_TOLERANCE:
            tyres = self._decide_tyres(state)
            if tyres.pit:
                return PitDecision(True, tyres.compound, refuel_kg=0.0)
            return tyres

        # Vermelha (parada gratis) ou nao chegaria a proxima entrada dos boxes
        # com a folga do piloto: para agora.
        if state.free_tyre_change or plan.must_pit(
            end_kg, state.lap_number, state.total_laps, margin_kg
        ):
            return self._fuel_stop(state, fuel, needs_second)

        # Ultima volta em cujo fim ainda da para entrar nos boxes com a folga.
        latest = state.lap_number + 1 + floor(
            (end_kg - margin_kg - plan.fuel_to_reach_pit_kg) / burn_kg
        )
        latest = min(latest, state.total_laps - 1)
        if latest <= state.lap_number:
            return self._fuel_stop(state, fuel, needs_second)
        stop_now_ms = self._stop_scenario_cost_ms(
            state, fuel, state.lap_number, needs_second, state.pit_loss_factor
        )
        stop_late_ms = self._stop_scenario_cost_ms(
            state, fuel, latest, needs_second, 1.0
        )
        if stop_now_ms + self._heuristics.decision_margin_ms < stop_late_ms:
            return self._fuel_stop(state, fuel, needs_second)
        return PitDecision(False)

    def _fuel_stop(
        self, state: StrategyState, fuel: FuelStatus, needs_second: bool
    ) -> PitDecision:
        """Parada agora: composto e abastecimento do primeiro stint planejado."""

        _, fill_kg, compound = self._plan_rest(
            fuel,
            fuel.end_kg,
            state.total_laps - state.lap_number,
            state.tyre.compound,
            needs_second,
        )
        return PitDecision(True, compound, refuel_kg=fill_kg)

    def _stop_scenario_cost_ms(
        self,
        state: StrategyState,
        fuel: FuelStatus,
        stop_lap: int,
        needs_second: bool,
        pit_loss_factor: float,
    ) -> float:
        """Custo, da proxima volta ao fim, de parar ao fim de ``stop_lap``.

        A volta corrente e igual nos dois cenarios e fica de fora. Ate a
        parada o carro segue no pneu atual (idade deslocada pelo
        ``offset_laps`` do piloto) e com o combustivel atual; a massa e
        cobrada acima da reserva ao fim de cada volta, a mesma ancora do
        motor.
        """

        plan = fuel.plan
        burn_kg = plan.burn_kg_per_lap
        reserve_kg = plan.parameters.finish_reserve_kg
        mass_kg = fuel.end_kg
        age = max(0, state.effective_tyre_age - self._offset_laps)
        cost_ms = 0.0
        for _ in range(state.lap_number + 1, stop_lap + 1):
            age += 1
            mass_kg = max(0.0, mass_kg - burn_kg)
            cost_ms += self._adjusted_tyre_penalty_ms(state.tyre.compound, age)
            cost_ms += plan.ms_per_kg * max(0.0, mass_kg - reserve_kg)
        rest_ms, fill_kg, _ = self._plan_rest(
            fuel,
            mass_kg,
            state.total_laps - stop_lap,
            state.tyre.compound,
            needs_second,
        )
        return (
            cost_ms
            + fuel.stop_loss_ms * pit_loss_factor
            + plan.stationary_extra_ms(fill_kg)
            + rest_ms
        )

    def _plan_rest(
        self,
        fuel: FuelStatus,
        mass_kg: float,
        laps_left: int,
        current_compound: str,
        needs_second: bool,
        first_compound: str | None = None,
    ) -> tuple[float, float, str]:
        """Plano do resto da corrida a partir de uma parada agora.

        Devolve ``(custo_ms, abastecer_kg, composto)`` do plano mais barato
        entre o menor numero de stints que o tanque permite e ate duas paradas
        a mais. Stints iguais (a sobra vai para os primeiros); cada um enche
        para suas voltas mais a folga do piloto, ou a reserva no ultimo. O
        custo soma desgaste do composto escolhido para o stint, peso do
        combustivel e as paradas seguintes, estas com o vies do piloto.
        """

        plan = fuel.plan
        burn_kg = plan.burn_kg_per_lap
        reserve_kg = plan.parameters.finish_reserve_kg
        margin_kg = self._fuel_traits.margin_laps * burn_kg
        cap_kg = plan.parameters.max_fuel_kg
        if laps_left <= 0:
            return 0.0, 0.0, current_compound
        longest = max(1, floor((cap_kg - max(margin_kg, reserve_kg)) / burn_kg))
        fewest = ceil(laps_left / longest)

        best: tuple[float, float, str] | None = None
        for stints in range(fewest, min(laps_left, fewest + 2) + 1):
            lengths = self._stint_lengths(laps_left, stints, longest)
            cost_ms = 0.0
            previous = current_compound
            need = needs_second
            first_load_kg = 0.0
            first_choice = current_compound
            arrive_kg = 0.0
            for index, laps in enumerate(lengths):
                last = index == stints - 1
                load_kg = min(
                    cap_kg, laps * burn_kg + (reserve_kg if last else margin_kg)
                )
                if index == 0 and first_compound is not None:
                    compound = first_compound
                else:
                    compound = self._next_compound(laps, previous, need)
                need = need and compound == previous
                cost_ms += sum(
                    self._adjusted_tyre_penalty_ms(compound, age)
                    for age in range(laps)
                )
                cost_ms += sum(
                    plan.ms_per_kg * max(0.0, load_kg - lap * burn_kg - reserve_kg)
                    for lap in range(1, laps + 1)
                )
                if index == 0:
                    first_load_kg, first_choice = load_kg, compound
                else:
                    cost_ms += fuel.stop_loss_ms * self._fuel_traits.stop_cost_bias
                    cost_ms += plan.stationary_extra_ms(max(0.0, load_kg - arrive_kg))
                arrive_kg = max(0.0, load_kg - laps * burn_kg)
                previous = compound
            if best is None or cost_ms < best[0]:
                best = (cost_ms, max(0.0, first_load_kg - mass_kg), first_choice)
        assert best is not None
        return best

    def _stint_lengths(self, laps_left: int, stints: int, longest: int) -> list[int]:
        """Stints quase iguais, com o primeiro deslocado pela preferencia.

        ``stint_shift`` move o proximo stint (e so ele) em fracao do stint
        igual; o resto e repartido igualmente. Os limites mantem todo stint
        com ao menos uma volta e dentro do que o tanque permite.
        """

        equal = [
            laps_left // stints + (1 if index < laps_left % stints else 0)
            for index in range(stints)
        ]
        if stints == 1 or self._fuel_traits.stint_shift == 0.0:
            return equal
        rest = stints - 1
        first = round(equal[0] * (1.0 + self._fuel_traits.stint_shift))
        first = max(1, max(laps_left - rest * longest, min(first, longest)))
        first = min(first, laps_left - rest)
        remaining = laps_left - first
        return [first] + [
            remaining // rest + (1 if index < remaining % rest else 0)
            for index in range(rest)
        ]
