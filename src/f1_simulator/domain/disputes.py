"""Disputa de posicao entre carros vizinhos, resolvida dentro de uma volta.

O que este modulo representa, e em que resolucao
------------------------------------------------
O motor avanca por volta, entao nao existe um instante de roda a roda para
simular. O que existe e o **desfecho** de uma briga que durou uma volta: no
inicio da volta dois carros estao proximos; no fim, ou a ultrapassagem
aconteceu, ou nao aconteceu, ou os dois se tocaram.

E nessa resolucao que o modelo opera, e ela e suficiente para produzir os tres
fenomenos que faltavam:

1. **Bloqueio.** Ate aqui o trafego era apenas um imposto de tempo: um carro
   mais rapido perdia alguns decimos e passava assim mesmo. O historico diz
   outra coisa -- entre pares adjacentes, o carro de tras passa em apenas 7,3%
   das voltas. Na esmagadora maioria das voltas, ele fica preso.
2. **Ultrapassagem como evento.** Passar deixa de ser consequencia aritmetica de
   ser mais rapido e passa a ser um sorteio cuja probabilidade depende da
   vantagem de ritmo e do circuito.
3. **Exclusao fisica.** Dois carros nao podem ocupar o mesmo ponto da pista. O
   espacamento minimo e imposto no dominio do tempo, que e onde o motor vive.

Contato como consequencia, nao como sorteio solto
--------------------------------------------------
41% dos abandonos da era calibrada vem de colisao, dano de colisao ou acidente.
Um risco plano por volta, igual para todos, nao representa isso: quem briga no
meio do pelotao bate mais do que quem lidera sozinho. Aqui a colisao so pode
acontecer **durante uma disputa**, o que torna o risco endogeno ao trafego.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Literal

from f1_simulator.domain.model_parameters import ModelParameters, TrackParameters
from f1_simulator.domain.random_source import RandomSource


@dataclass(frozen=True, slots=True)
class DisputeProfile:
    """Moduladores relativos de um carro nas disputas de posicao.

    Os tres valores sao multiplicadores adimensionais e ``1.0`` e o perfil
    neutro. O contrato e propositalmente desacoplado de ``DriverAttributes``:
    cabe ao composition root do motor mapear atributos para este perfil, sem
    fazer o mecanismo de disputa depender da origem daqueles dados.

    ``consistency_factor`` tem a mesma orientacao do multiplicador de ruido:
    valores maiores representam menor consistencia. O modelo de pressao reduz
    levemente o ataque nesses casos, conforme documentado em
    :func:`pressure_pass_probability`.
    """

    aggression: float = 1.0
    composure: float = 1.0
    consistency_factor: float = 1.0

    def __post_init__(self) -> None:
        for name, value in (
            ("aggression", self.aggression),
            ("composure", self.composure),
            ("consistency_factor", self.consistency_factor),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value <= 0.0
            ):
                raise ValueError(f"{name} deve ser positivo e finito")


@dataclass(frozen=True, slots=True)
class DisputeHeuristics:
    """Coeficientes assumidos e versionados do modelo de pressao.

    ``resistance_scale`` e o ``k_resistencia`` dos slides. O valor padrao
    ``33/7`` ancora o modelo na formula legacy: com vantagem de 500 ms, escala
    de 1400 ms, proximidade 1, perfis neutros e dificuldade mediana 0,5,
    ``P=5/14`` e ``R=33/14``; portanto ``P/(P+R)=5/38=13,16%``, a mesma chance
    legacy ``0,5 * 500 / (500 + 1400)``.

    ``consistency_pressure_exponent`` controla uma modulacao pequena por
    ``consistency_factor ** -expoente``. O expoente 0,25 faz um multiplicador
    de ruido 20% maior reduzir a pressao em cerca de 4,5%, em vez de contar a
    consistencia com a mesma forca que a agressividade.

    O contato nao atribui culpa: por padrao, cada participante tem 50% de
    chance de ser o carro retirado. Essa escolha tambem e heuristica e, por
    isso, aparece nomeada junto dos demais coeficientes.
    """

    origin: str = "heuristic"
    parameter_version: str = "dispute-pressure-v1"
    rationale: str = (
        "Implementa P/(P+R) dos slides, ancora 500 ms em 13,16% e divide "
        "igualmente o abandono por contato entre os dois carros."
    )
    resistance_scale: float = 33.0 / 7.0
    consistency_pressure_exponent: float = 0.25
    attacker_retirement_probability_on_contact: float = 0.5

    def __post_init__(self) -> None:
        if self.origin != "heuristic":
            raise ValueError("origin deve ser 'heuristic'")
        if not self.parameter_version:
            raise ValueError("parameter_version nao pode ser vazio")
        if not self.rationale:
            raise ValueError("rationale nao pode ser vazio")
        if (
            isinstance(self.resistance_scale, bool)
            or not isinstance(self.resistance_scale, (int, float))
            or not isfinite(self.resistance_scale)
            or self.resistance_scale <= 0.0
        ):
            raise ValueError("resistance_scale deve ser positivo e finito")
        if (
            isinstance(self.consistency_pressure_exponent, bool)
            or not isinstance(self.consistency_pressure_exponent, (int, float))
            or not isfinite(self.consistency_pressure_exponent)
            or self.consistency_pressure_exponent < 0.0
        ):
            raise ValueError(
                "consistency_pressure_exponent deve ser nao negativo e finito"
            )
        retirement_probability = self.attacker_retirement_probability_on_contact
        if (
            isinstance(retirement_probability, bool)
            or not isinstance(retirement_probability, (int, float))
            or not isfinite(retirement_probability)
            or not 0.0 <= retirement_probability <= 1.0
        ):
            raise ValueError(
                "attacker_retirement_probability_on_contact deve estar em [0, 1]"
            )


DEFAULT_DISPUTE_HEURISTICS = DisputeHeuristics()
"""Parametros heuristicos padrao do modelo ``pressure``."""


@dataclass(frozen=True, slots=True)
class DisputeOutcome:
    """Resultado da volta para um carro, depois de resolvidas as disputas.

    ``blocked_by`` nomeia o carro que impediu a passagem, quando houve bloqueio.
    Ele existe para o relatorio: sem ele, um carro preso e indistinguivel de um
    carro lento, e a diferenca importa para quem le a corrida. ``collided``
    continua significando "este carro abandona por contato", preservando o
    consumidor legado. No modelo pressure, ``contact_with`` identifica o outro
    participante nos dois resultados, mas somente o sorteado tem
    ``collided=True``.
    """

    driver_id: str
    end_time_ms: float
    blocked_by: str | None = None
    collided: bool = False
    contact_with: str | None = None


def pass_probability(
    advantage_ms: float,
    difficulty: float,
    parameters: ModelParameters,
) -> float:
    """Chance de concluir uma ultrapassagem nesta volta.

    Forma saturante: ``(1 - dificuldade) * v / (v + escala)``, com ``v`` a
    vantagem de ritmo da volta. Ela tem as tres propriedades que o fenomeno
    exige e que uma constante nao teria:

    - vantagem nula da chance nula -- ninguem passa sem ser mais rapido;
    - vantagem muito grande satura em ``1 - dificuldade``, e nao em 1: mesmo um
      carro muito mais rapido nao passa garantidamente em Monaco;
    - a escala controla quanta vantagem e precisa para uma chance razoavel, e e
      o unico parametro livre -- calibrado contra a taxa de troca observada.
    """

    if advantage_ms <= 0:
        return 0.0
    ceiling = max(0.0, 1.0 - difficulty)
    scale = parameters.overtake_advantage_scale_ms
    if scale <= 0:
        return ceiling
    return ceiling * advantage_ms / (advantage_ms + scale)


def pressure_pass_probability(
    advantage_ms: float,
    proximity: float,
    difficulty: float,
    parameters: ModelParameters,
    *,
    attacker_profile: DisputeProfile = DisputeProfile(),
    defender_profile: DisputeProfile = DisputeProfile(),
    heuristics: DisputeHeuristics = DEFAULT_DISPUTE_HEURISTICS,
    overtake_factor: float = 1.0,
) -> float:
    """Calcule a chance ``P/(P+R)`` de concluir uma ultrapassagem.

    ``advantage_ms`` e quanto o atacante seria mais rapido na volta sem o
    bloqueio. ``proximity`` deve estar em ``[0, 1]`` e e calculada por
    :func:`resolve_disputes` a partir do intervalo no **inicio da volta**. Essa
    escolha evita usar o proprio resultado proposto para afirmar que os carros
    ja estavam proximos e preserva a interpretacao causal dos slides.

    A pressao e
    ``(advantage_ms / overtake_advantage_scale_ms) * proximity * aggression *
    consistency_factor ** -expoente``. A resistencia e
    ``difficulty * composure * resistance_scale``. Dificuldade deve ser
    estritamente positiva neste modelo: resistencia nula produziria chance 1,
    proibida pelo contrato. Os circuitos calibrados e o fallback do modelo v1
    satisfazem essa pre-condicao.

    ``overtake_factor`` multiplica a probabilidade final para representar, por
    exemplo, amarela ou relargada. Fatores acima de 1 sao aceitos enquanto o
    resultado continuar abaixo de 1; uma configuracao que o leve a 1 ou mais e
    rejeitada explicitamente, nunca limitada por um clamp silencioso.
    """

    for name, value in (
        ("advantage_ms", advantage_ms),
        ("proximity", proximity),
        ("difficulty", difficulty),
        ("overtake_factor", overtake_factor),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
        ):
            raise ValueError(f"{name} deve ser um numero finito")
    if not 0.0 <= proximity <= 1.0:
        raise ValueError("proximity deve estar em [0, 1]")
    if not 0.0 < difficulty <= 1.0:
        raise ValueError("difficulty deve estar em (0, 1] no modelo pressure")
    if overtake_factor < 0.0:
        raise ValueError("overtake_factor deve ser nao negativo")
    if advantage_ms <= 0.0 or proximity == 0.0 or overtake_factor == 0.0:
        return 0.0

    scale_ms = parameters.overtake_advantage_scale_ms
    if scale_ms <= 0.0:
        raise ValueError(
            "overtake_advantage_scale_ms deve ser positivo no modelo pressure"
        )

    consistency_effect = (
        attacker_profile.consistency_factor
        ** -heuristics.consistency_pressure_exponent
    )
    pressure = (
        advantage_ms
        / scale_ms
        * proximity
        * attacker_profile.aggression
        * consistency_effect
    )
    resistance = (
        difficulty * defender_profile.composure * heuristics.resistance_scale
    )
    probability = pressure / (pressure + resistance) * overtake_factor
    if probability >= 1.0:
        raise ValueError(
            "overtake_factor produz probabilidade de ultrapassagem fora de [0, 1)"
        )
    return probability


def _non_negative_factor(value: float, name: str) -> None:
    """Valide multiplicadores de controle antes de consumir aleatoriedade."""

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < 0.0
    ):
        raise ValueError(f"{name} deve ser nao negativo e finito")


def _proximity(start_gap_ms: float, threshold_ms: float) -> float:
    """Converta o intervalo inicial em proximidade explicitamente limitada."""

    if threshold_ms <= 0.0:
        return 1.0 if start_gap_ms == 0.0 else 0.0
    return max(0.0, min(1.0, 1.0 - start_gap_ms / threshold_ms))


def _profile_for(
    driver_id: str,
    profiles: Mapping[str, DisputeProfile] | None,
) -> DisputeProfile:
    """Use o perfil neutro quando o carro nao recebeu atributos."""

    if profiles is None:
        return DisputeProfile()
    if driver_id not in profiles:
        return DisputeProfile()
    profile = profiles[driver_id]
    if not isinstance(profile, DisputeProfile):
        raise ValueError(f"perfil de {driver_id!r} deve ser DisputeProfile")
    return profile


def _laps_for(
    proposed: list[tuple[str, float, float]],
    laps_completed: Mapping[str, int] | None,
) -> dict[str, int] | None:
    """Valide voltas sem transformar ausencia em zero."""

    if laps_completed is None:
        return None
    validated: dict[str, int] = {}
    for driver_id, _start_ms, _end_ms in proposed:
        if driver_id not in laps_completed:
            raise ValueError(f"laps_completed nao informa {driver_id!r}")
        laps = laps_completed[driver_id]
        if type(laps) is not int or laps < 0:
            raise ValueError(
                f"laps_completed de {driver_id!r} deve ser inteiro nao negativo"
            )
        validated[driver_id] = laps
    return validated


def _contact_probability(
    base_probability: float,
    contact_factor: float,
    *,
    attacker_profile: DisputeProfile | None = None,
    defender_profile: DisputeProfile | None = None,
) -> float:
    """Escale contato e rejeite configuracoes que deixem de ser probabilidade."""

    aggression = 1.0
    if attacker_profile is not None and defender_profile is not None:
        aggression = (attacker_profile.aggression + defender_profile.aggression) / 2.0
    probability = base_probability * aggression * contact_factor
    if probability >= 1.0:
        raise ValueError(
            "contact_factor e aggression produzem probabilidade de contato "
            "fora de [0, 1)"
        )
    return probability


def resolve_disputes(
    proposed: list[tuple[str, float, float]],
    *,
    parameters: ModelParameters,
    track: TrackParameters,
    rng: RandomSource,
    model: Literal["legacy", "pressure"] = "legacy",
    profiles: Mapping[str, DisputeProfile] | None = None,
    heuristics: DisputeHeuristics = DEFAULT_DISPUTE_HEURISTICS,
    laps_completed: Mapping[str, int] | None = None,
    overtake_factor: float = 1.0,
    contact_factor: float = 1.0,
) -> tuple[DisputeOutcome, ...]:
    """Resolva bloqueios, ultrapassagens e contatos de uma volta.

    ``proposed`` traz ``(driver_id, tempo acumulado no inicio da volta, tempo
    acumulado proposto no fim)``, ja com todas as parcelas do modelo aplicadas.

    Duas fases, nesta ordem:

    **Fase A -- disputas.** Percorre os carros na ordem do inicio da volta, da
    frente para tras. Se o tempo proposto de um carro o colocaria a frente (ou
    colado demais) no carro imediatamente a sua frente, houve disputa: sorteia a
    ultrapassagem e, se ela falhar, prende o carro atras. Processar de frente
    para tras faz o bloqueio se propagar -- um carro preso segura quem vem atras,
    que e exatamente como se forma um trem de carros.

    **Fase B -- exclusao fisica.** Reordena pelo tempo final e impoe o
    espacamento minimo entre carros consecutivos. Isso garante a invariante
    mesmo quando uma ultrapassagem bem-sucedida reembaralha a ordem, e e o que
    impede dois carros de ocuparem o mesmo ponto da pista.

    ``model="legacy"`` preserva a formula, o desfecho de contato e as chamadas
    sem rotulo do motor calibrado. Com todos os opcionais no padrao, cada
    disputa continua consumindo exatamente dois uniformes: passagem e contato.

    ``model="pressure"`` usa perfis neutros para carros ausentes de
    ``profiles``. A ordem de sorteios e fixa, da frente para tras: ``pass``,
    ``contact`` e, somente se houve contato, ``contact-retiree``. Os rotulos
    incluem atacante e defensor. Se ``laps_completed`` informa voltas
    diferentes, nao ha disputa nem sorteio: o retardatario cede e apenas a
    exclusao fisica continua valendo.
    """

    if model not in ("legacy", "pressure"):
        raise ValueError("model deve ser 'legacy' ou 'pressure'")
    _non_negative_factor(overtake_factor, "overtake_factor")
    _non_negative_factor(contact_factor, "contact_factor")
    validated_laps = _laps_for(proposed, laps_completed)

    if not proposed:
        return ()

    ordered = sorted(proposed, key=lambda row: (row[1], row[0]))
    minimum_gap = parameters.minimum_gap_ms

    # ---- Fase A: bloqueio e ultrapassagem -------------------------------
    results: list[DisputeOutcome] = []
    ahead_end: float | None = None
    ahead_id: str | None = None
    ahead_start_ms: float | None = None
    for driver_id, start_ms, proposed_end in ordered:
        end = proposed_end
        blocked_by: str | None = None
        collided = False
        contact_with: str | None = None
        yielded_to: DisputeOutcome | None = None

        if ahead_end is not None and end < ahead_end + minimum_gap:
            assert ahead_id is not None
            assert ahead_start_ms is not None

            different_laps = (
                validated_laps is not None
                and validated_laps[driver_id] != validated_laps[ahead_id]
            )
            if different_laps:
                # Nao se trata de uma briga por posicao, e nenhum dos casos
                # ganha ``blocked_by`` ou consome aleatoriedade.
                if validated_laps[driver_id] < validated_laps[ahead_id]:
                    # O carro atual e o retardatario: permanece atras.
                    end = max(end, ahead_end + minimum_gap)
                else:
                    # O carro atual vai dar volta no da frente (bandeira azul).
                    # Quem cede e o retardatario: o lider mantem o proprio
                    # tempo -- nem e segurado, nem ganha tempo artificial -- e
                    # o retardatario termina a volta atras dele, perdendo o
                    # espaco minimo. Sem isso, a fase B prenderia o lider atras
                    # do retardatario, o que a bandeira azul proibe.
                    lapped = results[-1]
                    results[-1] = DisputeOutcome(
                        driver_id=lapped.driver_id,
                        end_time_ms=max(lapped.end_time_ms, end + minimum_gap),
                        blocked_by=lapped.blocked_by,
                        collided=lapped.collided,
                        contact_with=lapped.contact_with,
                    )
                    yielded_to = lapped
            else:
                # Disputa: o carro de tras alcancou o da frente nesta volta.
                advantage = ahead_end - end
                if model == "legacy":
                    chance = pass_probability(
                        advantage, track.overtaking_difficulty, parameters
                    )
                    chance *= overtake_factor
                    if chance > 1.0:
                        raise ValueError(
                            "overtake_factor produz probabilidade legacy acima de 1"
                        )
                    contact_chance = _contact_probability(
                        parameters.collision_probability_per_dispute,
                        contact_factor,
                    )
                    # Sem rotulos por compatibilidade estrita com as fontes
                    # aleatorias do motor legado e sua sequencia auditada.
                    pass_draw = rng.uniform01()
                    contact_draw = rng.uniform01()
                else:
                    attacker_profile = _profile_for(driver_id, profiles)
                    defender_profile = _profile_for(ahead_id, profiles)
                    chance = pressure_pass_probability(
                        advantage,
                        _proximity(
                            start_ms - ahead_start_ms,
                            parameters.traffic_threshold_ms,
                        ),
                        track.overtaking_difficulty,
                        parameters,
                        attacker_profile=attacker_profile,
                        defender_profile=defender_profile,
                        heuristics=heuristics,
                        overtake_factor=overtake_factor,
                    )
                    contact_chance = _contact_probability(
                        parameters.collision_probability_per_dispute,
                        contact_factor,
                        attacker_profile=attacker_profile,
                        defender_profile=defender_profile,
                    )
                    label = f"lap-dispute:{driver_id}:{ahead_id}"
                    pass_draw = rng.uniform01(f"{label}:pass")
                    contact_draw = rng.uniform01(f"{label}:contact")

                if pass_draw >= chance:
                    end = ahead_end + minimum_gap
                    blocked_by = ahead_id

                # O contato e sorteado tenha a passagem dado certo ou nao. No
                # pressure, ambos registram o par, mas exatamente um abandona.
                if contact_draw < contact_chance:
                    if model == "legacy":
                        collided = True
                    else:
                        contact_with = ahead_id
                        retiree_draw = rng.uniform01(
                            f"lap-dispute:{driver_id}:{ahead_id}:contact-retiree"
                        )
                        attacker_retires = (
                            retiree_draw
                            < heuristics.attacker_retirement_probability_on_contact
                        )
                        collided = attacker_retires
                        defender = results[-1]
                        results[-1] = DisputeOutcome(
                            driver_id=defender.driver_id,
                            end_time_ms=defender.end_time_ms,
                            blocked_by=defender.blocked_by,
                            # Um segundo incidente na mesma volta nunca pode
                            # "ressuscitar" quem ja havia sido retirado.
                            collided=defender.collided or not attacker_retires,
                            contact_with=driver_id,
                        )

        results.append(
            DisputeOutcome(
                driver_id=driver_id,
                end_time_ms=end,
                blocked_by=blocked_by,
                collided=collided,
                contact_with=contact_with,
            )
        )
        if yielded_to is not None:
            # Depois da bandeira azul, o carro mais atrasado do par na pista e
            # o retardatario que cedeu; e com ele que o proximo carro disputa.
            ahead_end = results[-2].end_time_ms
            ahead_id = yielded_to.driver_id
            ahead_start_ms = start_ms
        else:
            ahead_end = end
            ahead_id = driver_id
            ahead_start_ms = start_ms

    # ---- Fase B: nenhum par pode terminar sobreposto ---------------------
    results.sort(key=lambda outcome: (outcome.end_time_ms, outcome.driver_id))
    spaced: list[DisputeOutcome] = []
    previous_end: float | None = None
    for outcome in results:
        end = outcome.end_time_ms
        if previous_end is not None and end < previous_end + minimum_gap:
            end = previous_end + minimum_gap
        spaced.append(
            DisputeOutcome(
                driver_id=outcome.driver_id,
                end_time_ms=end,
                blocked_by=outcome.blocked_by,
                collided=outcome.collided,
                contact_with=outcome.contact_with,
            )
        )
        previous_end = end
    return tuple(spaced)
