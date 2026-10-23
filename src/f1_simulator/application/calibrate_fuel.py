"""Calibracao e validacao do modelo de massa de combustivel.

Este modulo contem apenas a matematica. A leitura do banco e da extensao das
pistas fica em ``scripts/calibrate_fuel.py`` e nos adaptadores existentes,
preservando a fronteira do ADR 0002.

O que se mede
-------------
O Trotman nao registra combustivel, mas registra o seu efeito: o carro fica
mais rapido conforme queima. A identificacao reaproveita a regressao de dois
relogios de ``calibrate_model.py`` (numero da volta contra idade do pneu, ambos
centrados por corrida/piloto) com uma mudanca no regressor de combustivel.

No modelo linear legado o regressor e o numero da volta, e o coeficiente
(ms por volta) vale igual em Monaco e em Spa. No modelo de massa a inclinacao
de uma corrida e

    ms_por_volta = fracao_por_km * T_ms * L_km

porque cada volta queima o combustivel de ``L_km`` km e cada kg custa uma
fracao fixa do tempo de volta ``T_ms``. O regressor passa a ser
``volta * T_ms * L_km`` e o coeficiente estimado e ``-fracao_por_km``, um unico
numero valido para todos os circuitos.

Validacao
---------
``validate_fuel`` estima a inclinacao de combustivel de cada corrida de
temporadas reservadas (fora da calibracao) e compara com a previsao dos dois
modelos. O erro e medido em ms por volta, a mesma unidade do parametro legado.

Tempo de parada por carro
-------------------------
``calibrate_refuel_stops`` mede, nas paradas reais (``pit_stops.duration``,
tempo de pit lane), quanto cada equipe difere da mediana da propria corrida.
Subtrair a mediana da corrida elimina o comprimento do pit lane de cada
circuito. Como as equipes mudam de uma temporada para outra, o deslocamento
previsto e o medido vezes a persistencia observada entre janelas
consecutivas do historico -- todas anteriores as temporadas de validacao.

Limite conhecido: a evolucao da pista (borracha acumulada) tambem deixa as
voltas mais rapidas ao longo da corrida e acompanha o numero da volta. O
coeficiente medido inclui esse efeito, como ja acontecia com o parametro
legado; ele e o "combustivel efetivo" que reproduz a tendencia observada.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from f1_simulator.application.calibrate_model import LapObservation, _ols_two_slopes
from f1_simulator.domain.fuel import (
    FuelModelParameters,
    RefuelStopParameters,
    TeamPitOffset,
)
from f1_simulator.domain.model_parameters import CalibrationProvenance

METHOD_VERSION = "fuel-mass-two-clock-v1"

#: Volta usada apenas para traduzir o coeficiente em ms/kg no relatorio.
REPORT_LAP_MS = 90_000.0

#: Mesmo minimo de voltas limpas por piloto usado em ``calibrate_model``.
MINIMUM_LAPS_PER_DRIVER_RACE = 10

#: Voltas limpas minimas para estimar a inclinacao de uma unica corrida. Abaixo
#: disso a separacao entre combustivel e pneu e ruido.
MINIMUM_LAPS_PER_RACE = 300


@dataclass(frozen=True, slots=True)
class FuelRaceContext:
    """O que a calibracao precisa saber de uma corrida alem das voltas.

    ``reference_lap_ms`` segue o metodo de ``application/reference_laps.py``
    (mediana das voltas mais rapidas de cada piloto), que e a mesma referencia
    que o motor recebe; assim a fracao calibrada e aplicada sobre a mesma
    grandeza em que foi medida. ``lap_length_km`` vem da geometria FastF1.
    """

    race_id: str
    name: str
    season: int
    circuit_id: str
    reference_lap_ms: float
    lap_length_km: float

    def __post_init__(self) -> None:
        if self.reference_lap_ms <= 0 or self.lap_length_km <= 0:
            raise ValueError(f"contexto invalido para {self.race_id}")


@dataclass(frozen=True, slots=True)
class FuelCalibrationDiagnostics:
    """Evidencia que acompanha o coeficiente calibrado."""

    clean_laps: int
    races: int
    skipped_races: tuple[str, ...]
    collinearity: float
    lap_time_fraction_per_fuel_km: float
    tyre_ms_per_lap: float
    implied_ms_per_kg_at_90s: float


@dataclass(frozen=True, slots=True)
class RaceFuelCheck:
    """Inclinacao observada de uma corrida contra a previsao dos dois modelos.

    Todos os valores sao penalidade por volta restante (ms), positivos quando o
    carro fica mais rapido ao queimar combustivel.
    """

    race_id: str
    name: str
    season: int
    laps_used: int
    observed_ms_per_lap: float
    mass_model_ms_per_lap: float
    linear_model_ms_per_lap: float


@dataclass(frozen=True, slots=True)
class FuelValidationReport:
    """Erro por corrida dos dois modelos numa amostra fora da calibracao.

    O erro medio e ponderado pelas voltas usadas; a mediana e incluida porque
    corridas de chuva produzem inclinacoes absurdas que nenhum modelo de
    combustivel deveria explicar.
    """

    seasons: tuple[int, ...]
    races: tuple[RaceFuelCheck, ...]
    mass_weighted_mae_ms: float
    linear_weighted_mae_ms: float
    mass_median_ae_ms: float
    linear_median_ae_ms: float


def _rows_by_race(
    laps: Sequence[LapObservation], contexts: Mapping[str, FuelRaceContext]
) -> tuple[dict[str, list[tuple[float, float, float, float]]], tuple[str, ...]]:
    """Linhas centradas por (corrida, piloto): (volta, volta*T*L, idade, tempo).

    Corridas sem contexto (sem extensao de pista ou sem voltas rapidas) sao
    devolvidas a parte, em vez de receberem um valor inventado.
    """

    grouped: dict[tuple[str, str], list[LapObservation]] = defaultdict(list)
    for lap in laps:
        grouped[(lap.race_id, lap.driver_id)].append(lap)

    rows: dict[str, list[tuple[float, float, float, float]]] = defaultdict(list)
    skipped: set[str] = set()
    for (race_id, _), observations in grouped.items():
        if len(observations) < MINIMUM_LAPS_PER_DRIVER_RACE:
            continue
        context = contexts.get(race_id)
        if context is None:
            skipped.add(race_id)
            continue
        scale = context.reference_lap_ms * context.lap_length_km
        mean_lap = statistics.fmean(float(o.lap_number) for o in observations)
        mean_age = statistics.fmean(float(o.tyre_age_laps) for o in observations)
        mean_time = statistics.fmean(float(o.lap_time_ms) for o in observations)
        for o in observations:
            centred_lap = o.lap_number - mean_lap
            rows[race_id].append(
                (
                    centred_lap,
                    centred_lap * scale,
                    o.tyre_age_laps - mean_age,
                    o.lap_time_ms - mean_time,
                )
            )
    return dict(rows), tuple(sorted(skipped))


def calibrate_fuel(
    laps: Sequence[LapObservation],
    contexts: Mapping[str, FuelRaceContext],
    *,
    version: str,
    seasons: tuple[int, ...],
    source_name: str,
    source_version: int,
    calibrated_at: str | None = None,
) -> tuple[FuelModelParameters, FuelCalibrationDiagnostics]:
    """Estime ``lap_time_fraction_per_fuel_km`` e devolva os parametros.

    Os demais campos de ``FuelModelParameters`` mantem as hipoteses e o teto
    regulamentar declarados no dominio: o Trotman nao os observa.
    """

    rows_by_race, skipped = _rows_by_race(laps, contexts)
    rows = [
        (scaled, age, time)
        for race_rows in rows_by_race.values()
        for _, scaled, age, time in race_rows
    ]
    if not rows:
        raise ValueError("nenhuma corrida com contexto e voltas limpas suficientes")

    slope, tyre_slope, collinearity = _ols_two_slopes(rows)
    fraction = -slope
    # Inclinacao positiva significaria carro mais lento ao queimar: o efeito
    # nao foi identificado nesta amostra. Recusar e mais honesto que zerar.
    if fraction <= 0:
        raise ValueError(
            f"efeito do combustivel nao identificado (coeficiente {slope:.3e})"
        )

    used_races = tuple(sorted(rows_by_race))
    parameters = FuelModelParameters(
        version=version,
        provenance=CalibrationProvenance(
            source_name=source_name,
            source_version=source_version,
            seasons=seasons,
            races=len(used_races),
            clean_laps=len(rows),
            calibrated_at=calibrated_at or date.today().isoformat(),
        ),
        lap_time_fraction_per_fuel_km=round(fraction, 9),
        origin="calibrated",
    )
    diagnostics = FuelCalibrationDiagnostics(
        clean_laps=len(rows),
        races=len(used_races),
        skipped_races=skipped,
        collinearity=round(collinearity, 4),
        lap_time_fraction_per_fuel_km=fraction,
        tyre_ms_per_lap=round(tyre_slope, 2),
        implied_ms_per_kg_at_90s=round(
            parameters.lap_time_fraction_per_kg * REPORT_LAP_MS, 2
        ),
    )
    return parameters, diagnostics


def validate_fuel(
    laps: Sequence[LapObservation],
    contexts: Mapping[str, FuelRaceContext],
    parameters: FuelModelParameters,
    *,
    linear_ms_per_lap: float,
    seasons: tuple[int, ...],
    minimum_laps_per_race: int = MINIMUM_LAPS_PER_RACE,
) -> FuelValidationReport:
    """Compare as previsoes por corrida com a inclinacao observada.

    A inclinacao observada de cada corrida sai da regressao de dois relogios
    (volta, idade do pneu) restrita a ela. Corridas em que a regressao e
    singular (sem paradas suficientes) ficam de fora.
    """

    rows_by_race, _ = _rows_by_race(laps, contexts)
    checks: list[RaceFuelCheck] = []
    for race_id, race_rows in sorted(rows_by_race.items()):
        if len(race_rows) < minimum_laps_per_race:
            continue
        try:
            slope, _, _ = _ols_two_slopes(
                [(lap, age, time) for lap, _, age, time in race_rows]
            )
        except ValueError:
            continue
        context = contexts[race_id]
        checks.append(
            RaceFuelCheck(
                race_id=race_id,
                name=context.name,
                season=context.season,
                laps_used=len(race_rows),
                observed_ms_per_lap=round(-slope, 1),
                mass_model_ms_per_lap=round(
                    parameters.lap_time_fraction_per_fuel_km
                    * context.reference_lap_ms
                    * context.lap_length_km,
                    1,
                ),
                linear_model_ms_per_lap=round(linear_ms_per_lap, 1),
            )
        )
    if not checks:
        raise ValueError("nenhuma corrida de validacao com voltas suficientes")

    weights = sum(check.laps_used for check in checks)

    def weighted_mae(predicted: str) -> float:
        return round(
            sum(
                abs(check.observed_ms_per_lap - getattr(check, predicted))
                * check.laps_used
                for check in checks
            )
            / weights,
            1,
        )

    def median_ae(predicted: str) -> float:
        return round(
            statistics.median(
                abs(check.observed_ms_per_lap - getattr(check, predicted))
                for check in checks
            ),
            1,
        )

    return FuelValidationReport(
        seasons=seasons,
        races=tuple(checks),
        mass_weighted_mae_ms=weighted_mae("mass_model_ms_per_lap"),
        linear_weighted_mae_ms=weighted_mae("linear_model_ms_per_lap"),
        mass_median_ae_ms=median_ae("mass_model_ms_per_lap"),
        linear_median_ae_ms=median_ae("linear_model_ms_per_lap"),
    )


#: Faixa plausivel de uma passagem pelo pit lane (ms). Acima, o registro e uma
#: parada sob bandeira vermelha, com o carro minutos parado.
MIN_STOP_DURATION_MS = 10_000
MAX_STOP_DURATION_MS = 60_000

#: Paradas minimas numa corrida para que sua mediana sirva de referencia.
MINIMUM_STOPS_PER_RACE = 10

#: Paradas minimas para uma equipe receber deslocamento proprio.
MINIMUM_STOPS_PER_TEAM = 20


@dataclass(frozen=True, slots=True)
class PitStopObservation:
    """Uma parada real: duracao no pit lane e a equipe do carro."""

    race_id: str
    season: int
    team_id: str
    team_name: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class TeamStopCheck:
    """Deslocamento previsto contra o medido numa temporada fora da amostra."""

    team_id: str
    name: str
    stops: int
    observed_offset_ms: float
    predicted_offset_ms: float


@dataclass(frozen=True, slots=True)
class RefuelStopValidation:
    """Erro do tempo de parada por equipe e cobertura da variacao por parada.

    ``*_mae_ms`` compara tres previsoes do deslocamento de cada equipe: o
    modelo (medido x persistencia), o medido cru e zero (todas iguais ao
    campo). ``p10_p90_coverage`` e a fracao das paradas reais cujo desvio cai
    entre os percentis 10 e 90 da variacao modelada; o ideal e 0,80.
    """

    seasons: tuple[int, ...]
    teams: tuple[TeamStopCheck, ...]
    model_mae_ms: float
    raw_offset_mae_ms: float
    zero_offset_mae_ms: float
    p10_p90_coverage: float
    stops: int


def _stop_deltas(
    stops: Sequence[PitStopObservation],
) -> list[tuple[PitStopObservation, float]]:
    """Desvio de cada parada plausivel em relacao a mediana da sua corrida."""

    plausible = [
        stop
        for stop in stops
        if MIN_STOP_DURATION_MS < stop.duration_ms < MAX_STOP_DURATION_MS
    ]
    by_race: dict[str, list[int]] = defaultdict(list)
    for stop in plausible:
        by_race[stop.race_id].append(stop.duration_ms)
    medians = {
        race_id: statistics.median(values)
        for race_id, values in by_race.items()
        if len(values) >= MINIMUM_STOPS_PER_RACE
    }
    return [
        (stop, stop.duration_ms - medians[stop.race_id])
        for stop in plausible
        if stop.race_id in medians
    ]


def _team_offsets(
    deltas: Sequence[tuple[PitStopObservation, float]],
    seasons: Sequence[int],
) -> dict[str, tuple[str, float, int]]:
    """Mediana do desvio por equipe nas temporadas: {id: (nome, ms, paradas)}."""

    wanted = set(seasons)
    grouped: dict[str, list[float]] = defaultdict(list)
    names: dict[str, str] = {}
    for stop, delta in deltas:
        if stop.season in wanted:
            grouped[stop.team_id].append(delta)
            names[stop.team_id] = stop.team_name
    return {
        team_id: (names[team_id], statistics.median(values), len(values))
        for team_id, values in grouped.items()
        if len(values) >= MINIMUM_STOPS_PER_TEAM
    }


def _persistence(
    deltas: Sequence[tuple[PitStopObservation, float]],
    windows: Sequence[tuple[tuple[int, ...], int]],
) -> float:
    """Inclinacao pela origem do deslocamento seguinte contra o da janela.

    Cada janela e ``(temporadas, temporada seguinte)``. Equipes que mudaram de
    identificador (AlphaTauri -> RB, Alfa Romeo -> Sauber) simplesmente nao
    entram no par em que mudaram.
    """

    sxx = sxy = 0.0
    for window, following in windows:
        before = _team_offsets(deltas, window)
        after = _team_offsets(deltas, (following,))
        for team_id in before.keys() & after.keys():
            x, y = before[team_id][1], after[team_id][1]
            sxx += x * x
            sxy += x * y
    if sxx == 0.0:
        raise ValueError("persistencia nao identificada: sem equipes em comum")
    return min(1.0, max(0.0, sxy / sxx))


def calibrate_refuel_stops(
    stops: Sequence[PitStopObservation],
    *,
    seasons: tuple[int, ...],
    persistence_windows: Sequence[tuple[tuple[int, ...], int]],
    source_name: str,
    source_version: int,
    calibrated_at: str | None = None,
) -> RefuelStopParameters:
    """Estime deslocamento por equipe, persistencia e variacao por parada.

    ``persistence_windows`` deve terminar antes de qualquer temporada usada na
    validacao; o script garante isso.
    """

    deltas = _stop_deltas(stops)
    offsets = _team_offsets(deltas, seasons)
    if not offsets:
        raise ValueError("nenhuma equipe com paradas suficientes nas temporadas")
    persistence = _persistence(deltas, persistence_windows)

    wanted = set(seasons)
    residuals = [
        delta - offsets[stop.team_id][1]
        for stop, delta in deltas
        if stop.season in wanted and stop.team_id in offsets
    ]
    # A normal assimetrica e ajustada aos percentis 10 e 90 observados:
    # p90 = z90 * sigma * (1 + skew) e p10 = -z90 * sigma * (1 - skew). O
    # desvio absoluto mediano subestimava a cauda (so 68% das paradas reais de
    # 2025 caiam na faixa p10-p90 modelada) e a media seria dominada por
    # penalidades cumpridas na parada, que ficam alem do p90 de proposito.
    deciles = statistics.quantiles(residuals, n=10)
    p10, p90 = deciles[0], deciles[8]
    z90 = statistics.NormalDist().inv_cdf(0.90)
    spread = (p90 - p10) / (2.0 * z90)
    skew = (p90 + p10) / (p90 - p10) if p90 > p10 else 0.0

    return RefuelStopParameters(
        provenance=CalibrationProvenance(
            source_name=source_name,
            source_version=source_version,
            seasons=seasons,
            races=len({stop.race_id for stop, _ in deltas if stop.season in wanted}),
            clean_laps=len(residuals),
            calibrated_at=calibrated_at or date.today().isoformat(),
        ),
        team_offsets=tuple(
            TeamPitOffset(team_id, name, round(offset, 1), count)
            for team_id, (name, offset, count) in sorted(offsets.items())
        ),
        persistence=round(persistence, 3),
        stop_sigma_ms=round(spread, 1),
        stop_skew=round(min(1.0, max(0.0, skew)), 3),
        origin="calibrated",
    )


def _modelled_quantile(parameters: RefuelStopParameters, quantile: float) -> float:
    """Percentil da normal assimetrica usada em ``sample_refuel_stops``."""

    z = statistics.NormalDist().inv_cdf(quantile)
    scale = 1.0 + parameters.stop_skew if z > 0 else 1.0 - parameters.stop_skew
    return z * parameters.stop_sigma_ms * scale


def validate_refuel_stops(
    stops: Sequence[PitStopObservation],
    parameters: RefuelStopParameters,
    *,
    seasons: tuple[int, ...],
) -> RefuelStopValidation:
    """Confronte o tempo de parada previsto com temporadas fora da amostra."""

    deltas = _stop_deltas(stops)
    observed = _team_offsets(deltas, seasons)
    raw = {item.team_id: item.offset_ms for item in parameters.team_offsets}
    checks = tuple(
        TeamStopCheck(
            team_id=team_id,
            name=name,
            stops=count,
            observed_offset_ms=round(offset, 1),
            predicted_offset_ms=round(parameters.offset_ms(team_id), 1),
        )
        for team_id, (name, offset, count) in sorted(observed.items())
    )
    if not checks:
        raise ValueError("nenhuma equipe com paradas suficientes na validacao")

    def mae(predict) -> float:
        return round(
            statistics.fmean(
                abs(check.observed_offset_ms - predict(check)) for check in checks
            ),
            1,
        )

    low = _modelled_quantile(parameters, 0.10)
    high = _modelled_quantile(parameters, 0.90)
    wanted = set(seasons)
    residuals = [
        delta - parameters.offset_ms(stop.team_id)
        for stop, delta in deltas
        if stop.season in wanted
    ]
    inside = sum(1 for value in residuals if low <= value <= high)
    return RefuelStopValidation(
        seasons=seasons,
        teams=checks,
        model_mae_ms=mae(lambda check: check.predicted_offset_ms),
        raw_offset_mae_ms=mae(lambda check: raw.get(check.team_id, 0.0)),
        zero_offset_mae_ms=mae(lambda check: 0.0),
        p10_p90_coverage=round(inside / len(residuals), 3) if residuals else 0.0,
        stops=len(residuals),
    )
