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
  dela, porque o motor decide o abandono depois de contabilizar a volta;
- o pneu mostrado e o do ultimo retrato do proprio carro: o motor troca o jogo
  ao fim da volta da parada, entao o composto novo aparece quando o carro
  fecha essa volta. Durante a volta da parada a tabela mostra ``in_pit``;
- o combustivel, quando a corrida traz o modelo de massa, cai em linha reta
  entre dois fins de volta, como a posicao. A economia (lift-and-coast) e
  decidida pelo motor para a volta inteira e aparece na volta inteira;
- numa volta de reabastecimento o medidor desce ate a massa de chegada aos
  boxes (``fuel.refuel_stops[].fuel_before_kg``) e sobe de uma vez no fim da
  volta, quando o motor aplica o reabastecimento. A volta inteira e marcada
  como ``in_pit``, como uma parada de pneus.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import floor

RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True)
class TyreState:
    """Pneu e paradas de um carro num retrato; ``None`` quando desconhecido.

    O estado inicial vem de ``starting_grid``. Corridas salvas antes desse
    campo nao informam o pneu da largada, e ele fica ``None`` em vez de ser
    adivinhado a partir do primeiro retrato.
    """

    compound: str | None
    age_laps: int | None
    stops: int


@dataclass(frozen=True, slots=True)
class FuelState:
    """Combustivel de um carro num retrato.

    ``kg`` e a massa a bordo; ``saving_laps`` conta as voltas ja fechadas em
    lift-and-coast (``fuel_saving_laps`` do motor). O estado da largada vem de
    ``starting_grid[].fuel_kg`` e comeca com zero voltas de economia.
    """

    kg: float
    saving_laps: int
    #: Paradas de reabastecimento ja feitas (``refuels_made`` do motor).
    refuels: int = 0
    #: Massa ao chegar aos boxes, antes de reabastecer, quando esta volta
    #: termina num reabastecimento; ``None`` nas demais.
    before_refuel_kg: float | None = None


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
    # ``tyre_states[k]`` e o estado depois da volta ``k``; ``[0]`` e a largada.
    tyre_states: tuple[TyreState, ...] = ()
    retirement_cause: str | None = None
    grid_position: int | None = None
    # ``fuel_states[k]`` e o combustivel depois da volta ``k``; ``[0]`` e a
    # largada. Vazio quando a corrida nao traz o modelo de massa.
    fuel_states: tuple[FuelState, ...] = ()

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

    def tyre_at(self, t_ms: float) -> TyreState | None:
        """Pneu em uso no instante: o do ultimo retrato do proprio carro."""

        if not self.tyre_states:
            return None
        completed = min(floor(self.laps_at(t_ms)), len(self.tyre_states) - 1)
        return self.tyre_states[completed]

    def in_pit_lap_at(self, t_ms: float) -> bool:
        """Se a volta em andamento termina com uma parada nos boxes.

        O motor nao modela a entrada no pit lane: a perda da parada esta
        diluida na volta inteira, e por isso a volta inteira e marcada.
        """

        laps = self.laps_at(t_ms)
        completed = floor(laps)
        if completed >= self.laps_completed or completed + 1 >= len(self.tyre_states):
            return False
        before = self.tyre_states[completed]
        after = self.tyre_states[completed + 1]
        if after.stops > before.stops:
            return True
        fuel = self.fuel_states
        return (
            completed + 1 < len(fuel)
            and fuel[completed + 1].refuels > fuel[completed].refuels
        )

    def fuel_at(self, t_ms: float) -> float | None:
        """Combustivel a bordo (kg) no instante ``t_ms``; ``None`` sem dados.

        Interpola linearmente na fracao da volta entre dois fins de volta,
        como ``laps_at`` faz com a posicao. Nao e uma aproximacao a mais: o
        motor queima uma massa unica por volta, e a exibicao ja supoe
        velocidade constante dentro da volta, entao a massa cai em linha reta
        com a distancia que o carro desenhado percorreu. Depois da chegada ou
        do abandono, vale o ultimo retrato.
        """

        states = self.fuel_states
        if not states:
            return None
        laps = self.laps_at(t_ms)
        completed = floor(laps)
        if completed >= len(states) - 1:
            return states[-1].kg
        start = states[completed].kg
        following = states[completed + 1]
        end = (
            following.kg
            if following.before_refuel_kg is None
            else following.before_refuel_kg
        )
        return start + (laps - completed) * (end - start)

    def lift_and_coast_at(self, t_ms: float) -> bool:
        """Se a volta em andamento e feita economizando combustivel.

        O motor decide a economia no inicio da volta e soma uma volta a
        ``fuel_saving_laps`` ao fecha-la; como em ``in_pit_lap_at``, a volta
        inteira e marcada.
        """

        states = self.fuel_states
        completed = floor(self.laps_at(t_ms))
        if completed >= self.laps_completed or completed + 1 >= len(states):
            return False
        return states[completed + 1].saving_laps > states[completed].saving_laps


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
    tyre: TyreState | None = None
    in_pit: bool = False
    retirement_cause: str | None = None
    # Largada menos posicao atual: positivo quando ganhou posicoes.
    positions_gained: int | None = None
    # Combustivel a bordo e volta de lift-and-coast; ``None`` e ``False`` em
    # corridas sem o modelo de massa.
    fuel_kg: float | None = None
    lift_and_coast: bool = False


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
        self._cars = _build_timelines(
            history,
            total_laps,
            _starting_grid(race.get("starting_grid")),
            _refuel_levels(race.get("fuel")),
        )
        self._by_id = {car.driver_id: car for car in self._cars}
        self.duration_ms = max(car.finish_time_ms for car in self._cars)
        # Teto regulamentar do bloco ``fuel`` (kg), escala natural do medidor.
        self.max_fuel_kg = _max_fuel_kg(race.get("fuel"))

    @property
    def cars(self) -> tuple[CarTimeline, ...]:
        return self._cars

    @property
    def has_fuel(self) -> bool:
        """Se algum carro tem combustivel; falso em corridas sem o modelo."""

        return any(car.fuel_states for car in self._cars)

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
            position = len(rows) + 1
            rows.append(
                StandingRow(
                    position=position,
                    driver_id=car.driver_id,
                    name=car.name,
                    lap=_lap_in_progress(laps, self.total_laps),
                    retired=False,
                    gap_ms=gap_ms,
                    tyre=car.tyre_at(t_ms),
                    in_pit=car.in_pit_lap_at(t_ms),
                    positions_gained=(
                        car.grid_position - position
                        if car.grid_position is not None
                        else None
                    ),
                    fuel_kg=car.fuel_at(t_ms),
                    lift_and_coast=car.lift_and_coast_at(t_ms),
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
                    tyre=car.tyre_at(t_ms),
                    retirement_cause=car.retirement_cause,
                    fuel_kg=car.fuel_at(t_ms),
                )
            )
        return rows


def _starting_grid(value: object) -> dict[str, tuple[int, str, float | None]]:
    """``driver_id -> (posicao, composto, combustivel)`` de ``starting_grid``.

    O combustivel e ``None`` quando a largada nao traz ``fuel_kg``: corridas
    salvas antes do modelo de massa ou um backend sem ``fuel-v1.json``.
    """

    if value is None:
        return {}
    if not isinstance(value, Sequence):
        raise ValueError("starting_grid deveria ser uma lista")
    grid: dict[str, tuple[int, str, float | None]] = {}
    for entry in value:
        try:
            fuel = entry.get("fuel_kg")
            grid[str(entry["driver_id"])] = (
                int(entry["position"]),
                str(entry["compound"]),
                float(fuel) if fuel is not None else None,
            )
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise ValueError(f"starting_grid malformado: {error!r}") from error
    return grid


def _refuel_levels(value: object) -> dict[tuple[str, int], float]:
    """``(driver_id, volta) -> massa antes de reabastecer`` do bloco ``fuel``.

    Corridas sem reabastecimento, ou salvas antes dele, nao trazem a lista;
    o resultado e vazio e o medidor interpola entre fins de volta como antes.
    """

    if not isinstance(value, Mapping):
        return {}
    events = value.get("refuel_stops")
    if events is None:
        return {}
    if not isinstance(events, Sequence):
        raise ValueError("fuel.refuel_stops deveria ser uma lista")
    levels = {}
    for event in events:
        try:
            levels[(str(event["driver_id"]), int(event["lap"]))] = float(
                event["fuel_before_kg"]
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"fuel.refuel_stops malformado: {error!r}") from error
    return levels


def _max_fuel_kg(value: object) -> float | None:
    """``max_fuel_kg`` do bloco ``fuel``; ``None`` se a corrida nao o traz."""

    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("bloco fuel deveria ser um objeto")
    max_fuel = value.get("max_fuel_kg")
    if max_fuel is None:
        return None
    try:
        max_fuel = float(max_fuel)
    except (TypeError, ValueError) as error:
        raise ValueError(f"fuel.max_fuel_kg malformado: {error!r}") from error
    if not max_fuel > 0.0:
        raise ValueError("fuel.max_fuel_kg deve ser positivo")
    return max_fuel


def _tyre_state(car: Mapping[str, object]) -> TyreState:
    compound = car.get("compound")
    age = car.get("tyre_age_laps")
    return TyreState(
        compound=str(compound) if compound is not None else None,
        age_laps=int(age) if age is not None else None,
        stops=int(car.get("stops_made") or 0),
    )


def _fuel_state(
    car: Mapping[str, object], before_refuel_kg: float | None = None
) -> FuelState | None:
    fuel = car.get("fuel_kg")
    if fuel is None:
        return None
    return FuelState(
        kg=float(fuel),
        saving_laps=int(car.get("fuel_saving_laps") or 0),
        refuels=int(car.get("refuels_made") or 0),
        before_refuel_kg=before_refuel_kg,
    )


def _build_timelines(
    history: Sequence[object],
    total_laps: int,
    starting_grid: Mapping[str, tuple[int, str, float | None]],
    refuel_levels: Mapping[tuple[str, int], float] | None = None,
) -> tuple[CarTimeline, ...]:
    """Monte as linhas do tempo validando o contrato do ``history``.

    Cada retrato deve listar os carros com ``laps_completed`` e
    ``total_time_ms``. Um carro em pista avanca exatamente uma volta por
    retrato; um carro que abandonou repete o ultimo valor. Qualquer outra
    coisa indica um JSON de outra versao do motor, e o erro e explicito em vez
    de virar uma animacao plausivel e errada.

    O combustivel e opcional e vale por carro, tudo ou nada: sem a carga da
    largada ou sem ``fuel_kg`` em alguma volta nao ha de onde interpolar, e o
    carro fica sem combustivel em vez de ter um trecho adivinhado.
    """

    order: list[str] = []
    names: dict[str, str] = {}
    times: dict[str, list[float]] = {}
    statuses: dict[str, str] = {}
    tyres: dict[str, list[TyreState]] = {}
    # ``None`` assim que falta um retrato de combustivel do carro.
    fuels: dict[str, list[FuelState] | None] = {}
    causes: dict[str, str | None] = {}
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
                start = starting_grid.get(driver_id)
                tyres[driver_id] = [
                    TyreState(start[1], 0, 0) if start else TyreState(None, None, 0)
                ]
                start_fuel = start[2] if start else None
                fuels[driver_id] = (
                    [FuelState(start_fuel, 0)] if start_fuel is not None else None
                )
            lap_times = times[driver_id]
            if laps == len(lap_times) + 1:
                previous = lap_times[-1] if lap_times else 0.0
                lap_times.append(max(total_ms, previous))
                try:
                    tyres[driver_id].append(_tyre_state(car))
                except (TypeError, ValueError) as error:
                    raise ValueError(
                        f"{driver_id}: pneu malformado no history: {error!r}"
                    ) from error
                fuel_states = fuels[driver_id]
                if fuel_states is not None:
                    try:
                        fuel = _fuel_state(
                            car, (refuel_levels or {}).get((driver_id, laps))
                        )
                    except (TypeError, ValueError) as error:
                        raise ValueError(
                            f"{driver_id}: combustivel malformado no history: "
                            f"{error!r}"
                        ) from error
                    if fuel is None:
                        fuels[driver_id] = None
                    else:
                        fuel_states.append(fuel)
            elif laps != len(lap_times):
                raise ValueError(
                    f"{driver_id}: laps_completed salta de {len(lap_times)} para {laps}"
                )
            statuses[driver_id] = str(car.get("status", ""))
            cause = car.get("retirement_cause")
            causes[driver_id] = str(cause) if cause is not None else None

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
        start = starting_grid.get(driver_id)
        timelines.append(
            CarTimeline(
                driver_id,
                names[driver_id],
                tuple(lap_times),
                retired,
                tyre_states=tuple(tyres[driver_id]),
                retirement_cause=causes[driver_id] if retired else None,
                grid_position=start[0] if start else None,
                fuel_states=tuple(fuels[driver_id] or ()),
            )
        )
    if not timelines:
        raise ValueError("history sem carros")
    return tuple(timelines)


def _lap_in_progress(laps: float, total_laps: int) -> int:
    return max(1, min(floor(laps) + 1, total_laps))


def _next_lap_end(car: CarTimeline, laps: float) -> float:
    times = car.lap_end_times_ms
    return times[min(floor(laps), len(times) - 1)]
