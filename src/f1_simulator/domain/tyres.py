"""Estado e penalidade de tempo do conjunto de pneus.

O Trotman v128 **nao** registra composto, stint nem idade de pneu. Portanto o
composto aqui e uma decisao do cenario simulado, nao uma observacao recuperada
do dataset. O que foi medido no historico e a degradacao media dentro dos
stints (delimitados pelos pit stops registrados); a separacao dessa degradacao
entre SOFT/MEDIUM/HARD e uma hipotese do grupo, declarada em
``CompoundParameters.origin``.

Consequencia pratica: um relatorio nunca deve afirmar que o simulador
"reproduziu a estrategia de pneus real", porque a estrategia real nao esta
disponivel nesta fonte. Ele pode afirmar que reproduziu o *numero de paradas*,
que esta registrado.
"""

from __future__ import annotations

from dataclasses import dataclass

from f1_simulator.domain.model_parameters import CompoundParameters, TrackParameters


@dataclass(frozen=True, slots=True)
class TyreSet:
    """Um jogo montado no carro: composto e quantas voltas ja rodou.

    ``age_laps`` comeca em zero num jogo novo e e incrementado ao fim de cada
    volta completada. Idade negativa nao existe; ela e sempre consequencia de
    voltas efetivamente percorridas.
    """

    compound: str
    age_laps: int = 0

    def __post_init__(self) -> None:
        if not self.compound:
            raise ValueError("o jogo de pneus precisa de um composto")
        if self.age_laps < 0:
            raise ValueError("age_laps nao pode ser negativo")

    def aged(self) -> "TyreSet":
        """Devolva o mesmo jogo uma volta mais velho (objeto novo, imutavel)."""

        return TyreSet(self.compound, self.age_laps + 1)


def tyre_penalty_ms(
    tyre: TyreSet,
    compound: CompoundParameters,
    track: TrackParameters,
) -> float:
    """Penalidade do jogo em ms, relativa a uma volta de pneu novo de referencia.

    Aplica ``a * idade + b * idade ** 2`` escalado pela severidade do circuito,
    somado ao deslocamento de ritmo do composto. Apenas a degradacao e escalada:
    a diferenca intrinseca entre compostos nao depende do desgaste da pista.

    O resultado pode ser negativo para um composto macio com pneu novo, que e
    genuinamente mais rapido que a referencia. O piso nao negativo vale para a
    soma final do tempo de volta, nao para esta parcela isolada.
    """

    if compound.name != tyre.compound:
        raise ValueError(
            f"parametros do composto {compound.name!r} nao descrevem "
            f"o jogo {tyre.compound!r}"
        )
    age = tyre.age_laps
    wear = compound.degradation_ms_per_lap * age
    wear += compound.degradation_ms_per_lap2 * age * age
    return compound.pace_offset_ms + wear * track.tyre_severity
