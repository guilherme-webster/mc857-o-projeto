"""Estime a aderencia e o downforce do carro de referencia (ADR 0014).

O motor fisico (``domain/speed_dynamics.py``) transforma a geometria de cada
pista num tempo de volta. Dois parametros do carro nao tem valor publico
confiavel e decidem quase tudo: o coeficiente de atrito pneu-asfalto ``mu`` e a
area de downforce ``C_L * A``. Eles sao escolhidos aqui para que o piloto
neutro reproduza a volta de referencia historica de cada circuito
(``reference-laps-v1.json``: mediana das voltas mais rapidas do pelotao).

Metodo, deliberadamente simples:

1. o erro de uma pista e ``log(volta fisica / volta de referencia)``; o log
   trata 5% rapido e 5% lento como o mesmo erro, independente da extensao;
2. o objetivo e a raiz do erro quadratico medio entre as pistas;
3. busca em grade grossa e depois fina em torno do melhor ponto. Com dois
   parametros e 24 pistas, uma grade e transparente e suficiente; um otimizador
   generico esconderia empates entre ``mu`` e downforce, que existem: mais
   aderencia mecanica compensa menos downforce nas curvas lentas.

Os demais campos do carro (massa, potencia, arrasto, velocidade maxima e
parcela de tracao) ficam fixos como hipoteses de ordem de grandeza. Eles nao
sao identificaveis so com tempos de volta: dois parametros ja explicam a
maior parte da variacao entre pistas, e liberar mais ajustaria ruido.

O que este ajuste NAO resolve: curvas inclinadas (Zandvoort), altitude (Mexico)
e chicanes curtas que a polilinha de 240 pontos nao resolve (Monza) deixam
residuos de 5-10%, publicados por pista no artefato.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from math import exp, isfinite, log, sqrt
from statistics import median

from f1_simulator.domain.speed_dynamics import (
    DEFAULT_CAR_PHYSICS,
    CarPhysics,
    lap_time_ms,
    steady_lap,
)
from f1_simulator.domain.track_geometry import TrackGeometry

METHOD_VERSION = "grid-search-log-rms-v1"


@dataclass(frozen=True, slots=True)
class CircuitFit:
    """Volta fisica do carro ajustado contra a referencia de um circuito."""

    circuit_id: str
    reference_lap_ms: float
    physical_lap_ms: float

    @property
    def ratio(self) -> float:
        return self.physical_lap_ms / self.reference_lap_ms


@dataclass(frozen=True, slots=True)
class CarPhysicsFit:
    """Resultado do ajuste: o carro estimado e o erro que ele deixa."""

    physics: CarPhysics
    rms_log_error: float
    circuits: tuple[CircuitFit, ...]
    method_version: str = METHOD_VERSION

    @property
    def median_ratio(self) -> float:
        return median(c.ratio for c in self.circuits)


def _frange(start: float, stop: float, step: float) -> list[float]:
    count = int(round((stop - start) / step))
    return [round(start + i * step, 10) for i in range(count + 1)]


def _rms_log(
    tracks: Sequence[tuple[str, TrackGeometry, float]], physics: CarPhysics
) -> tuple[float, tuple[CircuitFit, ...]]:
    fits = []
    total = 0.0
    for circuit_id, geometry, reference_ms in tracks:
        physical = lap_time_ms(steady_lap(geometry, physics))
        fits.append(CircuitFit(circuit_id, reference_ms, physical))
        total += log(physical / reference_ms) ** 2
    return sqrt(total / len(tracks)), tuple(fits)


def fit_car_physics(
    tracks: Mapping[str, tuple[TrackGeometry, float]],
    *,
    base: CarPhysics = DEFAULT_CAR_PHYSICS,
    coarse_mu: Sequence[float] = tuple(_frange(1.0, 2.2, 0.1)),
    coarse_cla_m2: Sequence[float] = tuple(_frange(1.5, 6.5, 0.5)),
    fine_mu_step: float = 0.02,
    fine_cla_step: float = 0.1,
) -> CarPhysicsFit:
    """Ajuste ``grip_mu`` e ``downforce_cla_m2`` do carro de referencia.

    ``tracks`` mapeia o circuito para ``(geometria, volta de referencia em
    ms)``. Os demais campos vem de ``base``. A grade fina cobre um passo da
    grade grossa para cada lado do melhor ponto grosso.
    """

    if not tracks:
        raise ValueError("o ajuste precisa de pelo menos um circuito")
    rows = []
    for circuit_id, (geometry, reference_ms) in sorted(tracks.items()):
        if not isfinite(reference_ms) or reference_ms <= 0:
            raise ValueError(f"volta de referencia invalida em {circuit_id}")
        rows.append((circuit_id, geometry, float(reference_ms)))

    def search(mus, clas):
        best = None
        for mu in mus:
            for cla in clas:
                candidate = replace(base, grip_mu=mu, downforce_cla_m2=cla)
                error, fits = _rms_log(rows, candidate)
                if best is None or error < best[0]:
                    best = (error, candidate, fits)
        return best

    _, coarse, _ = search(coarse_mu, coarse_cla_m2)
    mu_step = coarse_mu[1] - coarse_mu[0] if len(coarse_mu) > 1 else fine_mu_step
    cla_step = (
        coarse_cla_m2[1] - coarse_cla_m2[0] if len(coarse_cla_m2) > 1 else fine_cla_step
    )
    fine_mu = [
        mu
        for mu in _frange(
            coarse.grip_mu - mu_step, coarse.grip_mu + mu_step, fine_mu_step
        )
        if mu > 0
    ]
    fine_cla = [
        cla
        for cla in _frange(
            coarse.downforce_cla_m2 - cla_step,
            coarse.downforce_cla_m2 + cla_step,
            fine_cla_step,
        )
        if cla >= 0
    ]
    error, physics, fits = search(fine_mu, fine_cla)
    return CarPhysicsFit(physics=physics, rms_log_error=error, circuits=fits)


def evaluate_car_physics(
    tracks: Mapping[str, tuple[TrackGeometry, float]],
    physics: CarPhysics,
) -> CarPhysicsFit:
    """Erro de um carro ja escolhido, sem ajustar nada (para comparar modelos)."""

    rows = [
        (circuit_id, geometry, float(reference_ms))
        for circuit_id, (geometry, reference_ms) in sorted(tracks.items())
    ]
    error, fits = _rms_log(rows, physics)
    return CarPhysicsFit(physics=physics, rms_log_error=error, circuits=fits)


def ratio_summary(fit: CarPhysicsFit) -> dict:
    """Mediana, extremos e erro medio do ajuste, em forma serializavel."""

    ratios = [c.ratio for c in fit.circuits]
    return {
        "rms_log_error": round(fit.rms_log_error, 4),
        "rms_error_pct": round((exp(fit.rms_log_error) - 1) * 100, 1),
        "median_ratio": round(fit.median_ratio, 3),
        "min_ratio": round(min(ratios), 3),
        "max_ratio": round(max(ratios), 3),
    }
