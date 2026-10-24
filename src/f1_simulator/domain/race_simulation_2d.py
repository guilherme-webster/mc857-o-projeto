"""Motor de corrida 2D (ADR 0011): roda a fisica espacial de ``track_space`` e
produz o mesmo ``history`` por volta que o motor por volta, para o frontend e as
corridas salvas lerem sem mudanca.

A fisica continua em ``track_space`` (posicao, ultrapassagem, colisao). Aqui se
converte a trajetoria continua em retratos de fim de volta e se traduzem, para a
moeda espacial do 2D, os efeitos que o motor por volta cobra em tempo:

- pneu, combustivel, clima e lift-and-coast viram uma penalidade em ms por
  volta, convertida numa reducao fracionaria da velocidade (``speed_scale``);
- a perda de boxes de uma parada entra como penalidade de tempo na volta de
  entrada, pelo mesmo caminho;
- o controle de prova (SC, VSC, amarela, vermelha, relargada) reusa o automato
  de ``race_control``: ``LapEffects`` modula o ``speed_scale`` de todos os
  carros na volta neutralizada, e ``track_space`` segura a fila sem disputa nem
  contato naquelas voltas;
- a bandeira azul nao precisa de aproximacao temporal como no motor por volta:
  no 2D o retardatario ja esta fisicamente atras em ``distance_m``, entao a fila
  o mantem atras do carro que vai dar a volta nele.

Fronteiras (ADR 0011): este e o motor 2D, selecionavel. O resultado continua um
cenario hipotetico, nao comparavel ao historico; a estrategia e as heuristicas
reusadas sao as mesmas do motor por volta. Tudo rotulado em ``assumptions``.
"""

from __future__ import annotations

from f1_simulator.domain.fuel import FuelLap, FuelPlan, fuel_lap
from f1_simulator.domain.model_parameters import (
    CompoundParameters,
    ModelParameters,
    TrackParameters,
)
from f1_simulator.domain.race_control import (
    HEURISTIC_RACE_CONTROL,
    GREEN,
    Incident,
    LapEffects,
    RaceControlParameters,
    RaceControlState,
    effects,
    step,
)
from f1_simulator.domain.random_source import RandomSource
from f1_simulator.domain.speed_dynamics import (
    CarPhysics,
    lap_time_ms,
    physics_for,
    steady_lap,
)
from f1_simulator.domain.strategy import (
    FuelStatus,
    HeuristicPitStrategy,
    StrategyState,
)
from f1_simulator.domain.track_space import (
    ASSUMED_CAR_LENGTH_M,
    ASSUMED_CAR_WIDTH_M,
    CarSpaceState,
    FieldSample,
    build_track_space,
    integrate_field,
)
from f1_simulator.domain.track_geometry import TrackGeometry
from f1_simulator.domain.tyres import TyreSet, tyre_penalty_ms

RUNNING = "RUNNING"
RETIRED = "RETIRED"
CONTACT = "CONTACT"
MECHANICAL = "MECHANICAL"
FUEL = "FUEL"

#: Espacamento longitudinal (m) entre posicoes de largada no grid 2D. Hipotese
#: nao calibrada; so evita que os carros nascam sobrepostos na linha.
GRID_SPACING_M = 8.0


def _lap_crossing_times_ms(
    samples: tuple[FieldSample, ...],
    driver_id: str,
    lap_length_m: float,
    total_laps: int,
) -> tuple[list[float], bool, int | None, float | None]:
    """Instantes (ms) em que o carro cruza cada volta, e seu desfecho.

    Interpola linearmente o instante em que ``distance_m`` cruza ``k *
    lap_length`` entre dois retratos. Retorna os tempos por volta concluida, se
    o carro abandonou, a volta do abandono e o instante (ms) do abandono.
    """

    times_ms: list[float] = []
    retired = False
    retired_on: int | None = None
    retired_at_ms: float | None = None
    next_lap = 1
    prev = None
    for sample in samples:
        car = next(c for c in sample.cars if c.driver_id == driver_id)
        if prev is not None and next_lap <= total_laps:
            target = next_lap * lap_length_m
            if prev[1] < target <= car.distance_m:
                span = car.distance_m - prev[1]
                f = (target - prev[1]) / span if span > 0 else 0.0
                t_ms = (prev[0] + (sample.time_s - prev[0]) * f) * 1000.0
                times_ms.append(t_ms)
                next_lap += 1
        if car.retired and not retired:
            retired = True
            retired_on = len(times_ms) + 1
            retired_at_ms = sample.time_s * 1000.0
        prev = (sample.time_s, car.distance_m)
    return times_ms, retired, retired_on, retired_at_ms


#: Resolucao minima de reamostragem (ms) da faixa lateral. Mais esparso que o
#: passo de integracao (50 ms); o frontend interpola entre pontos.
TRAJECTORY_SAMPLE_MS = 250.0

#: So emite um ponto quando o deslocamento lateral mudou mais que isto (m) desde
#: o ultimo emitido. Como o carro anda no centro quase o tempo todo
#: (``lateral_m ~= 0``), o limiar corta a imensa maioria dos pontos e deixa so
#: as manobras (ultrapassagem, retorno ao centro), onde o lado a lado importa.
TRAJECTORY_LATERAL_EPS_M = 0.15


def _trajectories_2d(
    samples: tuple[FieldSample, ...],
    driver_ids: list[str],
) -> dict[str, list[list[float]]]:
    """Faixa lateral por carro ao longo do tempo, comprimida para o frontend.

    Cada ponto e ``[t_ms, lateral_m]``: so o deslocamento lateral, porque a
    posicao longitudinal o frontend ja reconstroi do tempo de volta. A serie e
    reamostrada a ``TRAJECTORY_SAMPLE_MS`` e comprimida por limiar
    (``TRAJECTORY_LATERAL_EPS_M``): so vira ponto quando o lateral muda o
    bastante, mais o primeiro e o ultimo instante. Assim um carro que corre no
    centro a corrida toda gera pouquissimos pontos, e o payload nao explode com
    a duracao. O frontend interpola linearmente entre os pontos.

    Formato de lista (``[t, lat]``) em vez de dict por ponto para encolher ainda
    mais o JSON; o frontend le por indice.
    """

    series: dict[str, list[list[float]]] = {did: [] for did in driver_ids}
    last_emit_ms: dict[str, float] = {did: -TRAJECTORY_SAMPLE_MS for did in driver_ids}
    last_lat: dict[str, float] = {did: 0.0 for did in driver_ids}
    pending: dict[str, list[float] | None] = {did: None for did in driver_ids}
    done: set[str] = set()

    def _push(did: str, t_ms: float, lat: float) -> None:
        series[did].append([round(t_ms, 1), round(lat, 3)])
        last_emit_ms[did] = t_ms
        last_lat[did] = lat

    for sample in samples:
        t_ms = sample.time_s * 1000.0
        for car in sample.cars:
            did = car.driver_id
            if did in done:
                continue
            lat = car.lateral_m
            if not series[did]:
                _push(did, t_ms, lat)  # primeiro ponto sempre entra
            elif car.retired:
                _push(did, t_ms, lat)
                done.add(did)
            elif t_ms - last_emit_ms[did] >= TRAJECTORY_SAMPLE_MS:
                if abs(lat - last_lat[did]) >= TRAJECTORY_LATERAL_EPS_M:
                    # Fecha o patamar anterior antes do novo valor, para a
                    # interpolacao nao "cortar caminho" na manobra.
                    if pending[did] is not None:
                        _push(did, *pending[did])
                        pending[did] = None
                    _push(did, t_ms, lat)
                else:
                    pending[did] = [t_ms, lat]
    # Garante o ultimo instante de quem nao abandonou, para a serie cobrir o fim.
    for did in driver_ids:
        if pending[did] is not None and did not in done:
            _push(did, *pending[did])
    return series


def _classification(states: dict[str, dict]) -> list[dict]:
    """Ordene e numere os carros pela regra da corrida (igual ao motor por volta)."""

    ordered = sorted(
        states.values(),
        key=lambda s: (
            s["status"] == RETIRED,
            -s["laps_completed"],
            s["total_time_ms"],
            s["driver_id"],
        ),
    )
    rows = []
    for index, s in enumerate(ordered, start=1):
        laps = s["laps_completed"]
        row = {
            "position": index,
            "driver_id": s["driver_id"],
            "name": s["name"],
            "total_time_ms": round(s["total_time_ms"], 1),
            "lap_time_ms": round(s["total_time_ms"] / laps, 1) if laps else 0.0,
            "laps_completed": laps,
            "status": s["status"],
            "compound": s["compound"],
            "tyre_age_laps": s["tyre_age_laps"],
            "stops_made": s["stops_made"],
            "retirement_cause": s["retirement_cause"],
            "blocked_laps": 0,
        }
        if s.get("fuel_kg") is not None:
            row["fuel_kg"] = round(s["fuel_kg"], 3)
            row["fuel_saving_laps"] = s["fuel_saving_laps"]
            row["refuels_made"] = s["refuels_made"]
        rows.append(row)
    return rows


def simulate_2d_race(
    entrants: list[dict],
    geometry: TrackGeometry,
    *,
    total_laps: int,
    rng: RandomSource,
    base_physics: CarPhysics = CarPhysics(),
    compounds: dict[str, CompoundParameters] | None = None,
    track_params: TrackParameters | None = None,
    model_parameters: ModelParameters | None = None,
    fuel: FuelPlan | None = None,
    lap_surface_water: list[float] | None = None,
    reliability_by_id: dict[str, float] | None = None,
    mechanical_hazard_per_lap: float = 0.0,
    race_control: RaceControlParameters | None = HEURISTIC_RACE_CONTROL,
    width_m: float | None = None,
    dt_s: float = 0.05,
) -> dict:
    """Simule a corrida no motor 2D e devolva ``history`` + ``classification``.

    Cada entrante e ``{"driver_id", "name", "grid_position", "attributes",
    "aggression", "compound"}``; ``attributes`` (ou ``None``) deriva o envelope
    fisico por carro, como no ADR 0010.

    Pneu, combustivel e clima entram como penalidades de tempo (os modelos
    existentes) convertidas numa reducao fracionaria da velocidade do carro
    (``speed_scale``), de modo que a volta mais lenta emerge do movimento:

    - ``compounds`` + ``track_params``: o pneu degrada com a idade (``tyres.py``);
    - ``fuel``: a massa a bordo custa tempo e diminui a cada volta queimada; sem
      reabastecimento permitido, o lift-and-coast economiza combustivel ao custo
      de tempo (``fuel.py``);
    - ``lap_surface_water``: a agua na pista penaliza por volta (``weather.py``).

    Com ``model_parameters`` + ``track_params`` + ``fuel``, cada piloto ganha
    uma ``HeuristicPitStrategy`` (a mesma do motor por volta): ela decide a volta
    de parada, o composto e o abastecimento; a perda de boxes entra como tempo na
    volta de entrada. Sem esses parametros o 2D roda sem paradas.

    Com ``race_control``, o automato de ``race_control`` roda uma vez por volta
    da corrida (lider) e neutraliza o pelotao sob SC/VSC/vermelha, modulando o
    ritmo de todos; a relargada acelera a volta seguinte. Incidentes de contato
    (abandono por toque no integrador) e falhas mecanicas alimentam o automato.

    Cada efeito ausente simplesmente nao atua.
    """

    track = (
        build_track_space(geometry)
        if width_m is None
        else build_track_space(geometry, width_m=width_m)
    )
    lap_length_m = track.lap_length_m

    tyre_active = compounds is not None and track_params is not None
    pit_active = (
        tyre_active and model_parameters is not None and fuel is not None
    )
    refuel_mode = (
        fuel is not None and fuel.parameters.refuelling_allowed
    )

    cars: list[CarSpaceState] = []
    physics_by_id: dict[str, CarPhysics] = {}
    aggression_by_id: dict[str, float] = {}
    names: dict[str, str] = {}
    grid_by_id: dict[str, int] = {}
    tyre_by_id: dict[str, TyreSet] = {}
    compounds_used: dict[str, tuple[str, ...]] = {}
    fuel_kg: dict[str, float] = {}
    strategy_by_id: dict[str, HeuristicPitStrategy] = {}
    stops_made: dict[str, int] = {}
    refuels_made: dict[str, int] = {}
    fuel_saving_laps: dict[str, int] = {}
    start_fuel_kg_by_id: dict[str, float] = {}
    # Eventos de reabastecimento para o bloco ``fuel`` que o frontend consome.
    refuel_events: list[dict] = []
    # Volta de referencia de cada carro (ms), para converter penalidades de tempo
    # em fator de velocidade. E o tempo que o proprio envelope fisico produz.
    ref_ms: dict[str, float] = {}
    for entry in sorted(entrants, key=lambda e: e["grid_position"]):
        did = entry["driver_id"]
        names[did] = entry["name"]
        grid_by_id[did] = entry["grid_position"]
        physics = physics_for(entry.get("attributes"), base_physics)
        physics_by_id[did] = physics
        aggression_by_id[did] = float(entry.get("aggression", 1.0))
        compound = entry.get("compound", "MEDIUM")
        tyre_by_id[did] = TyreSet(compound, 0)
        compounds_used[did] = (compound,)
        stops_made[did] = 0
        refuels_made[did] = 0
        fuel_saving_laps[did] = 0
        ref_ms[did] = lap_time_ms(steady_lap(geometry, physics))
        if fuel is not None:
            load = entry.get("start_fuel_kg")
            fuel_kg[did] = (
                float(load) if load is not None else fuel.start_fuel_kg(total_laps)
            )
            start_fuel_kg_by_id[did] = fuel_kg[did]
        if pit_active:
            assert model_parameters is not None and track_params is not None
            strategy_by_id[did] = HeuristicPitStrategy(model_parameters, track_params)
        offset = (len(entrants) - entry["grid_position"]) * GRID_SPACING_M
        cars.append(CarSpaceState(did, distance_m=offset, lateral_m=0.0))

    # Retrato do estado de pneu/combustivel/paradas ao fim de cada volta de cada
    # carro, para o history refletir a evolucao e nao apenas o estado final.
    lap_snapshots: dict[str, dict[int, dict]] = {did: {} for did in names}

    # Estado global do controle de prova, avancado uma vez por volta da corrida.
    control_state = RaceControlState()
    control_events: list[dict] = []
    control_by_lap: list[dict] = []
    # ``LapEffects`` da volta corrente da corrida, aplicado a todos os carros.
    lap_effects_by_lap: dict[int, LapEffects] = {}
    control_laps_done = 0

    def _status_for_lap(lap_number: int) -> str:
        """Estado da pista na volta ``lap_number`` para a queima de combustivel."""

        if race_control is None:
            return GREEN
        entry = next(
            (row for row in control_by_lap if row["lap"] == lap_number), None
        )
        return entry["status"] if entry is not None else GREEN

    def _neutralized_lap(lap_number: int) -> bool:
        eff = lap_effects_by_lap.get(lap_number)
        return eff is not None and eff.neutralized

    def _lap_effects(lap_number: int) -> LapEffects:
        return lap_effects_by_lap.get(lap_number) or effects(RaceControlState())

    def _tyre_penalty_ms(did: str) -> float:
        if not tyre_active:
            return 0.0
        tyre = tyre_by_id[did]
        return tyre_penalty_ms(tyre, compounds[tyre.compound], track_params)

    def _apply_scale(car: CarSpaceState, lap_number: int, pit_ms: float = 0.0) -> None:
        """Converta as penalidades de tempo da volta em fator de velocidade.

        A referencia fisica do carro e o denominador comum; pneu, combustivel,
        clima, controle de prova e a perda de boxes da volta de entrada entram
        como ms a mais, e o fator reduz a velocidade na mesma proporcao.
        """

        did = car.driver_id
        base = ref_ms[did]
        eff = _lap_effects(lap_number)
        penalty = _tyre_penalty_ms(did) + pit_ms
        if fuel is not None:
            penalty += _last_fuel_ms.get(did, 0.0)
        if lap_surface_water:
            idx = min(lap_number - 1, len(lap_surface_water) - 1)
            penalty += base * 0.40 * lap_surface_water[idx]
        on_track_ms = (base + penalty) * eff.lap_time_factor + eff.lap_time_loss_ms
        car.speed_scale = base / on_track_ms if on_track_ms > 0 else 1.0

    reliability_by_id = reliability_by_id or {}
    mechanical_retired: dict[str, int] = {}
    fuel_retired: dict[str, int] = {}
    # Parcela de combustivel (ms) da ultima volta de cada carro, para o
    # ``speed_scale`` da proxima volta refletir a massa ja queimada.
    _last_fuel_ms: dict[str, float] = {}

    def _advance_control(lap: int, incidents: list[Incident]) -> None:
        """Avance o controle de prova uma volta e registre estado e eventos."""

        nonlocal control_state
        if race_control is None:
            return
        control_state, lap_events = step(
            control_state, incidents, rng, race_control, lap
        )
        control_events.extend(lap_events)
        # O estado resultante vale para a PROXIMA volta: e o que o motor por
        # volta tambem faz (``step`` devolve o estado da volta seguinte).
        next_lap = lap + 1
        lap_effects_by_lap[next_lap] = effects(control_state, race_control)
        control_by_lap.append(
            {
                "lap": next_lap,
                "status": control_state.status.value,
                "restart_lap": control_state.restart_lap,
            }
        )

    def _consume_fuel(car: CarSpaceState, completed_lap: int) -> FuelLap | None:
        """Queime a volta ``completed_lap`` e guarde a massa e a parcela de tempo."""

        if fuel is None:
            return None
        did = car.driver_id
        laps_remaining = max(1, total_laps - completed_lap + 1)
        lap_fuel = fuel_lap(
            fuel,
            fuel_kg=fuel_kg[did],
            laps_remaining=laps_remaining,
            status=_status_for_lap(completed_lap),
        )
        fuel_kg[did] = lap_fuel.end_kg
        _last_fuel_ms[did] = lap_fuel.fuel_ms
        if lap_fuel.saved_kg > 0.0:
            fuel_saving_laps[did] += 1
        return lap_fuel

    def _maybe_pit(car: CarSpaceState, completed_lap: int) -> float:
        """Decida a parada ao fim de ``completed_lap`` e devolva a perda (ms).

        Reusa a ``HeuristicPitStrategy`` do motor por volta. Numa parada o pneu
        novo estreia na proxima volta e a perda de boxes e cobrada agora; com
        reabastecimento, soma-se o tempo de abastecer alem da troca de pneus.
        A perda e escalada pelo ``pit_loss_factor`` do controle de prova.
        """

        if not pit_active:
            return 0.0
        did = car.driver_id
        strategy = strategy_by_id[did]
        eff = _lap_effects(completed_lap)
        status_obj = None
        if fuel is not None:
            burn = fuel.burn_kg_per_lap * fuel.burn_factor(
                _status_for_lap(completed_lap)
            )
            status_obj = FuelStatus(
                fuel, fuel_kg[did], burn, track_params.pit_loss_ms
            )
        state = StrategyState(
            lap_number=completed_lap,
            total_laps=total_laps,
            tyre=tyre_by_id[did],
            stops_made=stops_made[did],
            neutralization=_neutralization_name(completed_lap),
            pit_loss_factor=eff.pit_loss_factor,
            compounds_used=compounds_used[did],
            free_tyre_change=eff.free_tyre_change,
            fuel=status_obj,
        )
        decision = strategy.decide(state)
        if not decision.pit:
            tyre_by_id[did] = tyre_by_id[did].aged()
            return 0.0
        assert decision.compound is not None
        pit_ms = track_params.pit_loss_ms * eff.pit_loss_factor
        if refuel_mode and decision.refuel_kg is not None:
            fill_kg = min(
                max(0.0, decision.refuel_kg),
                fuel.parameters.max_fuel_kg - fuel_kg[did],
            )
            if fill_kg > 0.0:
                before_kg = fuel_kg[did]
                pit_ms += fuel.stationary_extra_ms(fill_kg) * eff.pit_loss_factor
                fuel_kg[did] += fill_kg
                refuels_made[did] += 1
                refuel_events.append(
                    {
                        "lap": completed_lap,
                        "driver_id": did,
                        "fuel_before_kg": round(before_kg, 3),
                        "added_kg": round(fill_kg, 3),
                        "compound": decision.compound,
                    }
                )
        if eff.free_tyre_change:
            # Troca gratis de bandeira vermelha: estreia ja com uma volta de uso
            # e nao conta como parada, como no motor por volta.
            tyre_by_id[did] = TyreSet(decision.compound, 1)
            pit_ms = 0.0
        else:
            tyre_by_id[did] = TyreSet(decision.compound, 0)
            stops_made[did] += 1
        if decision.compound not in compounds_used[did]:
            compounds_used[did] = (*compounds_used[did], decision.compound)
        return pit_ms

    def _neutralization_name(lap_number: int) -> str | None:
        eff = lap_effects_by_lap.get(lap_number)
        if eff is None or not eff.neutralized:
            return None
        status = _status_for_lap(lap_number)
        return status if status in ("SC", "VSC") else None

    # Incidentes acumulados por volta da corrida, drenados quando o controle de
    # prova daquela volta e avancado.
    pending_incidents: dict[int, list[Incident]] = {}
    retired_seen: set[str] = set()

    def on_lap_complete(car: CarSpaceState, lap: int) -> None:
        nonlocal control_laps_done
        did = car.driver_id
        lap_fuel = _consume_fuel(car, lap)
        # Pane seca: o carro para como uma quebra; vira incidente mecanico.
        if (
            lap_fuel is not None
            and lap_fuel.ran_dry
            and not refuel_mode
            and lap < total_laps
            and did not in mechanical_retired
            and did not in fuel_retired
        ):
            car.retired = True
            fuel_retired[did] = lap
            pending_incidents.setdefault(lap, []).append(
                Incident(lap, "mechanical", (did,))
            )
            return
        # Abandono mecanico: sorteio por volta. Ordem fixa pelo rotulo.
        if mechanical_hazard_per_lap > 0.0 and lap < total_laps:
            hazard = mechanical_hazard_per_lap * reliability_by_id.get(did, 1.0)
            if rng.uniform01(f"mechanical:{did}:lap:{lap}") < hazard:
                car.retired = True
                mechanical_retired[did] = lap
                pending_incidents.setdefault(lap, []).append(
                    Incident(lap, "mechanical", (did,))
                )
                return
        pit_ms = _maybe_pit(car, lap)
        _apply_scale(car, lap + 1, pit_ms=pit_ms)

        # Retrato do estado ao fim desta volta (pneu ja envelhecido ou resetado
        # pela eventual parada), para o history nao repetir o estado final.
        lap_snapshots[did][lap] = {
            "compound": tyre_by_id[did].compound,
            "tyre_age_laps": tyre_by_id[did].age_laps,
            "stops_made": stops_made[did],
            "fuel_kg": fuel_kg[did] if fuel is not None else None,
            "fuel_saving_laps": fuel_saving_laps[did],
            "refuels_made": refuels_made[did],
        }

        # Controle de prova: avanca uma vez por volta da corrida, na primeira
        # vez que qualquer carro completa a volta ``lap``.
        if race_control is not None and lap > control_laps_done:
            control_laps_done = lap
            incidents = pending_incidents.pop(lap, [])
            # Contato: carros que abandonaram por toque viram incidente.
            for other in cars:
                if (
                    other.retired
                    and other.driver_id not in retired_seen
                    and other.driver_id not in mechanical_retired
                    and other.driver_id not in fuel_retired
                ):
                    retired_seen.add(other.driver_id)
                    incidents.append(Incident(lap, "contact", (other.driver_id,)))
            _advance_control(lap, incidents)

    # Fator inicial da volta 1 (pneu novo, tanque cheio, clima da volta 1).
    for car in cars:
        if fuel is not None:
            _last_fuel_ms[car.driver_id] = fuel.ms_per_kg * fuel_kg[car.driver_id]
        _apply_scale(car, 1)

    samples = integrate_field(
        cars,
        track,
        physics_by_id,
        total_laps=total_laps,
        dt_s=dt_s,
        aggression_by_id=aggression_by_id,
        rng=rng,
        on_lap_complete=on_lap_complete,
        neutralized_lap=_neutralized_lap if race_control is not None else None,
    )

    per_car: dict[str, list[float]] = {}
    outcome: dict[str, tuple[bool, int | None, float | None]] = {}
    for did in names:
        times, retired, retired_on, retired_at_ms = _lap_crossing_times_ms(
            samples, did, lap_length_m, total_laps
        )
        # Carro que abandonou sem completar nenhuma volta registra uma "volta"
        # com o tempo do abandono, porque o retrato por volta (e o RacePlayback
        # do frontend) exige ao menos uma volta por carro.
        if retired and not times:
            times = [retired_at_ms if retired_at_ms is not None else 0.0]
            retired_on = 1
        per_car[did] = times
        outcome[did] = (retired, retired_on, retired_at_ms)

    def _snapshot_for(did: str, laps_done: int) -> dict:
        """Estado de pneu/combustivel na volta ``laps_done``, com fallback inicial."""

        snap = lap_snapshots[did].get(laps_done)
        if snap is not None:
            return snap
        return {
            "compound": compounds_used[did][0],
            "tyre_age_laps": max(0, laps_done),
            "stops_made": 0,
            "fuel_kg": fuel_kg[did] if fuel is not None else None,
            "fuel_saving_laps": 0,
            "refuels_made": 0,
        }

    history: list[dict] = []
    for lap in range(1, total_laps + 1):
        states: dict[str, dict] = {}
        for did in names:
            times = per_car[did]
            retired, retired_on, _ = outcome[did]
            laps_done = min(lap, len(times))
            total_ms = times[laps_done - 1] if laps_done >= 1 else 0.0
            is_retired = retired and retired_on is not None and lap >= retired_on
            cause = None
            if is_retired:
                if did in mechanical_retired:
                    cause = MECHANICAL
                elif did in fuel_retired:
                    cause = FUEL
                else:
                    cause = CONTACT
            snap = _snapshot_for(did, laps_done)
            states[did] = {
                "driver_id": did,
                "name": names[did],
                "total_time_ms": total_ms,
                "laps_completed": laps_done,
                "status": RETIRED if is_retired else RUNNING,
                "retirement_cause": cause,
                "compound": snap["compound"],
                "tyre_age_laps": snap["tyre_age_laps"],
                "stops_made": snap["stops_made"],
                "fuel_kg": snap["fuel_kg"] if fuel is not None else None,
                "fuel_saving_laps": snap["fuel_saving_laps"],
                "refuels_made": snap["refuels_made"],
            }
        history.append({"lap": lap, "cars": _classification(states)})

    classification = history[-1]["cars"] if history else []
    result = {
        "total_laps": total_laps,
        "circuit_id": geometry.circuit_id,
        "history": history,
        "classification": classification,
        "starting_grid": [
            {
                "position": grid_by_id[did],
                "driver_id": did,
                "compound": compounds_used[did][0],
                **(
                    {"fuel_kg": round(start_fuel_kg_by_id[did], 3)}
                    if fuel is not None
                    else {}
                ),
            }
            for did in sorted(names, key=lambda d: grid_by_id[d])
        ],
        "race_control_events": control_events,
        "race_control_by_lap": control_by_lap,
        # Trajetoria espacial para o frontend desenhar carros lado a lado com
        # hitbox. ``track_space_2d`` traz a largura e a escala para converter os
        # metros laterais em unidades do desenho normalizado.
        "trajectories_2d": _trajectories_2d(samples, list(names)),
        "track_space_2d": {
            "width_m": track.width_m,
            "xy_per_metre": track.xy_per_metre,
            "car_length_m": ASSUMED_CAR_LENGTH_M,
            "car_width_m": ASSUMED_CAR_WIDTH_M,
            "lap_length_m": lap_length_m,
        },
        "assumptions": [
            {
                "kind": "engine_2d",
                "origin": "assumed",
                "parameter_version": "motor-2d-v2",
                "rationale": (
                    "ADR 0011: motor 2D de posicao continua. Velocidade, "
                    "ultrapassagem e colisao emergem da fisica espacial; pneu, "
                    "combustivel, clima, pit stop, reabastecimento, "
                    "lift-and-coast e controle de prova (SC/VSC/bandeiras) "
                    "entram como penalidades de tempo convertidas em velocidade, "
                    "reusando as mesmas heuristicas do motor por volta."
                ),
                "tyre_active": tyre_active,
                "fuel_active": fuel is not None,
                "refuel_active": refuel_mode,
                "pit_active": pit_active,
                "weather_active": bool(lap_surface_water),
                "race_control_active": race_control is not None,
                "mechanical_hazard_per_lap": mechanical_hazard_per_lap,
            }
        ],
    }
    if fuel is not None:
        # Bloco que o frontend (``race_playback.py``) consome para a escala do
        # medidor (``max_fuel_kg``), a carga de largada e os reabastecimentos.
        result["fuel"] = {
            "burn_kg_per_lap": round(fuel.burn_kg_per_lap, 4),
            "ms_per_kg": round(fuel.ms_per_kg, 2),
            "lap_length_km": round(fuel.lap_length_km, 3),
            "lap_length_source": fuel.lap_length_source,
            "reference_lap_ms": fuel.reference_lap_ms,
            "max_fuel_kg": fuel.parameters.max_fuel_kg,
            "finish_reserve_kg": fuel.parameters.finish_reserve_kg,
            "range_laps_at_max_fuel": round(fuel.range_laps_at_max_fuel, 1),
            "race_exceeds_fuel_range": total_laps > fuel.range_laps_at_max_fuel,
            "refuelling_allowed": fuel.parameters.refuelling_allowed,
            "start_fuel_kg": {
                did: round(load, 3)
                for did, load in sorted(start_fuel_kg_by_id.items())
            },
            "refuel_stops": refuel_events,
        }
    return result
