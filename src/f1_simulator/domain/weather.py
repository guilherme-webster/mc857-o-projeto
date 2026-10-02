"""Evolução determinística do clima e da água superficial, por volta.

As intensidades são entradas do cenário, não observações inferidas do FastF1.
O índice de água é adimensional (0 = seco, 1 = saturado); não representa
milímetros de precipitação nem um coeficiente físico de aderência. Este módulo
não altera tempos de volta, pneus ou resultados de corrida.
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

    def __post_init__(self) -> None:
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


def simulate_weather(
    conditions: Sequence[RainLevel],
    *,
    initial_state: WeatherState = WeatherState(50.0, 0.0),
    parameters: WeatherParameters = ASSUMED_WEATHER_PARAMETERS,
) -> tuple[LapWeather, ...]:
    """Evolua uma volta por entrada, sem aleatoriedade nem dependências externas.

    ``initial_state`` é o estado antes da volta 1. Cada item retornado contém
    o estado após aplicar a condição daquela volta. Não converte rótulos de UI:
    a futura borda deverá mapear explicitamente esses rótulos para RainLevel.
    """

    if not conditions:
        raise ValueError("a sequência climática deve conter pelo menos uma volta")
    if not isinstance(initial_state, WeatherState):
        raise ValueError("initial_state deve ser WeatherState")
    if not isinstance(parameters, WeatherParameters):
        raise ValueError("parameters deve ser WeatherParameters")

    state = initial_state
    history: list[LapWeather] = []
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
    for lap, rain in enumerate(conditions, start=1):
        if type(rain) is not RainLevel:
            raise ValueError(f"condição climática inválida na volta {lap}: {rain!r}")
        humidity = state.humidity_pct + parameters.humidity_response_fraction * (
            targets[rain] - state.humidity_pct
        )
        evaporation = parameters.evaporation_per_lap * (1 - humidity / 100)
        water = (
            state.surface_water
            + gains[rain]
            - parameters.drainage_per_lap
            - evaporation
        )
        state = WeatherState(
            humidity_pct=max(0.0, min(100.0, humidity)),
            surface_water=max(0.0, min(1.0, water)),
        )
        history.append(LapWeather(lap=lap, rain=rain, state=state))
    return tuple(history)
