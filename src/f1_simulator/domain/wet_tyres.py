"""Pneus de chuva: aderencia por composto conforme a agua na pista (issue #120).

A camada de pista (``track_condition``, ADR 0015) diz quanta aderencia a pista
oferece **com o pneu adequado** a cada nivel de agua. Esta camada diz quanto
pior e o pneu que o carro esta usando, comparado ao melhor composto para aquela
agua. O produto das duas e a aderencia do carro.

Cada classe de pneu tem uma curva de aderencia absoluta contra a agua (0 =
seco, 1 = saturada), em pontos interpolados linearmente:

- **slick** (macio, medio e duro): o melhor no seco, perde rapido com agua;
- **intermediario**: um pouco pior no seco, o melhor na pista umida;
- **chuva**: lento no seco, o melhor com agua acumulada.

As curvas passam pelas ancoras da pista (0,81 na umida com intermediario, 0,69
saturada com pneu de chuva). Os cruzamentos emergem delas: slick ->
intermediario com agua ~0,07 e intermediario -> chuva com ~0,39. Fora do seu
ponto, o pneu de chuva superaquece e gasta mais.

Parametros ``assumed``: ordem de grandeza, nao medidos. O Trotman nao registra
composto, e o export FastF1 de 2023-2024 que motivou as ancoras ainda nao tem
proveniencia registrada.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Literal

SLICK = "SLICK"
INTERMEDIATE = "INTERMEDIATE"
WET = "WET"
WET_COMPOUNDS = (INTERMEDIATE, WET)

Curve = tuple[tuple[float, float], ...]


def _check_curve(name: str, curve: Curve) -> None:
    waters = [w for w, _ in curve]
    if not curve or waters[0] != 0.0 or waters[-1] != 1.0:
        raise ValueError(f"{name} deve ir da agua 0 a 1")
    if waters != sorted(set(waters)):
        raise ValueError(f"{name} precisa de agua estritamente crescente")
    if any(not isfinite(g) or not 0 < g <= 1.2 for _, g in curve):
        raise ValueError(f"{name} tem aderencia fora de (0, 1,2]")


def _interpolate(curve: Curve, water: float) -> float:
    for (w0, g0), (w1, g1) in zip(curve, curve[1:]):
        if water <= w1:
            return g0 + (water - w0) / (w1 - w0) * (g1 - g0)
    return curve[-1][1]


@dataclass(frozen=True, slots=True)
class WetTyreParameters:
    """Hipoteses de aderencia, desgaste, risco e decisao com pista molhada.

    ``*_curve``: pares ``(agua, aderencia absoluta)``.

    Superaquecimento: abaixo de ``overheat_water`` o pneu de chuva gasta
    ``1 + ganho * falta_de_agua_relativa`` vezes mais.

    Risco: o acidente individual escala com ``1 + crash_water_gain * agua`` e,
    com o pneu errado, com ``1 + crash_wrong_tyre_gain * (1 - aderencia
    relativa)``; a compostura do piloto (habilidade na chuva) divide o efeito
    da agua. O contato em disputa escala com ``1 + contact_water_gain * agua``.

    Decisao: a estrategia supoe que a condicao atual dura
    ``switch_horizon_laps`` voltas ao comparar a perda com o pneu atual e o
    custo da parada.
    """

    slick_curve: Curve = ((0.0, 1.0), (0.1, 0.86), (0.3, 0.62), (0.6, 0.48), (1.0, 0.40))
    intermediate_curve: Curve = (
        (0.0, 0.93),
        (0.1, 0.905),
        (0.3, 0.81),
        (0.6, 0.70),
        (1.0, 0.58),
    )
    wet_curve: Curve = ((0.0, 0.86), (0.1, 0.85), (0.3, 0.79), (0.6, 0.745), (1.0, 0.69))
    overheat_water: float = 0.1
    intermediate_overheat_gain: float = 3.0
    wet_overheat_gain: float = 6.0
    crash_water_gain: float = 2.0
    crash_wrong_tyre_gain: float = 8.0
    contact_water_gain: float = 1.0
    switch_horizon_laps: int = 8
    source_kind: Literal["assumed"] = "assumed"
    parameter_version: str = "assumed-wet-tyres-v1"
    rationale: str = (
        "Curvas de aderencia por classe de pneu escolhidas para passar pelas "
        "ancoras da pista (intermediario +13% na umida, chuva +25% saturada) e "
        "dar cruzamentos plausiveis; desgaste, risco e horizonte de decisao "
        "sao hipoteses de ordem de grandeza, nao medidas."
    )

    def __post_init__(self) -> None:
        for name in ("slick_curve", "intermediate_curve", "wet_curve"):
            _check_curve(name, getattr(self, name))
        for name in (
            "overheat_water",
            "intermediate_overheat_gain",
            "wet_overheat_gain",
            "crash_water_gain",
            "crash_wrong_tyre_gain",
            "contact_water_gain",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} nao pode ser negativo")
        if not 0 < self.overheat_water < 1:
            raise ValueError("overheat_water deve estar em (0, 1)")
        if type(self.switch_horizon_laps) is not int or self.switch_horizon_laps < 1:
            raise ValueError("switch_horizon_laps deve ser inteiro positivo")

    def curve(self, tyre_class: str) -> Curve:
        if tyre_class == SLICK:
            return self.slick_curve
        if tyre_class == INTERMEDIATE:
            return self.intermediate_curve
        if tyre_class == WET:
            return self.wet_curve
        raise ValueError(f"classe de pneu desconhecida: {tyre_class!r}")


ASSUMED_WET_TYRES = WetTyreParameters()


def tyre_class(compound: str) -> str:
    """``INTERMEDIATE`` ou ``WET`` para pneus de chuva; ``SLICK`` para os demais."""

    return compound if compound in WET_COMPOUNDS else SLICK


def _check_water(water: float) -> None:
    if isinstance(water, bool) or not isfinite(water) or not 0 <= water <= 1:
        raise ValueError("surface_water deve estar em [0, 1]")


def absolute_grip(
    compound: str, water: float, parameters: WetTyreParameters = ASSUMED_WET_TYRES
) -> float:
    """Aderencia absoluta do composto com essa agua (o slick seco vale 1)."""

    _check_water(water)
    return _interpolate(parameters.curve(tyre_class(compound)), water)


def best_tyre_class(
    water: float, parameters: WetTyreParameters = ASSUMED_WET_TYRES
) -> str:
    """A classe de pneu mais aderente para essa agua (empate fica com o slick)."""

    _check_water(water)
    return max(
        (SLICK, INTERMEDIATE, WET),
        key=lambda name: (_interpolate(parameters.curve(name), water), name == SLICK),
    )


def relative_grip(
    compound: str, water: float, parameters: WetTyreParameters = ASSUMED_WET_TYRES
) -> float:
    """Aderencia do composto dividida pela do melhor composto para essa agua.

    Vale 1 com o pneu adequado; e o fator que o carro paga por estar com o
    pneu errado, por cima da aderencia que a pista oferece.
    """

    best = absolute_grip(best_tyre_class(water, parameters), water, parameters)
    return absolute_grip(compound, water, parameters) / best


def wear_factor(
    compound: str, water: float, parameters: WetTyreParameters = ASSUMED_WET_TYRES
) -> float:
    """Multiplicador do desgaste: pneu de chuva superaquece em pista secando."""

    _check_water(water)
    gain = {
        INTERMEDIATE: parameters.intermediate_overheat_gain,
        WET: parameters.wet_overheat_gain,
    }.get(compound)
    if gain is None or water >= parameters.overheat_water:
        return 1.0
    return 1.0 + gain * (parameters.overheat_water - water) / parameters.overheat_water


def crash_multiplier(
    compound: str,
    water: float,
    wet_skill: float = 1.0,
    parameters: WetTyreParameters = ASSUMED_WET_TYRES,
) -> float:
    """Quanto a agua e o pneu errado multiplicam o risco de acidente individual.

    ``wet_skill`` 1,0 e o piloto neutro; maior que 1 reduz o efeito da agua
    (a compostura do piloto serve como habilidade na chuva).
    """

    if isinstance(wet_skill, bool) or not isfinite(wet_skill) or wet_skill <= 0:
        raise ValueError("wet_skill deve ser positivo")
    water_part = 1.0 + parameters.crash_water_gain * water / wet_skill
    tyre_part = 1.0 + parameters.crash_wrong_tyre_gain * (
        1.0 - relative_grip(compound, water, parameters)
    )
    return water_part * tyre_part


def contact_multiplier(
    water: float, parameters: WetTyreParameters = ASSUMED_WET_TYRES
) -> float:
    """Quanto a agua multiplica a chance de contato numa disputa."""

    _check_water(water)
    return 1.0 + parameters.contact_water_gain * water


def best_compound(
    water: float,
    dry_choice: str,
    parameters: WetTyreParameters = ASSUMED_WET_TYRES,
) -> str:
    """Composto a montar: o de chuva indicado, ou ``dry_choice`` se for slick."""

    best = best_tyre_class(water, parameters)
    return dry_choice if best == SLICK else best


def wet_compound_used(compounds: Sequence[str]) -> bool:
    """Se algum pneu de chuva ja foi usado (suspende a regra de dois compostos)."""

    return any(compound in WET_COMPOUNDS for compound in compounds)
