"""Fabrica de parametros de combustivel compartilhada pelos testes.

Mora fora de ``tests/test_fuel.py`` para que outros modulos de teste usem
``fuel_parameters`` sem importar um modulo de teste (e sem herdar suas
dependencias). Os valores sao redondos e arbitrarios de proposito, como em
``tests/model_support.py``: os testes verificam regras, nao coeficientes
calibrados.
"""

from __future__ import annotations

from f1_simulator.domain.fuel import FuelModelParameters
from tests.model_support import provenance

REFERENCE_MS = 90_000.0


def fuel_parameters(**overrides) -> FuelModelParameters:
    """Parametros redondos: 0,5 kg/km e 12,5 ms/kg numa volta de 90 s.

    Com 4 km por volta, a queima e 2 kg/volta e a inclinacao 25 ms/volta, a
    mesma de ``tests.model_support.parameters``; isso permite comparar o
    modelo de massa com o linear legado numa corrida limpa.
    """

    defaults = dict(
        version="fuel-teste",
        provenance=provenance(),
        lap_time_fraction_per_fuel_km=12.5 / REFERENCE_MS * 0.5,
        burn_kg_per_km=0.5,
        finish_reserve_kg=1.0,
    )
    defaults.update(overrides)
    return FuelModelParameters(**defaults)
