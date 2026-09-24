"""Execute uma sequência de corridas sem depender de resultados históricos.

Os tempos-base são informados em milissegundos por quilômetro. O comprimento
de cada pista é dado em metros pelo catálogo; portanto, a mesma lista de
participantes pode correr em circuitos de tamanhos diferentes sem reutilizar
um tempo de volta absoluto de uma pista em outra.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from f1_simulator.domain.race_simulation import Competitor, simulate_race


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
) -> dict:
    """Simule as etapas em ordem; cada corrida tem classificação independente.

    Esta primeira fatia não inventa pontuação de campeonato, efeito do clima ou
    parâmetros de pilotos reais. A lista de corridas é um plano sequencial; o
    motor atual calcula cada uma deterministicamente com ritmo constante.
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

    races = []
    for track in tracks:
        lap_distance_km = track.lap_length_m / 1000
        field = []
        for driver in competitors:
            lap_time_ms = round(driver.pace_ms_per_km * lap_distance_km, 1)
            if not isfinite(lap_time_ms) or lap_time_ms <= 0:
                raise ValueError("ritmo convertido em tempo de volta inválido")
            field.append(Competitor(driver.driver_id, driver.name, lap_time_ms))
        result = simulate_race(field, track.total_laps)
        races.append(
            {
                "circuit_id": track.circuit_id,
                "name": track.name,
                "lap_length_m": track.lap_length_m,
                **result,
            }
        )
    return {"race_count": len(races), "races": races}
