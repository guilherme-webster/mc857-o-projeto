"""Fonte de aleatoriedade reproduzivel e auditavel para regras de dominio.

O modulo encapsula todo estado pseudoaleatorio em instancias explicitamente
semeadas. Assim, consumidores podem injetar a dependencia, repetir uma
simulacao e testar rejeicoes sem recorrer ao estado global de :mod:`random`.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from random import Random
from typing import Protocol


MAX_TRUNCATED_STANDARD_NORMAL_ATTEMPTS = 10_000
"""Numero maximo de sorteios antes de declarar a truncagem inviavel."""


class RandomSource(Protocol):
    """Contrato minimo para consumir uma variavel normal padrao.

    ``label`` identifica a finalidade do sorteio para fontes que mantenham
    auditoria. Ele nao altera a distribuicao nem substitui a ordem determinista
    que deve ser definida pelo consumidor.
    """

    def standard_normal(self, label: str) -> float:
        """Retorne um sorteio de uma normal com media zero e desvio padrao um."""

        ...


@dataclass(frozen=True, slots=True)
class RandomDraw:
    """Registro imutavel de um sorteio e da finalidade informada pelo chamador."""

    label: str
    value: float


class SeededRandomSource:
    """Fonte local baseada em ``random.Random`` e reproduzivel por semente.

    O registro e opcional porque uma corrida pode produzir muitos sorteios e a
    auditoria nao deve impor custo de memoria quando nao for solicitada.
    ``spawn`` usa SHA-256 sobre a semente original e a chave. O ``hash()``
    nativo nunca e adequado aqui: seu sal varia entre processos Python e
    quebraria a reproducibilidade exigida para a simulacao.
    """

    __slots__ = ("_draws", "_record_draws", "_rng", "_seed")

    def __init__(self, seed: int, record_draws: bool = False) -> None:
        """Crie um fluxo isolado; ``bool`` nao e aceito como semente inteira."""

        if type(seed) is not int:
            raise ValueError("seed deve ser um int verdadeiro")
        if type(record_draws) is not bool:
            raise ValueError("record_draws deve ser bool")

        self._seed = seed
        self._record_draws = record_draws
        self._rng = Random(seed)
        self._draws: list[RandomDraw] = []

    @property
    def draws(self) -> tuple[RandomDraw, ...]:
        """Devolva um retrato imutavel dos sorteios registrados, em ordem."""

        return tuple(self._draws)

    def standard_normal(self, label: str) -> float:
        """Sorteie uma normal padrao e, se habilitado, registre-a em ordem."""

        if not isinstance(label, str):
            raise ValueError("label deve ser str")

        value = self._rng.gauss(0.0, 1.0)
        if self._record_draws:
            self._draws.append(RandomDraw(label=label, value=value))
        return value

    def spawn(self, key: str) -> SeededRandomSource:
        """Derive de ``(seed, key)`` um fluxo independente e reproduzivel.

        A derivacao nao consulta nem avanca ``_rng``; portanto, criar um filho
        nao consome sorteios do pai e independe de quantos valores o pai ja
        produziu. A representacao inclui um separador e um prefixo de versao
        para evitar concatenacoes ambiguas e permitir evolucao explicita.
        SHA-256 e usado no lugar de ``hash()``, que e salgado por processo.
        """

        if not isinstance(key, str):
            raise ValueError("key deve ser str")

        seed_bytes = str(self._seed).encode("ascii")
        key_bytes = key.encode("utf-8")
        material = b"f1-random-source-v1\x00" + seed_bytes + b"\x00" + key_bytes
        child_seed = int.from_bytes(sha256(material).digest(), byteorder="big")
        return SeededRandomSource(child_seed, record_draws=self._record_draws)


def truncated_standard_normal(
    source: RandomSource,
    label: str,
    limit_sigmas: float,
) -> float:
    """Sorteie uma normal padrao restrita a ``+/-limit_sigmas`` por rejeicao.

    Cada tentativa consome ``source.standard_normal(label)`` com a mesma label,
    inclusive quando o valor e rejeitado. Valores fora do intervalo nao sao
    limitados artificialmente, pois um clamp concentraria massa nas bordas e
    esconderia que o sorteio original violou o suporte declarado.

    Apos :data:`MAX_TRUNCATED_STANDARD_NORMAL_ATTEMPTS`, levanta ``ValueError``
    em vez de manter um laco potencialmente infinito. ``limit_sigmas`` deve ser
    um numero positivo e finito; ``bool`` nao representa uma medida valida.
    """

    if (
        isinstance(limit_sigmas, bool)
        or not isinstance(limit_sigmas, (int, float))
        or not isfinite(limit_sigmas)
        or limit_sigmas <= 0
    ):
        raise ValueError("limit_sigmas deve ser positivo e finito")

    for _ in range(MAX_TRUNCATED_STANDARD_NORMAL_ATTEMPTS):
        value = source.standard_normal(label)
        if -limit_sigmas <= value <= limit_sigmas:
            return value

    raise ValueError(
        "normal truncada excedeu o numero maximo de tentativas "
        f"({MAX_TRUNCATED_STANDARD_NORMAL_ATTEMPTS})"
    )
