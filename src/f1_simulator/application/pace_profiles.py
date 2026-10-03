"""Ritmo de referencia derivado de corridas anteriores, fora da amostra.

Este modulo fecha a lacuna mais seria do backtest original. Ate aqui, cada
participante entrava na simulacao com o ritmo observado **no proprio fim de
semana** que estava sendo validado. Isso isolava o modelo de corrida, mas
impedia qualquer afirmacao sobre poder preditivo: o resultado ja sabia quem era
rapido naquele domingo.

Aqui o ritmo relativo de cada piloto vem exclusivamente de corridas
**anteriores**, estimado pelo metodo da issue #40
(``domain/driver_profile.estimate_profiles``), que este modulo reutiliza sem
alterar.

A separacao entre o que vem do passado e o que vem do fim de semana
--------------------------------------------------------------------
Um tempo de volta absoluto depende do carro daquele ano, do circuito e do
regulamento. Prever isso seria prever o desenvolvimento das equipes, o que nao
esta em questao. O que se separa e:

- **nivel do fim de semana** -- a mediana do campo naquela corrida, que vem do
  proprio evento e nao e objeto de previsao;
- **posicao de cada piloto dentro do campo** -- vem apenas de eventos passados.

O produto dos dois da o ritmo de referencia. A previsao que isso permite testar
e, portanto, "dada a velocidade tipica deste fim de semana, quem termina na
frente de quem" -- e essa ordenacao e genuinamente fora da amostra.

Uma transferencia assumida, declarada
-------------------------------------
``pace_delta_pct`` da #40 e medido contra a referencia **do contexto** (que ja
contem combustivel e idade de pneu daquele recorte), enquanto a referencia do
motor e a volta limpa ideal. Aplicar a mesma porcentagem aos dois niveis assume
que estar 1% atras do campo em contexto equivale a estar 1% atras do campo em
volta limpa. Porcentagens transferem melhor que milissegundos entre niveis, mas
isto e uma hipotese de aplicacao, nao um resultado medido.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from f1_simulator.domain.driver_profile import (
    LapAssessment,
    ProfileConfig,
    estimate_profiles,
)

#: Recorte exploratorio usado com dados Trotman. As janelas sao largas porque o
#: contexto disponivel e pobre: sem composto nem clima, particionar fino apenas
#: esvaziaria os contextos sem torna-los mais comparaveis.
TROTMAN_PROFILE_CONFIG = ProfileConfig(
    lap_window=15,
    tyre_age_window=10,
    weather_max_age_ms=600_000,
    min_laps_per_context=3,
    min_drivers_per_context=4,
    min_events=3,
)


@dataclass(frozen=True, slots=True)
class PaceProfile:
    """Ritmo relativo de um piloto, estimado apenas com eventos anteriores."""

    driver_id: str
    pace_delta_pct: float
    events: int
    compared_laps: int


@dataclass(frozen=True, slots=True)
class ProfileCoverage:
    """Quantos participantes receberam perfil e quantos usaram reserva.

    A cobertura precisa acompanhar qualquer metrica publicada: um experimento em
    que metade do grid caiu na reserva nao demonstra o mesmo que um em que todos
    tiveram perfil proprio.
    """

    profiled: int
    fell_back: int
    reasons: tuple[tuple[str, int], ...]


def build_pace_profiles(
    assessments: tuple[LapAssessment, ...],
    driver_ids: tuple[str, ...],
    config: ProfileConfig = TROTMAN_PROFILE_CONFIG,
) -> tuple[dict[str, PaceProfile], tuple[tuple[str, int], ...]]:
    """Rode o estimador da #40 e devolva os perfis disponiveis.

    Pilotos sem contexto comparavel ou sem eventos suficientes simplesmente nao
    aparecem no dicionario. Ausencia e uma condicao de dominio legivel; nao e
    preenchida com zero, que significaria "exatamente na media do campo".
    """

    if not assessments or not driver_ids:
        return {}, ()

    profiles, _ = estimate_profiles(assessments, driver_ids, config)

    available: dict[str, PaceProfile] = {}
    reasons: dict[str, int] = {}
    for profile in profiles:
        if profile.unavailable_reason or profile.pace_delta_pct is None:
            reason = profile.unavailable_reason or "no_pace_estimate"
            reasons[reason] = reasons.get(reason, 0) + 1
            continue
        available[profile.driver_id] = PaceProfile(
            driver_id=profile.driver_id,
            pace_delta_pct=profile.pace_delta_pct,
            events=profile.events,
            compared_laps=profile.compared_laps,
        )
    return available, tuple(sorted(reasons.items()))


def reference_times_from_profiles(
    weekend_references_ms: dict[str, float],
    profiles: dict[str, PaceProfile],
) -> tuple[dict[str, float], ProfileCoverage]:
    """Combine o nivel do fim de semana com o ritmo relativo do passado.

    O nivel e a **mediana do campo** naquela corrida -- uma grandeza do evento,
    nao de um piloto. Sobre ela aplica-se o deslocamento percentual estimado de
    eventos anteriores.

    Quem nao tem perfil mantem seu proprio ritmo do fim de semana. Essa reserva
    e deliberada e precisa ser contada: substituir por um valor neutro faria o
    piloto parecer mediano em vez de desconhecido, e distorceria a comparacao
    entre as duas fontes de ritmo.
    """

    if not weekend_references_ms:
        raise ValueError("e necessario ao menos um ritmo de fim de semana")

    field_level = statistics.median(weekend_references_ms.values())

    references: dict[str, float] = {}
    profiled = 0
    for driver_id, weekend in weekend_references_ms.items():
        profile = profiles.get(driver_id)
        if profile is None:
            references[driver_id] = weekend
            continue
        modelled = field_level * (1.0 + profile.pace_delta_pct / 100.0)
        # Um deslocamento absurdo produziria tempo nao positivo e derrubaria o
        # motor no meio da corrida; rejeitar aqui mantem a falha proxima da
        # causa.
        if modelled <= 0:
            references[driver_id] = weekend
            continue
        references[driver_id] = modelled
        profiled += 1

    return references, ProfileCoverage(
        profiled=profiled,
        fell_back=len(weekend_references_ms) - profiled,
        reasons=(),
    )
