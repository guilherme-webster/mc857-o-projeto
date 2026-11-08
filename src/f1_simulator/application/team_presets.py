"""Presets ficticios de equipe: execucao operacional (ADR 0008).

Terceira heuristica, ao lado dos presets de piloto e de carro. Enquanto o
carro modela o ritmo (``car_presets``) e o piloto modela estilo e ritmo
(``driver_attributes``), a equipe modela a **execucao operacional**: hoje, o
quanto a equipe perde (ou ganha) tempo no pit stop por organizacao de box.

Deliberadamente **nao** modela confiabilidade mecanica (abandono por quebra):
isso ja vem calibrado do historico em ``ModelParameters.team_reliability``
(``hazard_factor``), e sobrepor uma heuristica a um dado estimado seria um
retrocesso proibido pelo AGENTS.md. A equipe desorganizada perde tempo no box,
nao quebra mais o carro -- essas duas coisas sao fontes diferentes.

``pit_execution_factor`` multiplica o tempo de parada da equipe: 1.0 e a
equipe media, acima de 1 e um box lento/desorganizado, abaixo de 1 e um box
rapido e consistente. Vale nos dois motores (perda de boxes no detalhado,
tempo de servico no 2D).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal


@dataclass(frozen=True, slots=True)
class TeamPreset:
    """Preset ficticio validado de execucao operacional de uma equipe.

    A metainformacao explicita que o numero e heuristico narrativo, nao uma
    observacao do desempenho real da equipe nomeada.
    """

    team_id: str
    team_name: str
    pit_execution_factor: float
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
            isinstance(self.pit_execution_factor, bool)
            or not isinstance(self.pit_execution_factor, (int, float))
            or not isfinite(self.pit_execution_factor)
            or self.pit_execution_factor <= 0
        ):
            raise ValueError("pit_execution_factor deve ser positivo e finito")
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
