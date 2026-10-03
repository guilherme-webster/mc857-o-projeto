"""Politica de pneus e paradas (padrao Strategy, plano secao 5.2).

A interface e a prevista no plano: ``decide(state) -> PitDecision``. Manter a
decisao atras de uma porta permite rodar o mesmo cenario com politicas
diferentes sem alterar o motor, que e exatamente o caso de uso citado na tabela
de padroes do plano.

Nenhuma implementacao aqui le banco, consulta HTTP ou sorteia numero: a decisao
e uma funcao pura do estado visivel da corrida.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from f1_simulator.domain.model_parameters import ModelParameters
from f1_simulator.domain.tyres import TyreSet


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
    """Estado visivel a politica no fim de uma volta.

    Deliberadamente estreito: a politica ve o proprio carro e o relogio da
    corrida, nao a classificacao inteira. Ampliar isso exigiria um caso de uso
    concreto (por exemplo, reagir a um undercut), ainda fora do MVP.
    """

    lap_number: int
    total_laps: int
    tyre: TyreSet
    stops_made: int


class TyreStrategy(Protocol):
    """Porta de decisao de parada consumida pelo motor."""

    def decide(self, state: StrategyState) -> PitDecision:
        """Decida parar ou seguir ao fim da volta ``state.lap_number``."""
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
