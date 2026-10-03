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
from math import isfinite
from typing import Literal, Protocol

from f1_simulator.domain.model_parameters import ModelParameters, TrackParameters
from f1_simulator.domain.tyres import TyreSet, tyre_penalty_ms


_DEFAULT_DRY_COMPOUNDS = ("SOFT", "MEDIUM", "HARD")
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
    """

    pit: bool
    compound: str | None = None

    def __post_init__(self) -> None:
        if self.pit and not self.compound:
            raise ValueError("uma parada precisa declarar o composto de destino")


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
        if state.tyre.age_laps >= life:
            return PitDecision(True, self._next_compound)
        return PitDecision(False)


class HeuristicPitStrategy:
    """Decida paradas secas pelo custo acumulado de pneus ate o fim.

    A regra economica compara dois cenarios de uma unica decisao: continuar com
    o jogo atual ate a bandeirada ou fazer uma parada agora e terminar com um
    jogo novo. Numa parada normal, a volta corrente e a volta de entrada e ainda
    usa o pneu antigo, exatamente como ``simulate_detailed_race``; o jogo novo
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

    Nas ultimas voltas configuradas, uma parada normal e recusada. A excecao de
    seguranca ocorre quando o jogo ja ultrapassou sua vida tipica por mais que
    toda essa janela: usar o proprio tamanho da janela evita esconder outro
    limiar heuristico fora do objeto de parametros.
    """

    __slots__ = (
        "_dry_compounds",
        "_heuristics",
        "_offset_laps",
        "_parameters",
        "_track",
        "_tyre_management_factor",
    )

    def __init__(
        self,
        parameters: ModelParameters,
        track: TrackParameters,
        heuristics: HeuristicPitParameters = DEFAULT_HEURISTIC_PIT_PARAMETERS,
        tyre_management_factor: float = 1.0,
        offset_laps: int = 0,
        dry_compounds: Sequence[str] = _DEFAULT_DRY_COMPOUNDS,
    ) -> None:
        """Construa uma politica pura e valide todo o catalogo antes da corrida."""

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

        self._parameters = parameters
        self._track = track
        self._heuristics = heuristics
        self._tyre_management_factor = float(tyre_management_factor)
        self._offset_laps = offset_laps
        self._dry_compounds = compounds

    def decide(self, state: StrategyState) -> PitDecision:
        """Decida a parada sem sortear nem manter estado interno mutavel."""

        if state.tyre.compound not in self._dry_compounds:
            raise ValueError(
                f"composto atual {state.tyre.compound!r} nao pertence a "
                "dry_compounds"
            )
        unknown_used = sorted(
            set(state.compounds_used).difference(self._dry_compounds)
        )
        if unknown_used:
            raise ValueError(
                f"compounds_used contem compostos fora de dry_compounds: "
                f"{unknown_used}"
            )
        if state.lap_number >= state.total_laps:
            return PitDecision(False)

        used = frozenset((*state.compounds_used, state.tyre.compound))
        needs_second_compound = len(used) < 2
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

        decision_age_laps = max(0, state.tyre.age_laps - self._offset_laps)
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

    def _adjusted_tyre_penalty_ms(self, compound: str, age_laps: int) -> float:
        """Aplique gestao a degradacao sem distorcer o ritmo do composto novo."""

        compound_parameters = self._parameters.compound(compound)
        raw_penalty_ms = tyre_penalty_ms(
            TyreSet(compound, age_laps), compound_parameters, self._track
        )
        degradation_ms = raw_penalty_ms - compound_parameters.pace_offset_ms
        return (
            compound_parameters.pace_offset_ms
            + degradation_ms * self._tyre_management_factor
        )

    def _old_tyre_cost_ms(
        self, state: StrategyState, decision_age_laps: int
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
        decision_age_laps: int,
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
        decision_age_laps: int,
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
        self, state: StrategyState, decision_age_laps: int
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
        self, state: StrategyState, decision_age_laps: int
    ) -> bool:
        life_laps = self._parameters.compound(
            state.tyre.compound
        ).typical_stint_laps
        return decision_age_laps > (
            life_laps + self._heuristics.final_laps_without_pit
        )
