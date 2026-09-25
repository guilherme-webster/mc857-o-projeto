"""Nucleo minimo da simulacao de corrida: deterministico por padrao.

Por padrao, este core considera apenas o ritmo do piloto: cada carro percorre
todas as voltas a um tempo de volta constante (``base_lap_time_ms``, derivado do
ETL). A posicao por volta emerge do tempo total acumulado -- quem soma menos
tempo lidera.

Duas fontes de variacao sao opcionais e ficam DESLIGADAS a menos que o chamador
as peca explicitamente (PRD ``nao-determinismo-pneus-assumidos``):

* um desgaste linear de pneu (``tyre_plan``), com parametros de
  :mod:`f1_simulator.domain.tyres`;
* um ruido aleatorio por volta (``variability`` + ``rng``), sorteado por uma
  :class:`~f1_simulator.domain.random_source.RandomSource` injetada.

Os parametros dessas duas fontes sao HIPOTESES assumidas e rotuladas como tal
(``source_kind``); nenhum foi calibrado com dados. Por isso o resultado ativo
sempre carrega a lista ``assumptions``, e nada aqui deve ser apresentado como
medicao.

Fronteiras (ADR 0002 / AGENTS.md): o core e a fonte de verdade da classificacao
e nao conhece Arcade, FastAPI, SQLite nem formatos de dados. A aleatoriedade e
sempre injetada (nunca ha sorteio global nem semente escolhida aqui), de modo que
a mesma semente reproduz o resultado inteiro. Pit stop, abandono e geometria da
pista continuam deliberadamente fora de escopo. Tempos em milissegundos.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Literal

from f1_simulator.domain.random_source import (
    RandomSource,
    truncated_standard_normal,
)
from f1_simulator.domain.tyres import (
    ASSUMED_DRY_TYRES,
    TyreModelParameters,
    TyreState,
    tyre_effect_ms,
    tyre_parameters_for,
)


@dataclass(frozen=True, slots=True)
class Competitor:
    """Um participante e seu unico atributo nesta fatia: o ritmo constante.

    ``lap_time_ms`` e o tempo de volta constante do carro, em milissegundos.
    Deve ser estritamente positivo; pilotos sem ritmo derivavel do ETL nao
    entram na simulacao e devem ser filtrados antes de chegar aqui.

    Quando um modelo de pneu esta ativo (``tyre_plan``), ``lap_time_ms`` passa a
    significar o tempo de volta NO PONTO DE ANCORAGEM do pneu (efeito de pneu
    zero). O efeito de idade e somado por cima; se o ritmo informado ja embutisse
    o desgaste, ele seria contado duas vezes, por isso o contrato exige que o
    chamador informe o ritmo de referencia.
    """

    driver_id: str
    name: str
    lap_time_ms: float


@dataclass(frozen=True, slots=True)
class LapPosition:
    """Estado classificatorio de um carro ao fim de uma volta."""

    position: int
    driver_id: str
    name: str
    total_time_ms: float


@dataclass(frozen=True, slots=True)
class LapTimeBreakdown:
    """Decomposicao do tempo de uma volta, em milissegundos.

    ``reference_ms`` e o ritmo do competidor no ponto de ancoragem. Os outros
    dois componentes valem ``None`` quando a corrida NAO os modela: um efeito
    nao modelado nao e o mesmo que um efeito medido igual a zero, e o
    AGENTS.md proibe preencher ausencia com zero. O tempo da volta soma apenas
    os componentes presentes.
    """

    reference_ms: float
    tyre_effect_ms: float | None
    noise_ms: float | None

    @property
    def lap_time_ms(self) -> float:
        """Some referencia, efeito de pneu e ruido (componentes ausentes valem 0)."""

        total = self.reference_ms
        if self.tyre_effect_ms is not None:
            total += self.tyre_effect_ms
        if self.noise_ms is not None:
            total += self.noise_ms
        return total


@dataclass(frozen=True, slots=True)
class LapVariabilityAssumption:
    """Ruido por volta assumido: dispersao proporcional ao tempo de referencia.

    ``sigma_pct_of_reference`` e o desvio padrao do ruido, em percentual do
    tempo de referencia da volta. ``truncation_sigmas`` limita o sorteio a
    +/- esse numero de desvios (regra documentada e parametrizada, nao um clamp
    escondido). Nao e uma medida calibrada: o MAD dos perfis de pilotos mede
    dispersao observada e NAO pode ser convertido em ruido de simulacao.
    """

    sigma_pct_of_reference: float
    truncation_sigmas: float
    source_kind: Literal["assumed", "estimated"]
    parameter_version: str
    rationale: str

    def __post_init__(self) -> None:
        for name in ("sigma_pct_of_reference", "truncation_sigmas"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name} deve ser positivo e finito")
        for name in ("source_kind", "parameter_version", "rationale"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} deve ser uma string nao vazia")
        if self.source_kind not in ("assumed", "estimated"):
            raise ValueError("source_kind deve ser 'assumed' ou 'estimated'")


ASSUMED_LAP_VARIABILITY = LapVariabilityAssumption(
    sigma_pct_of_reference=0.2,
    truncation_sigmas=3.0,
    source_kind="assumed",
    parameter_version="assumed-lap-noise-v1",
    rationale=(
        "Hipotese assumida, nao calibrada: 0,2% do tempo de referencia, truncada "
        "em 3 desvios. O MAD dos perfis de pilotos mede dispersao observada e "
        "nao pode ser convertido em ruido de simulacao."
    ),
)


def simulate_race(
    competitors: tuple[Competitor, ...] | list[Competitor],
    total_laps: int,
    *,
    tyre_plan: Mapping[str, str] | None = None,
    variability: LapVariabilityAssumption | None = None,
    rng: RandomSource | None = None,
    tyre_catalogue: tuple[TyreModelParameters, ...] = ASSUMED_DRY_TYRES,
) -> dict:
    """Simule ``total_laps`` voltas e retorne as posicoes por volta.

    **Modo padrao** (sem ``tyre_plan`` nem ``variability``): a cada volta, cada
    carro soma seu ``lap_time_ms`` constante ao tempo total, e os carros sao
    ordenados pelo tempo acumulado (menor tempo = frente). O resultado e
    deterministico e independe da ordem de entrada dos competidores; empates de
    tempo sao desempatados por ``driver_id`` para ser reproduzivel.

    **Modo com modelo** (qualquer um dos dois opcionais ativo):

    * ``tyre_plan`` mapeia ``driver_id -> composto``, um composto por corrida e
      SEM pit stop. Deve cobrir TODOS os competidores e nenhum ``driver_id``
      desconhecido (ausencia nunca vira efeito zero). A idade do pneu na volta
      ``k`` e ``k - 1`` (a primeira volta tem idade zero, convencao de
      :mod:`f1_simulator.domain.tyres`). Idade fora da faixa de suporte levanta
      ``ValueError``; nao ha clamp nem extrapolacao.
    * ``variability`` exige ``rng`` e vice-versa: um ``rng`` sem ``variability``
      seria ignorado em silencio, o que esconderia um erro de configuracao.
      O ruido da volta e ``sigma_pct/100 * referencia * z``, com ``z`` normal
      padrao truncada. Para a saida nao depender da ordem de entrada, os sorteios
      seguem voltas crescentes e, dentro de cada volta, ``driver_id`` crescente,
      com a ``label`` ``lap:<volta>:<driver_id>`` (o ``driver_id`` canonico ja
      carrega o prefixo ``driver:``, entao nao ha prefixo repetido).

    Retorna um dicionario pronto para transporte JSON::

        {
            "total_laps": int,
            "history": [
                {"lap": int, "cars": [
                    {"position", "driver_id", "name", "total_time_ms",
                     "lap_time_ms"[, "breakdown"]}, ...
                ]},
                ...
            ],
            "classification": [ ...mesma forma dos cars da ultima volta... ],
            "assumptions": [...],   # somente quando um modelo esta ativo
        }

    No modo padrao a estrutura e exatamente a original (sem ``breakdown`` nem
    ``assumptions``, ``lap_time_ms`` inalterado). No modo com modelo,
    ``lap_time_ms`` e o tempo REAL da volta arredondado a 0,1 ms, tal como
    ``total_time_ms``, e ``breakdown`` traz ``reference_ms``, ``tyre_effect_ms``
    e ``noise_ms`` sem arredondar (``None`` para o que nao foi modelado).
    ``assumptions`` lista, de forma ordenada, os parametros usados com seu
    ``source_kind`` para que nada assumido seja lido como calibrado.

    A aritmetica e em ``float`` (decisao D1 do PRD): a unificacao de precisao com
    ``Decimal`` fica para quando os perfis entrarem no motor.

    ``total_laps`` deve ser positivo. Uma lista vazia de competidores produz um
    historico com voltas sem carros, o que mantem o contrato simples e explicito.
    """

    if total_laps <= 0:
        raise ValueError("total_laps deve ser positivo")

    seen: set[str] = set()
    for competitor in competitors:
        if competitor.lap_time_ms <= 0:
            raise ValueError(
                f"lap_time_ms deve ser positivo para {competitor.driver_id}"
            )
        if competitor.driver_id in seen:
            raise ValueError(f"driver_id duplicado: {competitor.driver_id}")
        seen.add(competitor.driver_id)

    if variability is not None and rng is None:
        raise ValueError("variability exige um rng injetado")
    if rng is not None and variability is None:
        raise ValueError(
            "rng informado sem variability: o sorteio seria ignorado em silencio"
        )

    tyre_parameters = _resolve_tyre_parameters(
        competitors, tyre_plan, tyre_catalogue, total_laps
    )
    model_active = tyre_plan is not None or variability is not None

    totals: dict[str, float] = {c.driver_id: 0.0 for c in competitors}

    # Ordem canonica dos sorteios: independe da ordem de entrada dos competidores.
    draw_order = sorted(competitors, key=lambda c: c.driver_id)

    history = []
    for lap in range(1, total_laps + 1):
        lap_times: dict[str, float] = {}
        breakdowns: dict[str, LapTimeBreakdown] = {}
        for competitor in draw_order:
            if model_active:
                breakdown = _lap_breakdown(
                    competitor,
                    lap,
                    tyre_parameters.get(competitor.driver_id),
                    variability,
                    rng,
                )
                lap_time = breakdown.lap_time_ms
                if not isfinite(lap_time) or lap_time <= 0:
                    raise ValueError(
                        f"tempo de volta nao positivo ou invalido para "
                        f"{competitor.driver_id} na volta {lap}: {lap_time}"
                    )
                breakdowns[competitor.driver_id] = breakdown
            else:
                lap_time = competitor.lap_time_ms
            lap_times[competitor.driver_id] = lap_time
            totals[competitor.driver_id] += lap_time
        history.append(
            {
                "lap": lap,
                "cars": _classify(
                    competitors, totals, lap_times, breakdowns, model_active
                ),
            }
        )

    classification = history[-1]["cars"] if history else []
    result: dict = {
        "total_laps": total_laps,
        "history": history,
        "classification": classification,
    }
    if model_active:
        result["assumptions"] = _assumptions(tyre_parameters, variability)
    return result


def _resolve_tyre_parameters(
    competitors: tuple[Competitor, ...] | list[Competitor],
    tyre_plan: Mapping[str, str] | None,
    catalogue: tuple[TyreModelParameters, ...],
    total_laps: int,
) -> dict[str, TyreModelParameters]:
    """Valide o plano de pneus e resolva os parametros de cada competidor.

    Falha cedo, antes de qualquer volta: plano incompleto, ``driver_id``
    desconhecido, composto fora do catalogo ou corrida mais longa que o suporte
    do pneu. Sem plano, devolve um mapa vazio (nenhum pneu e modelado).
    """

    if tyre_plan is None:
        return {}

    known_ids = {c.driver_id for c in competitors}
    planned_ids = set(tyre_plan)
    unknown = sorted(planned_ids - known_ids)
    if unknown:
        raise ValueError(f"tyre_plan com driver_id desconhecido: {unknown}")
    missing = sorted(known_ids - planned_ids)
    if missing:
        raise ValueError(
            f"tyre_plan deve cobrir todos os competidores; faltam: {missing}"
        )

    resolved: dict[str, TyreModelParameters] = {}
    for driver_id in sorted(known_ids):
        parameters = tyre_parameters_for(tyre_plan[driver_id], catalogue)
        # Sem pit stop, a idade cresce ate total_laps - 1: precisa caber no suporte.
        if total_laps - 1 > parameters.max_age_laps:
            raise ValueError(
                f"corrida de {total_laps} voltas excede o suporte do pneu "
                f"{parameters.compound} para {driver_id} "
                f"(idade maxima {parameters.max_age_laps})"
            )
        resolved[driver_id] = parameters
    return resolved


def _lap_breakdown(
    competitor: Competitor,
    lap: int,
    tyre_parameters: TyreModelParameters | None,
    variability: LapVariabilityAssumption | None,
    rng: RandomSource | None,
) -> LapTimeBreakdown:
    """Componha o tempo de uma volta; o que nao e modelado permanece ``None``."""

    tyre_effect: float | None = None
    if tyre_parameters is not None:
        state = TyreState(tyre_parameters.compound, lap - 1)
        tyre_effect = tyre_effect_ms(tyre_parameters, state)

    noise: float | None = None
    if variability is not None and rng is not None:
        z = truncated_standard_normal(
            rng,
            f"lap:{lap}:{competitor.driver_id}",
            variability.truncation_sigmas,
        )
        noise = (
            variability.sigma_pct_of_reference / 100.0
            * competitor.lap_time_ms
            * z
        )

    return LapTimeBreakdown(competitor.lap_time_ms, tyre_effect, noise)


def _assumptions(
    tyre_parameters: Mapping[str, TyreModelParameters],
    variability: LapVariabilityAssumption | None,
) -> list[dict]:
    """Liste, em ordem deterministica, os parametros assumidos realmente usados."""

    items: list[dict] = []
    by_compound = {p.compound: p for p in tyre_parameters.values()}
    for compound in sorted(by_compound):
        parameters = by_compound[compound]
        items.append(
            {
                "kind": "tyre",
                "compound": parameters.compound,
                "source_kind": parameters.source_kind,
                "parameter_version": parameters.parameter_version,
                "rationale": parameters.rationale,
                "anchor_age_laps": parameters.anchor_age_laps,
                "min_age_laps": parameters.min_age_laps,
                "max_age_laps": parameters.max_age_laps,
                "linear_ms_per_lap": parameters.linear_ms_per_lap,
            }
        )
    if variability is not None:
        items.append(
            {
                "kind": "lap_variability",
                "source_kind": variability.source_kind,
                "parameter_version": variability.parameter_version,
                "rationale": variability.rationale,
                "sigma_pct_of_reference": variability.sigma_pct_of_reference,
                "truncation_sigmas": variability.truncation_sigmas,
            }
        )
    return items


def _classify(
    competitors: tuple[Competitor, ...] | list[Competitor],
    totals: dict[str, float],
    lap_times: dict[str, float],
    breakdowns: dict[str, LapTimeBreakdown],
    model_active: bool,
) -> list[dict]:
    """Ordene por tempo acumulado (desempate por driver_id) e atribua posicoes.

    No modo padrao, ``lap_time_ms`` e o valor original do competidor, sem
    arredondar; no modo com modelo, e o tempo real da volta a 0,1 ms.
    """

    ordered = sorted(
        competitors, key=lambda c: (totals[c.driver_id], c.driver_id)
    )
    cars = []
    for index, competitor in enumerate(ordered, start=1):
        lap_time = lap_times[competitor.driver_id]
        car = {
            "position": index,
            "driver_id": competitor.driver_id,
            "name": competitor.name,
            "total_time_ms": round(totals[competitor.driver_id], 1),
            "lap_time_ms": round(lap_time, 1) if model_active else lap_time,
        }
        if model_active:
            breakdown = breakdowns[competitor.driver_id]
            car["breakdown"] = {
                "reference_ms": breakdown.reference_ms,
                "tyre_effect_ms": breakdown.tyre_effect_ms,
                "noise_ms": breakdown.noise_ms,
            }
        cars.append(car)
    return cars
