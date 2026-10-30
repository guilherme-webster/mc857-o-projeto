"""Torneio ja simulado: navegacao entre etapas e tabela final, sem Arcade.

Guarda as corridas devolvidas pelo backend na ordem do plano e as regras
escolhidas na tela. A pontuacao e regra de dominio
(``f1_simulator.domain.championship``) e e calculada pelo backend em
``POST /championship/standings``: o cliente Arcade fala com o nucleo so por
HTTP/JSON (ADR 0004) e nao tem o pacote ``f1_simulator`` instalado. Aqui so se
traduzem os rotulos da tela e o JSON de cada corrida para aquele contrato.
"""

from __future__ import annotations

from dataclasses import dataclass

from frontend.arcade.configuration_state import (
    SCORING_OPTIONS,
    TIEBREAK_OPTIONS,
    TournamentRules,
)
from frontend.arcade.race_launcher import LaunchedRace

# Rotulo da tela -> parametro do dominio.
SCORING = {SCORING_OPTIONS[0]: "f1", SCORING_OPTIONS[1]: "none"}
TIEBREAK = {TIEBREAK_OPTIONS[0]: "best_average", TIEBREAK_OPTIONS[1]: "most_wins"}
RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True)
class TournamentSession:
    races: tuple[LaunchedRace, ...]
    rules: TournamentRules
    notices: tuple[str, ...] = ()
    # Seed usada nas etapas (#105); vai para o torneio salvo (#109).
    tournament_seed: int | None = None

    def __post_init__(self) -> None:
        if not self.races:
            raise ValueError("torneio sem etapas simuladas")

    @property
    def total_stages(self) -> int:
        return len(self.races)

    @property
    def scored(self) -> bool:
        return SCORING[self.rules.scoring] == "f1"

    def stage(self, index: int) -> LaunchedRace:
        """Etapa ``index``, contada a partir de 1."""

        if not 1 <= index <= self.total_stages:
            raise IndexError(f"etapa {index} fora de 1..{self.total_stages}")
        return self.races[index - 1]

    def stage_title(self, index: int) -> str:
        return f"Etapa {index}/{self.total_stages} · {self.stage(index).planned.name}"

    def has_next(self, index: int) -> bool:
        return index < self.total_stages

    def stage_names(self) -> tuple[str, ...]:
        return tuple(race.planned.name for race in self.races)

    def driver_names(self) -> dict[str, str]:
        names: dict[str, str] = {}
        for race in self.races:
            for car in _classification(race):
                names.setdefault(str(car["driver_id"]), str(car.get("name", "")))
        return names

    def standings_request(self) -> dict:
        """Corpo de ``POST /championship/standings`` para este torneio."""

        return {
            "scoring": SCORING[self.rules.scoring],
            "tiebreak": TIEBREAK[self.rules.tiebreak],
            "stages": [
                [
                    {
                        "driver_id": str(car["driver_id"]),
                        "position": int(car["position"]),
                        "retired": car.get("status") == RETIRED,
                    }
                    for car in _classification(race)
                ]
                for race in self.races
            ],
        }


@dataclass(frozen=True, slots=True)
class StandingLine:
    """Linha da tabela do campeonato como o backend a devolve."""

    position: int
    driver_id: str
    points: int
    wins: int
    podiums: int
    average_position: float
    stage_positions: tuple[int | None, ...]
    stage_retired: tuple[bool, ...]


def parse_standings(payload: dict, total_stages: int) -> list[StandingLine]:
    """Valide a resposta do backend antes de desenha-la."""

    try:
        lines = [
            StandingLine(
                position=int(row["position"]),
                driver_id=str(row["driver_id"]),
                points=int(row["points"]),
                wins=int(row["wins"]),
                podiums=int(row["podiums"]),
                average_position=float(row["average_position"]),
                stage_positions=tuple(
                    None if value is None else int(value)
                    for value in row["stage_positions"]
                ),
                stage_retired=tuple(bool(value) for value in row["stage_retired"]),
            )
            for row in payload["rows"]
        ]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"resposta de campeonato inválida: {error!r}") from error
    if any(len(line.stage_positions) != total_stages for line in lines):
        raise ValueError("resposta de campeonato com número de etapas diferente")
    return lines


def _classification(race: LaunchedRace) -> list[dict]:
    classification = race.race.get("classification")
    if not isinstance(classification, list) or not classification:
        raise ValueError(f"{race.planned.name}: corrida sem classificacao final")
    return classification
