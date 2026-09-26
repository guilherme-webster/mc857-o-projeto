"""Execute uma sequência de corridas sem depender de resultados históricos.

Os tempos-base são informados em milissegundos por quilômetro. O comprimento
de cada pista é dado em metros pelo catálogo; portanto, a mesma lista de
participantes pode correr em circuitos de tamanhos diferentes sem reutilizar
um tempo de volta absoluto de uma pista em outra.

Por padrão a série é determinística. Pneu assumido e ruído por volta são
opcionais (ver :mod:`f1_simulator.domain.race_simulation`) e sempre carregam a
lista de hipóteses usadas, que nunca deve ser lida como calibração.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

from f1_simulator.domain.race_simulation import (
    Competitor,
    LapVariabilityAssumption,
    simulate_race,
)
from f1_simulator.domain.random_source import SeededRandomSource


@dataclass(frozen=True, slots=True)
class SeriesTrack:
    """Uma etapa da sequência, na ordem escolhida pelo usuário."""

    circuit_id: str
    name: str
    lap_length_m: float
    total_laps: int


@dataclass(frozen=True, slots=True)
class SeriesCompetitor:
    """Piloto configurado pelo usuário, com ritmo constante em ms/km."""

    driver_id: str
    name: str
    pace_ms_per_km: float


def simulate_series(
    tracks: tuple[SeriesTrack, ...],
    competitors: tuple[SeriesCompetitor, ...],
    *,
    tyre_plan: Mapping[str, str] | None = None,
    variability: LapVariabilityAssumption | None = None,
    seed: int | None = None,
) -> dict:
    """Simule as etapas em ordem; cada corrida tem classificação independente.

    Esta fatia não inventa pontuação de campeonato, efeito do clima ou
    parâmetros de pilotos reais. A lista de corridas é um plano sequencial.

    **Modo padrão** (sem argumentos opcionais): cada corrida é calculada
    deterministicamente com ritmo constante, e a saída é a de sempre
    (``race_count`` e ``races``).

    **Modo com modelo:**

    * ``tyre_plan`` mapeia ``driver_id -> composto`` e vale para TODAS as
      corridas da série (um composto por corrida, sem pit stop). Deve cobrir
      todos os participantes. Uma corrida mais longa que o suporte do pneu
      levanta ``ValueError``; não há extrapolação.
    * ``variability`` exige ``seed`` e vice-versa. Este módulo NUNCA escolhe a
      semente: quem chama (na prática, a borda HTTP) a informa, para que a
      corrida "aleatória" possa ser reproduzida depois. Cada corrida recebe o
      fluxo ``SeededRandomSource(seed).spawn(circuit_id)``, que depende só da
      semente e do circuito; reordenar as pistas da sequência, ou remover uma
      delas, não altera o resultado das demais.

    No modo com modelo o retorno ganha ``assumptions`` (uma única lista, pois
    os mesmos parâmetros valem para todas as corridas; por isso ela é retirada
    de cada corrida) e, se houver ruído, ``seed``.
    """

    if not tracks:
        raise ValueError("selecione pelo menos uma pista")
    if not competitors:
        raise ValueError("informe pelo menos um participante")
    ids = [track.circuit_id for track in tracks]
    if len(ids) != len(set(ids)):
        raise ValueError("pistas duplicadas na sequência")
    driver_ids = [driver.driver_id for driver in competitors]
    if len(driver_ids) != len(set(driver_ids)):
        raise ValueError("participantes duplicados")
    for track in tracks:
        if not track.circuit_id or not track.name:
            raise ValueError("pista sem identificação")
        if track.total_laps <= 0:
            raise ValueError("total_laps deve ser positivo")
        if not isfinite(track.lap_length_m) or track.lap_length_m <= 0:
            raise ValueError("lap_length_m deve ser positivo e finito")
    for driver in competitors:
        if not driver.driver_id or not driver.name:
            raise ValueError("participante sem identificação")
        if not isfinite(driver.pace_ms_per_km) or driver.pace_ms_per_km <= 0:
            raise ValueError("pace_ms_per_km deve ser positivo e finito")

    if variability is not None and seed is None:
        raise ValueError("variability exige uma seed informada pelo chamador")
    if seed is not None and variability is None:
        raise ValueError(
            "seed informada sem variability: seria ignorada em silêncio"
        )
    # Valida o tipo da semente (bool não vale) antes de simular qualquer etapa.
    base_source = SeededRandomSource(seed) if seed is not None else None

    races = []
    assumptions: list[dict] | None = None
    for track in tracks:
        lap_distance_km = track.lap_length_m / 1000
        field = []
        for driver in competitors:
            lap_time_ms = round(driver.pace_ms_per_km * lap_distance_km, 1)
            if not isfinite(lap_time_ms) or lap_time_ms <= 0:
                raise ValueError("ritmo convertido em tempo de volta inválido")
            field.append(Competitor(driver.driver_id, driver.name, lap_time_ms))
        rng = base_source.spawn(track.circuit_id) if base_source else None
        result = simulate_race(
            field,
            track.total_laps,
            tyre_plan=tyre_plan,
            variability=variability,
            rng=rng,
        )
        # Os parâmetros são os mesmos em toda corrida: guardar uma vez só.
        race_assumptions = result.pop("assumptions", None)
        if assumptions is None:
            assumptions = race_assumptions
        races.append(
            {
                "circuit_id": track.circuit_id,
                "name": track.name,
                "lap_length_m": track.lap_length_m,
                **result,
            }
        )

    series: dict = {"race_count": len(races), "races": races}
    if seed is not None:
        series["seed"] = seed
    if assumptions is not None:
        series["assumptions"] = assumptions
    return series
