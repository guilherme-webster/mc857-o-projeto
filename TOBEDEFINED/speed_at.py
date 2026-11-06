"""Parqueado de ``src/f1_simulator/domain/speed_dynamics.py``.

``speed_at`` interpola a velocidade (m/s) numa distancia dentro da volta a
partir dos ``SpeedSample`` do motor de velocidade por distancia (ADR 0010).
Foi escrita no spike original para a visualizacao, mas ficou sem nenhum
consumidor: o frontend consome o perfil fisico por outro caminho
(``speed_profiles`` no resultado) e o motor 2D nao a usa.

Movida para ca por nao ter uso vivo; preservada caso uma visualizacao futura
precise de velocidade por distancia. Para reativar, reponha a funcao no modulo
e importe ``SpeedSample`` de ``speed_dynamics``.
"""

from __future__ import annotations


def speed_at(samples, distance_m: float) -> float:
    lap_length = samples[-1].distance_m
    d = distance_m % lap_length if lap_length else 0.0
    lo, hi = 0, len(samples) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if samples[mid].distance_m < d:
            lo = mid + 1
        else:
            hi = mid
    i = max(1, lo)
    a, b = samples[i - 1], samples[i]
    span = b.distance_m - a.distance_m
    f = (d - a.distance_m) / span if span > 0 else 0.0
    return a.speed_ms + (b.speed_ms - a.speed_ms) * f
