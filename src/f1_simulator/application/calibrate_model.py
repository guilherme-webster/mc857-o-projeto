"""Estimativa dos parametros do modelo a partir de observacoes canonicas.

Este modulo contem apenas a **matematica** da calibracao. Ele nao abre banco,
nao le CSV e nao conhece o esquema do Trotman: recebe observacoes ja
normalizadas e devolve ``ModelParameters``. A leitura fica no adaptador
``adapters/persistence/sqlite_calibration.py``, preservando a fronteira do
ADR 0002.

Metodo, e por que ele funciona
------------------------------
O problema central e separar **combustivel** de **pneu**. Os dois efeitos sao
grandes, atuam em sentidos opostos e, olhados isoladamente, se cancelam: a
inclinacao bruta do tempo de volta ao longo de uma corrida fica proxima de zero.
Foi exatamente isso que tornou inutil o estimador anterior do backend, que
regredia a corrida inteira e ainda truncava a inclinacao em zero.

A identificacao usa o fato de que os dois efeitos tem **relogios diferentes**:

- o combustivel queima monotonicamente ao longo da corrida e acompanha o numero
  da volta;
- o pneu e trocado nos boxes, entao sua idade **reinicia** a cada parada.

Regredindo o tempo de volta simultaneamente sobre o numero da volta e a idade do
pneu, os dois coeficientes ficam identificados pela variacao que os stints
posteriores introduzem entre as duas contagens. E uma regressao linear de duas
variaveis -- nao ha aprendizado de maquina envolvido.

Os tempos sao centrados dentro de cada par (corrida, piloto) antes da regressao.
Isso elimina o ritmo proprio do carro e do circuito, que sao justamente o que a
``reference_lap_time_ms`` de cada participante ja representa. Sem essa
centragem, a regressao mediria diferencas entre circuitos em vez de efeitos
dentro da corrida.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from f1_simulator.domain.model_parameters import (
    CalibrationProvenance,
    CompoundParameters,
    ModelParameters,
    TeamReliability,
    TrackParameters,
)

#: Fator que converte o desvio absoluto mediano em desvio padrao equivalente
#: sob normalidade. Usado por robustez: a media e o desvio padrao simples sao
#: dominados pelas voltas de safety car que o filtro nao consegue identificar.
MAD_TO_SIGMA = 1.4826

#: Hipotese do grupo para repartir a degradacao medida entre compostos. O
#: Trotman v128 nao registra composto, entao esta divisao NAO e calibrada: o
#: valor medido ancora o MEDIUM e os demais sao escalados por estes fatores.
#: Ordem: (multiplicador de degradacao, deslocamento de ritmo em ms).
COMPOUND_HYPOTHESIS = {
    "SOFT": (1.6, -450.0),
    "MEDIUM": (1.0, 0.0),
    "HARD": (0.6, +450.0),
}


@dataclass(frozen=True, slots=True)
class LapObservation:
    """Uma volta limpa do historico, ja filtrada pelo adaptador.

    ``tyre_age_laps`` e quantas voltas o jogo atual ja havia completado no
    inicio desta volta; zero logo apos uma parada. Como o composto nao esta
    disponivel na fonte, a idade e derivada dos pit stops registrados.
    """

    race_id: str
    circuit_id: str
    driver_id: str
    lap_number: int
    tyre_age_laps: int
    lap_time_ms: int


@dataclass(frozen=True, slots=True)
class PitLossObservation:
    """Perda total medida de uma passagem pelos boxes, em ms."""

    circuit_id: str
    loss_ms: float


@dataclass(frozen=True, slots=True)
class GridObservation:
    """Atraso da primeira volta em relacao ao ritmo limpo do proprio piloto."""

    grid_position: int
    first_lap_excess_ms: float


#: Voltas limpas a partir das quais a degradacao de um circuito deixa de ser
#: encolhida para a media do campo. Abaixo disso a estimativa por circuito e
#: ruidosa e seria irresponsavel usa-la crua.
SEVERITY_SHRINK_LAPS = 1_500

#: Faixa admitida para a severidade de pneu de um circuito. O limite inferior
#: existe porque a regressao por circuito chega a devolver valores negativos
#: onde ha poucos stints -- e pneu que melhora com a idade nao e um fenomeno,
#: e uma falha de identificacao.
SEVERITY_MIN = 0.30
SEVERITY_MAX = 2.50

#: Entradas equivalentes de prior usadas para encolher a confiabilidade de uma
#: equipe para a media do campo. Cerca de um terco de temporada.
RELIABILITY_PRIOR_ENTRIES = 30

#: Limites da dificuldade de ultrapassagem derivada. Nem Monaco impede toda
#: troca de posicao, nem Spa a torna gratuita.
OVERTAKING_MIN = 0.15
OVERTAKING_MAX = 0.95


@dataclass(frozen=True, slots=True)
class PositionChurnObservation:
    """Trocas de posicao por volta observadas em um evento.

    E o proxy de dificuldade de ultrapassagem. Nao separa ultrapassagem em
    pista de troca por pit stop, entao mede *quanto a ordem se mexe*, nao
    quantas ultrapassagens houve. Os extremos observados confirmam que o proxy
    ordena corretamente: Monaco no fundo da lista, Spa no topo.
    """

    circuit_id: str
    changes_per_lap: float


@dataclass(frozen=True, slots=True)
class QualifyingObservation:
    """Melhor volta de classificacao e ritmo limpo de corrida do mesmo piloto."""

    qualifying_ms: int
    race_reference_ms: float


@dataclass(frozen=True, slots=True)
class TeamAttritionObservation:
    """Entradas e abandonos de uma equipe na era calibrada."""

    team_id: str
    name: str
    entries: int
    retirements: int


@dataclass(frozen=True, slots=True)
class AttritionObservation:
    """Contagem agregada de abandonos da era calibrada.

    ``contact_retirements`` conta os abandonos por colisao, dano de colisao,
    acidente ou rodada. Eles sao separados porque tem origem diferente no
    modelo: nao vem de uma falha do carro, vem de uma disputa de posicao.
    """

    entries: int
    retirements: int
    mean_race_laps: float
    contact_retirements: int = 0


@dataclass(frozen=True, slots=True)
class CalibrationInput:
    """Tudo que o adaptador precisa entregar para calibrar o modelo."""

    source_name: str
    source_version: int
    seasons: tuple[int, ...]
    laps: tuple[LapObservation, ...]
    pit_losses: tuple[PitLossObservation, ...]
    grid: tuple[GridObservation, ...]
    attrition: AttritionObservation
    pit_window_spread_laps: float
    position_churn: tuple[PositionChurnObservation, ...]
    qualifying: tuple[QualifyingObservation, ...]
    team_attrition: tuple[TeamAttritionObservation, ...]
    circuit_names: dict[str, str]


@dataclass(frozen=True, slots=True)
class CalibrationDiagnostics:
    """Evidencia que acompanha os coeficientes e permite critica-los.

    ``collinearity`` e a correlacao entre numero da volta e idade do pneu. Ela e
    naturalmente alta (o primeiro stint tem as duas contagens iguais), mas
    precisa ficar abaixo de 1 para que a regressao seja identificavel. Se
    aproximar-se de 1, os dois coeficientes deixam de ser separaveis e o
    resultado nao deve ser usado.
    """

    clean_laps: int
    races: int
    collinearity: float
    fuel_ms_per_lap: float
    tyre_ms_per_lap: float
    residual_sigma_ms: float
    residual_skew: float
    circuits_calibrated: int
    circuits_with_severity: int
    teams_calibrated: int


def _ols_two_slopes(
    rows: list[tuple[float, float, float]],
) -> tuple[float, float, float]:
    """Ajuste ``z = a*x + b*y`` sem intercepto e devolva ``(a, b, corr(x, y))``.

    Sem intercepto porque ``z`` ja vem centrado dentro de cada corrida/piloto.
    A solucao fechada de duas variaveis evita qualquer dependencia externa.
    """

    sxx = syy = sxy = sxz = syz = 0.0
    for x, y, z in rows:
        sxx += x * x
        syy += y * y
        sxy += x * y
        sxz += x * z
        syz += y * z
    determinant = sxx * syy - sxy * sxy
    correlation = abs(sxy) / (sxx * syy) ** 0.5 if sxx and syy else 1.0
    # Colinearidade praticamente perfeita significa que a amostra nao contem
    # paradas suficientes para separar os dois relogios. Recusar e melhor do que
    # devolver dois coeficientes enormes e de sinais opostos que somados
    # parecem ajustar bem os dados.
    if determinant == 0 or correlation > 0.999:
        raise ValueError(
            "regressao singular: volta e idade do pneu nao variam "
            "independentemente na amostra (correlacao "
            f"{correlation:.4f}). Sao necessarios stints multiplos."
        )
    a = (syy * sxz - sxy * syz) / determinant
    b = (sxx * syz - sxy * sxz) / determinant
    return a, b, correlation


def _successive_differences(
    grouped: dict[tuple[str, str], list[LapObservation]],
) -> list[float]:
    """Diferencas entre voltas limpas consecutivas do mesmo stint.

    Este e o estimador correto da perturbacao **independente** por volta, e a
    razao e importante: o residuo em torno da tendencia global contem tambem
    efeitos que variam devagar *dentro* da corrida -- trafego, economia de
    combustivel, gestao de pneu, safety car nao detectado. Esses efeitos sao
    persistentes, nao sorteios independentes.

    Medir a diferenca entre voltas vizinhas cancela qualquer componente que
    varie lentamente e deixa apenas a inovacao. Para ruido independente de
    desvio ``sigma``, a diferenca de duas voltas tem desvio ``sigma * sqrt(2)``,
    de onde ``sigma`` e recuperado.

    Usar o residuo bruto superestimaria a escala em cerca de tres vezes e
    injetaria no motor um passeio aleatorio que corridas reais nao apresentam.
    """

    differences: list[float] = []
    for observations in grouped.values():
        ordered = sorted(observations, key=lambda o: o.lap_number)
        for current, following in zip(ordered, ordered[1:]):
            same_stint = (
                following.lap_number == current.lap_number + 1
                and following.tyre_age_laps == current.tyre_age_laps + 1
            )
            if same_stint:
                differences.append(
                    float(following.lap_time_ms - current.lap_time_ms)
                )
    return differences


def _robust_scale_and_skew(differences: list[float]) -> tuple[float, float]:
    """Escala e assimetria da perturbacao, a partir das diferencas sucessivas.

    A escala usa o desvio absoluto mediano, convertido para desvio padrao
    equivalente e dividido por ``sqrt(2)`` para desfazer a diferenciacao. A
    mediana e usada em vez da media porque as voltas de safety car que o filtro
    nao identifica dominariam qualquer momento nao robusto.

    A assimetria compara as dispersoes dos dois lados. Se perder tempo for mais
    facil que ganhar, o lado positivo tera dispersao maior. Valores negativos
    sao truncados em zero: o modelo nao representa uma cauda rapida.
    """

    if len(differences) < 2:
        return 0.0, 0.0
    centre = statistics.median(differences)
    positive = [d - centre for d in differences if d > centre]
    negative = [centre - d for d in differences if d < centre]
    if not positive or not negative:
        return 0.0, 0.0
    spread = statistics.median([abs(d - centre) for d in differences])
    sigma = spread * MAD_TO_SIGMA / (2.0**0.5)
    mad_positive = statistics.median(positive)
    mad_negative = statistics.median(negative)
    total = mad_positive + mad_negative
    skew = (mad_positive - mad_negative) / total if total else 0.0
    return sigma, max(0.0, min(1.0, skew))



def _within_rows(observations: list[LapObservation]) -> list[tuple[float, float, float]]:
    """Centre lap, tyre age and time by the mean of their own driver-race group."""

    mean_lap = statistics.fmean(float(o.lap_number) for o in observations)
    mean_age = statistics.fmean(float(o.tyre_age_laps) for o in observations)
    mean_time = statistics.fmean(float(o.lap_time_ms) for o in observations)
    return [
        (
            o.lap_number - mean_lap,
            o.tyre_age_laps - mean_age,
            o.lap_time_ms - mean_time,
        )
        for o in observations
    ]


def _circuit_severity(
    grouped: dict[tuple[str, str], list[LapObservation]], field_slope: float
) -> dict[str, tuple[float, int]]:
    """Degradacao de cada circuito, relativa a do campo, com encolhimento.

    Roda a mesma regressao de dois relogios restrita a um circuito e divide o
    coeficiente de pneu pelo do campo inteiro. Um circuito com poucos stints
    produz uma estimativa ruidosa -- e chega a devolver inclinacao negativa --
    entao o resultado e puxado para 1.0 conforme a amostra encolhe e depois
    limitado a uma faixa fisicamente defensavel.

    Devolve ``{circuit_id: (severidade, voltas usadas)}``; circuitos onde a
    regressao e singular simplesmente nao aparecem.
    """

    by_circuit: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    for observations in grouped.values():
        if len(observations) < 10:
            continue
        by_circuit[observations[0].circuit_id].extend(_within_rows(observations))

    severities: dict[str, tuple[float, int]] = {}
    if field_slope <= 0:
        return severities
    for circuit_id, rows in by_circuit.items():
        try:
            _, slope, _ = _ols_two_slopes(rows)
        except ValueError:
            continue
        ratio = slope / field_slope
        weight = len(rows) / (len(rows) + SEVERITY_SHRINK_LAPS)
        shrunk = weight * ratio + (1.0 - weight) * 1.0
        severities[circuit_id] = (
            round(min(SEVERITY_MAX, max(SEVERITY_MIN, shrunk)), 3),
            len(rows),
        )
    return severities


def _overtaking_difficulty(
    churn: tuple[PositionChurnObservation, ...],
) -> dict[str, float]:
    """Traduz trocas de posicao por volta em dificuldade de ultrapassagem.

    A escala e relativa a mediana do campo: um circuito mediano recebe 0.5, um
    que mexe metade recebe 1.0 e um que mexe o dobro recebe 0.25. Usar a razao
    com a mediana, em vez de uma normalizacao entre minimo e maximo, impede que
    um unico evento atipico redefina a escala inteira.
    """

    by_circuit: dict[str, list[float]] = defaultdict(list)
    for observation in churn:
        by_circuit[observation.circuit_id].append(observation.changes_per_lap)
    averages = {
        circuit_id: statistics.fmean(values)
        for circuit_id, values in by_circuit.items()
        if values
    }
    if not averages:
        return {}
    field = statistics.median(averages.values())
    result = {}
    for circuit_id, value in averages.items():
        if value <= 0:
            continue
        raw = 0.5 * field / value
        result[circuit_id] = round(
            min(OVERTAKING_MAX, max(OVERTAKING_MIN, raw)), 3
        )
    return result


def _team_reliability(
    teams: tuple[TeamAttritionObservation, ...], field_rate: float
) -> tuple[TeamReliability, ...]:
    """Risco de abandono por equipe, encolhido para a media do campo.

    Uma equipe tem cerca de 44 entradas por temporada, o que torna a taxa bruta
    instavel: dois abandonos a mais mudam o numero em cinco pontos percentuais.
    O encolhimento bayesiano simples soma um prior equivalente a
    ``RELIABILITY_PRIOR_ENTRIES`` entradas na taxa do campo, o que preserva a
    ordem entre equipes sem exagerar os extremos.
    """

    if field_rate <= 0:
        return ()
    result = []
    for team in sorted(teams, key=lambda t: t.team_id):
        if team.entries < 1:
            continue
        shrunk = (team.retirements + RELIABILITY_PRIOR_ENTRIES * field_rate) / (
            team.entries + RELIABILITY_PRIOR_ENTRIES
        )
        result.append(
            TeamReliability(
                team_id=team.team_id,
                name=team.name,
                hazard_factor=round(shrunk / field_rate, 3),
                observed_entries=team.entries,
                retirements=team.retirements,
                origin="calibrated",
            )
        )
    return tuple(result)


def calibrate(
    data: CalibrationInput,
    *,
    version: str,
    calibrated_at: str | None = None,
    minimum_stops_per_circuit: int = 20,
) -> tuple[ModelParameters, CalibrationDiagnostics]:
    """Estime os parametros do modelo a partir das observacoes fornecidas.

    Erros de dado insuficiente sao levantados em vez de preenchidos com zero:
    um parametro ausente e uma condicao de dominio legivel, conforme exigido por
    ``docs/contrato-perfil-simulacao.md``.
    """

    if not data.laps:
        raise ValueError("a calibracao precisa de voltas limpas")
    if not data.pit_losses:
        raise ValueError("a calibracao precisa de paradas observadas")

    # Centragem dentro de (corrida, piloto): remove o ritmo do carro e do
    # circuito, deixando apenas a evolucao dentro da corrida.
    grouped: dict[tuple[str, str], list[LapObservation]] = defaultdict(list)
    for lap in data.laps:
        grouped[(lap.race_id, lap.driver_id)].append(lap)

    # Transformacao "within": as TRES variaveis sao centradas pela media do
    # proprio grupo (corrida, piloto). Centrar apenas o tempo e regredir sobre
    # numero de volta e idade brutos seria uma especificacao errada -- sobraria
    # em cada grupo um deslocamento constante que a reta pela origem nao
    # consegue absorver, e os coeficientes sairiam atenuados.
    #
    # A media (e nao a mediana) e usada porque e ela que torna a regressao pela
    # origem equivalente ao estimador com efeitos fixos por grupo. A robustez a
    # voltas anomalas vem do filtro de 107% aplicado antes, no adaptador.
    rows: list[tuple[float, float, float]] = []
    for observations in grouped.values():
        if len(observations) < 10:
            continue
        mean_lap = statistics.fmean(float(o.lap_number) for o in observations)
        mean_age = statistics.fmean(float(o.tyre_age_laps) for o in observations)
        mean_time = statistics.fmean(float(o.lap_time_ms) for o in observations)
        for o in observations:
            rows.append(
                (
                    o.lap_number - mean_lap,
                    o.tyre_age_laps - mean_age,
                    o.lap_time_ms - mean_time,
                )
            )
    if not rows:
        raise ValueError("nenhum par corrida/piloto com voltas limpas suficientes")

    fuel_slope, tyre_slope, collinearity = _ols_two_slopes(rows)
    sigma, skew = _robust_scale_and_skew(_successive_differences(grouped))

    # O combustivel deixa o carro mais rapido conforme queima, entao a
    # inclinacao medida e negativa. A penalidade por volta restante e o seu
    # simetrico. Uma inclinacao positiva significaria que o efeito nao foi
    # identificado nesta amostra; nesse caso a penalidade e zerada em vez de
    # inverter o sinal do fenomeno.
    fuel_penalty = max(0.0, -fuel_slope)
    tyre_degradation = max(0.0, tyre_slope)

    # Perda de boxes por circuito. A mediana e obrigatoria: a media e inflada
    # varias vezes por paradas sob bandeira vermelha, que ficam registradas com
    # duracao de varios minutos.
    by_circuit: dict[str, list[float]] = defaultdict(list)
    for stop in data.pit_losses:
        by_circuit[stop.circuit_id].append(stop.loss_ms)

    severities = _circuit_severity(grouped, tyre_degradation)
    difficulties = _overtaking_difficulty(data.position_churn)

    tracks: list[TrackParameters] = []
    for circuit_id, losses in sorted(by_circuit.items()):
        if len(losses) < minimum_stops_per_circuit:
            continue
        severity, _ = severities.get(circuit_id, (1.0, 0))
        tracks.append(
            TrackParameters(
                circuit_id=circuit_id,
                name=data.circuit_names.get(circuit_id, circuit_id),
                pit_loss_ms=round(statistics.median(losses), 1),
                tyre_severity=severity,
                overtaking_difficulty=difficulties.get(circuit_id, 0.5),
                origin="calibrated",
                observed_stops=len(losses),
            )
        )
    if not tracks:
        raise ValueError(
            f"nenhum circuito atingiu {minimum_stops_per_circuit} paradas observadas"
        )

    fallback = TrackParameters(
        circuit_id="__fallback__",
        name="mediana do campo",
        pit_loss_ms=round(statistics.median([t.pit_loss_ms for t in tracks]), 1),
        origin="assumed",
    )

    # Penalidade de largada: quanto a primeira volta custa a mais por posicao
    # perdida no grid.
    #
    # A regressao PRECISA de intercepto. A largada parada custa varios segundos
    # a *todos* os carros, inclusive ao pole-sitter; esse custo comum nao altera
    # posicoes relativas e pertence ao intercepto, nao a inclinacao. Forcar a
    # reta pela origem empurraria esse custo fixo para dentro do coeficiente e
    # inflaria a penalidade por posicao em quase uma ordem de grandeza.
    grid_penalty = 0.0
    if len(data.grid) > 1:
        xs = [float(g.grid_position - 1) for g in data.grid]
        ys = [g.first_lap_excess_ms for g in data.grid]
        mean_x = statistics.fmean(xs)
        mean_y = statistics.fmean(ys)
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        denominator = sum((x - mean_x) ** 2 for x in xs)
        if denominator:
            grid_penalty = max(0.0, numerator / denominator)

    # Risco de abandono por volta, convertido da taxa por corrida observada.
    rate = data.attrition.retirements / data.attrition.entries
    hazard = 1.0 - (1.0 - rate) ** (1.0 / data.attrition.mean_race_laps)
    reliability = _team_reliability(data.team_attrition, rate)
    contact_share = (
        data.attrition.contact_retirements / data.attrition.retirements
        if data.attrition.retirements
        else 0.0
    )

    # Razao entre ritmo de corrida e volta de classificacao. A mediana
    # protege contra sessoes de classificacao molhadas, em que a volta e
    # muito mais lenta que o ritmo de corrida e a razao cai abaixo de 1.
    ratios = [
        q.race_reference_ms / q.qualifying_ms
        for q in data.qualifying
        if q.qualifying_ms > 0 and q.race_reference_ms > 0
    ]
    qualifying_ratio = round(statistics.median(ratios), 4) if ratios else 1.05

    compounds = tuple(
        CompoundParameters(
            name=name,
            pace_offset_ms=offset,
            degradation_ms_per_lap=round(tyre_degradation * factor, 3),
            # O termo quadratico permanece zero: a amostra nao mostrou curvatura
            # separavel do ruido, e inventa-lo produziria um "penhasco" de
            # degradacao sem evidencia.
            degradation_ms_per_lap2=0.0,
            typical_stint_laps=max(5, round(22 / factor)),
            origin="assumed",
        )
        for name, (factor, offset) in COMPOUND_HYPOTHESIS.items()
    )

    parameters = ModelParameters(
        version=version,
        provenance=CalibrationProvenance(
            source_name=data.source_name,
            source_version=data.source_version,
            seasons=data.seasons,
            races=len({lap.race_id for lap in data.laps}),
            clean_laps=len(data.laps),
            calibrated_at=calibrated_at or date.today().isoformat(),
        ),
        fuel_penalty_ms_per_remaining_lap=round(fuel_penalty, 3),
        grid_penalty_ms_per_position=round(grid_penalty, 1),
        reference_compound="MEDIUM",
        compounds=compounds,
        tracks=tuple(tracks),
        fallback_track=fallback,
        team_reliability=reliability,
        lap_noise_ms=round(sigma, 1),
        lap_noise_skew=round(skew, 3),
        dnf_hazard_per_lap=round(hazard, 6),
        # Trafego nao e observavel no Trotman: nao ha distancia entre carros
        # volta a volta. Estes dois valores sao HIPOTESES, ancoradas na ordem de
        # grandeza publicada para perda em ar sujo (cerca de 0,3 a 0,5 s por
        # volta logo atras de outro carro), e nao no otimo do backtest.
        #
        # A varredura no conjunto de calibracao continuava melhorando ate 900 ms
        # com limiar de 2,5 s, mas esse ganho (menos de 2% de MAE) foi recusado
        # de proposito: com o efeito real invisivel nos dados, um coeficiente
        # inflado passaria a absorver outros fenomenos nao modelados. E o erro
        # que o plano descreve como "somar varios mecanismos que explicam a
        # mesma perda de tempo".
        traffic_penalty_ms=400.0,
        traffic_threshold_ms=1500.0,
        pit_window_spread_laps=round(data.pit_window_spread_laps, 2),
        qualifying_to_race_ratio=qualifying_ratio,
        contact_dnf_share=round(min(1.0, max(0.0, contact_share)), 3),
        # Disputa de posicao: o Trotman nao mede distancia entre carros,
        # entao estes tres sao hipoteses ajustadas contra uma grandeza que
        # ELE mede -- a taxa observada de troca entre carros vizinhos.
        # Escolhido pela plausibilidade fisica, nao pelo otimo da metrica:
        # a 1400 ms um carro 0,5 s/volta mais rapido passa em cerca de sete
        # voltas num circuito mediano. Valores muito acima exigiriam uma
        # vantagem irreal; muito abaixo tornariam a ultrapassagem gratuita.
        overtake_advantage_scale_ms=1400.0,
        minimum_gap_ms=700.0,
        # Ajustado para reproduzir a taxa de abandono observada na era
        # calibrada: com 0,0035 o motor retira 2,70 carros por corrida,
        # contra 2,70 observados em 2022-2023.
        collision_probability_per_dispute=0.0035,
    )

    diagnostics = CalibrationDiagnostics(
        clean_laps=len(rows),
        races=len({lap.race_id for lap in data.laps}),
        collinearity=round(collinearity, 4),
        fuel_ms_per_lap=round(fuel_slope, 2),
        tyre_ms_per_lap=round(tyre_slope, 2),
        residual_sigma_ms=round(sigma, 1),
        residual_skew=round(skew, 3),
        circuits_calibrated=len(tracks),
        circuits_with_severity=sum(
            1 for t in tracks if severities.get(t.circuit_id, (1.0, 0))[1]
        ),
        teams_calibrated=len(reliability),
    )
    return parameters, diagnostics
