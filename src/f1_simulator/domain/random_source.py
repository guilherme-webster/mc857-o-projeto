"""Fonte de aleatoriedade injetavel e reproduzivel do motor.

O AGENTS.md exige que toda aleatoriedade seja injetavel e testavel, e o plano
(secao 5.2) exige que o mesmo cenario com a mesma semente produza exatamente o
mesmo resultado. Nenhum modulo do dominio pode chamar ``random`` global: isso
tornaria a corrida irreprodutivel e dependente da ordem de importacao.

``SeededRandomSource`` usa uma instancia propria de ``random.Random``, isolada
do estado global do processo. ``FrozenRandomSource`` permite testar as regras
sem estocasticidade, sem precisar de mocks.
"""

from __future__ import annotations

import random
from typing import Protocol


class RandomSource(Protocol):
    """Porta de aleatoriedade consumida pelo motor.

    Deliberadamente minima: o motor so precisa de um uniforme em [0, 1) e de um
    desvio normal padrao. Ampliar esta porta exigiria uma variacao concreta, o
    que o AGENTS.md pede que seja evitado sem necessidade demonstrada.
    """

    def uniform01(self) -> float:
        """Devolva um uniforme em [0, 1)."""
        ...

    def standard_normal(self) -> float:
        """Devolva um desvio normal de media 0 e variancia 1."""
        ...


class SeededRandomSource:
    """Gerador reproduzivel; a mesma semente reproduz a mesma corrida.

    A sequencia depende da ordem em que o motor consome os sorteios. Alterar
    essa ordem muda o resultado mesmo com a mesma semente, o que e esperado: a
    reprodutibilidade vale para uma versao fixa do motor e dos parametros, nao
    entre versoes diferentes.
    """

    __slots__ = ("_random", "seed")

    def __init__(self, seed: int) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("a semente deve ser um inteiro")
        self.seed = seed
        self._random = random.Random(seed)

    def uniform01(self) -> float:
        return self._random.random()

    def standard_normal(self) -> float:
        return self._random.gauss(0.0, 1.0)


class FrozenRandomSource:
    """Fonte degenerada que nunca perturba nada.

    ``uniform01`` devolve 1.0 -- estritamente acima de qualquer probabilidade
    de risco em [0, 1), portanto nenhum evento raro dispara -- e
    ``standard_normal`` devolve 0.0, anulando o ruido. Serve para isolar as
    regras deterministicas nos testes e para o modo sem variabilidade descrito
    em ``docs/contrato-perfil-simulacao.md``.
    """

    __slots__ = ()

    def uniform01(self) -> float:
        return 1.0

    def standard_normal(self) -> float:
        return 0.0
