"""Gerador pseudoaleatório determinístico e versionado.

Por que não usar diretamente ``numpy.random`` ou ``random``?
A reprodutibilidade de uma casualização precisa sobreviver a atualizações de
bibliotecas. O NumPy não garante que ``Generator.permutation`` produza a mesma
sequência entre versões, e o módulo ``random`` do Python pode mudar detalhes
internos. Uma casualização publicada com "semente 1234" deve gerar o mesmo
croqui daqui a dez anos.

Algoritmo ``FY-SHA256-v1`` (documentado para reprodução independente):

1. Para cada fluxo identificado por ``(semente, contexto)``, o bloco ``i`` de
   bits aleatórios é ``SHA-256(f"{semente}|{contexto}|{i}")`` (UTF-8), lido
   como 4 inteiros sem sinal de 64 bits, big-endian.
2. Um inteiro uniforme em ``[0, n)`` é obtido por amostragem com rejeição:
   descarta-se ``x >= limite``, onde ``limite = 2**64 - (2**64 % n)``, e
   retorna-se ``x % n``. Não há viés de módulo.
3. Permutações usam Fisher–Yates descendente: para ``i = n-1 .. 1``, sorteia
   ``j`` em ``[0, i]`` e troca ``a[i]`` e ``a[j]``.

Cada bloco do DBC usa seu próprio contexto (``"bloco:1"``, ``"bloco:2"``…),
de modo que acrescentar um bloco não altera a casualização dos anteriores.
"""

from __future__ import annotations

import hashlib
from collections.abc import MutableSequence
from typing import TypeVar

ALGORITMO = "FY-SHA256-v1"
SEMENTE_MAX = 2**53 - 1  # limite de inteiros exatos em JavaScript (interface web)
_DOIS_64 = 1 << 64

T = TypeVar("T")


class GeradorDeterministico:
    def __init__(self, semente: int, contexto: str = "") -> None:
        if not isinstance(semente, int) or not 0 <= semente <= SEMENTE_MAX:
            raise ValueError(f"A semente deve ser um inteiro entre 0 e {SEMENTE_MAX}.")
        self.semente = semente
        self.contexto = contexto
        self._contador = 0
        self._buffer: list[int] = []

    def _proximo_u64(self) -> int:
        if not self._buffer:
            dados = f"{self.semente}|{self.contexto}|{self._contador}".encode()
            bloco = hashlib.sha256(dados).digest()
            self._contador += 1
            # 4 palavras de 64 bits; consumidas em ordem
            self._buffer = [int.from_bytes(bloco[k : k + 8], "big") for k in (24, 16, 8, 0)]
        return self._buffer.pop()

    def inteiro_abaixo(self, n: int) -> int:
        """Inteiro uniforme em [0, n)."""
        if n <= 0:
            raise ValueError("n deve ser positivo")
        limite = _DOIS_64 - (_DOIS_64 % n)
        while True:
            x = self._proximo_u64()
            if x < limite:
                return x % n

    def embaralhar(self, itens: MutableSequence[T]) -> None:
        """Fisher–Yates in place."""
        for i in range(len(itens) - 1, 0, -1):
            j = self.inteiro_abaixo(i + 1)
            itens[i], itens[j] = itens[j], itens[i]

    def permutacao(self, itens: list[T]) -> list[T]:
        copia = list(itens)
        self.embaralhar(copia)
        return copia


def semente_aleatoria() -> int:
    """Nova semente de 9 dígitos a partir da entropia do sistema operacional."""
    import secrets

    return 100_000_000 + secrets.randbelow(900_000_000)
