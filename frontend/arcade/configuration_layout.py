"""Layout specification shared by the Arcade configuration screen and tests.

Coordinates use Arcade's usual bottom-left origin. This module contains no
rendering calls so geometry remains testable without a window or OpenGL.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Bounds:
    """A rectangular area in pixels, measured from the screen's bottom-left."""

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        """Reject rectangles without a visible positive area."""

        if self.x < 0 or self.y < 0:
            raise ValueError("layout coordinates must be non-negative")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("layout bounds must have positive dimensions")

    @property
    def right(self) -> int:
        """Return the horizontal coordinate immediately after this rectangle."""

        return self.x + self.width

    @property
    def top(self) -> int:
        """Return the vertical coordinate immediately after this rectangle."""

        return self.y + self.height

    def contains(self, other: Bounds) -> bool:
        """Return whether ``other`` is completely inside this rectangle."""

        return (
            self.x <= other.x
            and self.y <= other.y
            and other.right <= self.right
            and other.top <= self.top
        )

    def overlaps(self, other: Bounds) -> bool:
        """Return whether this rectangle shares visible area with ``other``."""

        return not (
            self.right <= other.x
            or other.right <= self.x
            or self.top <= other.y
            or other.top <= self.y
        )


@dataclass(frozen=True, slots=True)
class Panel:
    """A titled visual group used to organize configuration controls."""

    identifier: str
    title: str
    bounds: Bounds


@dataclass(frozen=True, slots=True)
class Control:
    """One visible field or action, ready for a future Arcade renderer."""

    identifier: str
    label: str
    value: str
    kind: str
    editable: bool
    bounds: Bounds


@dataclass(frozen=True, slots=True)
class ConfigurationScreenLayout:
    """The complete static first layout for the race configuration screen."""

    screen: Bounds
    title: str
    subtitle: str
    panels: tuple[Panel, ...]
    controls: tuple[Control, ...]

    def validate(self) -> None:
        """Check that controls stay in the screen and panels do not overlap."""

        for panel in self.panels:
            if not self.screen.contains(panel.bounds):
                raise ValueError(f"panel outside screen: {panel.identifier}")
        for control in self.controls:
            if not self.screen.contains(control.bounds):
                raise ValueError(f"control outside screen: {control.identifier}")
        for index, panel in enumerate(self.panels):
            for other in self.panels[index + 1 :]:
                if panel.bounds.overlaps(other.bounds):
                    raise ValueError(
                        f"panels overlap: {panel.identifier} and {other.identifier}"
                    )


def build_initial_configuration_layout() -> ConfigurationScreenLayout:
    """Build the first 1280×720 configuration-screen wireframe.

    The historical values mirror the versioned test sample for race 1141. The
    lap count and weather schedule are scenario parameters; they do not rewrite
    canonical ETL data.
    """

    layout = ConfigurationScreenLayout(
        screen=Bounds(0, 0, 1280, 720),
        title="Simulador de Corrida de Fórmula 1",
        subtitle="Configure o cenário antes de iniciar a simulação",
        panels=(
            Panel("reference", "Dados de referência", Bounds(48, 248, 352, 300)),
            Panel("scenario", "Parâmetros da simulação", Bounds(424, 248, 352, 300)),
            Panel("summary", "Resumo do cenário", Bounds(800, 248, 432, 300)),
        ),
        controls=(
            Control(
                "preset",
                "Simulação pré-definida",
                "GP de São Paulo 2024",
                "select",
                True,
                Bounds(48, 592, 1184, 56),
            ),
            Control(
                "reference_race",
                "Corrida histórica",
                "São Paulo Grand Prix 2024",
                "read_only",
                False,
                Bounds(72, 460, 304, 44),
            ),
            Control(
                "reference_circuit",
                "Circuito",
                "Autódromo José Carlos Pace",
                "read_only",
                False,
                Bounds(72, 392, 304, 44),
            ),
            Control(
                "reference_entries",
                "Pilotos disponíveis",
                "Dados do ETL",
                "read_only",
                False,
                Bounds(72, 324, 304, 44),
            ),
            Control(
                "laps",
                "Número de voltas",
                "69",
                "number",
                True,
                Bounds(448, 460, 304, 44),
            ),
            Control(
                "weather_schedule",
                "Clima por volta",
                "Configurar clima por volta",
                "button",
                True,
                Bounds(448, 360, 304, 56),
            ),
            Control(
                "weather_summary",
                "Clima configurado",
                "Voltas 1–69: Seco",
                "dynamic_read_only",
                False,
                Bounds(824, 460, 384, 44),
            ),
            Control(
                "strategy_summary",
                "Estratégia",
                "Será configurada no próximo incremento",
                "read_only",
                False,
                Bounds(824, 324, 384, 44),
            ),
            Control(
                "start_simulation",
                "Iniciar simulação",
                "Iniciar",
                "button",
                True,
                Bounds(1016, 128, 216, 56),
            ),
            Control(
                "reset_configuration",
                "Restaurar configuração",
                "Restaurar",
                "button",
                True,
                Bounds(776, 128, 216, 56),
            ),
        ),
    )
    layout.validate()
    return layout
