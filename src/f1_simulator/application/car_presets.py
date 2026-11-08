"""Presets ficticios de carro por equipe (ADR 0008).

Espelha :class:`~f1_simulator.application.generate_attributes.DriverPreset`
no lado do carro: cada equipe recebe um ritmo heuristico
(``pace_offset_pct``) que o caso de uso converte no envelope fisico por
:func:`~f1_simulator.domain.speed_dynamics.car_pace_to_physics`. Como os
presets de piloto, sao caracterizacoes ficticias, nao medicoes de desempenho
real das equipes.

A convencao de ``pace_offset_pct`` e a mesma dos atributos de piloto: negativo
e mais rapido, zero e o carro de referencia (o mesmo que o piloto neutro
reproduz). Hoje o ritmo do piloto ja embute parte da vantagem do carro, entao
estes presets se sobrepoe a ele; a separacao piloto/carro e um ajuste de
calibracao posterior, nao coberto por esta fatia.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal


@dataclass(frozen=True, slots=True)
class CarPreset:
    """Preset ficticio validado de carro de equipe, independente do JSON.

    ``pace_offset_pct`` segue a mesma convencao dos atributos de piloto:
    negativo e mais rapido, zero e o carro de referencia. A metainformacao
    explicita que o numero e heuristico narrativo, nao uma observacao do
    desempenho real da equipe nomeada.
    """

    team_id: str
    team_name: str
    pace_offset_pct: float
    characterization: str
    source_kind: Literal["heuristic"]
    parameter_version: str
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.team_id, str) or not self.team_id.strip():
            raise ValueError("team_id deve ser texto nao vazio")
        if not isinstance(self.team_name, str) or not self.team_name.strip():
            raise ValueError("team_name deve ser texto nao vazio")
        if (
            isinstance(self.pace_offset_pct, bool)
            or not isinstance(self.pace_offset_pct, (int, float))
            or not isfinite(self.pace_offset_pct)
        ):
            raise ValueError("pace_offset_pct deve ser numero finito")
        if (
            not isinstance(self.characterization, str)
            or not self.characterization.strip()
        ):
            raise ValueError("characterization deve ser texto nao vazio")
        if self.source_kind != "heuristic":
            raise ValueError("source_kind deve ser 'heuristic'")
        if (
            not isinstance(self.parameter_version, str)
            or not self.parameter_version.strip()
        ):
            raise ValueError("parameter_version deve ser texto nao vazio")
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ValueError("rationale deve ser texto nao vazio")
