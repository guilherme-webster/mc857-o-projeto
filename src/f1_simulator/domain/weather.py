"""Evolução determinística do clima e da água superficial, por volta.

As intensidades são entradas do cenário, não observações inferidas do FastF1.
O índice de água é adimensional (0 = seco, 1 = saturado); não representa
milímetros de precipitação nem um coeficiente físico de aderência. A tradução
da água em aderência, e daí em tempo de volta, fica em
``domain/track_condition.py`` (ADR 0014); este módulo só evolui o estado.

Os fluxos são definidos por "volta de referência" de
``WeatherParameters.reference_lap_minutes``. Uma volta mais longa acumula e
seca proporcionalmente mais: Spa (~1,8 min) seca mais por volta que a Áustria
(~1,2 min). Sem duração informada, cada volta vale uma volta de referência,
como no modelo original da issue #69.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Literal


class RainLevel(StrEnum):
    """Intensidade de chuva prescrita para uma volta inteira."""

    DRY = "dry"
    LIGHT = "light_rain"
    HEAVY = "heavy_rain"


def _bounded(name: str, value: object, maximum: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or not 0 <= value <= maximum
    ):
        raise ValueError(f"{name} deve estar entre 0 e {maximum}")


@dataclass(frozen=True, slots=True)
class WeatherState:
    """Estado ao fim de uma volta: umidade relativa (%) e água (índice 0–1)."""

    humidity_pct: float
    surface_water: float

    def __post_init__(self) -> None:
        _bounded("humidity_pct", self.humidity_pct, 100)
        _bounded("surface_water", self.surface_water, 1)


@dataclass(frozen=True, slots=True)
class WeatherParameters:
    """Hipóteses por volta, independentes do tempo real e da taxa de desenho.

    A umidade se aproxima de um alvo por uma fração a cada volta. A água recebe
    o aporte da chuva e perde drenagem e evaporação; a evaporação é reduzida
    pela umidade calculada para a mesma volta. Todos os fluxos de água usam
    unidades do índice 0–1 por volta. Os valores não são calibrados.
    """

    dry_humidity_pct: float
    light_humidity_pct: float
    heavy_humidity_pct: float
    humidity_response_fraction: float
    light_water_gain_per_lap: float
    heavy_water_gain_per_lap: float
    drainage_per_lap: float
    evaporation_per_lap: float
    source_kind: Literal["assumed", "estimated"]
    parameter_version: str
    rationale: str
    #: Duração (min) da volta para a qual os fluxos acima foram escritos.
    reference_lap_minutes: float = 1.5

    def __post_init__(self) -> None:
        if (
            isinstance(self.reference_lap_minutes, bool)
            or not isfinite(self.reference_lap_minutes)
            or self.reference_lap_minutes <= 0
        ):
            raise ValueError("reference_lap_minutes deve ser positivo")
        for name in (
            "dry_humidity_pct",
            "light_humidity_pct",
            "heavy_humidity_pct",
        ):
            _bounded(name, getattr(self, name), 100)
        if not (
            self.dry_humidity_pct <= self.light_humidity_pct <= self.heavy_humidity_pct
        ):
            raise ValueError("alvos de umidade devem crescer com a chuva")
        for name in (
            "humidity_response_fraction",
            "light_water_gain_per_lap",
            "heavy_water_gain_per_lap",
            "drainage_per_lap",
            "evaporation_per_lap",
        ):
            _bounded(name, getattr(self, name), 1)
        if self.light_water_gain_per_lap > self.heavy_water_gain_per_lap:
            raise ValueError(
                "chuva intensa deve aportar pelo menos tanta água quanto leve"
            )
        if self.source_kind not in ("assumed", "estimated"):
            raise ValueError("source_kind deve ser 'assumed' ou 'estimated'")
        if (
            not isinstance(self.parameter_version, str)
            or not self.parameter_version.strip()
        ):
            raise ValueError("parameter_version deve ser não vazio")
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ValueError("rationale deve ser não vazio")


ASSUMED_WEATHER_PARAMETERS = WeatherParameters(
    dry_humidity_pct=50.0,
    light_humidity_pct=75.0,
    heavy_humidity_pct=90.0,
    humidity_response_fraction=0.25,
    light_water_gain_per_lap=0.12,
    heavy_water_gain_per_lap=0.30,
    drainage_per_lap=0.03,
    evaporation_per_lap=0.06,
    source_kind="assumed",
    parameter_version="assumed-weather-per-lap-v1",
    rationale=(
        "Valores ilustrativos para testar acúmulo e secagem; não são "
        "estimativas físicas ou coeficientes inferidos do FastF1."
    ),
)


@dataclass(frozen=True, slots=True)
class LapWeather:
    """Condição aplicada e estado resultante ao fim da volta numerada desde 1."""

    lap: int
    rain: RainLevel
    state: WeatherState


def step_weather(
    state: WeatherState,
    rain: RainLevel,
    parameters: WeatherParameters = ASSUMED_WEATHER_PARAMETERS,
    *,
    lap_minutes: float | None = None,
    evaporation_scale: float = 1.0,
) -> WeatherState:
    """Estado ao fim de uma volta de ``lap_minutes`` sob a chuva ``rain``.

    ``lap_minutes`` ``None`` vale uma volta de referência. Os fluxos de água
    escalam linearmente com a duração; a aproximação da umidade ao alvo, que é
    uma fração por volta, vira ``1 - (1 - f) ** escala`` para que duas voltas
    curtas equivalham a uma longa. ``evaporation_scale`` multiplica só a
    evaporação: é por onde a temperatura da pista acelera a secagem
    (``track_condition``).
    """

    if type(rain) is not RainLevel:
        raise ValueError(f"condição climática inválida: {rain!r}")
    scale = 1.0 if lap_minutes is None else lap_minutes / parameters.reference_lap_minutes
    if not isfinite(scale) or scale <= 0:
        raise ValueError("lap_minutes deve ser positivo")
    if not isfinite(evaporation_scale) or evaporation_scale < 0:
        raise ValueError("evaporation_scale nao pode ser negativo")
    targets = {
        RainLevel.DRY: parameters.dry_humidity_pct,
        RainLevel.LIGHT: parameters.light_humidity_pct,
        RainLevel.HEAVY: parameters.heavy_humidity_pct,
    }
    gains = {
        RainLevel.DRY: 0.0,
        RainLevel.LIGHT: parameters.light_water_gain_per_lap,
        RainLevel.HEAVY: parameters.heavy_water_gain_per_lap,
    }
    response = 1.0 - (1.0 - parameters.humidity_response_fraction) ** scale
    humidity = state.humidity_pct + response * (targets[rain] - state.humidity_pct)
    evaporation = (
        parameters.evaporation_per_lap * evaporation_scale * (1 - humidity / 100)
    )
    water = state.surface_water + scale * (
        gains[rain] - parameters.drainage_per_lap - evaporation
    )
    return WeatherState(
        humidity_pct=max(0.0, min(100.0, humidity)),
        surface_water=max(0.0, min(1.0, water)),
    )


def simulate_weather(
    conditions: Sequence[RainLevel],
    *,
    initial_state: WeatherState = WeatherState(50.0, 0.0),
    parameters: WeatherParameters = ASSUMED_WEATHER_PARAMETERS,
    lap_minutes: float | None = None,
) -> tuple[LapWeather, ...]:
    """Evolua uma volta por entrada, sem aleatoriedade nem dependências externas.

    ``initial_state`` é o estado antes da volta 1. Cada item retornado contém
    o estado após aplicar a condição daquela volta. Não converte rótulos de UI:
    a borda mapeia explicitamente esses rótulos para RainLevel.
    """

    if not conditions:
        raise ValueError("a sequência climática deve conter pelo menos uma volta")
    if not isinstance(initial_state, WeatherState):
        raise ValueError("initial_state deve ser WeatherState")
    if not isinstance(parameters, WeatherParameters):
        raise ValueError("parameters deve ser WeatherParameters")

    state = initial_state
    history: list[LapWeather] = []
    for lap, rain in enumerate(conditions, start=1):
        if type(rain) is not RainLevel:
            raise ValueError(f"condição climática inválida na volta {lap}: {rain!r}")
        state = step_weather(state, rain, parameters, lap_minutes=lap_minutes)
        history.append(LapWeather(lap=lap, rain=rain, state=state))
    return tuple(history)


@dataclass(frozen=True, slots=True)
class WeatherSegment:
    """Intervalo inclusivo de voltas com uma intensidade de chuva."""

    from_lap: int
    to_lap: int
    rain: RainLevel

    def __post_init__(self) -> None:
        if type(self.from_lap) is not int or type(self.to_lap) is not int:
            raise ValueError("from_lap e to_lap devem ser inteiros")
        if self.from_lap < 1 or self.to_lap < self.from_lap:
            raise ValueError("segmento inválido: exija 1 <= from_lap <= to_lap")
        if type(self.rain) is not RainLevel:
            raise ValueError("rain deve ser RainLevel")


def expand_segments(
    segments: Sequence[WeatherSegment],
    total_laps: int,
) -> tuple[RainLevel, ...]:
    """Expanda segmentos numa condição por volta; voltas não cobertas = seco.

    Segmentos sobrepostos (mesma volta em dois segmentos) são erro. Voltas além
    de ``total_laps`` em um segmento também. A ausência de cobertura vira ``dry``
    de forma explícita, nunca um estado indefinido.
    """

    if type(total_laps) is not int or total_laps < 1:
        raise ValueError("total_laps deve ser inteiro positivo")
    conditions = [RainLevel.DRY] * total_laps
    assigned = [False] * total_laps
    for segment in segments:
        if segment.to_lap > total_laps:
            raise ValueError(
                f"segmento {segment.from_lap}-{segment.to_lap} excede {total_laps} voltas"
            )
        for lap in range(segment.from_lap, segment.to_lap + 1):
            if assigned[lap - 1]:
                raise ValueError(f"volta {lap} coberta por mais de um segmento")
            assigned[lap - 1] = True
            conditions[lap - 1] = segment.rain
    return tuple(conditions)
