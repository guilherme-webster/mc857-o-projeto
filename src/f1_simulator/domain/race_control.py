"""Controle de prova heuristico, puro e avancado uma volta por vez.

Referencia resumida (PRD 4.4.1): uma amarela real e local; o VSC reduz o
ritmo em cerca de 30--40% sem apagar intervalos; o SC agrupa o pelotao; e a
bandeira vermelha interrompe a prova, permite troca de pneus e precede uma
relargada controlada. Este modelo nao tem setores, por isso representa a
amarela como um efeito global leve, com ultrapassagens apenas reduzidas. Nao
modela bandeira laranja, amarela dupla nem desdobramento de retardatarios.

``step`` recebe os incidentes ocorridos em ``lap`` e devolve o estado que vale
para a volta seguinte. Logo, ``duration_laps`` conta voltas futuras completas
sob a intervencao; esta convencao evita que a ordem do laco do motor altere a
duracao. Incidentes na mesma volta sao ordenados canonicamente por tipo e IDs.
Para cada batida, sorteia-se gravidade, depois resposta quando nao for grave e,
por ultimo, duracao quando aplicavel. Para falha mecanica, sorteiam-se resposta
e eventual duracao. Nenhum sorteio ocorre quando nao ha incidentes.

Sob uma neutralizacao, uma resposta mais grave a substitui; uma resposta igual
renova o fim para o mais distante entre o prazo restante e a nova duracao; uma
resposta menos grave nao encurta o estado vigente. Assim, um incidente sob VSC
pode escalar para SC, mas nao reinicia ingenuamente toda neutralizacao.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isclose, isfinite
from typing import Literal, TypeAlias

from f1_simulator.domain.random_source import RandomSource


IncidentKind: TypeAlias = Literal["contact", "solo_crash", "mechanical"]
RaceControlEvent: TypeAlias = dict[str, object]


class RaceStatus(StrEnum):
    """Estado global da pista aplicavel a uma volta da corrida."""

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    VSC = "VSC"
    SC = "SC"
    RED = "RED"


GREEN = RaceStatus.GREEN
YELLOW = RaceStatus.YELLOW
VSC = RaceStatus.VSC
SC = RaceStatus.SC
RED = RaceStatus.RED
"""Aliases publicos preservam a linguagem curta usada pelo motor e pelo PRD."""


_ACTIVE_STATUSES = frozenset((YELLOW, VSC, SC, RED))
_STATUS_PRIORITY = {YELLOW: 1, VSC: 2, SC: 3, RED: 4}
_INCIDENT_KIND_ORDER = {"contact": 0, "solo_crash": 1, "mechanical": 2}


def _probability(value: float, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or not 0.0 <= value <= 1.0
    ):
        raise ValueError(f"{name} deve ser uma probabilidade finita em [0, 1]")


def _non_negative(value: float, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < 0.0
    ):
        raise ValueError(f"{name} deve ser um numero nao negativo e finito")


def _positive(value: float, name: str) -> None:
    _non_negative(value, name)
    if value == 0.0:
        raise ValueError(f"{name} deve ser positivo")


@dataclass(frozen=True, slots=True)
class Incident:
    """Ocorrencia capaz de pedir uma intervencao do controle de prova.

    ``driver_ids`` registra todos os envolvidos conhecidos, sem atribuir culpa.
    A tupla e nao vazia e nao admite repeticao, mas sua cardinalidade nao e
    imposta: o motor pode conhecer apenas o carro retirado de um contato ou
    mais de dois envolvidos em um acidente.
    """

    lap: int
    kind: IncidentKind
    driver_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.lap) is not int or self.lap < 1:
            raise ValueError("lap deve ser um inteiro positivo")
        if self.kind not in _INCIDENT_KIND_ORDER:
            raise ValueError(
                "kind deve ser 'contact', 'solo_crash' ou 'mechanical'"
            )
        if not isinstance(self.driver_ids, tuple) or not self.driver_ids:
            raise ValueError("driver_ids deve ser uma tupla nao vazia")
        if any(not isinstance(item, str) or not item.strip() for item in self.driver_ids):
            raise ValueError("driver_ids deve conter strings nao vazias")
        if len(set(self.driver_ids)) != len(self.driver_ids):
            raise ValueError("driver_ids nao deve conter repeticoes")


@dataclass(frozen=True, slots=True)
class RaceControlParameters:
    """Coeficientes heurísticos e versionados do controle de prova.

    As probabilidades de SC, VSC e amarela para batidas sao condicionais a
    batida nao ter sido classificada como grave. Elas somam um. As tres
    respostas mecanicas tambem somam um e incluem explicitamente a ausencia de
    intervencao, para que um carro recolhido em local seguro nao invente uma
    bandeira.

    Todos os fatores que alteram o motor ficam neste contrato, inclusive os
    multiplicadores da primeira volta e da relargada. Isso permite que a fatia
    de integracao ajuste frequencias sem esconder numeros em condicionais.
    """

    crash_red_probability: float = 0.10
    crash_sc_probability: float = 0.33
    crash_vsc_probability: float = 0.17
    crash_yellow_probability: float = 0.50
    mechanical_no_intervention_probability: float = 0.65
    mechanical_yellow_probability: float = 0.25
    mechanical_vsc_probability: float = 0.10
    yellow_duration_laps: int = 1
    vsc_min_duration_laps: int = 1
    vsc_max_duration_laps: int = 3
    sc_min_duration_laps: int = 3
    sc_max_duration_laps: int = 5
    red_duration_laps: int = 1
    vsc_lap_time_factor: float = 1.40
    sc_lap_time_factor: float = 1.60
    yellow_overtake_factor: float = 0.50
    yellow_lap_time_loss_ms: float = 300.0
    restart_overtake_factor: float = 1.35
    restart_contact_factor: float = 1.50
    sc_pit_loss_factor: float = 0.50
    vsc_pit_loss_factor: float = 0.70
    solo_crash_probability_per_car_lap: float = 0.00005
    first_lap_solo_crash_multiplier: float = 3.0
    restart_solo_crash_multiplier: float = 2.0
    neutralized_solo_crash_multiplier: float = 0.25
    origin: Literal["heuristic"] = "heuristic"
    parameter_version: str = "heuristic-race-control-v2"
    rationale: str = (
        "Hipotese heuristica, nao calibrada. A v1 gerava 1,13 neutralizacao "
        "(SC+VSC) por corrida. A v2 reduz a chance de uma batida neutralizar a "
        "prova sem inverter a proporcao real (batida com detritos leva mais a SC "
        "que a VSC): vermelha 10% das batidas (teto aprovado no PRD 4.4.2); "
        "nas demais, SC 33%, VSC 17%, "
        "amarela 50%; abandono mecanico sem intervencao 65%, amarela 25%, VSC "
        "10%. Alvo do PRD 4.4.2: ~0,6 SC+VSC e ~1 vermelha a cada 6 corridas. "
        "Medido com race_control_frequency.py, 200 corridas por semente "
        "(67202, 1, 2026): 0,58-0,66 SC+VSC e 0,08-0,09 vermelha por corrida "
        "(cerca de 1 a cada 11-12). Atingir 1 a cada 6 exigiria ~15% de "
        "batidas graves, acima do teto aprovado; decisao pendente."
    )

    def __post_init__(self) -> None:
        probability_names = (
            "crash_red_probability",
            "crash_sc_probability",
            "crash_vsc_probability",
            "crash_yellow_probability",
            "mechanical_no_intervention_probability",
            "mechanical_yellow_probability",
            "mechanical_vsc_probability",
            "solo_crash_probability_per_car_lap",
        )
        for name in probability_names:
            _probability(getattr(self, name), name)

        crash_conditional_total = (
            self.crash_sc_probability
            + self.crash_vsc_probability
            + self.crash_yellow_probability
        )
        if not isclose(crash_conditional_total, 1.0, abs_tol=1e-12):
            raise ValueError(
                "probabilidades condicionais de batida devem somar 1"
            )
        mechanical_total = (
            self.mechanical_no_intervention_probability
            + self.mechanical_yellow_probability
            + self.mechanical_vsc_probability
        )
        if not isclose(mechanical_total, 1.0, abs_tol=1e-12):
            raise ValueError("probabilidades de falha mecanica devem somar 1")

        duration_names = (
            "yellow_duration_laps",
            "vsc_min_duration_laps",
            "vsc_max_duration_laps",
            "sc_min_duration_laps",
            "sc_max_duration_laps",
            "red_duration_laps",
        )
        for name in duration_names:
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} deve ser um inteiro positivo")
        if self.vsc_min_duration_laps > self.vsc_max_duration_laps:
            raise ValueError("duracao minima do VSC nao pode exceder a maxima")
        if self.sc_min_duration_laps > self.sc_max_duration_laps:
            raise ValueError("duracao minima do SC nao pode exceder a maxima")

        positive_names = (
            "vsc_lap_time_factor",
            "sc_lap_time_factor",
            "restart_overtake_factor",
            "restart_contact_factor",
            "first_lap_solo_crash_multiplier",
            "restart_solo_crash_multiplier",
        )
        for name in positive_names:
            _positive(getattr(self, name), name)
        for name in ("vsc_lap_time_factor", "sc_lap_time_factor"):
            if getattr(self, name) < 1.0:
                raise ValueError(f"{name} nao pode acelerar a volta")
        for name in ("restart_overtake_factor", "restart_contact_factor"):
            if getattr(self, name) <= 1.0:
                raise ValueError(f"{name} deve aumentar o efeito na relargada")
        for name in (
            "first_lap_solo_crash_multiplier",
            "restart_solo_crash_multiplier",
        ):
            if getattr(self, name) <= 1.0:
                raise ValueError(f"{name} deve aumentar o risco base")
        non_negative_names = (
            "yellow_overtake_factor",
            "yellow_lap_time_loss_ms",
            "sc_pit_loss_factor",
            "vsc_pit_loss_factor",
            "neutralized_solo_crash_multiplier",
        )
        for name in non_negative_names:
            _non_negative(getattr(self, name), name)
        if self.yellow_overtake_factor > 1.0:
            raise ValueError("yellow_overtake_factor deve estar em [0, 1]")
        for name in ("sc_pit_loss_factor", "vsc_pit_loss_factor"):
            if getattr(self, name) > 1.0:
                raise ValueError(f"{name} deve estar em [0, 1]")

        largest_state_multiplier = max(
            1.0,
            self.restart_solo_crash_multiplier,
            self.neutralized_solo_crash_multiplier,
        )
        largest_solo_probability = (
            self.solo_crash_probability_per_car_lap
            * self.first_lap_solo_crash_multiplier
            * largest_state_multiplier
        )
        if largest_solo_probability > 1.0:
            raise ValueError(
                "probabilidade de acidente individual pode exceder 1"
            )
        if self.origin != "heuristic":
            raise ValueError("origin deve ser 'heuristic'")
        for name in ("parameter_version", "rationale"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} deve ser uma string nao vazia")


HEURISTIC_RACE_CONTROL = RaceControlParameters()
"""Conjunto inicial assumido; a versao identifica qualquer ajuste futuro."""


@dataclass(frozen=True, slots=True)
class RaceControlState:
    """Estado que sera aplicado na proxima volta do motor.

    ``restart_lap`` so existe em pista verde. ``restart_source`` distingue a
    relargada pos-vermelha, que ainda precisa comprimir o pelotao, daquela apos
    SC, cujo pelotao ja foi agrupado durante a neutralizacao.
    """

    status: RaceStatus = GREEN
    laps_remaining: int = 0
    cause: Incident | None = None
    restart_lap: bool = False
    restart_source: RaceStatus | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, RaceStatus):
            raise ValueError("status deve ser RaceStatus")
        if type(self.laps_remaining) is not int or self.laps_remaining < 0:
            raise ValueError("laps_remaining deve ser um inteiro nao negativo")
        if not isinstance(self.restart_lap, bool):
            raise ValueError("restart_lap deve ser bool")

        if self.status == GREEN:
            if self.laps_remaining != 0 or self.cause is not None:
                raise ValueError(
                    "estado GREEN nao pode ter duracao restante nem causa ativa"
                )
            if self.restart_lap:
                if self.restart_source not in (SC, RED):
                    raise ValueError("relargada deve declarar origem SC ou RED")
            elif self.restart_source is not None:
                raise ValueError("restart_source exige restart_lap=True")
            return

        if self.status not in _ACTIVE_STATUSES:
            raise ValueError("status de controle de prova desconhecido")
        if self.laps_remaining < 1:
            raise ValueError("estado ativo exige ao menos uma volta restante")
        if not isinstance(self.cause, Incident):
            raise ValueError("estado ativo exige um Incident como causa")
        if self.restart_lap or self.restart_source is not None:
            raise ValueError("estado ativo nao pode ser simultaneamente relargada")


@dataclass(frozen=True, slots=True)
class LapEffects:
    """Modificadores que a integracao aplica uniformemente na volta.

    ``lap_time_factor`` e multiplicativo; ``lap_time_loss_ms`` e aditivo e
    existe para a perda de poucos decimos da amarela. ``neutralized`` cobre
    VSC, SC e vermelha, mas nao a amarela local aproximada. Bandeira azul nao e
    um estado global: a fatia 5 deve fazer o retardatario ceder antes de criar
    uma disputa, portanto sem sorteio de ultrapassagem ou contato nesse par.
    """

    lap_time_factor: float
    lap_time_loss_ms: float
    disputes_enabled: bool
    overtake_factor: float
    contact_factor: float
    compress_field: bool
    freeze_order: bool
    pit_loss_factor: float
    free_tyre_change: bool
    neutralized: bool
    solo_crash_multiplier: float

    def __post_init__(self) -> None:
        _positive(self.lap_time_factor, "lap_time_factor")
        for name in (
            "lap_time_loss_ms",
            "overtake_factor",
            "contact_factor",
            "pit_loss_factor",
            "solo_crash_multiplier",
        ):
            _non_negative(getattr(self, name), name)
        for name in (
            "disputes_enabled",
            "compress_field",
            "freeze_order",
            "free_tyre_change",
            "neutralized",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} deve ser bool")


@dataclass(frozen=True, slots=True)
class _RequestedResponse:
    """Resposta intermediaria; nunca atravessa a fronteira publica do modulo."""

    status: RaceStatus | None
    duration_laps: int | None
    cause: Incident


def effects(
    state: RaceControlState,
    params: RaceControlParameters = HEURISTIC_RACE_CONTROL,
) -> LapEffects:
    """Converta o estado global nos modificadores da volta correspondente."""

    if state.status == GREEN:
        if state.restart_lap:
            return LapEffects(
                lap_time_factor=1.0,
                lap_time_loss_ms=0.0,
                disputes_enabled=True,
                overtake_factor=params.restart_overtake_factor,
                contact_factor=params.restart_contact_factor,
                compress_field=state.restart_source == RED,
                freeze_order=False,
                pit_loss_factor=1.0,
                free_tyre_change=False,
                neutralized=False,
                solo_crash_multiplier=params.restart_solo_crash_multiplier,
            )
        return _neutral_effects()

    if state.status == YELLOW:
        return LapEffects(
            lap_time_factor=1.0,
            lap_time_loss_ms=params.yellow_lap_time_loss_ms,
            disputes_enabled=True,
            overtake_factor=params.yellow_overtake_factor,
            contact_factor=1.0,
            compress_field=False,
            freeze_order=False,
            pit_loss_factor=1.0,
            free_tyre_change=False,
            neutralized=False,
            solo_crash_multiplier=1.0,
        )
    if state.status == VSC:
        return _neutralized_effects(
            lap_time_factor=params.vsc_lap_time_factor,
            pit_loss_factor=params.vsc_pit_loss_factor,
            compress_field=False,
            freeze_order=False,
            free_tyre_change=False,
            solo_crash_multiplier=params.neutralized_solo_crash_multiplier,
        )
    if state.status == SC:
        return _neutralized_effects(
            lap_time_factor=params.sc_lap_time_factor,
            pit_loss_factor=params.sc_pit_loss_factor,
            compress_field=True,
            freeze_order=False,
            free_tyre_change=False,
            solo_crash_multiplier=params.neutralized_solo_crash_multiplier,
        )
    return _neutralized_effects(
        lap_time_factor=1.0,
        pit_loss_factor=0.0,
        compress_field=False,
        freeze_order=True,
        free_tyre_change=True,
        solo_crash_multiplier=0.0,
    )


def solo_crash_probability(
    lap: int,
    lap_effects: LapEffects,
    params: RaceControlParameters = HEURISTIC_RACE_CONTROL,
) -> float:
    """Calcule a chance por carro da volta, sem realizar o sorteio.

    O chamador sorteia os carros em ordem canonica e cria um ``Incident`` para
    cada sucesso. Separar calculo e sorteio mantem este automato independente
    da quantidade de carros e torna a sequencia do motor auditavel.
    """

    if type(lap) is not int or lap < 1:
        raise ValueError("lap deve ser um inteiro positivo")
    probability = (
        params.solo_crash_probability_per_car_lap
        * lap_effects.solo_crash_multiplier
    )
    if lap == 1:
        probability *= params.first_lap_solo_crash_multiplier
    return probability


def should_yield_blue_flag(
    defender_laps_completed: int,
    attacker_laps_completed: int,
) -> bool:
    """Informe se o carro da frente deve ceder por estar sendo retardatario.

    O motor chama esta funcao antes de criar uma disputa. Quando ela devolve
    ``True``, a passagem e obrigatoria e nao sorteia bloqueio, ultrapassagem ou
    contato. Nomes de papeis, em vez de posicoes de classificacao, evitam
    inverter a regra quando o retardatario esta fisicamente a frente na pista.
    """

    for name, value in (
        ("defender_laps_completed", defender_laps_completed),
        ("attacker_laps_completed", attacker_laps_completed),
    ):
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} deve ser um inteiro nao negativo")
    return attacker_laps_completed > defender_laps_completed


def step(
    state: RaceControlState,
    incidents: tuple[Incident, ...] | list[Incident],
    rng: RandomSource,
    params: RaceControlParameters,
    lap: int,
) -> tuple[RaceControlState, tuple[RaceControlEvent, ...]]:
    """Avance uma volta e devolva ``(estado_da_proxima_volta, eventos)``.

    A ordem de sorteios independe da ordem recebida: contato, acidente
    individual e falha mecanica, cada grupo ordenado por ``driver_ids``. Os
    rotulos incluem volta, indice canonico, tipo e IDs. Eventos contem apenas
    strings, numeros, listas, dicionarios e ``None`` e podem ser entregues
    diretamente a ``json.dumps``.
    """

    if type(lap) is not int or lap < 1:
        raise ValueError("lap deve ser um inteiro positivo")
    if not isinstance(state, RaceControlState):
        raise ValueError("state deve ser RaceControlState")
    if not isinstance(params, RaceControlParameters):
        raise ValueError("params deve ser RaceControlParameters")
    if not isinstance(incidents, (tuple, list)):
        raise ValueError("incidents deve ser tuple ou list")
    if any(not isinstance(incident, Incident) for incident in incidents):
        raise ValueError("incidents deve conter apenas Incident")
    if any(incident.lap != lap for incident in incidents):
        raise ValueError("todo incidente deve pertencer a lap informada")

    ordered = sorted(
        incidents,
        key=lambda item: (_INCIDENT_KIND_ORDER[item.kind], item.driver_ids),
    )
    if not ordered:
        return _advance_without_response(state, lap)

    requests: list[_RequestedResponse] = []
    events: list[RaceControlEvent] = []
    for index, incident in enumerate(ordered, start=1):
        request = _response_for_incident(incident, rng, params, lap, index)
        requests.append(request)
        events.append(
            {
                "lap": lap,
                "type": "incident_response",
                "cause": _incident_payload(incident),
                "response": request.status.value if request.status else "NONE",
                "duration_laps": request.duration_laps,
            }
        )

    selected = _most_severe_request(requests)
    if state.status == GREEN:
        if selected is None:
            # Uma relargada dura exatamente uma volta. Mesmo com falha mecanica
            # sem intervencao, ela foi consumida e nao vaza para a volta seguinte.
            return RaceControlState(), tuple(events)
        new_state = _active_state(selected)
        events.append(_transition_event("race_control_started", lap, new_state))
        return new_state, tuple(events)

    assert state.status in _ACTIVE_STATUSES
    if selected is None or _STATUS_PRIORITY[selected.status] < _STATUS_PRIORITY[state.status]:
        advanced, end_events = _advance_without_response(state, lap)
        return advanced, tuple(events) + end_events

    if _STATUS_PRIORITY[selected.status] > _STATUS_PRIORITY[state.status]:
        new_state = _active_state(selected)
        events.append(_transition_event("race_control_escalated", lap, new_state))
        return new_state, tuple(events)

    remaining_after_lap = state.laps_remaining - 1
    assert selected.duration_laps is not None
    if selected.duration_laps <= remaining_after_lap:
        return (
            RaceControlState(
                status=state.status,
                laps_remaining=remaining_after_lap,
                cause=state.cause,
            ),
            tuple(events),
        )
    new_state = RaceControlState(
        status=state.status,
        laps_remaining=selected.duration_laps,
        cause=selected.cause,
    )
    events.append(_transition_event("race_control_extended", lap, new_state))
    return new_state, tuple(events)


def _neutral_effects() -> LapEffects:
    return LapEffects(
        lap_time_factor=1.0,
        lap_time_loss_ms=0.0,
        disputes_enabled=True,
        overtake_factor=1.0,
        contact_factor=1.0,
        compress_field=False,
        freeze_order=False,
        pit_loss_factor=1.0,
        free_tyre_change=False,
        neutralized=False,
        solo_crash_multiplier=1.0,
    )


def _neutralized_effects(
    *,
    lap_time_factor: float,
    pit_loss_factor: float,
    compress_field: bool,
    freeze_order: bool,
    free_tyre_change: bool,
    solo_crash_multiplier: float,
) -> LapEffects:
    return LapEffects(
        lap_time_factor=lap_time_factor,
        lap_time_loss_ms=0.0,
        disputes_enabled=False,
        overtake_factor=0.0,
        contact_factor=0.0,
        compress_field=compress_field,
        freeze_order=freeze_order,
        pit_loss_factor=pit_loss_factor,
        free_tyre_change=free_tyre_change,
        neutralized=True,
        solo_crash_multiplier=solo_crash_multiplier,
    )


def _advance_without_response(
    state: RaceControlState, lap: int
) -> tuple[RaceControlState, tuple[RaceControlEvent, ...]]:
    """Consuma a volta vigente sem consultar a fonte aleatoria."""

    if state.status == GREEN:
        return RaceControlState(), ()
    if state.laps_remaining > 1:
        return (
            RaceControlState(
                status=state.status,
                laps_remaining=state.laps_remaining - 1,
                cause=state.cause,
            ),
            (),
        )

    events: list[RaceControlEvent] = [
        {
            "lap": lap,
            "type": "race_control_ended",
            "status": state.status.value,
            "cause": _incident_payload(state.cause),
        }
    ]
    if state.status in (SC, RED):
        new_state = RaceControlState(
            restart_lap=True,
            restart_source=state.status,
        )
        events.append(
            {
                "lap": lap,
                "type": "restart_scheduled",
                "source": state.status.value,
            }
        )
        return new_state, tuple(events)
    return RaceControlState(), tuple(events)


def _response_for_incident(
    incident: Incident,
    rng: RandomSource,
    params: RaceControlParameters,
    lap: int,
    index: int,
) -> _RequestedResponse:
    label_base = (
        f"race_control:lap:{lap}:incident:{index}:{incident.kind}:"
        f"{','.join(incident.driver_ids)}"
    )
    if incident.kind in ("contact", "solo_crash"):
        severity = _draw(rng, f"{label_base}:severity")
        if severity < params.crash_red_probability:
            return _RequestedResponse(RED, params.red_duration_laps, incident)

        response_draw = _draw(rng, f"{label_base}:response")
        if response_draw < params.crash_sc_probability:
            duration = _draw_duration(
                rng,
                f"{label_base}:duration",
                params.sc_min_duration_laps,
                params.sc_max_duration_laps,
            )
            return _RequestedResponse(SC, duration, incident)
        if response_draw < (
            params.crash_sc_probability + params.crash_vsc_probability
        ):
            duration = _draw_duration(
                rng,
                f"{label_base}:duration",
                params.vsc_min_duration_laps,
                params.vsc_max_duration_laps,
            )
            return _RequestedResponse(VSC, duration, incident)
        return _RequestedResponse(YELLOW, params.yellow_duration_laps, incident)

    response_draw = _draw(rng, f"{label_base}:response")
    if response_draw < params.mechanical_no_intervention_probability:
        return _RequestedResponse(None, None, incident)
    if response_draw < (
        params.mechanical_no_intervention_probability
        + params.mechanical_yellow_probability
    ):
        return _RequestedResponse(YELLOW, params.yellow_duration_laps, incident)
    duration = _draw_duration(
        rng,
        f"{label_base}:duration",
        params.vsc_min_duration_laps,
        params.vsc_max_duration_laps,
    )
    return _RequestedResponse(VSC, duration, incident)


def _draw(rng: RandomSource, label: str) -> float:
    value = rng.uniform01(label)
    # ``FrozenRandomSource`` usa 1.0 como sentinela de nenhum evento. Aceita-se
    # a borda inclusiva para manter esse contrato; duracoes mapeiam 1.0 ao maximo.
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or not 0.0 <= value <= 1.0
    ):
        raise ValueError("RandomSource.uniform01 deve retornar valor em [0, 1]")
    return value


def _draw_duration(
    rng: RandomSource,
    label: str,
    minimum_laps: int,
    maximum_laps: int,
) -> int:
    draw = _draw(rng, label)
    count = maximum_laps - minimum_laps + 1
    offset = min(int(draw * count), count - 1)
    return minimum_laps + offset


def _most_severe_request(
    requests: list[_RequestedResponse],
) -> _RequestedResponse | None:
    active = [request for request in requests if request.status is not None]
    if not active:
        return None
    # A ordenacao canonica dos incidentes ja resolveu empates de causa. Entre
    # respostas da mesma gravidade, a maior duracao impede encurtar o periodo.
    return max(
        active,
        key=lambda request: (
            _STATUS_PRIORITY[request.status],
            request.duration_laps or 0,
        ),
    )


def _active_state(request: _RequestedResponse) -> RaceControlState:
    assert request.status is not None and request.duration_laps is not None
    return RaceControlState(
        status=request.status,
        laps_remaining=request.duration_laps,
        cause=request.cause,
    )


def _incident_payload(incident: Incident) -> dict[str, object]:
    return {
        "lap": incident.lap,
        "kind": incident.kind,
        "driver_ids": list(incident.driver_ids),
    }


def _transition_event(
    event_type: str, lap: int, state: RaceControlState
) -> RaceControlEvent:
    assert state.cause is not None
    return {
        "lap": lap,
        "type": event_type,
        "status": state.status.value,
        "duration_laps": state.laps_remaining,
        "cause": _incident_payload(state.cause),
    }
