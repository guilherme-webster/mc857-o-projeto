"""Decomposicao da velocidade de um carro para o grafico da reproducao.

Le ``result["speed_breakdown"]`` (penalidades por volta, do motor 2D) e
``result["speed_profiles"]`` (teto fisico por ponto) e devolve, para um
instante, as fatias que somam a velocidade maxima de reta do carro:

- ``corner``: quanto a curvatura do ponto atual tira do teto de reta;
- ``tyre``/``fuel``/``weather``/``race_control``: quanto cada condicao tira do
  que a curva deixou, repartido pelas parcelas que o motor cobrou na volta;
- ``effective``: a velocidade que sobra, o que o carro faz agora.

As fatias sao fracoes de ``v_max`` e somam ~1.0. Fronteira: o modulo so le o
resultado; nao simula nem corrige o motor.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass

#: Ordem de empilhamento e rotulos das penalidades, do mais proximo da
#: velocidade efetiva para o topo da barra.
PENALTY_FACTORS = ("tyre", "fuel", "weather", "race_control")


@dataclass(frozen=True, slots=True)
class SpeedBreakdown:
    """Fatias da velocidade de um carro num instante, em fracao de ``v_max``.

    ``effective + transient + corner + sum(penalties.values())`` vale ~1.0.
    As fatias, do que o carro faz agora ao que falta para o teto de reta:

    - ``effective``: a velocidade real do carro agora;
    - ``transient``: a diferenca para a velocidade de regime do ponto. Positivo
      quando o carro ainda acelera para o alvo (saindo de curva); negativo
      quando esta acima do alvo (freando ou por inercia);
    - ``corner``: o quanto a curvatura do ponto baixa o teto de reta;
    - ``penalties``: pneu, combustivel, clima e controle de prova. Negativo e
      um ganho (pneu macio novo mais rapido que a referencia).
    """

    driver_id: str
    v_max_kmh: float
    speed_kmh: float
    effective: float
    transient: float
    corner: float
    penalties: Mapping[str, float]

    @property
    def effective_pct(self) -> float:
        return self.effective * 100.0

    @property
    def corner_pct(self) -> float:
        return self.corner * 100.0


class SpeedBreakdownReader:
    """Constroi ``SpeedBreakdown`` por carro a partir do resultado da corrida."""

    def __init__(self, race: Mapping[str, object]) -> None:
        breakdown = race.get("speed_breakdown") or {}
        self._cars = breakdown.get("cars", {}) if isinstance(breakdown, Mapping) else {}
        profiles = race.get("speed_profiles") or {}
        # Teto fisico por ponto, pre-ordenado por distancia para a busca.
        self._ceiling: dict[str, tuple[list[float], list[float]]] = {}
        if isinstance(profiles, Mapping):
            for did, samples in profiles.items():
                if not samples:
                    continue
                dists = [float(s["distance_m"]) for s in samples]
                speeds = [float(s["speed_ms"]) * 3.6 for s in samples]
                self._ceiling[did] = (dists, speeds)

    @property
    def available(self) -> bool:
        """Se a corrida traz a decomposicao; falso em corridas antigas."""

        return bool(self._cars)

    def _lap_data(self, did: str, lap: int) -> Mapping[str, object] | None:
        car = self._cars.get(did)
        if not car:
            return None
        laps = car.get("laps") or {}
        # O retrato e por volta fechada; antes da volta 1 nao ha penalidade.
        key = str(max(1, lap))
        return laps.get(key) or laps.get(str(len(laps)))

    def _ceiling_kmh(self, did: str, distance_m: float) -> float | None:
        entry = self._ceiling.get(did)
        if entry is None:
            return None
        dists, speeds = entry
        lap_length = dists[-1] if dists else 0.0
        d = distance_m % lap_length if lap_length else 0.0
        i = bisect_right(dists, d)
        if i <= 0:
            return speeds[0]
        if i >= len(dists):
            return speeds[-1]
        a, b = i - 1, i
        span = dists[b] - dists[a]
        f = (d - dists[a]) / span if span > 0 else 0.0
        return speeds[a] + (speeds[b] - speeds[a]) * f

    def at(
        self,
        driver_id: str,
        *,
        distance_m: float,
        speed_kmh: float,
        lap: int,
    ) -> SpeedBreakdown | None:
        """Fatias da velocidade do carro no ponto e na volta dados.

        ``distance_m`` e ``speed_kmh`` vem da trajetoria exportada; ``lap`` e a
        volta em andamento, que escolhe as penalidades. Devolve ``None`` quando
        a corrida nao traz a decomposicao desse carro.
        """

        car = self._cars.get(driver_id)
        if not car:
            return None
        v_max = float(car.get("v_max_kmh") or 0.0)
        if v_max <= 0.0:
            return None

        ceiling_kmh = self._ceiling_kmh(driver_id, distance_m)
        # Sem perfil de ponto, a curva nao e separavel: tudo que nao e efetivo
        # vira penalidade, e a fatia de curva fica zero.
        corner = 0.0
        ceiling_frac = 1.0
        if ceiling_kmh is not None:
            ceiling_frac = max(0.0, min(1.0, ceiling_kmh / v_max))
            corner = 1.0 - ceiling_frac

        data = self._lap_data(driver_id, lap)
        speed_scale = float(data["speed_scale"]) if data else 1.0
        shares = dict(data["delta_shares"]) if data else {}

        # Em fracao de v_max: a curva tira ``corner``; as penalidades tiram
        # ``ceiling_frac * (1 - speed_scale)`` do que a curva deixou; o resto e
        # a velocidade de regime do ponto. Repartido pelas parcelas do motor.
        penalty_total = ceiling_frac * (1.0 - speed_scale)
        share_sum = sum(shares.get(k, 0.0) for k in PENALTY_FACTORS)
        penalties: dict[str, float] = {}
        if share_sum != 0.0:
            for k in PENALTY_FACTORS:
                penalties[k] = penalty_total * shares.get(k, 0.0) / share_sum
        else:
            for k in PENALTY_FACTORS:
                penalties[k] = 0.0

        # Velocidade de regime do ponto (teto reduzido pelas condicoes) versus a
        # velocidade real agora: o vao e o transitorio de aceleracao/frenagem,
        # o que falta (ou sobra) para o carro atingir o regime naquele ponto.
        target = ceiling_frac * speed_scale
        effective = max(0.0, speed_kmh / v_max)
        transient = target - effective
        return SpeedBreakdown(
            driver_id=driver_id,
            v_max_kmh=v_max,
            speed_kmh=speed_kmh,
            effective=effective,
            transient=transient,
            corner=corner,
            penalties=penalties,
        )
