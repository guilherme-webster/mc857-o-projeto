"""Motor de corrida 2D (ADR 0011, fatia 6): roda a fisica espacial de
``track_space`` e produz o mesmo ``history`` por volta que o motor por volta,
para o frontend e as corridas salvas lerem sem mudanca.

A fisica continua em ``track_space`` (posicao, ultrapassagem, colisao). Aqui so
se converte a trajetoria continua em retratos de fim de volta: para cada carro,
o instante em que cruza cada volta vira o ``total_time_ms`` daquele retrato.

Fronteiras (ADR 0011): este e o motor 2D, selecionavel e ainda sem os efeitos
que o motor por volta tem (pneu, combustivel, clima, controle de prova). Eles
entram como camadas nas sub-fatias seguintes; ate la, o retrato traz apenas
posicao, voltas e abandono por contato. Rotulado como tal em ``assumptions``.
"""

from __future__ import annotations

from f1_simulator.domain.fuel import FuelPlan
from f1_simulator.domain.model_parameters import CompoundParameters, TrackParameters
from f1_simulator.domain.random_source import RandomSource
from f1_simulator.domain.speed_dynamics import (
    CarPhysics,
    lap_time_ms,
    physics_for,
    steady_lap,
)
from f1_simulator.domain.track_space import (
    CarSpaceState,
    FieldSample,
    TrackSpace,
    build_track_space,
    integrate_field,
)
from f1_simulator.domain.track_geometry import TrackGeometry
from f1_simulator.domain.tyres import TyreSet, tyre_penalty_ms

RUNNING = "RUNNING"
RETIRED = "RETIRED"
CONTACT = "CONTACT"
MECHANICAL = "MECHANICAL"

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


def _classification(
    states: dict[str, dict],
) -> list[dict]:
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
        rows.append(
            {
                "position": index,
                "driver_id": s["driver_id"],
                "name": s["name"],
                "total_time_ms": round(s["total_time_ms"], 1),
                "lap_time_ms": round(s["total_time_ms"] / laps, 1) if laps else 0.0,
                "laps_completed": laps,
                "status": s["status"],
                "compound": s.get("compound", "MEDIUM"),
                "tyre_age_laps": laps,
                "stops_made": 0,
                "retirement_cause": s["retirement_cause"],
                "blocked_laps": 0,
            }
        )
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
    fuel: FuelPlan | None = None,
    lap_surface_water: list[float] | None = None,
    reliability_by_id: dict[str, float] | None = None,
    mechanical_hazard_per_lap: float = 0.0,
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
    - ``fuel``: a massa a bordo custa tempo e diminui a cada volta queimada;
    - ``lap_surface_water``: a agua na pista penaliza por volta (``weather.py``).

    Cada efeito ausente simplesmente nao atua. Reabastecimento, pit stop,
    controle de prova e abandono mecanico ainda nao sao modelados no 2D e ficam
    declarados como limitacao.
    """

    track = (
        build_track_space(geometry)
        if width_m is None
        else build_track_space(geometry, width_m=width_m)
    )
    lap_length_m = track.lap_length_m

    cars: list[CarSpaceState] = []
    physics_by_id: dict[str, CarPhysics] = {}
    aggression_by_id: dict[str, float] = {}
    names: dict[str, str] = {}
    grid_by_id: dict[str, int] = {}
    start_compound: dict[str, str] = {}
    tyre_by_id: dict[str, TyreSet] = {}
    fuel_kg: dict[str, float] = {}
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
        start_compound[did] = entry.get("compound", "MEDIUM")
        tyre_by_id[did] = TyreSet(start_compound[did], 0)
        ref_ms[did] = lap_time_ms(steady_lap(geometry, physics))
        if fuel is not None:
            load = entry.get("start_fuel_kg")
            fuel_kg[did] = (
                float(load) if load is not None else fuel.start_fuel_kg(total_laps)
            )
        offset = (len(entrants) - entry["grid_position"]) * GRID_SPACING_M
        cars.append(CarSpaceState(did, distance_m=offset, lateral_m=0.0))

    tyre_active = compounds is not None and track_params is not None

    def _penalty_ms(did: str, tyre: TyreSet, lap_number: int) -> float:
        """Soma das penalidades de tempo ativas para este carro nesta volta."""

        total = 0.0
        if tyre_active:
            total += tyre_penalty_ms(tyre, compounds[tyre.compound], track_params)
        if fuel is not None:
            total += fuel.ms_per_kg * fuel_kg[did]
        if lap_surface_water:
            idx = min(lap_number - 1, len(lap_surface_water) - 1)
            total += ref_ms[did] * 0.40 * lap_surface_water[idx]
        return total

    def _apply_scale(car: CarSpaceState, lap_number: int) -> None:
        base = ref_ms[car.driver_id]
        penalty = _penalty_ms(car.driver_id, tyre_by_id[car.driver_id], lap_number)
        car.speed_scale = base / (base + penalty) if base + penalty > 0 else 1.0

    reliability_by_id = reliability_by_id or {}
    mechanical_retired: dict[str, int] = {}

    def on_lap_complete(car: CarSpaceState, lap: int) -> None:
        did = car.driver_id
        if tyre_active:
            tyre_by_id[did] = tyre_by_id[did].aged()
        if fuel is not None:
            fuel_kg[did] = max(0.0, fuel_kg[did] - fuel.burn_kg_per_lap)
        # Abandono mecanico: sorteio por volta, antes de atualizar a velocidade.
        # Ordem de sorteio fixa pelo rotulo, para reproduzir por semente.
        if mechanical_hazard_per_lap > 0.0 and lap < total_laps:
            hazard = mechanical_hazard_per_lap * reliability_by_id.get(did, 1.0)
            if rng.uniform01(f"mechanical:{did}:lap:{lap}") < hazard:
                car.retired = True
                mechanical_retired[did] = lap
                return
        _apply_scale(car, lap + 1)

    # Fator inicial da volta 1 (pneu novo, tanque cheio, clima da volta 1).
    for car in cars:
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
    )

    history: list[dict] = []
    per_car: dict[str, list[float]] = {}
    outcome: dict[str, tuple[bool, int | None, float | None]] = {}
    for did in names:
        times, retired, retired_on, retired_at_ms = _lap_crossing_times_ms(
            samples, did, lap_length_m, total_laps
        )
        # Carro que abandonou sem completar nenhuma volta registra uma "volta"
        # com o tempo do abandono, porque o retrato por volta (e o RacePlayback
        # do frontend) exige ao menos uma volta por carro. A posicao de
        # abandono na pista fica implicita; o motor detalhado tambem contabiliza
        # a volta em que o carro cai.
        if retired and not times:
            times = [retired_at_ms if retired_at_ms is not None else 0.0]
            retired_on = 1
        per_car[did] = times
        outcome[did] = (retired, retired_on, retired_at_ms)

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
                cause = MECHANICAL if did in mechanical_retired else CONTACT
            states[did] = {
                "driver_id": did,
                "name": names[did],
                "total_time_ms": total_ms,
                "laps_completed": laps_done,
                "status": RETIRED if is_retired else RUNNING,
                "retirement_cause": cause,
                "compound": start_compound[did],
            }
        history.append({"lap": lap, "cars": _classification(states)})

    classification = history[-1]["cars"] if history else []
    return {
        "total_laps": total_laps,
        "circuit_id": geometry.circuit_id,
        "history": history,
        "classification": classification,
        "starting_grid": [
            {
                "position": grid_by_id[did],
                "driver_id": did,
                "compound": start_compound[did],
            }
            for did in sorted(names, key=lambda d: grid_by_id[d])
        ],
        "assumptions": [
            {
                "kind": "engine_2d",
                "origin": "assumed",
                "parameter_version": "motor-2d-v1",
                "rationale": (
                    "ADR 0011: motor 2D de posicao continua. Velocidade, "
                    "ultrapassagem e colisao emergem da fisica espacial; pneu, "
                    "combustivel, clima e abandono mecanico entram como "
                    "penalidades de tempo convertidas em velocidade. Ainda sem "
                    "reabastecimento, pit stop, SC/VSC e bandeiras."
                ),
                "tyre_active": tyre_active,
                "fuel_active": fuel is not None,
                "weather_active": bool(lap_surface_water),
                "mechanical_hazard_per_lap": mechanical_hazard_per_lap,
            }
        ],
    }
