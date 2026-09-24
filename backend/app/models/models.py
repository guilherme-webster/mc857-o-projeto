from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DriverParameters:
    """Parametros de um participante, expostos por ``GET /simulation/drivers``.

    Atencao ao escopo de cada campo, porque eles nao tem a mesma origem:

    - ``base_lap_time_ms`` e **do piloto**: a mediana do quartil mais rapido de
      suas voltas na corrida carregada, ou seja, sua volta limpa de referencia.
      E ``None`` quando o piloto nao registrou voltas.
    - ``degradation_ms_per_lap``, ``pit_loss_ms`` e ``retirement_per_lap`` sao
      **do modelo**, nao do piloto: vem dos parametros calibrados em
      ``data/parameters`` e sao iguais para todos os carros da mesma corrida.
      Valem zero quando ainda nao ha arquivo de parametros calibrados.

    Os tres ultimos campos eram antes estimados por piloto e estavam
    incorretos; o historico do projeto e a correcao estao descritos em
    ``docs/modelagem-corrida-calibrada.md``.
    """

    driver_id: str
    name: str
    team_id: str | None
    grid_position: int
    base_lap_time_ms: float | None
    degradation_ms_per_lap: float
    pit_loss_ms: float
    retirement_per_lap: float = 0.0
