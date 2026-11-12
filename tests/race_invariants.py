"""Invariantes reutilizaveis do resultado de ``simulate_2d_race``.

Moldado em ``tests/history_support.py``: concentra a montagem de insumos e as
verificacoes que qualquer teste de ponta a ponta do motor 2D precisa, para os
testes de regressao dos bugs #140 (combustivel) e #141 (pneu) reusarem as
mesmas regras em vez de reescreve-las.

Todas as verificacoes recebem o ``unittest.TestCase`` chamador e usam seus
``assert*``, de modo que a falha aponta o teste real. Nenhuma delas conhece o
motor alem do contrato do dicionario devolvido (``history``, ``classification``,
``race_control_events``, ``speed_breakdown``, ``trajectories_2d``).

Os numeros de combustivel sao redondos e arbitrarios (como em
``tests/model_support.py``): os testes verificam regras, nao calibracao.
"""

from __future__ import annotations

from pathlib import Path

from f1_simulator.adapters.datasets.mock_track_geometry import MockTrackDatasetAdapter
from f1_simulator.domain.fuel import FuelModelParameters, FuelPlan
from f1_simulator.factories.track_geometry_factory import TrackGeometryFactory
from tests.model_support import provenance

ROOT = Path(__file__).resolve().parents[1]
TRACKS = ROOT / "tests" / "fixtures" / "trotman_v128_tracks_2025"

#: O circuito 1 (cerca de 5 km, 240 pontos) mantem uma corrida de poucos carros
#: e voltas na casa de segundos.
DEFAULT_CIRCUIT = "circuit:1"


def real_geometry(circuit_id: str = DEFAULT_CIRCUIT):
    """Geometria real reduzida (ADR 0003) lida do fixture, sem rede."""

    adapter = MockTrackDatasetAdapter(
        TRACKS / "track_points.csv",
        ROOT / "data" / "sources" / "fastf1-tracks-2025.json",
        TRACKS / "pit_lane_points.csv",
        ROOT / "data" / "sources" / "fastf1-pit-lanes-2025.json",
    )
    return TrackGeometryFactory.build(adapter.load_geometry(circuit_id))


def entrants(count: int, **overrides) -> list[dict]:
    """``count`` entrantes sem atributos, grid 1..count, ``D1``..``Dn``."""

    return [
        {
            "driver_id": f"d{index}",
            "name": f"Piloto {index}",
            "grid_position": index,
            **overrides,
        }
        for index in range(1, count + 1)
    ]


def fuel_plan(geometry, *, reference_lap_ms: float = 90_000.0) -> FuelPlan:
    """Plano de combustivel assumido (valores de teste, nao calibrados)."""

    parameters = FuelModelParameters(
        version="fuel-teste",
        provenance=provenance(),
        lap_time_fraction_per_fuel_km=12.5 / reference_lap_ms * 0.5,
        burn_kg_per_km=0.5,
        finish_reserve_kg=1.0,
        origin="assumed",
        refuelling_allowed=False,
    )
    return FuelPlan(
        parameters, reference_lap_ms, geometry.lap_length_m / 1000, "track_geometry"
    )


def driver_ids(entries: list[dict]) -> list[str]:
    return [entry["driver_id"] for entry in entries]


# --- reprodutibilidade -----------------------------------------------------


def assert_same_race(case, first: dict, second: dict) -> None:
    """Mesma semente e insumos: saidas observaveis identicas."""

    for key in ("history", "classification", "race_control_events"):
        case.assertEqual(first[key], second[key], key)


# --- classificacao e historico --------------------------------------------


def assert_classification_invariants(
    case, result: dict, expected_ids: list[str], total_laps: int
) -> None:
    """Regras da tabela final: unicidade, posicoes 1..N, voltas, abandono."""

    rows = result["classification"]
    ids = [row["driver_id"] for row in rows]
    case.assertEqual(sorted(ids), sorted(expected_ids))
    case.assertEqual(len(ids), len(set(ids)))
    case.assertEqual([row["position"] for row in rows], list(range(1, len(rows) + 1)))
    for row in rows:
        if row["status"] == "RETIRED":
            case.assertTrue(row["retirement_cause"], row["driver_id"])
            case.assertGreaterEqual(row["laps_completed"], 0)
            case.assertLess(row["laps_completed"], total_laps)
        else:
            case.assertEqual(row["status"], "RUNNING")
            case.assertEqual(row["laps_completed"], total_laps, row["driver_id"])
            case.assertIsNone(row["retirement_cause"])
            case.assertGreater(row["total_time_ms"], 0)
    # Quem terminou vem antes de quem abandonou, e entre os que terminaram o
    # tempo total nao decresce com a posicao.
    finishers = [row for row in rows if row["status"] == "RUNNING"]
    case.assertEqual(rows[: len(finishers)], finishers)
    times = [row["total_time_ms"] for row in finishers]
    case.assertEqual(times, sorted(times))


def assert_history_invariants(
    case, result: dict, expected_ids: list[str], total_laps: int
) -> None:
    """Cada volta do ``history`` e uma classificacao valida; nada regride."""

    history = result["history"]
    case.assertEqual([entry["lap"] for entry in history], list(range(1, total_laps + 1)))
    previous: dict[str, dict] = {}
    for entry in history:
        rows = entry["cars"]
        case.assertEqual(sorted(r["driver_id"] for r in rows), sorted(expected_ids))
        case.assertEqual([r["position"] for r in rows], list(range(1, len(rows) + 1)))
        for row in rows:
            did = row["driver_id"]
            case.assertLessEqual(row["laps_completed"], entry["lap"])
            if did in previous:
                case.assertGreaterEqual(
                    row["laps_completed"], previous[did]["laps_completed"], did
                )
                case.assertGreaterEqual(
                    row["total_time_ms"], previous[did]["total_time_ms"], did
                )
                case.assertGreaterEqual(
                    row["stops_made"], previous[did]["stops_made"], did
                )
                if previous[did]["status"] == "RETIRED":
                    case.assertEqual(row["status"], "RETIRED", did)
            previous[did] = row
    case.assertEqual(result["classification"], history[-1]["cars"])


# --- pit stops, combustivel e pneu ----------------------------------------


def stop_laps(result: dict, driver_id: str) -> set[int]:
    """Voltas (ate ``laps_completed``) em que ``stops_made`` do carro subiu.

    Uma volta ``n`` esta no conjunto quando o retrato ao fim de ``n`` ja conta
    mais paradas que o de ``n - 1``: a troca de pneu valeu entre as duas.
    """

    laps: set[int] = set()
    count = 0
    for entry in result["history"]:
        row = next(r for r in entry["cars"] if r["driver_id"] == driver_id)
        if row["stops_made"] > count:
            laps.add(entry["lap"])
            count = row["stops_made"]
    return laps


def breakdown_series(result: dict, driver_id: str, key: str) -> list[tuple[int, float]]:
    """Serie ``(volta, valor)`` de ``speed_breakdown`` para um carro.

    ``key`` e um campo de volta: ``tyre_ms``, ``fuel_ms``, ``weather_ms``,
    ``speed_scale``... A volta ``n`` descreve o ritmo cobrado ao correr a volta
    ``n`` (fator aplicado ao fim da volta ``n - 1``).
    """

    laps = result["speed_breakdown"]["cars"][driver_id]["laps"]
    return sorted((int(lap), data[key]) for lap, data in laps.items())


def assert_effect_moves_only_with_stops(
    case,
    result: dict,
    driver_id: str,
    key: str,
    *,
    direction: str,
    tolerance: float = 1e-6,
) -> None:
    """Efeito de pneu/combustivel na velocidade so cai/sobe de forma coerente.

    Entre duas voltas consecutivas sem pit stop, o efeito (em ms, ``key``) pode
    se mover apenas na ``direction`` fisica: ``"nonincreasing"`` para o
    combustivel (a massa so diminui, o peso perdido so ajuda) e
    ``"nondecreasing"`` para o pneu (o desgaste so acumula). Sentido contrario
    sem troca de pneu e o sintoma dos bugs #140 e #141. Os pares de voltas que
    tocam uma volta de parada ficam isentos, pois o pneu novo zera o desgaste
    (``stop_laps`` e ``breakdown_series`` indexam a troca com defasagem de uma
    volta, e isentar os dois lados evita depender dela).

    ``key`` vem de ``breakdown_series``. Use com ``weather``/controle de prova
    desligados quando a decomposicao nao os separar do efeito testado.
    """

    case_directions = {"nonincreasing", "nondecreasing"}
    case.assertIn(direction, case_directions)
    stops = stop_laps(result, driver_id)
    series = breakdown_series(result, driver_id, key)
    for (lap_a, value_a), (lap_b, value_b) in zip(series, series[1:]):
        if lap_a in stops or lap_b in stops:
            continue
        delta = value_b - value_a
        if direction == "nonincreasing":
            case.assertLessEqual(
                delta, tolerance, f"{key} de {driver_id} subiu da volta {lap_a} a {lap_b}"
            )
        else:
            case.assertGreaterEqual(
                delta, -tolerance, f"{key} de {driver_id} caiu da volta {lap_a} a {lap_b}"
            )


def fuel_series(result: dict, driver_id: str) -> list[float]:
    """Massa de combustivel (kg) amostrada na trajetoria 2D, em ordem de tempo."""

    return [point[5] for point in result["trajectories_2d"][driver_id]]


def assert_fuel_never_increases(case, result: dict, driver_id: str) -> None:
    """Sem reabastecimento, a massa embarcada so diminui."""

    series = fuel_series(result, driver_id)
    case.assertTrue(series)
    for before, after in zip(series, series[1:]):
        case.assertLessEqual(after, before + 1e-9, driver_id)
