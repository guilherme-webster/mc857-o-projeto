"""Nucleo minimo e deterministico da simulacao de corrida.

Este core considera apenas o ritmo do piloto: cada carro percorre todas as
voltas a um tempo de volta constante (``base_lap_time_ms``, derivado do ETL). A
posicao por volta emerge do tempo total acumulado -- quem soma menos tempo lidera.

Fronteiras (ADR 0002 / AGENTS.md): o core e a fonte de verdade da classificacao
e nao conhece Arcade, FastAPI, SQLite nem formatos de dados. Nao ha aleatoriedade
aqui; degradacao de pneu, pit stop, abandono e geometria da pista sao
deliberadamente deixados de fora desta primeira fatia. Tempos em milissegundos.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Competitor:
    """Um participante e seu unico atributo nesta fatia: o ritmo constante.

    ``lap_time_ms`` e o tempo de volta constante do carro, em milissegundos.
    Deve ser estritamente positivo; pilotos sem ritmo derivavel do ETL nao
    entram na simulacao e devem ser filtrados antes de chegar aqui.
    """

    driver_id: str
    name: str
    lap_time_ms: float


@dataclass(frozen=True, slots=True)
class LapPosition:
    """Estado classificatorio de um carro ao fim de uma volta."""

    position: int
    driver_id: str
    name: str
    total_time_ms: float


def simulate_race(
    competitors: tuple[Competitor, ...] | list[Competitor],
    total_laps: int,
) -> dict:
    """Simule ``total_laps`` voltas e retorne as posicoes por volta.

    A cada volta, cada carro soma seu ``lap_time_ms`` constante ao tempo total,
    e os carros sao ordenados pelo tempo acumulado (menor tempo = frente). O
    resultado e determinístico e independe da ordem de entrada dos competidores;
    empates de tempo sao desempatados por ``driver_id`` para ser reproduzivel.

    Retorna um dicionario pronto para transporte JSON::

        {
            "total_laps": int,
            "history": [
                {"lap": int, "cars": [
                    {"position", "driver_id", "name", "total_time_ms"}, ...
                ]},
                ...
            ],
            "classification": [ ...mesma forma dos cars da ultima volta... ],
        }

    ``total_laps`` deve ser positivo. Uma lista vazia de competidores produz um
    historico com voltas sem carros, o que mantem o contrato simples e explicito.
    """

    if total_laps <= 0:
        raise ValueError("total_laps deve ser positivo")

    seen: set[str] = set()
    for competitor in competitors:
        if competitor.lap_time_ms <= 0:
            raise ValueError(
                f"lap_time_ms deve ser positivo para {competitor.driver_id}"
            )
        if competitor.driver_id in seen:
            raise ValueError(f"driver_id duplicado: {competitor.driver_id}")
        seen.add(competitor.driver_id)

    totals: dict[str, float] = {c.driver_id: 0.0 for c in competitors}

    history = []
    for lap in range(1, total_laps + 1):
        for competitor in competitors:
            totals[competitor.driver_id] += competitor.lap_time_ms
        history.append({"lap": lap, "cars": _classify(competitors, totals)})

    classification = history[-1]["cars"] if history else []
    return {
        "total_laps": total_laps,
        "history": history,
        "classification": classification,
    }


def _classify(
    competitors: tuple[Competitor, ...] | list[Competitor],
    totals: dict[str, float],
) -> list[dict]:
    """Ordene por tempo acumulado (desempate por driver_id) e atribua posicoes."""

    ordered = sorted(
        competitors, key=lambda c: (totals[c.driver_id], c.driver_id)
    )
    return [
        {
            "position": index,
            "driver_id": competitor.driver_id,
            "name": competitor.name,
            "total_time_ms": round(totals[competitor.driver_id], 1),
            "lap_time_ms": competitor.lap_time_ms,
        }
        for index, competitor in enumerate(ordered, start=1)
    ]
