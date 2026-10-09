from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from f1_simulator.domain.driver_attributes import DriverAttributes


def adjusted_reference_ms(
    base_reference_ms: float, attributes: DriverAttributes | None
) -> float:
    if attributes is None:
        return base_reference_ms
    return base_reference_ms * (1.0 + attributes.pace_offset_pct / 100.0)


@dataclass(frozen=True, slots=True)
class DetailedTyreManagementHeuristic:
    """Quanto do ``tyre_management_factor`` o motor detalhado aplica.

    As faixas dos arquetipos foram pensadas para o nucleo simples, em que o
    pneu pesa pouco: o agressivo chega a 1,45x de desgaste e o conservador a
    0,65x. No motor detalhado o desgaste e calibrado e escalado pela severidade
    do circuito (ate 2,5x em Spa), e as paradas custam ~19-24 s; com o fator
    integral, um agressivo fazia 2,4 paradas contra 1,1 do conservador e
    terminava atras dele, anulando a vantagem de ritmo. Uma diferenca de
    desgaste entre pilotos da ordem de +/-15% e mais plausivel.

    O efeito e ``1 + elasticity * (fator - 1)``: 1,0 continua neutro, a ordem
    entre pilotos e preservada e, com ``elasticity`` em (0, 1], o resultado e
    sempre positivo. Com 0,4 a faixa efetiva vai de 0,86x a 1,18x.
    """

    elasticity: float = 0.4
    origin: Literal["heuristic"] = "heuristic"
    parameter_version: str = "detailed-tyre-management-v1"
    rationale: str = (
        "Heuristica: aplica 40% do fator de gestao de pneus do arquetipo no "
        "motor detalhado, para que a diferenca de desgaste entre pilotos fique "
        "em torno de +/-15% e nao anule a vantagem de ritmo."
    )

    def __post_init__(self) -> None:
        value = self.elasticity
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or not 0.0 < value <= 1.0
        ):
            raise ValueError("elasticity deve estar em (0, 1]")
        if self.origin != "heuristic":
            raise ValueError("origin deve ser 'heuristic'")
        if not self.parameter_version.strip() or not self.rationale.strip():
            raise ValueError("parameter_version e rationale sao obrigatorios")


DETAILED_TYRE_MANAGEMENT = DetailedTyreManagementHeuristic()


def detailed_degradation_factor(
    attributes: DriverAttributes | None,
    heuristic: DetailedTyreManagementHeuristic = DETAILED_TYRE_MANAGEMENT,
) -> float:
    """Multiplicador da degradacao no motor detalhado (1.0 sem atributos).

    Motor detalhado e estrategia de parada devem usar este mesmo valor, para
    que a decisao de parar enxergue o desgaste que o carro de fato tera.
    """

    if attributes is None:
        return 1.0
    return 1.0 + heuristic.elasticity * (attributes.tyre_management_factor - 1.0)


def consistency_scale(attributes: DriverAttributes | None) -> float:
    if attributes is None:
        return 1.0
    return attributes.consistency_factor


def attributes_assumption(attributes: DriverAttributes) -> dict:
    """Exponha valores e proveniencia sem reinterpretar ausencia como zero."""

    return {
        "kind": "driver_attributes",
        "driver_id": attributes.driver_id,
        "archetype": attributes.archetype,
        "source_kind": attributes.source_kind,
        "parameter_version": attributes.parameter_version,
        "rationale": attributes.rationale,
        "pace_offset_pct": attributes.pace_offset_pct,
        "consistency_factor": attributes.consistency_factor,
        "tyre_management_factor": attributes.tyre_management_factor,
        "aggression": attributes.aggression,
        "composure": attributes.composure,
        "sources": dict(attributes.sources),
    }
