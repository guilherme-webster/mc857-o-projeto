"""Presentation state and validation for the race configuration screens."""

from __future__ import annotations

from dataclasses import dataclass


PRESET_OPTIONS = ("GP de São Paulo 2024",)
WEATHER_OPTIONS = ("Seco", "Chuva leve", "Chuva intensa")
MIN_LAPS = 1
MAX_LAPS = 200


class ConfigurationFormError(ValueError):
    """Raised when form values cannot create a valid scenario."""


@dataclass(frozen=True, slots=True)
class WeatherRange:
    """A contiguous inclusive range of laps with the same weather condition."""

    start_lap: int
    end_lap: int
    weather: str


@dataclass(frozen=True, slots=True)
class WeatherSchedule:
    """Weather selected for every lap of one configured race."""

    by_lap: tuple[str, ...]

    def __post_init__(self) -> None:
        """Require at least one lap and a known condition for every lap."""

        if not self.by_lap:
            raise ConfigurationFormError("o clima deve cobrir pelo menos uma volta")
        unknown = set(self.by_lap) - set(WEATHER_OPTIONS)
        if unknown:
            raise ConfigurationFormError("condição climática desconhecida")

    @classmethod
    def dry(cls, laps: int) -> WeatherSchedule:
        """Create a schedule with dry weather for all ``laps``."""

        _validate_laps(laps)
        return cls((WEATHER_OPTIONS[0],) * laps)

    @property
    def total_laps(self) -> int:
        """Return the number of configured laps."""

        return len(self.by_lap)

    def resize(self, laps: int) -> WeatherSchedule:
        """Preserve existing laps, truncate excess and add new laps as dry."""

        _validate_laps(laps)
        if laps <= self.total_laps:
            return WeatherSchedule(self.by_lap[:laps])
        missing = (WEATHER_OPTIONS[0],) * (laps - self.total_laps)
        return WeatherSchedule(self.by_lap + missing)

    def apply(self, start_lap: int, end_lap: int, weather: str) -> WeatherSchedule:
        """Return a copy with ``weather`` applied to an inclusive lap range."""

        if weather not in WEATHER_OPTIONS:
            raise ConfigurationFormError("condição climática desconhecida")
        if start_lap < 1 or end_lap > self.total_laps:
            raise ConfigurationFormError(
                f"as voltas devem estar entre 1 e {self.total_laps}"
            )
        if start_lap > end_lap:
            raise ConfigurationFormError(
                "a volta inicial não pode ser maior que a volta final"
            )
        updated = list(self.by_lap)
        updated[start_lap - 1 : end_lap] = (weather,) * (
            end_lap - start_lap + 1
        )
        return WeatherSchedule(tuple(updated))

    def apply_text(
        self, *, start_lap: str, end_lap: str, weather: str
    ) -> WeatherSchedule:
        """Parse interval text and apply its weather condition."""

        try:
            parsed_start = int(start_lap.strip())
            parsed_end = int(end_lap.strip())
        except ValueError as error:
            raise ConfigurationFormError(
                "as voltas inicial e final devem ser números inteiros"
            ) from error
        return self.apply(parsed_start, parsed_end, weather)

    def ranges(self) -> tuple[WeatherRange, ...]:
        """Compress the per-lap representation into contiguous ranges."""

        ranges: list[WeatherRange] = []
        start = 1
        current = self.by_lap[0]
        for lap, weather in enumerate(self.by_lap[1:], start=2):
            if weather == current:
                continue
            ranges.append(WeatherRange(start, lap - 1, current))
            start = lap
            current = weather
        ranges.append(WeatherRange(start, self.total_laps, current))
        return tuple(ranges)

    def summary(self) -> str:
        """Return one readable line per contiguous weather range."""

        return "\n".join(
            _format_weather_range(weather_range) for weather_range in self.ranges()
        )

    def compact_summary(self, maximum_ranges: int = 3) -> str:
        """Return a short summary suitable for the main configuration card."""

        ranges = self.ranges()
        visible = ranges[:maximum_ranges]
        lines = [_format_weather_range(weather_range) for weather_range in visible]
        if len(ranges) > maximum_ranges:
            lines.append(f"+ {len(ranges) - maximum_ranges} faixa(s)")
        return "\n".join(lines)


def _validate_laps(laps: int) -> None:
    """Validate the supported lap-count range shared by both screens."""

    if not MIN_LAPS <= laps <= MAX_LAPS:
        raise ConfigurationFormError(
            f"o número de voltas deve estar entre {MIN_LAPS} e {MAX_LAPS}"
        )


DEFAULT_WEATHER_SCHEDULE = WeatherSchedule.dry(69)


@dataclass(frozen=True, slots=True)
class ConfigurationFormData:
    """Validated values collected by the Arcade configuration flow."""

    preset: str = PRESET_OPTIONS[0]
    laps: int = 69
    weather_schedule: WeatherSchedule = DEFAULT_WEATHER_SCHEDULE

    def __post_init__(self) -> None:
        """Validate fields without depending on Arcade widgets."""

        if self.preset not in PRESET_OPTIONS:
            raise ConfigurationFormError("simulação pré-definida desconhecida")
        _validate_laps(self.laps)
        if self.weather_schedule.total_laps != self.laps:
            raise ConfigurationFormError(
                "o clima deve possuir uma condição para cada volta"
            )

    @classmethod
    def from_text(
        cls,
        *,
        preset: str,
        laps: str,
        weather_schedule: WeatherSchedule | None = None,
    ) -> ConfigurationFormData:
        """Parse widget text and preserve the configured weather where possible."""

        try:
            parsed_laps = int(laps.strip())
        except ValueError as error:
            raise ConfigurationFormError(
                "o número de voltas deve ser um número inteiro"
            ) from error
        _validate_laps(parsed_laps)
        schedule = weather_schedule or WeatherSchedule.dry(parsed_laps)
        return cls(
            preset=preset,
            laps=parsed_laps,
            weather_schedule=schedule.resize(parsed_laps),
        )

def _format_weather_range(weather_range: WeatherRange) -> str:
    """Format one inclusive interval without hiding single-lap ranges."""

    if weather_range.start_lap == weather_range.end_lap:
        laps = f"Volta {weather_range.start_lap}"
    else:
        laps = f"Voltas {weather_range.start_lap}–{weather_range.end_lap}"
    return f"{laps}: {weather_range.weather}"
