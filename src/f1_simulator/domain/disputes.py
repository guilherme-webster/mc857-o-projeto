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

from dataclasses import dataclass

from f1_simulator.domain.model_parameters import ModelParameters, TrackParameters
from f1_simulator.domain.random_source import RandomSource


@dataclass(frozen=True, slots=True)
class DisputeOutcome:
    """Resultado da volta para um carro, depois de resolvidas as disputas.

    ``blocked_by`` nomeia o carro que impediu a passagem, quando houve bloqueio.
    Ele existe para o relatorio: sem ele, um carro preso e indistinguivel de um
    carro lento, e a diferenca importa para quem le a corrida.
    """

    driver_id: str
    end_time_ms: float
    blocked_by: str | None = None
    collided: bool = False


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


def resolve_disputes(
    proposed: list[tuple[str, float, float]],
    *,
    parameters: ModelParameters,
    track: TrackParameters,
    rng: RandomSource,
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

    A fonte aleatoria e consumida em ordem fixa (da frente para tras, dois
    sorteios por disputa), preservando a reprodutibilidade por semente.
    """

    if not proposed:
        return ()

    ordered = sorted(proposed, key=lambda row: (row[1], row[0]))
    minimum_gap = parameters.minimum_gap_ms

    # ---- Fase A: bloqueio e ultrapassagem -------------------------------
    results: list[DisputeOutcome] = []
    ahead_end: float | None = None
    ahead_id: str | None = None
    for driver_id, _start_ms, proposed_end in ordered:
        end = proposed_end
        blocked_by: str | None = None
        collided = False

        if ahead_end is not None and end < ahead_end + minimum_gap:
            # Disputa: o carro de tras alcancou o da frente nesta volta.
            advantage = ahead_end - end
            chance = pass_probability(
                advantage, track.overtaking_difficulty, parameters
            )
            if rng.uniform01() >= chance:
                end = ahead_end + minimum_gap
                blocked_by = ahead_id
            # O contato e sorteado tenha a ultrapassagem dado certo ou nao:
            # bater ao tentar passar e bater ao ser passado sao o mesmo evento.
            if rng.uniform01() < parameters.collision_probability_per_dispute:
                collided = True

        results.append(DisputeOutcome(driver_id, end, blocked_by, collided))
        ahead_end = end
        ahead_id = driver_id

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
                outcome.driver_id, end, outcome.blocked_by, outcome.collided
            )
        )
        previous_end = end
    return tuple(spaced)
