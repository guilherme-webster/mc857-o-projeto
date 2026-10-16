"""Reproducao volta a volta de uma corrida ja simulada, sem depender do Arcade.

O motor detalhado devolve, em ``history``, um retrato da classificacao ao fim
de cada volta. Este modulo transforma esses retratos numa linha do tempo por
carro e responde, para qualquer instante do relogio da corrida, quantas voltas
cada carro ja percorreu, quem abandonou e qual e a classificacao ao vivo.

Fronteiras:

- o modulo apenas *le* o resultado; ele nao simula, nao sorteia e nao corrige
  nada do motor. A fonte de verdade continua sendo o JSON do backend;
- o relogio ``t_ms`` e o tempo de corrida em milissegundos, a mesma unidade de
  ``total_time_ms``. Converter tempo de tela em tempo de corrida (velocidade,
  pausa, retrocesso) e responsabilidade da ``TrackView``;
- o progresso e medido em **voltas** (fracionarias). Converter voltas em metros
  e em pontos da pista e responsabilidade de quem conhece a geometria.

Hipoteses de exibicao (nao fazem parte do modelo de corrida):

- todos os carros partem da linha no instante zero; a penalidade de largada por
  posicao ja esta embutida no tempo da primeira volta;
- dentro de uma volta a velocidade e constante, isto e, a posicao e
  interpolada linearmente entre dois fins de volta. Uma parada nos boxes ou um
  SC aparecem como uma volta inteira mais lenta, nao como um ponto da pista;
- o carro que abandona completa a volta registrada e some da pista no fim
  dela, porque o motor decide o abandono depois de contabilizar a volta.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import floor

RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True)
class CarTimeline:
    """Instantes em que um carro terminou cada volta.

    ``lap_end_times_ms[k - 1]`` e o tempo de corrida ao fim da volta ``k``.
    A sequencia e nao decrescente. Ela pode ter degraus de duracao zero: a
    compressao do SC reescreve o tempo acumulado como ``tempo_do_lider +
    k * intervalo_minimo`` e, para um carro que estava mais de uma volta atras,
    isso coloca o fim da volta antes do fim da volta anterior. O motor nao tem
    distancia fisica e chama isso de desdobramento implicito; aqui o fim da
    volta e elevado ao instante anterior, de modo que o carro avanca a volta
    instantaneamente em vez de andar para tras.
    """

    driver_id: str
    name: str
    lap_end_times_ms: tuple[float, ...]
    retired: bool

    @property
    def laps_completed(self) -> int:
        return len(self.lap_end_times_ms)

    @property
    def finish_time_ms(self) -> float:
        """Instante em que o carro termina a corrida ou abandona."""

        return self.lap_end_times_ms[-1] if self.lap_end_times_ms else 0.0

    def laps_at(self, t_ms: float) -> float:
        """Voltas percorridas no instante ``t_ms``, entre 0 e ``laps_completed``."""

        times = self.lap_end_times_ms
        if not times or t_ms <= 0.0:
            return 0.0
        if t_ms >= times[-1]:
            return float(len(times))
        # bisect_right escolhe o ultimo de varios fins de volta iguais, o que
        # aplica o degrau do desdobramento no proprio instante do empate.
        lap_index = bisect_right(times, t_ms)
        start = times[lap_index - 1] if lap_index else 0.0
        end = times[lap_index]
        return lap_index + (t_ms - start) / (end - start)

    def time_at_laps(self, laps: float) -> float | None:
        """Instante em que o carro atinge ``laps`` voltas; ``None`` se nunca."""

        times = self.lap_end_times_ms
        if laps <= 0.0:
            return 0.0
        if laps > len(times):
            return None
        lap_index = int(laps)
        if lap_index == laps:
            return times[lap_index - 1]
        start = times[lap_index - 1] if lap_index else 0.0
        end = times[lap_index]
        return start + (laps - lap_index) * (end - start)

    def is_retired_at(self, t_ms: float) -> bool:
        return self.retired and t_ms >= self.finish_time_ms


@dataclass(frozen=True, slots=True)
class StandingRow:
    """Linha da classificacao ao vivo.

    ``gap_ms`` e o intervalo para o lider, medido como na transmissao: quanto
    tempo depois do lider o carro passa pelo ponto onde o lider esta agora.
    E ``None`` para o lider, para carros fora da prova e quando o carro nao
    chegara aquele ponto antes de abandonar.
    """

    position: int
    driver_id: str
    name: str
    lap: int
    retired: bool
    gap_ms: float | None


class RacePlayback:
    """Linha do tempo de uma corrida construida a partir de ``history``."""

    def __init__(self, race: Mapping[str, object]) -> None:
        total_laps = race.get("total_laps")
        if isinstance(total_laps, bool) or not isinstance(total_laps, int):
            raise ValueError("corrida sem total_laps inteiro")
        if total_laps < 1:
            raise ValueError("total_laps deve ser positivo")
        history = race.get("history")
        if not isinstance(history, Sequence) or not history:
            raise ValueError(
                "corrida sem history volta a volta; rode-a de novo no motor atual"
            )
        self.total_laps = total_laps
        self._cars = _build_timelines(history, total_laps)
        self._by_id = {car.driver_id: car for car in self._cars}
        self.duration_ms = max(car.finish_time_ms for car in self._cars)

    @property
    def cars(self) -> tuple[CarTimeline, ...]:
        return self._cars

    def car(self, driver_id: str) -> CarTimeline:
        return self._by_id[driver_id]

    def on_track(self, t_ms: float) -> list[tuple[str, float]]:
        """``(driver_id, voltas)`` dos carros que ainda estao na pista."""

        return [
            (car.driver_id, car.laps_at(t_ms))
            for car in self._cars
            if not car.is_retired_at(t_ms)
        ]

    def leader_laps(self, t_ms: float) -> float:
        """Voltas percorridas pelo lider entre os carros ainda na pista."""

        return max(
            (laps for _, laps in self.on_track(t_ms)),
            default=max(car.laps_completed for car in self._cars),
        )

    def current_lap(self, t_ms: float) -> int:
        """Volta em andamento do lider, entre 1 e ``total_laps``."""

        return _lap_in_progress(self.leader_laps(t_ms), self.total_laps)

    def standings(self, t_ms: float) -> list[StandingRow]:
        """Classificacao ao vivo no instante ``t_ms``.

        Carros em pista vem primeiro, por voltas percorridas; quem abandonou
        vem depois, por voltas completadas e instante do abandono. E a regra
        de ``_detailed_classification`` do motor aplicada ao progresso
        interpolado, para que a tabela concorde com os carros desenhados. No
        fim da corrida ela coincide com a classificacao final.
        """

        running = []
        retired = []
        for car in self._cars:
            if car.is_retired_at(t_ms):
                retired.append(car)
            else:
                running.append((car, car.laps_at(t_ms)))

        # Empate exato so ocorre com zero voltas (largada) ou com todos ja na
        # chegada; desempata quem fecha antes a volta atual (ou a ultima).
        running.sort(
            key=lambda item: (
                -item[1],
                _next_lap_end(item[0], item[1]),
                item[0].driver_id,
            )
        )
        retired.sort(
            key=lambda car: (-car.laps_completed, car.finish_time_ms, car.driver_id)
        )

        rows: list[StandingRow] = []
        leader_time: float | None = None
        leader_laps = running[0][1] if running else 0.0
        if running:
            leader_time = running[0][0].time_at_laps(leader_laps)
        for car, laps in running:
            gap_ms: float | None = None
            if rows:
                reach_time = car.time_at_laps(leader_laps)
                if reach_time is not None and leader_time is not None:
                    gap_ms = reach_time - leader_time
            rows.append(
                StandingRow(
                    position=len(rows) + 1,
                    driver_id=car.driver_id,
                    name=car.name,
                    lap=_lap_in_progress(laps, self.total_laps),
                    retired=False,
                    gap_ms=gap_ms,
                )
            )
        for car in retired:
            rows.append(
                StandingRow(
                    position=len(rows) + 1,
                    driver_id=car.driver_id,
                    name=car.name,
                    lap=car.laps_completed,
                    retired=True,
                    gap_ms=None,
                )
            )
        return rows


def _build_timelines(
    history: Sequence[object], total_laps: int
) -> tuple[CarTimeline, ...]:
    """Monte as linhas do tempo validando o contrato do ``history``.

    Cada retrato deve listar os carros com ``laps_completed`` e
    ``total_time_ms``. Um carro em pista avanca exatamente uma volta por
    retrato; um carro que abandonou repete o ultimo valor. Qualquer outra
    coisa indica um JSON de outra versao do motor, e o erro e explicito em vez
    de virar uma animacao plausivel e errada.
    """

    order: list[str] = []
    names: dict[str, str] = {}
    times: dict[str, list[float]] = {}
    statuses: dict[str, str] = {}
    for snapshot in history:
        cars = snapshot.get("cars") if isinstance(snapshot, Mapping) else None
        if not isinstance(cars, Sequence):
            raise ValueError("retrato do history sem lista de carros")
        for car in cars:
            try:
                driver_id = str(car["driver_id"])
                laps = int(car["laps_completed"])
                total_ms = float(car["total_time_ms"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"carro malformado no history: {error!r}") from error
            if driver_id not in times:
                order.append(driver_id)
                names[driver_id] = str(car.get("name", driver_id))
                times[driver_id] = []
            lap_times = times[driver_id]
            if laps == len(lap_times) + 1:
                previous = lap_times[-1] if lap_times else 0.0
                lap_times.append(max(total_ms, previous))
            elif laps != len(lap_times):
                raise ValueError(
                    f"{driver_id}: laps_completed salta de {len(lap_times)} para {laps}"
                )
            statuses[driver_id] = str(car.get("status", ""))

    timelines = []
    for driver_id in order:
        lap_times = times[driver_id]
        retired = statuses[driver_id] == RETIRED
        if len(lap_times) > total_laps:
            raise ValueError(f"{driver_id}: mais voltas que total_laps")
        if not retired and len(lap_times) != total_laps:
            raise ValueError(
                f"{driver_id}: em prova com {len(lap_times)} de {total_laps} voltas"
            )
        if not lap_times:
            raise ValueError(f"{driver_id}: sem nenhuma volta registrada")
        timelines.append(
            CarTimeline(driver_id, names[driver_id], tuple(lap_times), retired)
        )
    if not timelines:
        raise ValueError("history sem carros")
    return tuple(timelines)


def _lap_in_progress(laps: float, total_laps: int) -> int:
    return max(1, min(floor(laps) + 1, total_laps))


def _next_lap_end(car: CarTimeline, laps: float) -> float:
    times = car.lap_end_times_ms
    return times[min(floor(laps), len(times) - 1)]
