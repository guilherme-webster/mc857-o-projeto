"""Decomposicao auditavel do tempo de volta (plano do produto, secao 8.2).

A regra e aditiva e cada parcela e devolvida separadamente em
``LapTimeBreakdown``. Isso atende ao risco "modelo aparentemente preciso, mas
sem evidencia" registrado na secao 15 do plano: qualquer tempo produzido pelo
motor pode ser aberto e conferido parcela a parcela.

**A referencia ja contem efeitos.** ``reference_ms`` e estimado a partir das
voltas historicas mais rapidas do proprio piloto, ou seja, voltas com pneu novo,
combustivel baixo e ar livre. Por isso as parcelas abaixo representam apenas o
*afastamento* dessa condicao ideal e nao podem ser somadas a uma referencia que
ja inclua combustivel alto ou pneu velho -- isso contaria o mesmo efeito duas
vezes, erro descrito em ``docs/contrato-perfil-simulacao.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

from f1_simulator.domain.model_parameters import ModelParameters, TrackParameters
from f1_simulator.domain.random_source import RandomSource
from f1_simulator.domain.tyres import TyreSet, tyre_penalty_ms

#: Piso absoluto de um tempo de volta modelado, em ms. Serve apenas para impedir
#: que uma combinacao extrema de ruido negativo produza tempo nao positivo; nao
#: e um limite fisico de nenhum circuito real.
MINIMUM_LAP_TIME_MS = 1_000.0


@dataclass(frozen=True, slots=True)
class LapTimeBreakdown:
    """Parcelas somadas para formar ``total_ms``; a soma e verificavel.

    ``total_ms`` pode diferir da soma exata das parcelas em um unico caso: se o
    piso ``MINIMUM_LAP_TIME_MS`` tiver sido aplicado. ``floored`` registra isso
    explicitamente em vez de esconder a diferenca.
    """

    reference_ms: float
    fuel_ms: float
    tyre_ms: float
    traffic_ms: float
    pit_ms: float
    noise_ms: float
    total_ms: float
    floored: bool = False

    def components_sum_ms(self) -> float:
        """Soma das parcelas antes do piso; usada por testes e pelo relatorio."""

        return (
            self.reference_ms
            + self.fuel_ms
            + self.tyre_ms
            + self.traffic_ms
            + self.pit_ms
            + self.noise_ms
        )


def fuel_penalty_ms(
    parameters: ModelParameters, lap_number: int, total_laps: int
) -> float:
    """Tempo perdido nesta volta pela massa de combustivel ainda embarcada.

    Modelada como proporcional as voltas que ainda faltam: na ultima volta o
    carro esta leve e a penalidade e zero, o que ancora a escala na mesma
    condicao da ``reference_ms``.

    Este e o unico efeito grande do modelo que **nao** foi calibrado por
    composto ou circuito: a inclinacao vem da regressao do historico completo
    (ver ``application/calibrate_model.py``) e vale para a era calibrada.
    """

    if lap_number < 1 or total_laps < 1 or lap_number > total_laps:
        raise ValueError(
            f"volta {lap_number} fora do intervalo 1..{total_laps}"
        )
    remaining = total_laps - lap_number
    return parameters.fuel_penalty_ms_per_remaining_lap * remaining


def traffic_penalty_ms(
    parameters: ModelParameters, track: TrackParameters, gap_ahead_ms: float | None
) -> float:
    """Penalidade por seguir de perto o carro da frente (ar sujo).

    Vale zero para o lider (``gap_ahead_ms is None``) e para quem esta alem do
    limiar. Dentro do limiar cresce linearmente conforme o carro se aproxima, e
    e escalada pela dificuldade de ultrapassagem do circuito.

    Esta parcela e uma **hipotese**: o Trotman nao registra distancia entre
    carros volta a volta. Ela existe para que a classificacao nao seja uma
    ordenacao trivial de ritmos constantes, e seu efeito agregado e conferido
    no backtest.
    """

    if gap_ahead_ms is None or gap_ahead_ms >= parameters.traffic_threshold_ms:
        return 0.0
    if gap_ahead_ms < 0:
        raise ValueError("gap_ahead_ms nao pode ser negativo")
    closeness = 1.0 - (gap_ahead_ms / parameters.traffic_threshold_ms)
    return parameters.traffic_penalty_ms * closeness * track.overtaking_difficulty


def lap_noise_ms(parameters: ModelParameters, rng: RandomSource) -> float:
    """Perturbacao assimetrica por volta, consumindo a fonte aleatoria injetada.

    Os residuos medidos no historico sao claramente assimetricos a direita
    (p05 aproximadamente -1.3 s, mediana +0.2 s, p95 +2.1 s): existe um piso
    fisico para quao rapido uma volta pode ser, mas nao um teto para quanto
    tempo se pode perder. Uma normal simetrica seria escolha por conveniencia.

    A construcao escala os desvios positivos por ``1 + skew`` e os negativos por
    ``1 - skew``, preservando a forma normal em cada lado. Com ``skew = 0`` o
    resultado volta a ser exatamente uma normal.
    """

    if parameters.lap_noise_ms == 0.0:
        return 0.0
    z = rng.standard_normal()
    scale = 1.0 + parameters.lap_noise_skew if z > 0 else 1.0 - parameters.lap_noise_skew
    return z * parameters.lap_noise_ms * scale


def compute_lap_time(
    *,
    reference_ms: float,
    parameters: ModelParameters,
    track: TrackParameters,
    tyre: TyreSet,
    lap_number: int,
    total_laps: int,
    gap_ahead_ms: float | None,
    pitting: bool,
    rng: RandomSource,
) -> LapTimeBreakdown:
    """Monte o tempo desta volta somando referencia e penalidades.

    A ordem de consumo da fonte aleatoria e fixa (apenas ``lap_noise_ms``), o
    que mantem a reprodutibilidade por semente. O abandono e sorteado pelo
    motor, nao aqui, para que esta funcao permaneca uma regra de tempo pura.
    """

    if reference_ms <= 0:
        raise ValueError("reference_ms deve ser positivo")

    compound = parameters.compound(tyre.compound)
    fuel = fuel_penalty_ms(parameters, lap_number, total_laps)
    tyre_ms = tyre_penalty_ms(tyre, compound, track)
    traffic = traffic_penalty_ms(parameters, track, gap_ahead_ms)
    pit = track.pit_loss_ms if pitting else 0.0
    noise = lap_noise_ms(parameters, rng)

    total = reference_ms + fuel + tyre_ms + traffic + pit + noise
    floored = total < MINIMUM_LAP_TIME_MS
    if floored:
        total = MINIMUM_LAP_TIME_MS

    return LapTimeBreakdown(
        reference_ms=reference_ms,
        fuel_ms=fuel,
        tyre_ms=tyre_ms,
        traffic_ms=traffic,
        pit_ms=pit,
        noise_ms=noise,
        total_ms=total,
        floored=floored,
    )
