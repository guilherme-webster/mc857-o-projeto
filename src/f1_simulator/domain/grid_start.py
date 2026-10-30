"""Parametros heuristicos para traduzir o grid no relogio da largada.

O coeficiente em milissegundos por posicao continua pertencendo ao modelo
calibrado. Este modulo guarda somente a escolha de produto que atenua esse
coeficiente no motor por volta. A separacao impede que uma nova calibracao
sobrescreva silenciosamente a heuristica e permite executar sensibilidades sem
editar o artefato calibrado.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal


@dataclass(frozen=True, slots=True)
class GridStartParameters:
    """Atenuacao heuristica da penalidade calibrada da posicao de largada.

    ``penalty_factor`` multiplica uma unica vez
    ``ModelParameters.grid_penalty_ms_per_position``. Zero torna simultaneo o
    relogio inicial dos carros; 1,0 reproduz o comportamento anterior. Valores
    acima de 1,0 sao aceitos para analises de sensibilidade. Negativos, booleanos
    e nao finitos sao erros de configuracao, nunca valores a limitar em silencio.
    """

    penalty_factor: float
    origin: Literal["heuristic"]
    parameter_version: str
    rationale: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.penalty_factor, bool)
            or not isinstance(self.penalty_factor, (int, float))
            or not isfinite(self.penalty_factor)
            or self.penalty_factor < 0.0
        ):
            raise ValueError("penalty_factor deve ser nao negativo e finito")
        if self.origin != "heuristic":
            raise ValueError("origin deve ser 'heuristic'")
        for name in ("parameter_version", "rationale"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} deve ser texto nao vazio")


LEGACY_GRID_START_PARAMETERS = GridStartParameters(
    penalty_factor=1.0,
    origin="heuristic",
    parameter_version="heuristic-grid-start-legacy-v1",
    rationale=(
        "Fator neutro para compatibilidade: preserva integralmente a penalidade "
        "calibrada de largada do modelo anterior."
    ),
)


def initial_grid_delay_ms(
    calibrated_ms_per_position: float,
    grid_position: int,
    parameters: GridStartParameters,
) -> float:
    """Calcule o atraso inicial, aplicando a heuristica exatamente uma vez.

    O chamador fornece o coeficiente calibrado para manter a fronteira explicita:
    esta funcao nao conhece arquivos nem duplica o valor de 782,4 ms. Posicoes
    comecam em um; aceitar zero produziria credito de tempo antes da largada.
    """

    if type(grid_position) is not int or grid_position < 1:
        raise ValueError("grid_position deve ser um inteiro positivo")
    return (
        float(calibrated_ms_per_position)
        * parameters.penalty_factor
        * (grid_position - 1)
    )
