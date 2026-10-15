"""Motor de casualização, independente do gerador visual.

Cada delineamento e arranjo respeita a sua unidade de casualização:

* **DIC** — os ``t × r`` rótulos de tratamento são permutados sobre todas as unidades, sem restrição.
* **DBC** — os ``t`` tratamentos são permutados independentemente dentro de cada bloco.
* **Quadrado latino** — linhas, colunas e símbolos de um quadrado cíclico ``t × t`` são permutados
  independentemente (procedimento de Fisher & Yates, 1938, o mesmo de ``agricolae::design.lsd``); cada tratamento
  aparece uma vez em cada linha e em cada coluna.
* **Parcelas subdivididas** — os níveis de A são sorteados nas parcelas principais (dentro de cada bloco no DBC;
  sobre todas as parcelas principais no DIC) e os níveis de B são sorteados, de forma independente, dentro de
  cada parcela principal.
* **Faixas (DBC)** — em cada bloco, os níveis de A são sorteados nas faixas horizontais (linhas) e os de B nas
  faixas verticais (colunas); cada unidade é o cruzamento de uma linha com uma coluna.

A posição gerada aqui é *lógica* (ordem, linha/coluna, parcela principal). A tradução em coordenadas físicas é
responsabilidade do módulo de geometria, que preserva essa ordem.
"""

from __future__ import annotations

from motor.casualizacao.gerador import ALGORITMO, GeradorDeterministico
from motor.dominio import COMBINACOES_VALIDAS, Arranjo, Casualizacao, Delineamento, UnidadeExperimental


class ErroCasualizacao(ValueError):
    pass


def casualizar(
    delineamento: Delineamento | str,
    n_tratamentos: int,
    repeticoes: int,
    semente: int,
    numeracao: str = "sequencial",
    arranjo: Arranjo | str = Arranjo.CONVENCIONAL,
    niveis: tuple[int, int] | None = None,
) -> Casualizacao:
    """Gera a casualização.

    ``numeracao``: ``"sequencial"`` (1..N) ou ``"bloco"`` (101, 102…, 201…; só com blocos).
    ``niveis``: ``(a, b)`` — níveis dos fatores A e B, obrigatório em subdivididas e faixas (o tratamento
    ``(i, j)`` tem número ``(i - 1)·b + j``, a mesma ordem da matriz fatorial).
    No quadrado latino, ``repeticoes`` deve ser igual ao número de tratamentos.
    """
    delineamento, arranjo = Delineamento(delineamento), Arranjo(arranjo)
    if (delineamento, arranjo) not in COMBINACOES_VALIDAS:
        raise ErroCasualizacao(f"Combinação não suportada: {delineamento.value} com arranjo {arranjo.nome}.")
    if n_tratamentos < 2:
        raise ErroCasualizacao("São necessários ao menos 2 tratamentos.")
    if numeracao not in ("sequencial", "bloco"):
        raise ErroCasualizacao(f"Numeração desconhecida: {numeracao}")
    if numeracao == "bloco" and delineamento is not Delineamento.DBC:
        raise ErroCasualizacao("A numeração por bloco só se aplica a delineamentos com blocos (DBC).")
    a = b = 0
    if arranjo is not Arranjo.CONVENCIONAL:
        if not niveis or len(niveis) != 2 or min(niveis) < 2:
            raise ErroCasualizacao("Subdivididas e faixas exigem dois fatores, cada um com ao menos 2 níveis.")
        a, b = niveis
        if a * b != n_tratamentos:
            raise ErroCasualizacao("O número de tratamentos deve ser o produto dos níveis de A e B.")

    if delineamento is Delineamento.QL:
        if not 3 <= n_tratamentos <= 12:
            raise ErroCasualizacao("O quadrado latino é suportado de 3 a 12 tratamentos.")
        repeticoes = n_tratamentos
        unidades = _ql(n_tratamentos, semente)
    else:
        if repeticoes < 2:
            raise ErroCasualizacao("São necessárias ao menos 2 repetições.")
        if arranjo is Arranjo.SUBDIVIDIDA:
            unidades = _subdividida(delineamento, a, b, repeticoes, semente, numeracao)
        elif arranjo is Arranjo.FAIXAS:
            unidades = _faixas(a, b, repeticoes, semente, numeracao)
        elif delineamento is Delineamento.DIC:
            unidades = _dic(n_tratamentos, repeticoes, semente)
        else:
            unidades = _dbc(n_tratamentos, repeticoes, semente, numeracao)
    return Casualizacao(
        delineamento=delineamento, semente=semente, algoritmo=ALGORITMO, unidades=unidades,
        n_tratamentos=n_tratamentos, n_repeticoes=repeticoes, arranjo=arranjo, niveis_a=a, niveis_b=b,
    )


def _dic(t: int, r: int, semente: int) -> list[UnidadeExperimental]:
    rotulos = [trat for trat in range(1, t + 1) for _ in range(r)]
    GeradorDeterministico(semente, "dic").embaralhar(rotulos)
    ocorrencias: dict[int, int] = {}
    unidades = []
    for k, trat in enumerate(rotulos, start=1):
        ocorrencias[trat] = ocorrencias.get(trat, 0) + 1
        unidades.append(UnidadeExperimental(numero=k, parcela=str(k), tratamento=trat, bloco=None,
                                            repeticao=ocorrencias[trat], posicao=k))
    return unidades


def _mult(n_por_bloco: int) -> int:
    return 100 if n_por_bloco < 100 else 1000


def _dbc(t: int, r: int, semente: int, numeracao: str) -> list[UnidadeExperimental]:
    unidades = []
    mult = _mult(t)
    k = 0
    for bl in range(1, r + 1):
        ordem = GeradorDeterministico(semente, f"bloco:{bl}").permutacao(list(range(1, t + 1)))
        for pos, trat in enumerate(ordem, start=1):
            k += 1
            parcela = str(bl * mult + pos) if numeracao == "bloco" else str(k)
            unidades.append(UnidadeExperimental(numero=k, parcela=parcela, tratamento=trat, bloco=bl,
                                                repeticao=bl, posicao=pos))
    return unidades


def _ql(t: int, semente: int) -> list[UnidadeExperimental]:
    linhas = GeradorDeterministico(semente, "ql:linhas").permutacao(list(range(t)))
    colunas = GeradorDeterministico(semente, "ql:colunas").permutacao(list(range(t)))
    simbolos = GeradorDeterministico(semente, "ql:tratamentos").permutacao(list(range(1, t + 1)))
    unidades = []
    k = 0
    for i in range(t):
        for j in range(t):
            k += 1
            trat = simbolos[(linhas[i] + colunas[j]) % t]
            unidades.append(UnidadeExperimental(numero=k, parcela=str(k), tratamento=trat, bloco=None,
                                                repeticao=i + 1, posicao=k, linha=i + 1, coluna=j + 1))
    return unidades


def _subdividida(delineamento: Delineamento, a: int, b: int, r: int, semente: int,
                 numeracao: str) -> list[UnidadeExperimental]:
    unidades: list[UnidadeExperimental] = []
    k = 0
    if delineamento is Delineamento.DBC:
        mult = _mult(a)
        for bl in range(1, r + 1):
            ordem_a = GeradorDeterministico(semente, f"bloco:{bl}|principal").permutacao(list(range(1, a + 1)))
            for j, nivel_a in enumerate(ordem_a, start=1):
                ordem_b = GeradorDeterministico(semente, f"bloco:{bl}|pp:{j}").permutacao(list(range(1, b + 1)))
                rot_pp = str(bl * mult + j) if numeracao == "bloco" else str((bl - 1) * a + j)
                for s, nivel_b in enumerate(ordem_b, start=1):
                    k += 1
                    unidades.append(UnidadeExperimental(
                        numero=k, parcela=f"{rot_pp}.{s}", tratamento=(nivel_a - 1) * b + nivel_b, bloco=bl,
                        repeticao=bl, posicao=(j - 1) * b + s, principal=j, sub=s))
    else:
        rotulos_a = [na for na in range(1, a + 1) for _ in range(r)]
        GeradorDeterministico(semente, "dic|principal").embaralhar(rotulos_a)
        ocorr: dict[int, int] = {}
        for j, nivel_a in enumerate(rotulos_a, start=1):
            ocorr[nivel_a] = ocorr.get(nivel_a, 0) + 1
            ordem_b = GeradorDeterministico(semente, f"pp:{j}").permutacao(list(range(1, b + 1)))
            for s, nivel_b in enumerate(ordem_b, start=1):
                k += 1
                unidades.append(UnidadeExperimental(
                    numero=k, parcela=f"{j}.{s}", tratamento=(nivel_a - 1) * b + nivel_b, bloco=None,
                    repeticao=ocorr[nivel_a], posicao=(j - 1) * b + s, principal=j, sub=s))
    return unidades


def _faixas(a: int, b: int, r: int, semente: int, numeracao: str) -> list[UnidadeExperimental]:
    unidades: list[UnidadeExperimental] = []
    mult = _mult(a * b)
    k = 0
    for bl in range(1, r + 1):
        ordem_a = GeradorDeterministico(semente, f"bloco:{bl}|linhas").permutacao(list(range(1, a + 1)))
        ordem_b = GeradorDeterministico(semente, f"bloco:{bl}|colunas").permutacao(list(range(1, b + 1)))
        for i, nivel_a in enumerate(ordem_a, start=1):
            for j, nivel_b in enumerate(ordem_b, start=1):
                k += 1
                pos = (i - 1) * b + j
                unidades.append(UnidadeExperimental(
                    numero=k, parcela=str(bl * mult + pos) if numeracao == "bloco" else str(k),
                    tratamento=(nivel_a - 1) * b + nivel_b, bloco=bl, repeticao=bl, posicao=pos,
                    linha=i, coluna=j))
    return unidades


def descrever_algoritmo() -> str:
    return (
        f"Algoritmo {ALGORITMO}: permutação de Fisher–Yates alimentada por SHA-256 em modo contador (um fluxo "
        "independente para cada bloco, parcela principal, linha ou coluna), com amostragem por rejeição sem viés "
        "de módulo. Mesma semente e mesmas configurações produzem resultado idêntico."
    )
