"""Parametros versionados do modelo de tempo de volta.

Todo valor aqui e um *parametro de modelo*: ou foi estimado a partir do
historico canonico (``origin="calibrated"``), ou e uma hipotese explicita do
grupo (``origin="assumed"``). Nenhum deles e um fato observado do dataset --
essa distincao e exigida pelo plano do produto (secao 8.3) e por
``docs/planejamento-modelagem.md``.

Convencao de sinal, valida para todo o modelo: a *referencia* e uma volta
limpa, com pneu novo, carga baixa de combustivel e ar livre. Todas as parcelas
somadas a ela sao penalidades **nao negativas**. Isso evita contar duas vezes um
efeito que ja esteja embutido na referencia, risco registrado em
``docs/contrato-perfil-simulacao.md``.

Unidades explicitas: tempos em milissegundos, distancia em metros. Este modulo
nao le arquivos, banco nem rede; a desserializacao JSON fica no adaptador.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

ORIGINS = ("calibrated", "assumed")


def _positive(value: float, name: str) -> None:
    """Rejeite valores nao finitos ou nao positivos com mensagem nomeada."""

    if isinstance(value, bool) or not isfinite(value) or value <= 0:
        raise ValueError(f"{name} deve ser um numero positivo e finito")


def _non_negative(value: float, name: str) -> None:
    """Rejeite valores nao finitos ou negativos com mensagem nomeada."""

    if isinstance(value, bool) or not isfinite(value) or value < 0:
        raise ValueError(f"{name} deve ser um numero nao negativo e finito")


@dataclass(frozen=True, slots=True)
class CalibrationProvenance:
    """De onde vieram os coeficientes; acompanha o parametro, nao o substitui.

    ``seasons`` delimita a era usada. Misturar regulamentos diferentes invalida
    a comparacao (plano, secao 7.3), por isso a faixa fica registrada junto dos
    coeficientes e e reexibida em todo relatorio de backtest.
    """

    source_name: str
    source_version: int
    seasons: tuple[int, ...]
    races: int
    clean_laps: int
    calibrated_at: str

    def __post_init__(self) -> None:
        if not self.seasons:
            raise ValueError("a calibracao precisa declarar ao menos uma temporada")
        if self.races < 1 or self.clean_laps < 1:
            raise ValueError("a calibracao precisa de corridas e voltas positivas")


@dataclass(frozen=True, slots=True)
class CompoundParameters:
    """Ritmo e degradacao de um composto, relativos ao composto de referencia.

    ``pace_offset_ms`` e a diferenca de ritmo com pneu novo: negativo significa
    mais rapido que a referencia. E o unico campo do modelo que pode ser
    negativo, porque compara compostos entre si, nao contra a volta ideal.

    A degradacao segue ``a * idade + b * idade ** 2`` (plano, secao 8.2). Os
    coeficientes NAO sao universais: dependem de circuito, temperatura e carro.
    O Trotman v128 nao registra composto, entao a divisao entre compostos e uma
    hipotese do grupo, ancorada na degradacao media medida dentro dos stints.
    """

    name: str
    pace_offset_ms: float
    degradation_ms_per_lap: float
    degradation_ms_per_lap2: float
    typical_stint_laps: int
    origin: str = "assumed"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("o composto precisa de um nome")
        if self.origin not in ORIGINS:
            raise ValueError(f"origin deve estar em {ORIGINS}")
        if isinstance(self.pace_offset_ms, bool) or not isfinite(self.pace_offset_ms):
            raise ValueError("pace_offset_ms deve ser finito")
        _non_negative(self.degradation_ms_per_lap, "degradation_ms_per_lap")
        _non_negative(self.degradation_ms_per_lap2, "degradation_ms_per_lap2")
        if self.typical_stint_laps < 1:
            raise ValueError("typical_stint_laps deve ser positivo")


@dataclass(frozen=True, slots=True)
class TrackParameters:
    """Propriedades do circuito que afetam o modelo, nao a geometria desenhada.

    ``pit_loss_ms`` e uma propriedade do pit lane, portanto igual para todos os
    carros -- por isso este campo pertence ao circuito e nao ao piloto. E a
    perda total de passagem pelos boxes, medida como o atraso das voltas de
    entrada e saida em relacao ao ritmo limpo do proprio piloto.

    ``tyre_severity`` multiplica a degradacao dos compostos.
    ``overtaking_difficulty`` (0..1) escala a penalidade de trafego: 1 significa
    que o carro preso praticamente nao consegue passar.
    """

    circuit_id: str
    name: str
    pit_loss_ms: float
    tyre_severity: float = 1.0
    overtaking_difficulty: float = 0.5
    origin: str = "assumed"
    observed_stops: int = 0

    def __post_init__(self) -> None:
        if not self.circuit_id:
            raise ValueError("o circuito precisa de um identificador canonico")
        if self.origin not in ORIGINS:
            raise ValueError(f"origin deve estar em {ORIGINS}")
        _positive(self.pit_loss_ms, "pit_loss_ms")
        _positive(self.tyre_severity, "tyre_severity")
        if not 0.0 <= self.overtaking_difficulty <= 1.0:
            raise ValueError("overtaking_difficulty deve estar em [0, 1]")


@dataclass(frozen=True, slots=True)
class TeamReliability:
    """Risco de abandono de uma equipe, relativo a media do campo.

    ``hazard_factor`` multiplica ``dnf_hazard_per_lap``: 1.0 e a equipe media,
    acima de 1 quebra mais, abaixo quebra menos. O historico mostra uma faixa
    real de cerca de tres vezes entre a equipe mais e a menos confiavel de uma
    mesma era.

    Este parametro existe para responder a uma limitacao concreta do modelo
    anterior: com um risco unico para todos os carros, o motor acertava *quantos*
    abandonos ocorriam, mas nunca *quais* -- e errar qual carro quebra custa
    cerca de vinte posicoes de erro absoluto por evento.

    As contagens observadas acompanham o fator porque uma equipe com poucas
    entradas nao sustenta a mesma confianca que uma com uma temporada inteira.
    """

    team_id: str
    name: str
    hazard_factor: float
    observed_entries: int
    retirements: int
    origin: str = "calibrated"

    def __post_init__(self) -> None:
        if not self.team_id:
            raise ValueError("a equipe precisa de um identificador canonico")
        if self.origin not in ORIGINS:
            raise ValueError(f"origin deve estar em {ORIGINS}")
        _non_negative(self.hazard_factor, "hazard_factor")
        if self.observed_entries < 1:
            raise ValueError("observed_entries deve ser positivo")
        if self.retirements < 0 or self.retirements > self.observed_entries:
            raise ValueError("retirements deve estar entre 0 e observed_entries")


@dataclass(frozen=True, slots=True)
class ModelParameters:
    """Conjunto completo e versionado consumido pelo motor.

    ``fuel_penalty_ms_per_remaining_lap`` e positivo: representa quanto tempo o
    carro perde por volta ainda nao percorrida, por causa da massa de
    combustivel que ainda carrega. Na ultima volta a penalidade e zero, o que
    alinha a referencia com a volta mais leve da corrida.

    ``lap_noise_ms`` e a escala da perturbacao aleatoria por volta e
    ``lap_noise_skew`` a assimetria: tempos de volta tem piso fisico e cauda
    lenta, entao perder tempo e muito mais provavel que ganhar. Uma normal
    simetrica seria escolha por conveniencia, nao pelo residuo observado.

    ``dnf_hazard_per_lap`` e a probabilidade por volta de abandono, convertida
    da taxa historica por corrida; nao e uma constante escolhida no codigo.

    ``pit_window_spread_laps`` e o desvio tipico da volta de parada entre os
    carros de uma mesma corrida. Ele importa mais do que parece: se todos os
    carros param na mesma volta, a perda de boxes vira um deslocamento comum
    e desaparece da ordem de chegada. E o escalonamento das paradas que
    transforma a estrategia em trocas de posicao.

    ``overtake_advantage_scale_ms`` controla quanta vantagem de ritmo numa
    volta e precisa para ter chance razoavel de concluir uma ultrapassagem;
    ``minimum_gap_ms`` e a distancia minima, em tempo, entre dois carros
    consecutivos -- e ela que impede que ocupem o mesmo ponto da pista.

    ``contact_dnf_share`` divide o risco de abandono entre falha mecanica e
    contato. O contato nao e sorteado por volta: ele so pode ocorrer durante
    uma disputa, com probabilidade ``collision_probability_per_dispute``, o
    que torna o risco endogeno ao trafego -- quem briga no pelotao bate mais
    do que quem lidera sozinho.

    ``qualifying_to_race_ratio`` converte a melhor volta de classificacao no
    ritmo limpo esperado na corrida. A classificacao acontece ANTES da
    largada, entao usa-la para estimar o ritmo nao e vazamento: e a unica
    medida de velocidade especifica daquele fim de semana disponivel sem
    olhar o resultado. Um perfil de temporada, por melhor que seja, nao
    captura se o carro foi bem justamente naquele circuito.

    ``grid_penalty_ms_per_position`` traduz a posicao de largada em um atraso
    inicial de relogio. Sem ele o grid seria irrelevante e o carro mais rapido
    venceria sempre, o que contraria o historico: posicao de pista e uma das
    variaveis mais fortes do resultado de uma corrida de Formula 1.
    """

    version: str
    provenance: CalibrationProvenance
    fuel_penalty_ms_per_remaining_lap: float
    grid_penalty_ms_per_position: float
    reference_compound: str
    compounds: tuple[CompoundParameters, ...]
    tracks: tuple[TrackParameters, ...]
    fallback_track: TrackParameters
    team_reliability: tuple[TeamReliability, ...]
    lap_noise_ms: float
    lap_noise_skew: float
    dnf_hazard_per_lap: float
    traffic_penalty_ms: float
    traffic_threshold_ms: float
    pit_window_spread_laps: float
    qualifying_to_race_ratio: float
    overtake_advantage_scale_ms: float
    minimum_gap_ms: float
    collision_probability_per_dispute: float
    contact_dnf_share: float

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("os parametros precisam de uma versao")
        if not self.compounds:
            raise ValueError("e necessario ao menos um composto")
        names = [c.name for c in self.compounds]
        if len(set(names)) != len(names):
            raise ValueError(f"composto duplicado em {names}")
        if self.reference_compound not in names:
            raise ValueError(
                f"reference_compound {self.reference_compound!r} nao esta em {names}"
            )
        ids = [t.circuit_id for t in self.tracks]
        if len(set(ids)) != len(ids):
            raise ValueError("circuit_id duplicado em tracks")
        team_ids = [t.team_id for t in self.team_reliability]
        if len(set(team_ids)) != len(team_ids):
            raise ValueError("team_id duplicado em team_reliability")
        _non_negative(
            self.fuel_penalty_ms_per_remaining_lap,
            "fuel_penalty_ms_per_remaining_lap",
        )
        _non_negative(
            self.grid_penalty_ms_per_position, "grid_penalty_ms_per_position"
        )
        _non_negative(self.lap_noise_ms, "lap_noise_ms")
        _non_negative(self.traffic_penalty_ms, "traffic_penalty_ms")
        _non_negative(self.traffic_threshold_ms, "traffic_threshold_ms")
        _non_negative(self.pit_window_spread_laps, "pit_window_spread_laps")
        _positive(self.qualifying_to_race_ratio, "qualifying_to_race_ratio")
        _non_negative(
            self.overtake_advantage_scale_ms, "overtake_advantage_scale_ms"
        )
        _non_negative(self.minimum_gap_ms, "minimum_gap_ms")
        if not 0.0 <= self.collision_probability_per_dispute < 1.0:
            raise ValueError(
                "collision_probability_per_dispute deve estar em [0, 1)"
            )
        if not 0.0 <= self.contact_dnf_share <= 1.0:
            raise ValueError("contact_dnf_share deve estar em [0, 1]")
        if not 0.0 <= self.dnf_hazard_per_lap < 1.0:
            raise ValueError("dnf_hazard_per_lap deve estar em [0, 1)")
        if not 0.0 <= self.lap_noise_skew <= 1.0:
            raise ValueError("lap_noise_skew deve estar em [0, 1]")

    def compound(self, name: str) -> CompoundParameters:
        """Devolva o composto pelo nome; desconhecido e erro, nunca um padrao.

        Substituir um composto ausente por outro silenciosamente esconderia um
        cenario mal configurado atras de um resultado plausivel.
        """

        for candidate in self.compounds:
            if candidate.name == name:
                return candidate
        raise KeyError(
            f"composto {name!r} nao existe em {[c.name for c in self.compounds]}"
        )

    def mechanical_hazard_per_lap(self) -> float:
        """Parcela do risco de abandono que nao depende de disputa.

        O contato e modelado separadamente, em ``domain/disputes.py``, e sai
        desta conta para nao ser contado duas vezes.
        """

        return self.dnf_hazard_per_lap * (1.0 - self.contact_dnf_share)

    def reliability_factor(self, team_id: str | None) -> float:
        """Fator de risco da equipe; 1.0 quando ela nao foi calibrada.

        Equipes trocam de nome e de identificador entre temporadas (Alfa Romeo
        vira Sauber, AlphaTauri vira RB). Uma equipe ausente da calibracao
        recebe o risco medio do campo em vez de um erro: o cenario continua
        executavel e o relatorio consegue apontar quantos carros cairam nesse
        caso.
        """

        if team_id:
            for candidate in self.team_reliability:
                if candidate.team_id == team_id:
                    return candidate.hazard_factor
        return 1.0

    def track(self, circuit_id: str) -> TrackParameters:
        """Devolva o circuito calibrado ou o fallback declarado.

        O fallback e legitimo e rastreavel: ele carrega ``origin="assumed"``, de
        modo que o relatorio consegue distinguir um circuito medido de um
        circuito representado pela mediana do campo.
        """

        for candidate in self.tracks:
            if candidate.circuit_id == circuit_id:
                return candidate
        return self.fallback_track
