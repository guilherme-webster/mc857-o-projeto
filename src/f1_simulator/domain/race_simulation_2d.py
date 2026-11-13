"""Motor de corrida 2D (ADR 0011): roda a fisica espacial de ``track_space`` e
produz o mesmo ``history`` por volta que o motor por volta, para o frontend e as
corridas salvas lerem sem mudanca.

A fisica continua em ``track_space`` (posicao, ultrapassagem, colisao). Aqui se
converte a trajetoria continua em retratos de fim de volta e se traduzem, para a
moeda espacial do 2D, os efeitos que o motor por volta cobra em tempo:

- desgaste e queima são integrados por movimento; desgaste e massa atuais,
  junto com clima, modulam a velocidade (``speed_scale``);
- as paradas percorrem a pit lane e consomem tempo real no serviço;
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

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, replace

from f1_simulator.domain.attribute_effects import detailed_degradation_factor
from f1_simulator.domain.dynamic_usage import (
    DynamicUsageParameters,
    curvature_profile,
    usage_delta,
    usage_reference,
)
from f1_simulator.domain.fuel import FuelPlan
from f1_simulator.domain.model_parameters import (
    CompoundParameters,
    ModelParameters,
    TrackParameters,
)
from f1_simulator.domain.pit_lane import (
    PitLaneParameters,
    PitStopRequest,
    build_pit_lane,
)
from f1_simulator.domain.race_control import (
    GREEN,
    HEURISTIC_RACE_CONTROL,
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
    GripLapTimes,
    physics_for,
)
from f1_simulator.domain.strategy import (
    HeuristicPitStrategy,
    SpatialPitPlanningParameters,
    StrategyState,
    TyreStrategy,
)
from f1_simulator.domain.track_condition import TrackState
from f1_simulator.domain.track_geometry import TrackGeometry
from f1_simulator.domain.track_space import (
    ASSUMED_CAR_LENGTH_M,
    ASSUMED_CAR_WIDTH_M,
    CarSpaceState,
    FieldSample,
    MotionIncrement,
    build_track_space,
    integrate_field,
)
from f1_simulator.domain.tyres import TyreSet, tyre_penalty_ms
from f1_simulator.domain.wet_tyres import relative_grip, wear_factor

RUNNING = "RUNNING"
RETIRED = "RETIRED"
CONTACT = "CONTACT"
MECHANICAL = "MECHANICAL"
FUEL = "FUEL"

#: Espacamento longitudinal (m) entre posicoes de largada no grid 2D. Cada
#: carro fica numa posicao longitudinal distinta (fila escalonada, nao 2x2),
#: com folga maior que o comprimento do carro para nunca largarem emparelhados
#: -- o que evitaria o contato artificial da largada. Hipotese de apresentacao.
GRID_ROW_SPACING_M = 10.0

#: Deslocamento lateral (m) alternado por posicao, so para o visual de grid
#: (um carro mais a um lado, o proximo ao outro). Pequeno o bastante para caber
#: na pista; como os carros ja estao separados longitudinalmente, nao chegam a
#: roçar. Hipotese de apresentacao.
GRID_LATERAL_OFFSET_M = 2.0


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
            retired_at_ms = (car.retired_time_s if car.retired_time_s is not None else sample.time_s) * 1000.0
        prev = (sample.time_s, car.distance_m)
    return times_ms, retired, retired_on, retired_at_ms


#: So emite um ponto de trajetoria quando a distancia percorrida avancou mais
#: que isto (m) OU o deslocamento lateral mudou mais que o limiar lateral desde
#: o ultimo ponto. A distancia avanca sempre, entao este limiar e quem controla
#: o volume: o frontend interpola entre os pontos, e a distancia e quase linear
#: no tempo, de modo que pontos esparsos reconstroem bem o movimento.
TRAJECTORY_DISTANCE_EPS_M = 60.0

#: Limiar lateral (m): uma manobra (troca de faixa) gera um ponto mesmo sem
#: avancar muito, para o lado a lado da ultrapassagem nao ser perdido.
TRAJECTORY_LATERAL_EPS_M = 0.3

#: Limiar de velocidade (km/h): emite um ponto quando a velocidade mudou mais
#: que isto desde o ultimo, para a aceleracao da largada e as freadas fortes
#: terem pontos densos o bastante (a velocidade exibida interpola entre eles).
#: No cruzeiro, com velocidade quase constante, nao dispara.
TRAJECTORY_SPEED_EPS_KMH = 15.0

#: Intervalo minimo (ms) entre dois pontos do mesmo carro. Mesmo numa manobra
#: rapida ou na largada parada (onde a distancia quase nao avanca mas o lateral
#: oscila), nao emite mais que um ponto por este intervalo; o frontend
#: interpola. Corta a rajada de pontos da largada sem perder o movimento.
TRAJECTORY_MIN_INTERVAL_MS = 150.0


def _trajectories_2d(
    samples: tuple[FieldSample, ...],
    driver_ids: list[str],
    race_distance_m: float,
) -> dict[str, list[list[float | None]]]:
    """Trajetoria espacial por carro ao longo do tempo, comprimida p/ o frontend.

    Cada ponto e ``[t_ms, distance_m, lateral_m, speed_kmh, pit_distance_m,
    fuel_kg, tyre_wear_laps]``. Campos de recursos ausentes são nulos.
    O quinto campo é nulo na pista e é a distância no caminho aberto nos
    boxes. Mudanças de fase preservam os dois lados da transição, inclusive
    o início/fim do serviço, para a interpolação não apagar o tempo parado.
    Posição longitudinal, deslocamento lateral e velocidade vêm do motor,
    para o frontend exibi-los sem derivar de segmentos. A série é comprimida
    por limiar: só vira ponto quando
    a distancia avancou ``TRAJECTORY_DISTANCE_EPS_M`` ou o lateral mudou
    ``TRAJECTORY_LATERAL_EPS_M``, respeitando um intervalo minimo, mais o
    primeiro e o ultimo instante. O frontend interpola linearmente entre pontos.

    Formato de lista (``[t, d, lat, v, pit_d]``) em vez de dict por ponto para encolher
    o JSON; o frontend le por indice. O primeiro ponto (t=0) fixa o grid de
    largada; o ultimo fecha a serie na chegada ou no abandono.
    """

    series: dict[str, list[list[float | None]]] = {did: [] for did in driver_ids}
    last_d: dict[str, float] = {did: 0.0 for did in driver_ids}
    last_lat: dict[str, float] = {did: 0.0 for did in driver_ids}
    last_v: dict[str, float] = {did: 0.0 for did in driver_ids}
    last_t: dict[str, float] = {did: -TRAJECTORY_MIN_INTERVAL_MS for did in driver_ids}
    pending: dict[str, list[float | None] | None] = {did: None for did in driver_ids}
    done: set[str] = set()
    previous: dict[str, tuple[list, str]] = {}

    def _phase(car) -> str:
        if car.pit_state is None:
            return "track"
        if car.pit_state.service_remaining_s > 0:
            return "service"
        return "out" if car.pit_state.serviced else "in"

    def _point(t_ms: float, car) -> list[float | None]:
        return [
            round(t_ms, 1),
            round(car.distance_m, 2),
            round(car.lateral_m, 3),
            round(car.speed_ms * 3.6, 1),
            round(car.pit_state.path_distance_m, 3)
            if car.pit_state is not None
            else None,
            round(car.fuel_kg, 6) if car.fuel_kg is not None else None,
            round(car.tyre_wear_laps, 6) if car.tyre_wear_laps is not None else None,
        ]

    def _push(did: str, point: list[float | None]) -> None:
        series[did].append(point)
        last_d[did] = point[1]
        last_lat[did] = point[2]
        last_v[did] = point[3]
        last_t[did] = point[0]

    for sample in samples:
        t_ms = sample.time_s * 1000.0
        for car in sample.cars:
            did = car.driver_id
            if did in done:
                continue
            d, lat, v_kmh = car.distance_m, car.lateral_m, car.speed_ms * 3.6
            if not series[did]:
                _push(did, _point(t_ms, car))  # grid de largada (t=0)
                previous[did] = (_point(t_ms, car), _phase(car))
                continue
            if car.retired or car.distance_m >= race_distance_m:
                stop_ms = (
                    car.retired_time_s * 1000
                    if car.retired_time_s is not None
                    else t_ms
                )
                _push(did, _point(stop_ms, car))
                done.add(did)
                continue
            point, phase = _point(t_ms, car), _phase(car)
            prior, prior_phase = previous[did]
            previous[did] = (point, phase)
            if phase != prior_phase:
                if prior[0] > last_t[did]:
                    _push(did, prior)
                _push(did, point)
                pending[did] = None
                continue
            changed = (
                d - last_d[did] >= TRAJECTORY_DISTANCE_EPS_M
                or abs(lat - last_lat[did]) >= TRAJECTORY_LATERAL_EPS_M
                or abs(v_kmh - last_v[did]) >= TRAJECTORY_SPEED_EPS_KMH
            )
            if not changed:
                continue
            # Houve mudanca relevante, mas respeita o intervalo minimo: guarda
            # como pendente e so emite quando o intervalo passa.
            if t_ms - last_t[did] < TRAJECTORY_MIN_INTERVAL_MS:
                pending[did] = _point(t_ms, car)
                continue
            pending[did] = None
            _push(did, _point(t_ms, car))
    # Ultimo instante de quem nao abandonou, para a serie cobrir o fim.
    for did in driver_ids:
        if pending[did] is not None and did not in done:
            _push(did, pending[did])
        if did not in done and previous[did][0][0] > last_t[did]:
            _push(did, previous[did][0])
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
            "team_name": s.get("team_name", ""),
            "total_time_ms": round(s["total_time_ms"], 1),
            "lap_time_ms": round(s["total_time_ms"] / laps, 1) if laps else 0.0,
            "laps_completed": laps,
            "status": s["status"],
            "compound": s["compound"],
            "tyre_age_laps": s["tyre_age_laps"],
            "tyre_wear_laps": round(s["tyre_wear_laps"], 6) if s["tyre_wear_laps"] is not None else None,
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
    base_physics_by_id: Mapping[str, CarPhysics] | None = None,
    pit_execution_by_id: Mapping[str, float] | None = None,
    compounds: dict[str, CompoundParameters] | None = None,
    track_params: TrackParameters | None = None,
    model_parameters: ModelParameters | None = None,
    fuel: FuelPlan | None = None,
    track_states: Sequence[TrackState] | None = None,
    reliability_by_id: dict[str, float] | None = None,
    mechanical_hazard_per_lap: float = 0.0,
    race_control: RaceControlParameters | None = HEURISTIC_RACE_CONTROL,
    standing_start: bool = True,
    width_m: float | None = None,
    dt_s: float = 0.5,
    pit_parameters: PitLaneParameters = PitLaneParameters(),
    usage_parameters: DynamicUsageParameters = DynamicUsageParameters(),
    pit_planning: SpatialPitPlanningParameters = SpatialPitPlanningParameters(),
    on_progress: Callable[[int, int], None] | None = None,
    check_cancelled: Callable[[], None] | None = None,
) -> dict:
    """Simule a corrida no motor 2D e devolva ``history`` + ``classification``.

    Cada entrante e ``{"driver_id", "name", "grid_position", "attributes",
    "aggression", "compound"}``; ``attributes`` (ou ``None``) deriva o envelope
    fisico por carro, como no ADR 0010.

    Pneu, combustivel e clima entram como penalidades de tempo (os modelos
    existentes) convertidas numa reducao fracionaria da velocidade do carro
    (``speed_scale``), de modo que a volta mais lenta emerge do movimento:

    - ``compounds`` + ``track_params``: exposição por distância e esforço
      determina a penalidade do pneu, separada da idade em voltas;
    - ``fuel``: queima por movimento e marcha lenta; massa custa tempo. O
      proxy de desaceleração reduz a demanda, sem chamar ``fuel_lap``;
    - ``track_states``: agua, temperatura e borracha da volta viram um fator de
      aderencia (``track_condition.py``), e a fisica do proprio carro diz quanto
      tempo ele perde com esse fator -- o mesmo calculo do motor por volta.

    Com ``model_parameters`` + ``track_params`` + ``compounds``, cada piloto ganha
    uma ``HeuristicPitStrategy``. Uma estratégia explícita no entrante pode
    substituí-la. A decisão reserva a próxima entrada, o serviço troca pneus
    e a saída devolve o carro à pista. A perda histórica de boxes só informa
    a decisão: não é somada ao tempo efetivamente gasto. Reabastecimento
    continua fora deste caminho 2D. Sem aqueles parâmetros não há paradas.

    Com ``race_control``, o automato de ``race_control`` roda uma vez por volta
    da corrida (lider) e neutraliza o pelotao sob SC/VSC/vermelha, modulando o
    ritmo de todos; a relargada acelera a volta seguinte. Incidentes de contato
    (abandono por toque no integrador) e falhas mecanicas alimentam o automato.

    O grid de largada e escalonado 2x2 (``GRID_ROW_SPACING_M``,
    ``GRID_LATERAL_OFFSET_M``), atras da linha de chegada: a pole mais perto
    dela, cada fileira recuada, os dois
    carros de uma fileira em lados opostos da pista. Com ``standing_start`` (o
    default), o pelotao larga parado e acelera pela propria fisica; ``False``
    mantem a largada de regime do ADR 0010.

    Cada efeito ausente simplesmente nao atua.
    """

    track = (
        build_track_space(geometry)
        if width_m is None
        else build_track_space(geometry, width_m=width_m)
    )
    lap_length_m = track.lap_length_m

    tyre_active = compounds is not None and track_params is not None
    usage_active = tyre_active or fuel is not None
    curvature = curvature_profile(geometry) if usage_active else None
    reference_usage = usage_reference(geometry, curvature, base_physics, usage_parameters) if usage_active else None
    pit_active = tyre_active and model_parameters is not None
    pit_lane = build_pit_lane(geometry) if pit_active else None
    refuel_mode = False  # O 2D ainda executa apenas serviço de pneus.
    pit_events: list[dict] = []
    pending_compounds: dict[str, str] = {}

    # TODO(motor-2d): duas features do motor detalhado ficaram de fora por
    # decisao, e este e o ponto de entrada para quando forem portadas:
    #
    # 1. Reabastecimento. Hoje ``refuel_mode`` e sempre False e o pit so troca
    #    pneu. Para ligar: respeitar ``fuel.parameters.refuelling_allowed``,
    #    abastecer no serviço (``PitStopRequest`` + vazao ``refuel_rate_kg_per_s``)
    #    e recalcular ``fuel_kg``/``speed_scale`` do carro ao sair dos boxes.
    # 2. Perda historica de boxes calibrada. Hoje o tempo de parada vem so da
    #    geometria mockada + serviço; falta somar ``track_params.pit_loss_ms``
    #    (a perda medida por circuito) como no motor detalhado, para o tempo de
    #    parada deixar de ser puramente assumido.

    cars: list[CarSpaceState] = []
    physics_by_id: dict[str, CarPhysics] = {}
    aggression_by_id: dict[str, float] = {}
    names: dict[str, str] = {}
    team_names: dict[str, str] = {}
    grid_by_id: dict[str, int] = {}
    tyre_by_id: dict[str, TyreSet] = {}
    compounds_used: dict[str, tuple[str, ...]] = {}
    management: dict[str, float] = {}
    usage_totals: dict[str, dict[str, float]] = {}
    strategy_by_id: dict[str, TyreStrategy] = {}
    strategy_plans: dict[str, dict] = {}
    stops_made: dict[str, int] = {}
    refuels_made: dict[str, int] = {}
    fuel_saving_laps: dict[str, int] = {}
    start_fuel_kg_by_id: dict[str, float] = {}
    # Eventos de reabastecimento para o bloco ``fuel`` que o frontend consome.
    refuel_events: list[dict] = []
    # Volta de referencia de cada carro (ms), para converter penalidades de tempo
    # em fator de velocidade. E o tempo que o proprio envelope fisico produz.
    ref_ms: dict[str, float] = {}
    grip_laps: dict[str, GripLapTimes] = {}
    # Decomposicao da velocidade por carro e por volta: quanto pneu, combustivel,
    # clima e controle de prova tiram do ritmo fisico de referencia. Registrado
    # em ``_apply_scale`` sem alterar a fisica; alimenta a ferramenta de analise.
    speed_breakdown: dict[str, dict[int, dict]] = {}
    # Atributos (DriverAttributes) por carro, para o painel mostra-los como
    # contexto ao lado da decomposicao; ``None`` quando o carro nao os traz.
    attributes_by_id: dict[str, object] = {}
    for entry in sorted(entrants, key=lambda e: e["grid_position"]):
        did = entry["driver_id"]
        names[did] = entry["name"]
        # Equipe do piloto: opcional no contrato do entrante para nao quebrar
        # chamadas antigas; o frontend a exibe na classificacao e no grid.
        team_names[did] = entry.get("team_name", "")
        grid_by_id[did] = entry["grid_position"]
        base = (
            base_physics_by_id.get(did, base_physics)
            if base_physics_by_id
            else base_physics
        )
        attrs = entry.get("attributes")
        physics = physics_for(attrs, base)
        attributes_by_id[did] = attrs
        management[did] = detailed_degradation_factor(attrs)
        usage_totals[did] = dict(
            fuel_burned_kg=0.0,
            distance_wear_laps=0.0,
            lateral_wear_laps=0.0,
            longitudinal_wear_laps=0.0,
            max_lateral_acceleration_ms2=0.0,
        )
        physics_by_id[did] = physics
        aggression_by_id[did] = float(entry.get("aggression", 1.0))
        compound = entry.get("compound", "MEDIUM")
        tyre_by_id[did] = TyreSet(compound, 0)
        compounds_used[did] = (compound,)
        stops_made[did] = 0
        refuels_made[did] = 0
        fuel_saving_laps[did] = 0
        grip_laps[did] = GripLapTimes(geometry, physics)
        ref_ms[did] = grip_laps[did].lap_ms(1.0)
        speed_breakdown[did] = {}
        if fuel is not None:
            load = entry.get("start_fuel_kg")
            start_load = (
                float(load) if load is not None else fuel.start_fuel_kg(total_laps)
            )
            fuel.validate_start_fuel(start_load, did)
            start_fuel_kg_by_id[did] = start_load
        if pit_active:
            assert model_parameters is not None and track_params is not None
            target = pit_planning.wear_target(total_laps)
            offset_laps = entry.get("strategy_offset_laps", 0)
            strategy_by_id[did] = entry.get("strategy") or HeuristicPitStrategy(
                model_parameters,
                track_params,
                offset_laps=offset_laps,
                compulsory_wear_target_laps=target,
                reference_lap_ms=entry.get("reference_lap_ms", 90_000.0),
                weather_switch_bias=entry.get("weather_switch_bias", 1.0),
            )
            strategy_plans[did] = {
                "mode": "custom" if entry.get("strategy") is not None else "heuristic",
                "offset_laps": offset_laps,
                "compulsory_wear_target_laps": target
                if entry.get("strategy") is None
                else None,
            }
        # Grid atras da linha de chegada (distancia zero, onde cada volta comeca):
        # a pole fica ``GRID_ROW_SPACING_M`` atras da linha e cada posicao recua
        # mais uma folga, com distancia negativa. A posicao na pista usa modulo,
        # e a contagem de voltas so comeca no cruzamento de ``k * lap_length``
        # (k >= 1): o trecho do grid ate a linha entra na primeira volta, como
        # na F1. Lateral alternado so para o visual de grid. Separados
        # longitudinalmente, os carros nao largam emparelhados nem roçam.
        pos = entry["grid_position"]
        side = 1.0 if pos % 2 == 1 else -1.0
        usable = track.bounds.usable_m
        lateral = max(-usable, min(usable, side * GRID_LATERAL_OFFSET_M))
        offset = pos * GRID_ROW_SPACING_M
        cars.append(
            CarSpaceState(
                did,
                distance_m=-offset,
                lateral_m=lateral,
                fuel_kg=start_fuel_kg_by_id.get(did),
                tyre_wear_laps=0.0 if tyre_active else None,
            )
        )

    cars_by_id = {car.driver_id: car for car in cars}

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
    # Volta mais avancada ja completada por qualquer carro, para o progresso.
    # Independe do controle de prova (``control_laps_done`` so avanca com ele).
    progress_lap_done = 0

    def _status_for_lap(lap_number: int) -> str:
        """Estado da pista na volta ``lap_number`` para a estratégia."""

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

    def _water(lap_number: int) -> float:
        if not track_states:
            return 0.0
        return track_states[min(lap_number - 1, len(track_states) - 1)].surface_water

    def _tyre_penalty_ms(did: str, lap_number: int) -> float:
        if not tyre_active:
            return 0.0
        tyre = tyre_by_id[did]
        # Desgaste equivalente do movimento (ADR 0014). Pneu de chuva em
        # pista secando superaquece: so ele tem fator > 1, e o ritmo dele
        # (pace_offset) e zero, entao escalar a parcela inteira equivale a
        # escalar so o desgaste.
        return tyre_penalty_ms(
            tyre,
            compounds[tyre.compound],
            track_params,
            wear_laps=cars_by_id[did].tyre_wear_laps,
        ) * wear_factor(tyre.compound, _water(lap_number))

    def _record_breakdown(
        did: str,
        lap_number: int,
        base: float,
        tyre_ms: float,
        fuel_ms: float,
        weather_ms: float,
        eff: LapEffects,
        speed_scale: float,
    ) -> None:
        """Guarde a decomposicao da velocidade da volta, em ms e em fracao perdida.

        A perda de velocidade total e ``1 - speed_scale``. Cada fator recebe a
        fatia dessa perda proporcional ao tempo (ms) que ele acrescentou, de
        modo que as fracoes somam a perda total e espelham o que o motor cobrou.
        O controle de prova nao e um ms somado a ``base``: e o invluctro
        multiplicativo/aditivo da volta, entao a sua fatia e o que sobra.
        """

        penalty = tyre_ms + fuel_ms + weather_ms
        on_track_ms = base + penalty
        control_ms = on_track_ms * (eff.lap_time_factor - 1.0) + eff.lap_time_loss_ms
        # ``delta_ms`` e o tempo a mais (ou a menos) da volta sobre a referencia.
        # Pode ser negativo: um composto macio novo e mais rapido que a base, e
        # ai ``speed_scale`` passa de 1.0 (ganho, nao perda). A fatia de cada
        # fator e proporcional ao seu ms, com o mesmo sinal, somando a variacao
        # total de velocidade, seja ela perda (positiva) ou ganho (negativa).
        delta_ms = penalty + control_ms
        speed_delta = 1.0 - speed_scale
        if delta_ms != 0.0:
            unit = speed_delta / delta_ms
            shares = {
                "tyre": tyre_ms * unit,
                "fuel": fuel_ms * unit,
                "weather": weather_ms * unit,
                "race_control": control_ms * unit,
            }
        else:
            shares = {"tyre": 0.0, "fuel": 0.0, "weather": 0.0, "race_control": 0.0}
        speed_breakdown[did][lap_number] = {
            "base_ms": round(base, 3),
            "tyre_ms": round(tyre_ms, 3),
            "fuel_ms": round(fuel_ms, 3),
            "weather_ms": round(weather_ms, 3),
            "control_factor": eff.lap_time_factor,
            "control_loss_ms": eff.lap_time_loss_ms,
            "speed_scale": round(speed_scale, 6),
            "speed_delta_fraction": round(speed_delta, 6),
            "delta_shares": {k: round(v, 6) for k, v in shares.items()},
        }

    def _apply_scale(car: CarSpaceState, lap_number: int) -> None:
        """Converta as penalidades de tempo da volta em fator de velocidade.

        A referencia fisica do carro e o denominador comum; pneu, combustivel,
        clima e controle de prova entram como ms a mais. Boxes têm movimento
        e serviço próprios; incluí-los aqui cobraria a mesma parada duas vezes.

        Registra cada parcela em ``speed_breakdown`` para a ferramenta de
        decomposição, sem alterar o ``speed_scale`` resultante.
        """

        did = car.driver_id
        base = ref_ms[did]
        eff = _lap_effects(lap_number)
        tyre_ms = _tyre_penalty_ms(did, lap_number)
        fuel_ms = 0.0
        if fuel is not None:
            fuel_ms = fuel.ms_per_kg * max(
                0.0, car.fuel_kg - fuel.parameters.finish_reserve_kg
            )
        weather_ms = 0.0
        if track_states:
            idx = min(lap_number - 1, len(track_states) - 1)
            water = track_states[idx].surface_water
            grip_factor = track_states[idx].grip_factor * relative_grip(
                tyre_by_id[did].compound, water
            )
            if grip_factor != 1.0:
                weather_ms = grip_laps[did].delta_ms(grip_factor)
        penalty = tyre_ms + fuel_ms + weather_ms
        on_track_ms = (base + penalty) * eff.lap_time_factor + eff.lap_time_loss_ms
        car.speed_scale = base / on_track_ms if on_track_ms > 0 else 1.0
        _record_breakdown(
            did, lap_number, base, tyre_ms, fuel_ms, weather_ms, eff, car.speed_scale
        )

    reliability_by_id = reliability_by_id or {}
    mechanical_retired: dict[str, int] = {}
    fuel_retired: dict[str, int] = {}

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

    def _on_motion(car: CarSpaceState, motion: MotionIncrement) -> None:
        """Integre recursos e atualize o ritmo, antes dos eventos de serviço/volta."""

        if not usage_active:
            return
        assert curvature is not None and reference_usage is not None
        did = car.driver_id
        midpoint = motion.start_distance_m + motion.distance_m / 2
        delta = usage_delta(
            distance_m=motion.distance_m,
            dt_s=motion.dt_s,
            speed_ms=motion.speed_ms,
            acceleration_ms2=motion.acceleration_ms2,
            curvature_per_m=curvature.at(midpoint),
            lap_length_m=lap_length_m,
            burn_kg_per_km=fuel.parameters.burn_kg_per_km if fuel else 0.0,
            reference=reference_usage,
            parameters=usage_parameters,
            management_factor=management[did],
            in_pit=motion.in_pit,
        )
        fraction = 1.0
        burned = 0.0
        if fuel is not None:
            assert car.fuel_kg is not None
            burned = min(delta.fuel_kg, car.fuel_kg)
            if delta.fuel_kg > car.fuel_kg + 1e-12:
                fraction = car.fuel_kg / delta.fuel_kg
                car.retired = True
                car.retired_time_s = motion.time_s - motion.dt_s * (1 - fraction)
                car.speed_ms = 0.0
                car.distance_m = (
                    motion.start_distance_m
                    + (car.distance_m - motion.start_distance_m) * fraction
                )
                if motion.in_pit and car.pit_state is not None:
                    car.pit_state = replace(
                        car.pit_state,
                        path_distance_m=car.pit_state.path_distance_m
                        - motion.distance_m * (1 - fraction),
                    )
                fuel_retired[did] = max(1, int(car.distance_m // lap_length_m) + 1)
                pending_incidents.setdefault(fuel_retired[did], []).append(
                    Incident(fuel_retired[did], "mechanical", (did,))
                )
            car.fuel_kg = max(0.0, car.fuel_kg - burned)
        totals = usage_totals[did]
        totals["fuel_burned_kg"] += burned
        if tyre_active:
            assert car.tyre_wear_laps is not None
            car.tyre_wear_laps += delta.wear_laps * fraction
            for name in (
                "distance_wear_laps",
                "lateral_wear_laps",
                "longitudinal_wear_laps",
            ):
                totals[name] += getattr(delta, name) * fraction
        totals["max_lateral_acceleration_ms2"] = max(
            totals["max_lateral_acceleration_ms2"], delta.lateral_acceleration_ms2
        )
        _apply_scale(car, int(car.distance_m // lap_length_m) + 1)

    def _request_pit(car: CarSpaceState, lap_number: int) -> None:
        """Decida no início da volta; o pedido só troca pneus no serviço."""

        if not pit_active or car.pit_request is not None or lap_number > total_laps:
            return
        did = car.driver_id
        strategy = strategy_by_id[did]
        eff = _lap_effects(lap_number)
        state = StrategyState(
            lap_number=lap_number,
            total_laps=total_laps,
            tyre=tyre_by_id[did],
            stops_made=stops_made[did],
            neutralization=_neutralization_name(lap_number),
            pit_loss_factor=eff.pit_loss_factor,
            compounds_used=compounds_used[did],
            free_tyre_change=eff.free_tyre_change,
            fuel=None,
            tyre_wear_laps=car.tyre_wear_laps,
            # Radar: a agua prevista para a volta que comeca (como no detalhado).
            surface_water=_water(lap_number) if track_states else None,
        )
        decision = strategy.decide(state)
        if not decision.pit:
            return
        assert decision.compound is not None
        if eff.free_tyre_change:
            tyre_by_id[did] = TyreSet(decision.compound, 0)
            car.tyre_wear_laps = 0.0
            if decision.compound not in compounds_used[did]:
                compounds_used[did] = (*compounds_used[did], decision.compound)
        else:
            assert pit_lane is not None
            entry = pit_lane.next_entry(car.distance_m)
            exit_d = pit_lane.race_distance(entry, pit_lane.length_m)
            # Não iniciar uma visita que só termina depois da chegada.
            if exit_d >= total_laps * lap_length_m:
                return
            pending_compounds[did] = decision.compound
            # Execucao de box da equipe (heuristico): escala o tempo de
            # servico deste carro. Neutro em 1.0 (sem preset de equipe).
            execution = (
                pit_execution_by_id.get(did, 1.0) if pit_execution_by_id else 1.0
            )
            car.pit_request = PitStopRequest(
                entry, pit_parameters.service_time_s * execution
            )

    def _pit_event(car: CarSpaceState, kind: str, time_s: float) -> None:
        """Aplique a troca ao terminar o serviço, registrando instantes reais."""

        did = car.driver_id
        compound = pending_compounds[did]
        if kind == "service_completed":
            tyre_by_id[did] = TyreSet(compound, 0)
            car.tyre_wear_laps = 0.0
            stops_made[did] += 1
            if compound not in compounds_used[did]:
                compounds_used[did] = (*compounds_used[did], compound)
            _apply_scale(car, int(car.distance_m // lap_length_m) + 1)
        pit_events.append(
            {
                "driver_id": did,
                "type": kind,
                "time_ms": round(time_s * 1000, 3),
                "compound": compound,
                "stops_made": stops_made[did],
            }
        )
        if kind == "exit":
            pending_compounds.pop(did)

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
        nonlocal control_laps_done, progress_lap_done
        did = car.driver_id
        # Progresso: emite quando a volta mais avancada do pelotao cresce, uma
        # vez por volta da corrida. Callback puro injetado; o nucleo nao conhece
        # HTTP nem a tela (a borda decide o que fazer com o progresso).
        if on_progress is not None and lap > progress_lap_done:
            progress_lap_done = lap
            on_progress(min(lap, total_laps), total_laps)
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
        tyre_by_id[did] = tyre_by_id[did].aged()
        _apply_scale(car, lap + 1)

        # Retrato do estado ao fim desta volta (pneu ja envelhecido ou resetado
        # pela eventual parada), para o history nao repetir o estado final.
        lap_snapshots[did][lap] = {
            "compound": tyre_by_id[did].compound,
            "tyre_age_laps": tyre_by_id[did].age_laps,
            "tyre_wear_laps": car.tyre_wear_laps,
            "stops_made": stops_made[did],
            "fuel_kg": car.fuel_kg,
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
        _request_pit(car, lap + 1)

    # Fator inicial da volta 1 (pneu novo, tanque cheio, clima da volta 1).
    for car in cars:
        _apply_scale(car, 1)
        _request_pit(car, 1)

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
        standing_start=standing_start,
        pit_lane=pit_lane,
        pit_parameters=pit_parameters,
        on_pit_event=_pit_event,
        on_motion=_on_motion,
        check_cancelled=check_cancelled,
    )

    per_car: dict[str, list[float]] = {}
    outcome: dict[str, tuple[bool, int | None, float | None]] = {}
    for did in names:
        times, retired, retired_on, retired_at_ms = _lap_crossing_times_ms(
            samples, did, lap_length_m, total_laps
        )
        # Pane seca pode ocorrer antes da primeira linha. Não creditar uma
        # volta fictícia: a trajetória informa o instante e o progresso finais.
        per_car[did] = times
        outcome[did] = (retired, retired_on, retired_at_ms)

    def _snapshot_for(did: str, laps_done: int) -> dict:
        """Estado de pneu/combustivel na volta ``laps_done``, com fallback inicial."""

        snap = lap_snapshots[did].get(laps_done)
        if snap is not None:
            return snap
        # Carro que abandonou no meio da volta nao tem retrato dela: vale o
        # ultimo conhecido (composto e paradas reais), nao o estado da largada.
        earlier = [lap for lap in lap_snapshots[did] if lap <= laps_done]
        if earlier:
            return lap_snapshots[did][max(earlier)]
        return {
            "compound": compounds_used[did][0],
            "tyre_age_laps": max(0, laps_done),
            "tyre_wear_laps": cars_by_id[did].tyre_wear_laps,
            "stops_made": 0,
            "fuel_kg": cars_by_id[did].fuel_kg,
            "fuel_saving_laps": 0,
            "refuels_made": 0,
        }

    history: list[dict] = []
    for lap in range(1, total_laps + 1):
        states: dict[str, dict] = {}
        for did in names:
            times = per_car[did]
            retired, retired_on, retired_ms = outcome[did]
            laps_done = min(lap, len(times))
            total_ms = times[laps_done - 1] if laps_done >= 1 else 0.0
            is_retired = retired and retired_on is not None and lap >= retired_on
            if is_retired and retired_ms is not None:
                total_ms = retired_ms
            cause = None
            if is_retired:
                if did in mechanical_retired:
                    cause = MECHANICAL
                elif did in fuel_retired:
                    cause = FUEL
                else:
                    cause = CONTACT
            snap = _snapshot_for(did, laps_done)
            if is_retired:
                snap = {
                    **snap,
                    "fuel_kg": cars_by_id[did].fuel_kg,
                    "tyre_wear_laps": cars_by_id[did].tyre_wear_laps,
                    "compound": tyre_by_id[did].compound,
                    "tyre_age_laps": tyre_by_id[did].age_laps,
                    "stops_made": stops_made[did],
                }
            states[did] = {
                "driver_id": did,
                "name": names[did],
                "team_name": team_names[did],
                "total_time_ms": total_ms,
                "laps_completed": laps_done,
                "status": RETIRED if is_retired else RUNNING,
                "retirement_cause": cause,
                "compound": snap["compound"],
                "tyre_age_laps": snap["tyre_age_laps"],
                "tyre_wear_laps": snap["tyre_wear_laps"],
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
                "team_name": team_names[did],
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
        "pit_stop_events": pit_events,
        # Trajetoria espacial para o frontend desenhar carros lado a lado com
        # hitbox. ``track_space_2d`` traz a largura e a escala para converter os
        # metros laterais em unidades do desenho normalizado.
        "trajectories_2d": _trajectories_2d(
            samples, list(names), total_laps * lap_length_m
        ),
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
                "parameter_version": "motor-2d-v4",
                "rationale": (
                    "ADR 0011: motor 2D de posicao continua. Velocidade, "
                    "ultrapassagem e colisao emergem da fisica espacial; "
                    "desgaste e queima sao integrados por movimento. A massa e "
                    "a exposicao acumulada, o clima e o controle de prova "
                    "modulam a velocidade com parametros assumidos."
                    " Pit stop percorre geometria mockada e serviço de pneus; "
                    "não soma a perda histórica nem executa reabastecimento."
                ),
                "tyre_active": tyre_active,
                "fuel_active": fuel is not None,
                "refuel_active": refuel_mode,
                "pit_active": pit_active,
                "weather_active": bool(track_states)
                and any(state.surface_water > 0 for state in track_states),
                "track_condition_active": bool(track_states),
                "race_control_active": race_control is not None,
                "mechanical_hazard_per_lap": mechanical_hazard_per_lap,
            }
        ],
    }
    # Decomposicao da velocidade por carro: ritmo fisico de referencia, teto de
    # reta e, por volta, quanto pneu/combustivel/clima/controle tiram do ritmo.
    # A curva e lida ponto a ponto no frontend (teto do ponto vs v_max); aqui
    # fica so o invariante por carro e as penalidades por volta.
    def _attributes_echo(did: str) -> dict | None:
        attrs = attributes_by_id.get(did)
        if attrs is None:
            return None
        return {
            "archetype": attrs.archetype,
            "pace_offset_pct": attrs.pace_offset_pct,
            "consistency_factor": attrs.consistency_factor,
            "tyre_management_factor": attrs.tyre_management_factor,
            "aggression": attrs.aggression,
            "composure": attrs.composure,
        }

    result["speed_breakdown"] = {
        "cars": {
            did: {
                "v_max_kmh": round(physics_by_id[did].v_max_straight_kmh, 2),
                "reference_lap_ms": round(ref_ms[did], 3),
                "attributes": _attributes_echo(did),
                "laps": {
                    str(lap): data
                    for lap, data in sorted(speed_breakdown[did].items())
                },
            }
            for did in names
        },
    }
    if usage_active:
        reports = {}
        for did, totals in usage_totals.items():
            report = dict(totals)
            if fuel is None:
                report["fuel_burned_kg"] = None
            if not tyre_active:
                for name in (
                    "distance_wear_laps",
                    "lateral_wear_laps",
                    "longitudinal_wear_laps",
                ):
                    report[name] = None
            reports[did] = {
                **report,
                "current_tyre_wear_laps": cars_by_id[did].tyre_wear_laps,
                "management_factor": management[did] if tyre_active else None,
            }
        result["usage_2d"] = {
            "tyre_active": tyre_active,
            "fuel_active": fuel is not None,
            "reference": asdict(reference_usage),
            "curvature": {
                "distance_m": list(curvature.distances_m),
                "curvature_per_m": list(curvature.curvature_per_m),
            },
            "cars": reports,
        }
        result["assumptions"].append(
            {
                "kind": "dynamic_usage_2d",
                **asdict(usage_parameters),
                "reference_physics": asdict(base_physics),
                "rationale": "Carga lateral estimada por v²*curvatura; índices de desgaste e consumo "
                "normalizados pela mesma volta neutra, sem calibrar os pesos nem "
                "somar a idade/queima por volta ou os fatores de consumo SC/VSC. "
                "Gestão aplicada uma vez; agressividade atua pelo movimento. "
                "Frenagem é proxy de coasting, não acelerador medido. Vazão máxima usa 2025.",
                "sources": [
                    "https://press.pirelli.com/an-important-debut-on-one-of-the-toughest-tracks-for-tyres/",
                    "https://simulation.michelin.com/canopy/technical-articles/save-more-fuel-than-lando-norris-how-to-drive-an-f1-car-efficiently",
                    "https://www.fia.com/sites/default/files/fia_2025_formula_1_technical_regulations_-_issue_01_-_2024-12-11_1.pdf",
                ],
            }
        )
    if pit_lane is not None:
        result["pit_planning_2d"] = {
            "parameters": asdict(pit_planning),
            "cars": strategy_plans,
        }
        result["assumptions"].append(
            {
                "kind": "pit_planning_2d",
                **asdict(pit_planning),
                "rationale": "Troca obrigatória planejada pelo desgaste equivalente com preferência "
                "individual semeada; preserva o último prazo comum e não exige "
                "voltas distintas quando as decisões coincidirem.",
            }
        )
        result["pit_lane_2d"] = {
            "points": [list(point) for point in pit_lane.points],
            "entry_distance_m": pit_lane.entry_distance_m,
            "exit_distance_m": pit_lane.exit_distance_m,
            "service_distance_m": pit_lane.service_distance_m,
            "length_m": pit_lane.length_m,
        }
        result["assumptions"].append(
            {
                "kind": "pit_lane_2d",
                "origin": pit_parameters.origin,
                "parameter_version": pit_parameters.parameter_version,
                "speed_limit_kmh": pit_parameters.speed_limit_kmh,
                "service_time_s": pit_parameters.service_time_s,
                "merge_gap_m": pit_parameters.merge_gap_m,
                "rationale": "Comprimento estimado da polilinha mockada pela escala da pista; "
                "não calibrado. Serviço único representativo, fila sem ultrapassagem, "
                "limite aplicado na entrada e espera por folga na saída. "
                "A perda histórica só orienta a estratégia.",
            }
        )
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
