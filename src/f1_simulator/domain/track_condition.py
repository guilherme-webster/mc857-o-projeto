"""Estado dinamico da pista por volta e a aderencia que ele permite (ADR 0015).

A pista muda durante a corrida por tres motivos, todos modelados aqui:

- **agua** (``weather.py``): a chuva acumula, a pista drena e evapora;
- **temperatura do asfalto**: a chuva esfria a pista, o sol a devolve ao
  patamar seco; pista quente seca mais rapido;
- **borracha**: o pelotao deposita borracha na trajetoria e a aderencia sobe
  ao longo da corrida; a chuva lava essa camada.

O resultado de cada volta e um ``grip_factor`` que multiplica o ``mu`` do carro
(:meth:`CarPhysics.with_grip`). O motor fisico transforma o fator em tempo pela
propria geometria: a mesma agua custa mais em Monaco, que vive de curvas
lentas, do que em Monza.

Agua e aderencia: esta camada descreve a aderencia **com o pneu adequado** a
cada nivel de agua (a envoltoria entre os compostos). Os pontos de ancoragem
sao a ordem de grandeza observada em corridas molhadas de 2023-2024: voltas de
intermediario ~11-16% mais lentas que as de slick na mesma corrida, e de pneu
de chuva ~25%. No motor calibrado, um fator 0,81 custa ~13% e 0,69 custa ~25%
na pista mediana. A escolha do composto, e o custo de usar o errado, ficam
para a camada de pneus.

Temperatura: nesta versao ela evolui e acelera a secagem, mas nao altera a
aderencia diretamente; o efeito sobre o pneu (janela de operacao) pertence a
camada de pneus.

Todos os parametros sao hipoteses (``assumed``): nenhum foi ajustado por
regressao, e a fonte das ancoragens de chuva ainda nao tem proveniencia
registrada no repositorio.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import exp, isfinite
from typing import Literal

from f1_simulator.domain.weather import (
    ASSUMED_WEATHER_PARAMETERS,
    RainLevel,
    WeatherParameters,
    WeatherState,
    step_weather,
)

#: Expoente que aproxima ``tempo(fator) / tempo(1) ~= fator ** -expoente`` na
#: pista mediana do calendario, medido com o carro calibrado (fatores 0,5-0,95
#: deram 0,58-0,63). So e usado quando a corrida nao tem geometria e o motor
#: fisico nao pode responder pela pista especifica.
GRIP_LAP_TIME_EXPONENT = 0.6


def _check_fraction(name: str, value: float, *, allow_zero: bool = True) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < 0
        or value > 1
        or (not allow_zero and value == 0)
    ):
        raise ValueError(f"{name} deve estar em [0, 1]")


@dataclass(frozen=True, slots=True)
class TrackConditionParameters:
    """Hipoteses de como agua, temperatura e borracha evoluem e viram aderencia.

    Agua: a aderencia com o pneu adequado cai linearmente de 1 (seco) ate
    ``damp_grip`` em ``damp_water`` (pista de intermediario) e dai ate
    ``saturated_grip`` com a pista saturada (pneu de chuva).

    Borracha: indice de 0 (pista verde) a 1 (trajetoria emborrachada). A
    corrida comeca em ``initial_rubber`` (o fim de semana ja emborrachou a
    pista); a cada volta o pelotao recupera ``rubber_gain_per_lap`` do que
    falta, e uma volta saturada remove ``rubber_wash_per_lap_saturated`` da
    camada. A pista verde tem ``green_track_grip_loss`` menos aderencia.

    Temperatura: o asfalto tende a ``dry_track_temp_c`` sem agua e esfria ate
    ``wet_cooling_c`` graus abaixo disso com a pista saturada, aproximando-se do
    alvo com constante de tempo ``1 / temp_response_per_min`` minutos. A
    evaporacao escala com ``1 + evaporation_per_degree * (T - 30)``.
    """

    damp_water: float = 0.3
    damp_grip: float = 0.81
    saturated_grip: float = 0.69
    initial_rubber: float = 0.8
    rubber_gain_per_lap: float = 0.08
    traffic_reference_cars: int = 20
    rubber_wash_per_lap_saturated: float = 0.3
    green_track_grip_loss: float = 0.03
    dry_track_temp_c: float = 35.0
    wet_cooling_c: float = 12.0
    temp_response_per_min: float = 0.1
    evaporation_per_degree: float = 0.03
    source_kind: Literal["assumed", "estimated"] = "assumed"
    parameter_version: str = "assumed-track-condition-v2"
    rationale: str = (
        "Hipoteses de ordem de grandeza. Agua: aderencia com o pneu adequado "
        "ancorada em voltas de intermediario ~11-16% e de chuva ~25% mais "
        "lentas que slick (corridas molhadas de 2023-2024, fonte sem "
        "proveniencia registrada). Borracha e temperatura nao foram medidas."
    )

    def __post_init__(self) -> None:
        _check_fraction("damp_water", self.damp_water, allow_zero=False)
        _check_fraction("damp_grip", self.damp_grip, allow_zero=False)
        _check_fraction("saturated_grip", self.saturated_grip, allow_zero=False)
        if self.damp_water >= 1:
            raise ValueError("damp_water deve ser menor que 1")
        if self.saturated_grip > self.damp_grip:
            raise ValueError("a pista saturada nao pode ter mais aderencia que a umida")
        for name in (
            "initial_rubber",
            "rubber_gain_per_lap",
            "rubber_wash_per_lap_saturated",
            "green_track_grip_loss",
        ):
            _check_fraction(name, getattr(self, name))
        for name in (
            "wet_cooling_c",
            "temp_response_per_min",
            "evaporation_per_degree",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} nao pode ser negativo")
        if (
            type(self.traffic_reference_cars) is not int
            or self.traffic_reference_cars < 1
        ):
            raise ValueError("traffic_reference_cars deve ser inteiro positivo")
        if not isfinite(self.dry_track_temp_c):
            raise ValueError("dry_track_temp_c deve ser finito")
        if self.source_kind not in ("assumed", "estimated"):
            raise ValueError("source_kind deve ser 'assumed' ou 'estimated'")
        if not self.parameter_version.strip() or not self.rationale.strip():
            raise ValueError("parameter_version e rationale sao obrigatorios")


ASSUMED_TRACK_CONDITION = TrackConditionParameters()


def water_grip_factor(
    surface_water: float, parameters: TrackConditionParameters = ASSUMED_TRACK_CONDITION
) -> float:
    """Aderencia com o pneu adequado ao nivel de agua (1 = seco)."""

    _check_fraction("surface_water", surface_water)
    if surface_water <= parameters.damp_water:
        share = surface_water / parameters.damp_water
        return 1.0 + share * (parameters.damp_grip - 1.0)
    share = (surface_water - parameters.damp_water) / (1.0 - parameters.damp_water)
    return parameters.damp_grip + share * (
        parameters.saturated_grip - parameters.damp_grip
    )


def rubber_grip_factor(
    rubber: float, parameters: TrackConditionParameters = ASSUMED_TRACK_CONDITION
) -> float:
    """Aderencia pela borracha na trajetoria (1 = totalmente emborrachada)."""

    _check_fraction("rubber", rubber)
    return 1.0 - parameters.green_track_grip_loss * (1.0 - rubber)


def approximate_lap_time_ratio(grip_factor: float) -> float:
    """``tempo(fator) / tempo(1)`` na pista mediana, para corridas sem geometria."""

    if isinstance(grip_factor, bool) or not isfinite(grip_factor) or grip_factor <= 0:
        raise ValueError("grip_factor deve ser positivo")
    return grip_factor**-GRIP_LAP_TIME_EXPONENT


@dataclass(frozen=True, slots=True)
class TrackState:
    """Pista ao fim da volta ``lap`` (numerada desde 1) e a aderencia resultante."""

    lap: int
    rain: RainLevel
    humidity_pct: float
    surface_water: float
    track_temp_c: float
    rubber: float
    grip_factor: float

    def as_dict(self) -> dict:
        return {
            "lap": self.lap,
            "rain": self.rain.value,
            "humidity_pct": round(self.humidity_pct, 1),
            "surface_water": round(self.surface_water, 3),
            "track_temp_c": round(self.track_temp_c, 1),
            "rubber": round(self.rubber, 3),
            "grip_factor": round(self.grip_factor, 4),
        }


# Temperaturas ilustrativas de asfalto seco, nao observacoes climaticas.
# IDs ausentes usam explicitamente o padrao global.
ASSUMED_CIRCUIT_TEMPERATURES_C = {
    "circuit:1": 32.0,
    "circuit:3": 28.0,
    "circuit:6": 35.0,
    "circuit:13": 27.0,
    "circuit:14": 36.0,
    "circuit:69": 42.0,
}
CIRCUIT_TEMPERATURE_VERSION = "assumed-circuit-track-temperature-v1"


def circuit_dry_temperature_c(circuit_id: str | None) -> float:
    """Alvo seco assumido por circuito, com reserva global para IDs ausentes."""
    return ASSUMED_CIRCUIT_TEMPERATURES_C.get(
        circuit_id, ASSUMED_TRACK_CONDITION.dry_track_temp_c
    )


def step_track_condition(
    state: TrackState,
    rain: RainLevel,
    *,
    elapsed_s: float,
    traffic_laps: float,
    dry_temp_c: float,
    parameters: TrackConditionParameters = ASSUMED_TRACK_CONDITION,
    weather_parameters: WeatherParameters = ASSUMED_WEATHER_PARAMETERS,
) -> TrackState:
    """Avance pelo tempo simulado e pelas voltas equivalentes de carros na pista.

    Uma volta de referencia de 20 carros deposita 8% da borracha faltante;
    trafego zero nao deposita. Lavagem depende do tempo e da agua, nao do grid.
    Passos pequenos permitem ao motor responder ao clima sem usar tempo de tela.
    """
    if not isfinite(elapsed_s) or elapsed_s <= 0:
        raise ValueError("elapsed_s deve ser positivo e finito")
    if not isfinite(traffic_laps) or traffic_laps < 0 or not isfinite(dry_temp_c):
        raise ValueError("trafego e temperatura invalidos")
    minutes = elapsed_s / 60.0
    evaporation = min(
        2.0,
        max(0.3, 1.0 + parameters.evaporation_per_degree * (state.track_temp_c - 30.0)),
    )
    weather = step_weather(
        WeatherState(state.humidity_pct, state.surface_water),
        rain,
        weather_parameters,
        lap_minutes=minutes,
        evaporation_scale=evaporation,
    )
    temp = state.track_temp_c + (
        1.0 - exp(-parameters.temp_response_per_min * minutes)
    ) * (
        dry_temp_c
        - parameters.wet_cooling_c * weather.surface_water
        - state.track_temp_c
    )
    gain = 1.0 - (1.0 - parameters.rubber_gain_per_lap) ** (
        traffic_laps / parameters.traffic_reference_cars
    )
    rubber = state.rubber + gain * (1.0 - state.rubber)
    wash = (1.0 - parameters.rubber_wash_per_lap_saturated) ** (
        weather.surface_water * minutes / weather_parameters.reference_lap_minutes
    )
    rubber *= wash
    return TrackState(
        state.lap,
        rain,
        weather.humidity_pct,
        weather.surface_water,
        temp,
        rubber,
        water_grip_factor(weather.surface_water, parameters)
        * rubber_grip_factor(rubber, parameters),
    )


def simulate_track_conditions(
    conditions: Sequence[RainLevel],
    *,
    lap_minutes: float | None = None,
    weather_parameters: WeatherParameters = ASSUMED_WEATHER_PARAMETERS,
    parameters: TrackConditionParameters = ASSUMED_TRACK_CONDITION,
    initial_weather: WeatherState = WeatherState(50.0, 0.0),
    initial_track_temp_c: float | None = None,
) -> tuple[TrackState, ...]:
    """Evolua agua, temperatura e borracha volta a volta, sem aleatoriedade.

    ``lap_minutes`` e a duracao tipica de uma volta da pista (``None`` usa a
    volta de referencia do clima). A ordem dentro de cada volta e fixa: a
    temperatura do inicio da volta define a evaporacao; depois a agua evolui,
    a temperatura se aproxima do novo alvo e a borracha ganha a volta do
    pelotao e perde o que a agua lavou.
    """

    if not conditions:
        raise ValueError("a sequencia climatica deve conter pelo menos uma volta")
    minutes = (
        weather_parameters.reference_lap_minutes if lap_minutes is None else lap_minutes
    )
    if isinstance(minutes, bool) or not isfinite(minutes) or minutes <= 0:
        raise ValueError("lap_minutes deve ser positivo")

    weather = initial_weather
    temp = (
        parameters.dry_track_temp_c
        if initial_track_temp_c is None
        else float(initial_track_temp_c)
    )
    rubber = parameters.initial_rubber
    relax = 1.0 - exp(-parameters.temp_response_per_min * minutes)
    states = []
    for lap, rain in enumerate(conditions, start=1):
        evaporation_scale = min(
            2.0, max(0.3, 1.0 + parameters.evaporation_per_degree * (temp - 30.0))
        )
        weather = step_weather(
            weather,
            rain,
            weather_parameters,
            lap_minutes=minutes,
            evaporation_scale=evaporation_scale,
        )
        water = weather.surface_water
        target = parameters.dry_track_temp_c - parameters.wet_cooling_c * water
        temp += relax * (target - temp)
        rubber += parameters.rubber_gain_per_lap * (1.0 - rubber)
        rubber *= 1.0 - parameters.rubber_wash_per_lap_saturated * water
        grip = water_grip_factor(water, parameters) * rubber_grip_factor(
            rubber, parameters
        )
        states.append(
            TrackState(
                lap=lap,
                rain=rain,
                humidity_pct=weather.humidity_pct,
                surface_water=water,
                track_temp_c=temp,
                rubber=rubber,
                grip_factor=grip,
            )
        )
    return tuple(states)
