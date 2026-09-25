"""Contrato deterministico para o efeito linear de pneus no tempo de volta.

Os parametros padrao deste modulo sao hipoteses assumidas: foram inspirados
somente pela ordem de grandeza de uma analise exploratoria e nunca foram
calibrados. O contrato torna essa origem explicita para impedir que valores
provisorios sejam confundidos com estimativas empiricas nas proximas fatias.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal


_SUPPORTED_DRY_COMPOUNDS = frozenset(("SOFT", "MEDIUM", "HARD"))


def _require_non_empty_string(field_name: str, value: object) -> None:
    """Valide texto de contrato sem aceitar valores apenas com espacos."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} deve ser uma string nao vazia")


def _require_supported_compound(compound: object) -> None:
    """Restrinja o contrato aos tres compostos secos aprovados nesta fase."""

    _require_non_empty_string("compound", compound)
    if compound not in _SUPPORTED_DRY_COMPOUNDS:
        raise ValueError("compound deve ser SOFT, MEDIUM ou HARD nesta fase")


@dataclass(frozen=True, slots=True)
class TyreModelParameters:
    """Parametros versionados de um composto dentro de sua faixa de suporte.

    ``linear_ms_per_lap`` e a variacao, em milissegundos, causada por uma volta
    adicional de idade. A inclinacao pode ser zero ou negativa: o dominio a
    preserva porque truncar o sinal esconderia a hipotese declarada pelo
    produtor dos parametros.
    """

    compound: str
    source_kind: Literal["assumed", "estimated"]
    parameter_version: str
    anchor_age_laps: int
    min_age_laps: int
    max_age_laps: int
    linear_ms_per_lap: float
    rationale: str

    def __post_init__(self) -> None:
        _require_supported_compound(self.compound)
        _require_non_empty_string("source_kind", self.source_kind)
        _require_non_empty_string("parameter_version", self.parameter_version)
        _require_non_empty_string("rationale", self.rationale)

        if self.source_kind not in ("assumed", "estimated"):
            raise ValueError("source_kind deve ser 'assumed' ou 'estimated'")

        ages = (
            self.anchor_age_laps,
            self.min_age_laps,
            self.max_age_laps,
        )
        if any(type(age) is not int for age in ages):
            raise ValueError("idades de pneu devem ser inteiros verdadeiros")
        if self.min_age_laps < 0:
            raise ValueError("min_age_laps nao pode ser negativo")
        if not (
            self.min_age_laps
            <= self.anchor_age_laps
            <= self.max_age_laps
        ):
            raise ValueError(
                "a idade ancora deve pertencer a faixa de suporte inclusiva"
            )

        slope = self.linear_ms_per_lap
        if (
            isinstance(slope, bool)
            or not isinstance(slope, (int, float))
            or not isfinite(slope)
        ):
            raise ValueError("linear_ms_per_lap deve ser um numero finito")


@dataclass(frozen=True, slots=True)
class TyreState:
    """Estado do jogo antes do inicio da volta que sera calculada.

    ``age_laps_before_lap`` conta as voltas ja completadas com este jogo antes
    de a volta comecar; portanto, a primeira volta tem idade zero. Esta e uma
    convencao propria do simulador e nao equivale ao ``TyreLife`` do FastF1,
    cuja semantica pre/pos-volta ainda nao foi confirmada para este uso.
    """

    compound: str
    age_laps_before_lap: int

    def __post_init__(self) -> None:
        _require_supported_compound(self.compound)
        if type(self.age_laps_before_lap) is not int:
            raise ValueError("age_laps_before_lap deve ser um inteiro verdadeiro")
        if self.age_laps_before_lap < 0:
            raise ValueError("age_laps_before_lap nao pode ser negativo")


_ASSUMED_RATIONALE = (
    "Hipotese assumida, inspirada apenas na ordem de grandeza de uma analise "
    "exploratoria de pneus; este valor nunca foi calibrado."
)


# Este catalogo e intencionalmente uma tupla: a fatia define parametros
# versionados e imutaveis, nao um registro global que consumidores possam
# alterar durante uma simulacao.
ASSUMED_DRY_TYRES: tuple[TyreModelParameters, ...] = (
    TyreModelParameters(
        compound="SOFT",
        source_kind="assumed",
        parameter_version="assumed-dry-linear-v1",
        anchor_age_laps=0,
        min_age_laps=0,
        max_age_laps=80,
        linear_ms_per_lap=30.0,
        rationale=_ASSUMED_RATIONALE,
    ),
    TyreModelParameters(
        compound="MEDIUM",
        source_kind="assumed",
        parameter_version="assumed-dry-linear-v1",
        anchor_age_laps=0,
        min_age_laps=0,
        max_age_laps=80,
        linear_ms_per_lap=20.0,
        rationale=_ASSUMED_RATIONALE,
    ),
    TyreModelParameters(
        compound="HARD",
        source_kind="assumed",
        parameter_version="assumed-dry-linear-v1",
        anchor_age_laps=0,
        min_age_laps=0,
        max_age_laps=80,
        linear_ms_per_lap=6.0,
        rationale=_ASSUMED_RATIONALE,
    ),
)


def tyre_effect_ms(
    parameters: TyreModelParameters,
    state: TyreState,
) -> float:
    """Calcule o efeito linear em ms sem clamp nem extrapolacao silenciosa.

    O composto do estado deve corresponder ao dos parametros, e a idade deve
    estar na faixa inclusiva declarada. Violações levantam ``ValueError`` em vez
    de produzir zero, pois isso tornaria uma configuracao ausente indistinguivel
    de um efeito legitimamente nulo na ancora.
    """

    if state.compound != parameters.compound:
        raise ValueError(
            "o composto do estado deve corresponder ao composto dos parametros"
        )
    if not (
        parameters.min_age_laps
        <= state.age_laps_before_lap
        <= parameters.max_age_laps
    ):
        raise ValueError("idade do pneu fora da faixa de suporte dos parametros")

    age_delta_laps = state.age_laps_before_lap - parameters.anchor_age_laps
    return float(parameters.linear_ms_per_lap * age_delta_laps)


def tyre_parameters_for(
    compound: str,
    catalogue: tuple[TyreModelParameters, ...] = ASSUMED_DRY_TYRES,
) -> TyreModelParameters:
    """Retorne os parametros de ``compound`` ou levante ``ValueError``.

    A ausencia nunca e convertida em um parametro neutro: exigir que o chamador
    trate o erro evita simular silenciosamente um composto sem modelo.
    """

    _require_non_empty_string("compound", compound)
    for parameters in catalogue:
        if parameters.compound == compound:
            return parameters
    raise ValueError(f"composto sem parametros no catalogo: {compound}")
