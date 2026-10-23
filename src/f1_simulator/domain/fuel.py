"""Combustivel como massa embarcada em cada carro, consumida volta a volta.

Fisica adotada (era 2022-2025 do regulamento)
---------------------------------------------
- **Carga planejada para a corrida, ate 110 kg.** Cada carro larga com o
  combustivel da distancia que vai correr mais uma reserva, limitado pelo teto
  de 110 kg. Numa corrida de distancia real (~305 km) isso sempre cabe.
- **Reabastecimento e uma regra do cenario** (``refuelling_allowed``), nao do
  regulamento atual, que o proibe desde 2010. Ligado (decisao do grupo), vale
  a logica da era 1994-2009: toda parada troca pneus e reabastece, e quando
  parar e quanto colocar sao decisoes estrategicas de cada piloto
  (``HeuristicPitStrategy`` em ``domain/strategy.py``), pesando desgaste,
  peso do combustivel e custo da parada. O unico limite fisico e chegar a
  entrada dos boxes (``FuelPlan.must_pit``). A parada custa o tempo *daquele
  carro* (``RefuelStops``) mais o tempo de abastecer alem da troca de pneus.
  Desligado, vale a regra de 2010+: o carro economiza (lift-and-coast) ate o
  limite e, se ainda faltar, fica sem combustivel e abandona.
- **O consumo depende da distancia**, nao do numero de voltas configurado: uma
  volta em Spa (7 km) queima o dobro de uma volta em Monaco (3,3 km). Sob SC,
  VSC e bandeira vermelha o ritmo cai e o consumo por volta tambem.
- **O custo de tempo e proporcional a massa e a duracao da volta.** Carregar
  1 kg custa uma *fracao* do tempo de volta; em voltas longas a mesma massa
  custa mais milissegundos.

Passo de integracao
-------------------
O motor e discreto por volta, e a volta e o passo de integracao: o consumo e
constante dentro de uma volta sob o mesmo estado de pista, entao subtrair a
queima uma vez por volta e exato. Nao existe "frame" no nucleo; a interface,
que interpola a posicao linearmente entre fins de volta, pode interpolar a
massa da mesma forma para um medidor continuo.

O que foi medido e o que foi assumido
-------------------------------------
O Trotman v128 nao registra combustivel. O que os tempos de volta identificam
e o **produto** sensibilidade x consumo: quanto do tempo de volta se perde por
km de combustivel embarcado (``lap_time_fraction_per_fuel_km``, calibrado em
``application/calibrate_fuel.py``). A divisao desse produto entre kg/km e
ms/kg vem do regulamento e de uma hipotese de consumo (``burn_kg_per_km``).
Essa hipotese nao altera nenhum tempo de volta numa corrida limpa -- so o teto
de 110 kg, a economia e o valor exibido em kg dependem dela.

Ancora: a penalidade usa a massa ao **fim** da volta acima da reserva final.
Numa corrida limpa a ultima volta tem penalidade zero, a mesma ancora da
``reference_ms`` e de ``fuel_penalty_ms``; por isso, com o mesmo produto, o
modelo de massa reproduz exatamente o modelo linear legado. A diferenca para a
massa media da volta e uma constante (meia volta de queima) que desloca todos
os carros igualmente e ja esta absorvida na referencia.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from f1_simulator.domain.model_parameters import CalibrationProvenance
from f1_simulator.domain.random_source import RandomSource

#: Massa maxima de combustivel por corrida no regulamento tecnico 2022-2025.
REGULATION_MAX_FUEL_KG = 110.0

#: Abaixo deste deficit (kg) a economia e considerada ruido de ponto flutuante:
#: a subtracao repetida da queima pode deixar 1e-13 kg abaixo da reserva.
_DEFICIT_TOLERANCE_KG = 1e-9

FuelLengthSource = Literal["track_geometry", "reference_pace"]


def _positive(value: float, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{name} deve ser um numero positivo e finito")


def _non_negative(value: float, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{name} deve ser um numero nao negativo e finito")


def _fraction(value: float, name: str) -> None:
    _non_negative(value, name)
    if value > 1.0:
        raise ValueError(f"{name} deve estar em [0, 1]")


@dataclass(frozen=True, slots=True)
class TeamPitOffset:
    """Quanto o pit lane de uma equipe difere da mediana da corrida (ms).

    Medido nas paradas do Trotman como a mediana de ``duracao - mediana da
    corrida``: subtrair a mediana da corrida remove o comprimento do pit lane
    de cada circuito, e o que sobra e o tempo parado e a execucao da equipe.
    Negativo e mais rapido que o campo.
    """

    team_id: str
    name: str
    offset_ms: float
    stops: int

    def __post_init__(self) -> None:
        if not isinstance(self.team_id, str) or not self.team_id.strip():
            raise ValueError("team_id deve ser texto nao vazio")
        if isinstance(self.offset_ms, bool) or not isfinite(self.offset_ms):
            raise ValueError("offset_ms deve ser finito")
        if type(self.stops) is not int or self.stops < 1:
            raise ValueError("stops deve ser um inteiro positivo")


@dataclass(frozen=True, slots=True)
class RefuelStopParameters:
    """Tempo de parada por carro, calibrado nas paradas reais do Trotman.

    A perda media de um carro e ``pit_loss_ms`` do circuito (calibrado no
    ``model-v1.json``) mais o deslocamento da sua equipe vezes
    ``persistence``. A persistencia (0..1) e a fracao do deslocamento de uma
    temporada que se repete na seguinte, medida no historico: equipes mudam
    de equipamento e de pessoal, e um deslocamento cru exageraria a diferenca
    prevista. Equipe sem calibracao recebe o campo medio (deslocamento zero).

    Cada parada varia em torno da media por uma normal assimetrica
    (``stop_sigma_ms`` e ``stop_skew``, mesma construcao do ruido de volta):
    paradas lentas sao mais comuns que paradas excepcionalmente rapidas.
    """

    provenance: CalibrationProvenance
    team_offsets: tuple[TeamPitOffset, ...]
    persistence: float
    stop_sigma_ms: float
    stop_skew: float
    origin: Literal["calibrated", "assumed"] = "calibrated"

    def __post_init__(self) -> None:
        ids = [item.team_id for item in self.team_offsets]
        if len(set(ids)) != len(ids):
            raise ValueError("team_id duplicado em team_offsets")
        _fraction(self.persistence, "persistence")
        _non_negative(self.stop_sigma_ms, "stop_sigma_ms")
        _fraction(self.stop_skew, "stop_skew")
        if self.origin not in ("calibrated", "assumed"):
            raise ValueError("origin deve ser 'calibrated' ou 'assumed'")

    def offset_ms(self, team_id: str | None) -> float:
        """Deslocamento previsto da equipe; zero quando nao calibrada."""

        for item in self.team_offsets:
            if item.team_id == team_id:
                return item.offset_ms * self.persistence
        return 0.0


@dataclass(frozen=True, slots=True)
class RefuelStops:
    """Perda de tempo de cada parada de reabastecimento de um carro (ms).

    ``sampled_ms[i]`` e a perda da parada ``i`` (zero-based); paradas alem da
    amostra usam ``mean_ms``. Os valores sao sorteados antes da corrida por
    quem monta o cenario, num fluxo aleatorio proprio do carro: o motor nao
    sorteia nada para o reabastecimento, e o numero de paradas nao desloca
    ruido, incidentes ou controle de prova.
    """

    mean_ms: float
    sampled_ms: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        _positive(self.mean_ms, "mean_ms")
        for value in self.sampled_ms:
            _positive(value, "sampled_ms")

    def loss_ms(self, stop_index: int) -> float:
        if type(stop_index) is not int or stop_index < 0:
            raise ValueError("stop_index deve ser um inteiro nao negativo")
        if stop_index < len(self.sampled_ms):
            return self.sampled_ms[stop_index]
        return self.mean_ms


def sample_refuel_stops(
    mean_ms: float,
    parameters: RefuelStopParameters | None,
    rng: RandomSource,
    count: int,
    label: str,
) -> RefuelStops:
    """Sorteie ``count`` perdas de parada em torno de ``mean_ms``.

    O piso de metade da media so impede que uma cauda extrema produza uma
    parada fisicamente impossivel; com o desvio calibrado (~0,6 s numa perda
    de ~23 s) ele nunca e atingido na pratica.
    """

    _positive(mean_ms, "mean_ms")
    if type(count) is not int or count < 0:
        raise ValueError("count deve ser um inteiro nao negativo")
    if parameters is None or parameters.stop_sigma_ms == 0.0:
        return RefuelStops(mean_ms, (mean_ms,) * count)
    samples = []
    for index in range(count):
        z = rng.standard_normal(f"{label}:stop:{index}")
        scale = 1.0 + parameters.stop_skew if z > 0 else 1.0 - parameters.stop_skew
        samples.append(max(0.5 * mean_ms, mean_ms + z * parameters.stop_sigma_ms * scale))
    return RefuelStops(mean_ms, tuple(samples))


@dataclass(frozen=True, slots=True)
class FuelModelParameters:
    """Parametros versionados do combustivel, com a origem de cada grupo.

    Calibrado (Trotman v128):

    - ``lap_time_fraction_per_fuel_km``: fracao do tempo de volta perdida por
      carregar o combustivel de 1 km. Ex.: 1.27e-4 numa volta de 90 s e 5 km
      custa 57 ms por volta restante.

    Regulamento:

    - ``max_fuel_kg``: teto da carga de corrida (110 kg).

    Hipoteses (``assumed``), nao observaveis no Trotman:

    - ``burn_kg_per_km``: consumo em bandeira verde. 105 kg em 305 km, a
      distancia minima de um GP, e uma carga tipica abaixo do teto.
    - ``finish_reserve_kg``: sobra planejada na bandeirada; cobre a amostra de
      1 litro (~0,75 kg) exigida pela FIA.
    - ``vsc_burn_factor``, ``sc_burn_factor``, ``red_flag_burn_factor``:
      consumo relativo por volta neutralizada. A volta de bandeira vermelha do
      motor representa a ida lenta ao pit lane.
    - ``lift_coast_max_saving_fraction`` e ``lift_coast_ms_per_kg_saved``:
      quanto do consumo da volta o piloto consegue economizar tirando o pe e
      quanto tempo isso custa. So entram quando falta combustivel e o
      reabastecimento esta desligado.
    - ``refuel_rate_kg_per_s``: vazao do equipamento de reabastecimento da
      era 1994-2009 (~12 L/s de gasolina a ~0,75 kg/L).
    - ``tyre_change_ms``: tempo parado de uma troca de pneus moderna. A perda
      de boxes medida ja contem uma troca; o reabastecimento so acrescenta o
      que passar disso, porque pneus e combustivel sao feitos ao mesmo tempo.

    Regra do cenario:

    - ``refuelling_allowed``: liga o reabastecimento. Toda parada passa a
      trocar pneus e reabastecer, e a estrategia do piloto decide quando parar
      e quanto colocar. ``refuel_stops`` traz o tempo de parada por equipe;
      ``None`` usa a perda de boxes do circuito para todos.
    """

    version: str
    provenance: CalibrationProvenance
    lap_time_fraction_per_fuel_km: float
    max_fuel_kg: float = REGULATION_MAX_FUEL_KG
    burn_kg_per_km: float = 0.3443
    finish_reserve_kg: float = 1.0
    vsc_burn_factor: float = 0.6
    sc_burn_factor: float = 0.5
    red_flag_burn_factor: float = 0.5
    lift_coast_max_saving_fraction: float = 0.08
    lift_coast_ms_per_kg_saved: float = 1_500.0
    origin: Literal["calibrated", "assumed"] = "calibrated"
    refuelling_allowed: bool = True
    refuel_stops: RefuelStopParameters | None = None
    refuel_rate_kg_per_s: float = 9.0
    tyre_change_ms: float = 2_500.0

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("version deve ser texto nao vazio")
        if type(self.refuelling_allowed) is not bool:
            raise ValueError("refuelling_allowed deve ser bool")
        if self.refuel_stops is not None and not isinstance(
            self.refuel_stops, RefuelStopParameters
        ):
            raise ValueError("refuel_stops deve ser RefuelStopParameters")
        if self.origin not in ("calibrated", "assumed"):
            raise ValueError("origin deve ser 'calibrated' ou 'assumed'")
        _non_negative(
            self.lap_time_fraction_per_fuel_km, "lap_time_fraction_per_fuel_km"
        )
        _positive(self.max_fuel_kg, "max_fuel_kg")
        _positive(self.burn_kg_per_km, "burn_kg_per_km")
        _non_negative(self.finish_reserve_kg, "finish_reserve_kg")
        if self.finish_reserve_kg >= self.max_fuel_kg:
            raise ValueError("finish_reserve_kg deve ser menor que max_fuel_kg")
        for name in (
            "vsc_burn_factor",
            "sc_burn_factor",
            "red_flag_burn_factor",
            "lift_coast_max_saving_fraction",
        ):
            _fraction(getattr(self, name), name)
        _non_negative(self.lift_coast_ms_per_kg_saved, "lift_coast_ms_per_kg_saved")
        _positive(self.refuel_rate_kg_per_s, "refuel_rate_kg_per_s")
        _non_negative(self.tyre_change_ms, "tyre_change_ms")

    @property
    def lap_time_fraction_per_kg(self) -> float:
        """Fracao do tempo de volta perdida por kg embarcado (1/kg)."""

        return self.lap_time_fraction_per_fuel_km / self.burn_kg_per_km


@dataclass(frozen=True, slots=True)
class FuelPlan:
    """Numeros do combustivel para um circuito, iguais para todos os carros.

    ``ms_per_kg`` usa a volta de referencia do circuito, e nao a de cada piloto:
    a sensibilidade e uma propriedade do tracado (quanto tempo se passa
    acelerando e freando), e a calibracao tambem usou uma referencia por
    corrida. ``lap_length_source`` registra se a extensao veio da geometria ou
    foi derivada da referencia pela hipotese de ritmo por km.

    ``pit_entry_fraction`` e onde fica a entrada dos boxes na volta (1.0 = na
    linha), tirada da geometria do pit lane quando ha. O piloto precisa
    decidir antes de passar por ela: para parar no fim da proxima volta, o
    combustivel tem de cobrir a volta ate a entrada, nao a volta inteira.
    Pode passar de 1.0 quando a entrada fica depois da linha.
    """

    parameters: FuelModelParameters
    reference_lap_ms: float
    lap_length_km: float
    lap_length_source: FuelLengthSource
    pit_entry_fraction: float = 1.0

    def __post_init__(self) -> None:
        _positive(self.reference_lap_ms, "reference_lap_ms")
        _positive(self.lap_length_km, "lap_length_km")
        if self.lap_length_source not in ("track_geometry", "reference_pace"):
            raise ValueError(
                "lap_length_source deve ser 'track_geometry' ou 'reference_pace'"
            )
        _positive(self.pit_entry_fraction, "pit_entry_fraction")
        if self.pit_entry_fraction > 2.0:
            raise ValueError("pit_entry_fraction deve estar em (0, 2]")

    @property
    def burn_kg_per_lap(self) -> float:
        """Consumo de uma volta em bandeira verde, sem economia."""

        return self.parameters.burn_kg_per_km * self.lap_length_km

    @property
    def ms_per_kg(self) -> float:
        """Tempo perdido por volta para cada kg embarcado neste circuito."""

        return self.parameters.lap_time_fraction_per_kg * self.reference_lap_ms

    @property
    def range_laps_at_max_fuel(self) -> float:
        """Voltas verdes que o tanque cheio cobre, ja descontada a reserva."""

        usable = self.parameters.max_fuel_kg - self.parameters.finish_reserve_kg
        return usable / self.burn_kg_per_lap

    def start_fuel_kg(self, total_laps: int) -> float:
        """Carga planejada: corrida inteira em verde mais a reserva, ate o teto.

        As equipes enchem para a distancia que vao correr, nao para o tanque
        cheio: cada kg a mais custa tempo em todas as voltas. Corridas curtas
        largam leves; corridas alem do alcance largam no teto e dependem de
        reabastecimento (ou de economia, sem ele).
        """

        if type(total_laps) is not int or total_laps < 1:
            raise ValueError("total_laps deve ser um inteiro positivo")
        return self.refuel_target_kg(total_laps)

    def refuel_target_kg(self, laps_left: int) -> float:
        """Massa para cobrir ``laps_left`` voltas verdes e a reserva, ate o teto.

        Usada na largada e no reabastecimento: a equipe poe o necessario para
        terminar e nada mais, porque cada kg extra custa tempo em toda volta.
        """

        if type(laps_left) is not int or laps_left < 0:
            raise ValueError("laps_left deve ser um inteiro nao negativo")
        needed = self.burn_kg_per_lap * laps_left + self.parameters.finish_reserve_kg
        return min(self.parameters.max_fuel_kg, needed)

    @property
    def fuel_to_reach_pit_kg(self) -> float:
        """Queima verde da linha ate a entrada dos boxes na volta seguinte."""

        return self.burn_kg_per_lap * self.pit_entry_fraction

    def must_pit(
        self, end_kg: float, lap: int, total_laps: int, margin_kg: float = 0.0
    ) -> bool:
        """Se o carro nao chegaria a proxima entrada dos boxes com ``margin_kg``.

        E o unico limite fisico do reabastecimento: passar da entrada com o
        tanque baixo demais significa ficar sem combustivel antes da proxima
        chance de parar. A estrategia normalmente para antes, por custo; o
        motor usa este teste com margem zero como rede de seguranca para
        estrategias que nao olham o combustivel. A conta usa a queima verde,
        mesmo que a proxima volta venha a ser neutralizada: o piloto nao sabe
        disso ao decidir. Na ultima volta nao ha proxima.
        """

        return (
            self.parameters.refuelling_allowed
            and lap < total_laps
            and end_kg - margin_kg
            < self.fuel_to_reach_pit_kg - _DEFICIT_TOLERANCE_KG
        )

    def stationary_extra_ms(self, fill_kg: float) -> float:
        """Tempo parado a mais por reabastecer ``fill_kg``, alem da troca de pneus.

        Pneus e combustivel sao feitos ao mesmo tempo, entao a parada dura o
        mais lento dos dois. A perda de boxes medida ja inclui a troca de
        pneus; o reabastecimento so pesa quando passa dela.
        """

        _non_negative(fill_kg, "fill_kg")
        fuelling_ms = fill_kg / self.parameters.refuel_rate_kg_per_s * 1000.0
        return max(0.0, fuelling_ms - self.parameters.tyre_change_ms)

    def burn_factor(self, status: str) -> float:
        """Consumo relativo da volta conforme o estado global da pista."""

        if status == "VSC":
            return self.parameters.vsc_burn_factor
        if status == "SC":
            return self.parameters.sc_burn_factor
        if status == "RED":
            return self.parameters.red_flag_burn_factor
        if status in ("GREEN", "YELLOW"):
            return 1.0
        raise ValueError(f"estado de pista desconhecido: {status!r}")

    def validate_start_fuel(self, fuel_kg: float, driver_id: str) -> None:
        """Rejeite carga negativa ou acima do teto regulamentar."""

        _non_negative(fuel_kg, f"start_fuel_kg de {driver_id}")
        if fuel_kg > self.parameters.max_fuel_kg:
            raise ValueError(
                f"start_fuel_kg de {driver_id} ({fuel_kg} kg) excede o teto de "
                f"{self.parameters.max_fuel_kg} kg"
            )


@dataclass(frozen=True, slots=True)
class FuelLap:
    """Uma volta de combustivel: massa, queima, economia e custo em tempo.

    ``mass_ms`` e o tempo perdido pela massa; ``saving_ms`` o custo do
    lift-and-coast. ``ran_dry`` indica que o tanque esvaziou nesta volta.
    """

    start_kg: float
    burn_kg: float
    saved_kg: float
    end_kg: float
    mass_ms: float
    saving_ms: float
    ran_dry: bool

    @property
    def fuel_ms(self) -> float:
        """Parcela de combustivel do tempo de volta (massa + economia)."""

        return self.mass_ms + self.saving_ms


def fuel_lap(
    plan: FuelPlan,
    *,
    fuel_kg: float,
    laps_remaining: int,
    status: str = "GREEN",
    distance_fraction: float = 1.0,
) -> FuelLap:
    """Consuma uma volta e devolva a parcela de tempo correspondente.

    ``laps_remaining`` inclui a volta corrente. A economia so existe com o
    reabastecimento desligado -- com ele, faltar combustivel resolve-se nos
    boxes, nao tirando o pe. Ela e acionada em bandeira verde ou amarela e so
    quando a massa utilizavel nao cobre as voltas restantes em ritmo verde: o
    deficit e espalhado igualmente pelas voltas restantes, limitado a
    ``lift_coast_max_saving_fraction`` da queima. Sob SC/VSC a propria
    neutralizacao ja economiza, e o deficit encolhe sem custo extra. A funcao e
    deterministica e nao consome aleatoriedade.

    ``distance_fraction`` encurta a queima da volta de entrada nos boxes: o
    carro queima ate a entrada e quase nada no pit lane, a 80 km/h. E a mesma
    distancia que ``FuelPlan.must_pit`` exige para a decisao. A pane seca tem
    tolerancia de ponto flutuante: chegar com exatamente zero nao e pane.
    """

    _non_negative(fuel_kg, "fuel_kg")
    if type(laps_remaining) is not int or laps_remaining < 1:
        raise ValueError("laps_remaining deve ser um inteiro positivo")
    _positive(distance_fraction, "distance_fraction")
    if distance_fraction > 1.0:
        raise ValueError("distance_fraction deve estar em (0, 1]")
    parameters = plan.parameters
    factor = plan.burn_factor(status)
    planned_burn = plan.burn_kg_per_lap * factor * distance_fraction

    saved = 0.0
    if (
        factor >= 1.0
        and not parameters.refuelling_allowed
        and parameters.lift_coast_max_saving_fraction > 0.0
    ):
        usable = fuel_kg - parameters.finish_reserve_kg
        deficit = plan.burn_kg_per_lap * laps_remaining - usable
        if deficit > _DEFICIT_TOLERANCE_KG:
            saved = min(
                planned_burn * parameters.lift_coast_max_saving_fraction,
                deficit / laps_remaining,
            )
    burn = planned_burn - saved
    ran_dry = burn > fuel_kg + _DEFICIT_TOLERANCE_KG
    burn = min(burn, fuel_kg)
    end = fuel_kg - burn
    mass_ms = plan.ms_per_kg * max(0.0, end - parameters.finish_reserve_kg)
    return FuelLap(
        start_kg=fuel_kg,
        burn_kg=burn,
        saved_kg=saved,
        end_kg=end,
        mass_ms=mass_ms,
        saving_ms=saved * parameters.lift_coast_ms_per_kg_saved,
        ran_dry=ran_dry,
    )
