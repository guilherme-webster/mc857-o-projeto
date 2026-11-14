"""Consequências de um encontro físico; proximidade não é uma colisão.

Os limiares são hipóteses educacionais versionadas. A velocidade relevante é
a de aproximação entre os corpos, não a velocidade de um carro na pista.
Detecção geométrica e controle da trajetória pertencem ao integrador.
"""

from dataclasses import asdict, dataclass, field
from math import isfinite

from f1_simulator.domain.random_source import RandomSource


@dataclass(frozen=True, slots=True)
class ContactParameters:
    version: str = "spatial-contact-severity-assumed-v2"
    origin: str = "assumed"
    harmless_closing_ms: float = 2.0
    severe_closing_ms: float = 12.0
    damage_per_closing_ms: float = 0.025
    max_retirement_probability: float = 0.8
    maximum_speed_loss: float = 0.15
    episode_clearance_m: float = 0.5

    def __post_init__(self) -> None:
        for name in ("harmless_closing_ms", "severe_closing_ms", "damage_per_closing_ms",
                     "max_retirement_probability", "maximum_speed_loss", "episode_clearance_m"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} deve ser nao negativo e finito")
        if self.severe_closing_ms <= self.harmless_closing_ms:
            raise ValueError("impacto severo deve exceder o limite de toque leve")
        if self.max_retirement_probability > 1 or self.maximum_speed_loss > 1:
            raise ValueError("probabilidades e perdas devem estar em [0, 1]")

    def as_dict(self) -> dict:
        return asdict(self)


ASSUMED_CONTACT = ContactParameters()


@dataclass(slots=True)
class ContactTracker:
    """Memória por corrida: um impacto é avaliado uma vez até os corpos separarem."""

    active: set[tuple[str, str]] = field(default_factory=set)
    counts: dict[tuple[str, str], int] = field(default_factory=dict)

    def enter(self, pair: tuple[str, str]) -> int | None:
        if pair in self.active:
            return None
        self.active.add(pair)
        self.counts[pair] = self.counts.get(pair, 0) + 1
        return self.counts[pair]

    def retain(self, nearby: set[tuple[str, str]]) -> None:
        self.active.intersection_update(nearby)


@dataclass(frozen=True, slots=True)
class ContactConsequence:
    kind: str
    damage_fraction: float
    retirement_probability: float
    retires: bool


def contact_consequence(
    closing_speed_ms: float,
    aggression: float,
    rng: RandomSource | None,
    label: str,
    parameters: ContactParameters = ASSUMED_CONTACT,
) -> ContactConsequence:
    """Uma avaliação por episódio; toque leve nunca retira um carro.

    A agressividade modula a gravidade probabilística dentro de limites, sem
    transformar proximidade ou contato estacionário em abandono inevitável.
    A ausência de RNG permite executar a geometria sem acidentes sorteados.
    """
    if not isfinite(closing_speed_ms) or closing_speed_ms < 0:
        raise ValueError("velocidade de aproximacao invalida")
    if not isfinite(aggression) or aggression < 0:
        raise ValueError("agressividade invalida")
    excess = max(0.0, closing_speed_ms - parameters.harmless_closing_ms)
    if excess == 0:
        return ContactConsequence("touch", 0.0, 0.0, False)
    severity = min(1.0, excess / (parameters.severe_closing_ms - parameters.harmless_closing_ms))
    probability = min(parameters.max_retirement_probability,
                      parameters.max_retirement_probability * severity**2 * min(2.0, aggression))
    damage = min(1.0, excess * parameters.damage_per_closing_ms)
    retires = rng is not None and rng.uniform01(label) < probability
    return ContactConsequence("retirement" if retires else "damage", damage, probability, retires)
