"""Comparacao entre uma corrida simulada e a corrida realmente observada.

Este modulo responde a pergunta que o plano faz na secao 15 -- "modelo
aparentemente preciso, mas sem evidencia" -- com metricas definidas **antes** de
olhar o resultado.

O que este backtest mede, e o que ele NAO mede
----------------------------------------------
Cada participante entra na simulacao com o ritmo de referencia observado no
proprio fim de semana. Portanto o backtest **nao** avalia se o projeto consegue
prever o ritmo de um carro: ele avalia se a dinamica de corrida modelada
(combustivel, pneu, paradas, trafego, largada, abandono) reproduz o desfecho
quando o ritmo e conhecido. Essa distincao precisa aparecer em qualquer
relatorio, porque um leitor desavisado leria "erro de 1 posicao" como poder
preditivo sobre uma corrida futura, que este experimento nao demonstra.

Toda metrica e comparada contra duas linhas de base deliberadamente ingenuas:

``grid``      -- a ordem de largada e a ordem de chegada;
``constant``  -- o modelo antigo, de ritmo constante por carro.

Um modelo mais complexo so se justifica se vencer as duas. Essa regra evita
adicionar mecanismos que apenas aumentam a contagem de classes.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ObservedEntry:
    """Como um participante realmente terminou a corrida de referencia."""

    driver_id: str
    name: str
    team_id: str | None
    grid_position: int
    reference_lap_time_ms: float
    finish_position: int
    laps_completed: int
    retired: bool
    stops_made: int
    #: Melhor volta de classificacao, quando o evento a registra. Medida
    #: ANTES da largada, portanto utilizavel para prever sem vazamento.
    qualifying_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ObservedRace:
    """Corrida canonica usada como verdade de comparacao."""

    race_id: str
    name: str
    season: int
    circuit_id: str
    total_laps: int
    entries: tuple[ObservedEntry, ...]
    winner_total_time_ms: int | None
    lap_times_ms: dict[tuple[str, int], int]
    #: Trocas de posicao por volta realmente observadas. E o alvo que mede
    #: se o modelo de disputa deixa a corrida mexer na medida certa: um
    #: modelo que bloqueia demais congela a ordem de largada, e um que
    #: bloqueia de menos vira um carrossel.
    position_changes_per_lap: float = 0.0


@dataclass(frozen=True, slots=True)
class RaceMetrics:
    """Metricas de uma execucao contra a corrida observada.

    ``position_mae`` e o erro medio absoluto de posicao final, em posicoes.
    ``spearman`` e a correlacao de postos entre a ordem simulada e a real: 1.0 e
    ordem identica, 0.0 e ordem sem relacao.
    """

    label: str
    position_mae: float
    position_rmse: float
    spearman: float
    winner_correct: bool
    podium_overlap: int
    retirements_simulated: int
    retirements_observed: int
    mean_stops_simulated: float
    mean_stops_observed: float
    changes_per_lap_simulated: float
    changes_per_lap_observed: float
    lap_time_mae_ms: float | None


def _spearman(pairs: list[tuple[int, int]]) -> float:
    """Correlacao de postos de Spearman para posicoes ja inteiras e distintas.

    As posicoes finais sao uma permutacao sem empates, entao a forma fechada de
    Spearman se aplica diretamente e nao e preciso tratar postos medios.
    """

    n = len(pairs)
    if n < 2:
        return 0.0
    d2 = sum((a - b) ** 2 for a, b in pairs)
    return 1.0 - (6.0 * d2) / (n * (n * n - 1))


def position_changes_per_lap(history: list[dict]) -> float:
    """Trocas de posicao por volta num historico simulado.

    Conta, entre voltas consecutivas, quantos carros mudaram de posicao, e
    normaliza pelo numero de voltas -- exatamente a mesma definicao aplicada
    ao historico real, para que os dois numeros sejam comparaveis.
    """

    if len(history) < 2:
        return 0.0
    changes = 0
    for previous, current in zip(history, history[1:]):
        before = {c['driver_id']: c['position'] for c in previous['cars']}
        after = {c['driver_id']: c['position'] for c in current['cars']}
        changes += sum(
            1 for d in before.keys() & after.keys() if before[d] != after[d]
        )
    return changes / len(history)


def evaluate(
    *,
    label: str,
    observed: ObservedRace,
    simulated_classification: list[dict],
    simulated_lap_times_ms: dict[tuple[str, int], float] | None = None,
    simulated_history: list[dict] | None = None,
) -> RaceMetrics:
    """Compare uma classificacao simulada com a observada.

    Apenas pilotos presentes nos dois lados entram nas metricas de posicao; um
    participante ausente de um dos lados nao recebe posicao inventada.
    """

    observed_by_id = {e.driver_id: e for e in observed.entries}
    simulated_positions = {
        car["driver_id"]: car["position"] for car in simulated_classification
    }

    pairs: list[tuple[int, int]] = []
    for driver_id, simulated_position in simulated_positions.items():
        entry = observed_by_id.get(driver_id)
        if entry is None:
            continue
        pairs.append((simulated_position, entry.finish_position))

    if not pairs:
        raise ValueError("nenhum piloto em comum entre simulacao e observacao")

    errors = [abs(a - b) for a, b in pairs]
    mae = statistics.fmean(errors)
    rmse = (statistics.fmean([(a - b) ** 2 for a, b in pairs])) ** 0.5

    simulated_winner = next(
        (c["driver_id"] for c in simulated_classification if c["position"] == 1), None
    )
    observed_winner = next(
        (e.driver_id for e in observed.entries if e.finish_position == 1), None
    )

    simulated_podium = {
        c["driver_id"] for c in simulated_classification if c["position"] <= 3
    }
    observed_podium = {e.driver_id for e in observed.entries if e.finish_position <= 3}

    retirements_simulated = sum(
        1 for c in simulated_classification if c.get("status") == "RETIRED"
    )
    stops_simulated = [c.get("stops_made", 0) for c in simulated_classification]

    lap_mae: float | None = None
    if simulated_lap_times_ms:
        deltas = [
            abs(value - observed.lap_times_ms[key])
            for key, value in simulated_lap_times_ms.items()
            if key in observed.lap_times_ms
        ]
        if deltas:
            lap_mae = statistics.fmean(deltas)

    return RaceMetrics(
        label=label,
        position_mae=round(mae, 3),
        position_rmse=round(rmse, 3),
        spearman=round(_spearman(pairs), 4),
        winner_correct=bool(
            simulated_winner and simulated_winner == observed_winner
        ),
        podium_overlap=len(simulated_podium & observed_podium),
        retirements_simulated=retirements_simulated,
        retirements_observed=sum(1 for e in observed.entries if e.retired),
        mean_stops_simulated=round(
            statistics.fmean(stops_simulated) if stops_simulated else 0.0, 2
        ),
        mean_stops_observed=round(
            statistics.fmean([e.stops_made for e in observed.entries]), 2
        ),
        changes_per_lap_simulated=round(
            position_changes_per_lap(simulated_history) if simulated_history else 0.0,
            2,
        ),
        changes_per_lap_observed=round(observed.position_changes_per_lap, 2),
        lap_time_mae_ms=round(lap_mae, 1) if lap_mae is not None else None,
    )


def grid_baseline_classification(observed: ObservedRace) -> list[dict]:
    """Linha de base ``grid``: termina exatamente na ordem de largada."""

    ordered = sorted(
        observed.entries, key=lambda e: (e.grid_position, e.driver_id)
    )
    return [
        {
            "position": index,
            "driver_id": entry.driver_id,
            "name": entry.name,
            "status": "RUNNING",
            "stops_made": 0,
        }
        for index, entry in enumerate(ordered, start=1)
    ]


@dataclass(frozen=True, slots=True)
class AggregateMetrics:
    """Media das metricas sobre varias corridas de validacao."""

    label: str
    races: int
    position_mae: float
    position_rmse: float
    spearman: float
    winner_accuracy: float
    mean_podium_overlap: float
    mean_retirements_simulated: float
    mean_retirements_observed: float
    mean_stops_simulated: float
    mean_stops_observed: float
    changes_per_lap_simulated: float
    changes_per_lap_observed: float
    lap_time_mae_ms: float | None


def aggregate(label: str, metrics: list[RaceMetrics]) -> AggregateMetrics:
    """Agregue por corrida, com peso igual para cada evento.

    Peso igual por corrida (e nao por volta) impede que provas longas dominem o
    resultado -- a mesma precaucao ja adotada no perfilamento de pilotos.
    """

    if not metrics:
        raise ValueError("nenhuma corrida avaliada")
    lap_maes = [m.lap_time_mae_ms for m in metrics if m.lap_time_mae_ms is not None]
    return AggregateMetrics(
        label=label,
        races=len(metrics),
        position_mae=round(statistics.fmean([m.position_mae for m in metrics]), 3),
        position_rmse=round(statistics.fmean([m.position_rmse for m in metrics]), 3),
        spearman=round(statistics.fmean([m.spearman for m in metrics]), 4),
        winner_accuracy=round(
            statistics.fmean([1.0 if m.winner_correct else 0.0 for m in metrics]), 4
        ),
        mean_podium_overlap=round(
            statistics.fmean([m.podium_overlap for m in metrics]), 2
        ),
        mean_retirements_simulated=round(
            statistics.fmean([m.retirements_simulated for m in metrics]), 2
        ),
        mean_retirements_observed=round(
            statistics.fmean([m.retirements_observed for m in metrics]), 2
        ),
        mean_stops_simulated=round(
            statistics.fmean([m.mean_stops_simulated for m in metrics]), 2
        ),
        mean_stops_observed=round(
            statistics.fmean([m.mean_stops_observed for m in metrics]), 2
        ),
        changes_per_lap_simulated=round(
            statistics.fmean([m.changes_per_lap_simulated for m in metrics]), 2
        ),
        changes_per_lap_observed=round(
            statistics.fmean([m.changes_per_lap_observed for m in metrics]), 2
        ),
        lap_time_mae_ms=round(statistics.fmean(lap_maes), 1) if lap_maes else None,
    )
