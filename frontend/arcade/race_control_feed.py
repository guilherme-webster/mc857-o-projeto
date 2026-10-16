"""Estado da pista e mensagens de controle de prova para a TrackView.

Traduz ``race_control_by_lap`` e ``race_control_events`` do motor detalhado em
um rotulo de status por volta e em mensagens curtas em portugues. Nao importa o
Arcade: cores e posicoes na tela ficam com a view.

Convencao temporal do motor (``domain/race_control.py``):

- ``race_control_by_lap[lap]`` e o estado *aplicado durante* a volta ``lap``;
- um evento com ``lap = L`` acontece *ao fim* da volta ``L``: o incidente e
  sorteado depois de contabilizar a volta, e a resposta passa a valer na
  volta ``L + 1``.

Por isso a view consulta o status pela volta em andamento do lider e revela um
evento quando o lider completa a volta do evento. O controle de prova do motor
e global (nao ha setores), e a faixa tambem e: carros que ainda fecham a volta
do incidente ja aparecem sob a nova bandeira.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

STATUS_LABELS = {
    "GREEN": "BANDEIRA VERDE",
    "YELLOW": "BANDEIRA AMARELA",
    "VSC": "VSC",
    "SC": "SAFETY CAR",
    "RED": "BANDEIRA VERMELHA",
}
RESTART_LABEL = "RELARGADA"

_STATUS_NAMES = {
    "YELLOW": "Bandeira amarela",
    "VSC": "VSC",
    "SC": "Safety car",
    "RED": "Bandeira vermelha",
}
_ENDED = {
    "YELLOW": "Fim da bandeira amarela",
    "VSC": "Fim do VSC",
    "SC": "Safety car recolhido",
    "RED": "Fim da bandeira vermelha",
}


@dataclass(frozen=True, slots=True)
class TrackStatus:
    """Estado da pista numa volta; ``restart`` marca a volta de relargada."""

    status: str
    restart: bool

    @property
    def label(self) -> str:
        if self.restart and self.status == "GREEN":
            return RESTART_LABEL
        return STATUS_LABELS.get(self.status, self.status)


@dataclass(frozen=True, slots=True)
class FeedEntry:
    """Mensagem do controle de prova; ``status`` orienta a cor, se houver."""

    lap: int
    text: str
    status: str | None


class RaceControlFeed:
    """Consulta por volta do controle de prova de uma corrida simulada.

    Corridas sem ``race_control_by_lap`` ou ``race_control_events`` (o motor
    detalhado sempre os produz) ficam sem faixa e sem mensagens: a ausencia e
    mostrada como ausencia, nunca como bandeira verde inventada.
    """

    def __init__(self, race: Mapping[str, object], names: Mapping[str, str]) -> None:
        self._names = names
        self._by_lap: dict[int, TrackStatus] = {}
        for item in _sequence(race.get("race_control_by_lap")):
            try:
                lap = int(item["lap"])
                status = str(item["status"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    f"race_control_by_lap malformado: {error!r}"
                ) from error
            self._by_lap[lap] = TrackStatus(status, bool(item.get("restart_lap")))

        self._entries: list[FeedEntry] = []
        for event in _sequence(race.get("race_control_events")):
            entry = self._describe(event)
            if entry is not None:
                self._entries.append(entry)

    def status_on_lap(self, lap: int) -> TrackStatus | None:
        return self._by_lap.get(lap)

    def entries_through(self, laps_completed: float) -> list[FeedEntry]:
        """Mensagens das voltas ja completadas, em ordem cronologica."""

        return [entry for entry in self._entries if entry.lap <= laps_completed]

    def _describe(self, event: object) -> FeedEntry | None:
        if not isinstance(event, Mapping):
            raise ValueError("evento de controle de prova malformado")
        try:
            lap = int(event["lap"])
            kind = str(event["type"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"evento de controle de prova malformado: {error!r}"
            ) from error

        status = event.get("status")
        status = str(status) if status is not None else None
        name = _STATUS_NAMES.get(status or "", status)
        duration = event.get("duration_laps")
        if kind == "incident_response":
            # A resposta pedida por cada incidente pode ser superada por outra
            # mais grave na mesma volta; a efetiva vem no evento de transicao.
            return FeedEntry(lap, self._incident_text(event.get("cause")), None)
        if kind == "race_control_started":
            return FeedEntry(lap, f"{name}{_laps(duration)}", status)
        if kind == "race_control_escalated":
            return FeedEntry(lap, f"Escalado: {name}{_laps(duration)}", status)
        if kind == "race_control_extended":
            return FeedEntry(lap, f"Prorrogado: {name}{_laps(duration)}", status)
        if kind == "race_control_ended":
            return FeedEntry(lap, _ENDED.get(status or "", f"Fim de {status}"), None)
        if kind == "restart_scheduled":
            return FeedEntry(lap, f"Relargada na volta {lap + 1}", "GREEN")
        # Tipo novo do motor: mostrar cru e melhor que esconder.
        return FeedEntry(lap, kind, status)

    def _incident_text(self, cause: object) -> str:
        if not isinstance(cause, Mapping):
            return "Incidente"
        drivers = [
            self._names.get(str(driver_id), str(driver_id))
            for driver_id in _sequence(cause.get("driver_ids"))
        ]
        kind = cause.get("kind")
        if kind == "contact":
            return f"Contato: {' x '.join(drivers)}"
        if kind == "solo_crash":
            return f"Batida: {', '.join(drivers)}"
        if kind == "mechanical":
            return f"Quebra: {', '.join(drivers)}"
        return f"Incidente ({kind}): {', '.join(drivers)}"


def _sequence(value: object) -> Sequence:
    if value is None:
        return ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    raise ValueError("campo de controle de prova deveria ser uma lista")


def _laps(duration: object) -> str:
    if not isinstance(duration, int) or isinstance(duration, bool):
        return ""
    return f" ({duration} volta{'s' if duration != 1 else ''})"
