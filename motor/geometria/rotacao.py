"""Planos de rotação e remanejamento de vasos (ou de quaisquer unidades móveis).

Separação essencial: a **identidade** da unidade (número, código, tratamento) nunca muda; muda só a **vaga** — a
posição física que ela ocupa. As vagas são as células do croqui original, numeradas 1..N na ordem das unidades.
Um mapa ``{unidade: vaga}`` descreve onde cada unidade está; o mapa inicial é a identidade.

Restrições respeitadas (para não desfazer o controle local do delineamento):

* DIC — qualquer unidade pode ir para qualquer vaga;
* DBC — cada unidade permanece nas vagas do seu bloco (o bloco representa o gradiente que se quer controlar);
* parcelas subdivididas — a parcela principal se move inteira (suas subparcelas permanecem juntas e na mesma ordem);
* quadrado latino — só se movem linhas inteiras ou colunas inteiras, o que preserva a propriedade latina
  (cada tratamento uma vez por linha e por coluna física);
* faixas — não suportado (as faixas são estruturas de campo).

Por que rotacionar? Para reduzir — ou permitir avaliar — efeitos de posição causados por gradientes de luz,
temperatura e ventilação na casa de vegetação. A rotação é registrada (data, tipo, mapa), de modo que a posição de
cada vaso em qualquer data pode ser reconstituída.
"""

from __future__ import annotations

from collections.abc import Callable

from motor.casualizacao.gerador import GeradorDeterministico
from motor.dominio import Arranjo, Casualizacao, Delineamento
from motor.geometria.layout import Croqui


class ErroRotacao(ValueError):
    pass


TIPOS = {
    "deslocamento": "Deslocamento cíclico (cada unidade avança k vagas no seu grupo)",
    "inversao": "Inversão (a ordem das vagas em cada grupo é invertida)",
    "sorteio": "Novo sorteio de posições (dentro de cada grupo)",
    "troca": "Troca de duas unidades",
    "linhas": "Quadrado latino: deslocar linhas inteiras",
    "colunas": "Quadrado latino: deslocar colunas inteiras",
}


def tipos_permitidos(cas: Casualizacao) -> list[str]:
    if cas.arranjo is Arranjo.FAIXAS:
        return []
    if cas.delineamento is Delineamento.QL:
        return ["linhas", "colunas"]
    return ["deslocamento", "inversao", "sorteio", "troca"]


def mapa_inicial(cas: Casualizacao) -> dict[int, int]:
    return {u.numero: u.numero for u in cas.unidades}


def _blocos_das_vagas(croqui: Croqui) -> dict[int, int | None]:
    return {c.vaga: c.bloco for c in croqui.celulas}


def _grupos(cas: Casualizacao, croqui: Croqui) -> list[list[tuple[int, ...]]]:
    """Grupos de "lugares" entre os quais se permuta. Cada lugar é uma tupla de vagas que se movem juntas
    (uma vaga; ou as b vagas de uma parcela principal, em ordem)."""
    original = sorted(croqui.celulas, key=lambda c: c.vaga)
    unidade_da_vaga = {c.vaga: c.numero for c in original}       # no croqui original, vaga ↔ unidade
    por_num = {u.numero: u for u in cas.unidades}
    lugares: dict[object, list[tuple[int, ...]]] = {}
    if cas.arranjo is Arranjo.SUBDIVIDIDA:
        pps: dict[tuple, list[int]] = {}
        for v in sorted(unidade_da_vaga):
            u = por_num[unidade_da_vaga[v]]
            pps.setdefault((u.bloco, u.principal), []).append(v)
        for (bl, _), vagas in sorted(pps.items(), key=lambda kv: ((kv[0][0] or 0), kv[0][1])):
            ordenadas = sorted(vagas, key=lambda v: por_num[unidade_da_vaga[v]].sub)
            lugares.setdefault(bl, []).append(tuple(ordenadas))
    else:
        for v in sorted(unidade_da_vaga):
            u = por_num[unidade_da_vaga[v]]
            lugares.setdefault(u.bloco if cas.delineamento is Delineamento.DBC else None, []).append((v,))
    return [lugares[k] for k in sorted(lugares, key=lambda b: b or 0)]


def _permutar(mapa: dict[int, int], cas: Casualizacao, croqui: Croqui,
              nova_ordem: Callable[[int, list], list]) -> dict[int, int]:
    """Aplica, em cada grupo, uma permutação dos lugares: o conteúdo do lugar i vai para nova_ordem(...)[i]."""
    ocupante = {v: n for n, v in mapa.items()}
    novo = dict(mapa)
    for ig, lugares in enumerate(_grupos(cas, croqui)):
        destinos = nova_ordem(ig, lugares)
        for origem, destino in zip(lugares, destinos):
            for vo, vd in zip(origem, destino):
                novo[ocupante[vo]] = vd
    return novo


def deslocar(mapa, cas, croqui, k: int = 1) -> dict[int, int]:
    def ordem(_, lugares):
        n = len(lugares)
        return [lugares[(i + k) % n] for i in range(n)]
    return _permutar(mapa, cas, croqui, ordem)


def inverter(mapa, cas, croqui) -> dict[int, int]:
    return _permutar(mapa, cas, croqui, lambda _, lugares: list(reversed(lugares)))


def sortear(mapa, cas, croqui, semente: int, rodada: int) -> dict[int, int]:
    """Novo sorteio reprodutível (semente + número da rodada) das posições dentro de cada grupo."""
    def ordem(ig, lugares):
        return GeradorDeterministico(semente, f"rotacao:{rodada}|grupo:{ig}").permutacao(list(lugares))
    return _permutar(mapa, cas, croqui, ordem)


def trocar(mapa, cas, croqui, unidade_1: int, unidade_2: int) -> dict[int, int]:
    if unidade_1 == unidade_2:
        raise ErroRotacao("Escolha duas unidades diferentes.")
    grupos = _grupos(cas, croqui)
    v1, v2 = mapa[unidade_1], mapa[unidade_2]

    def localizar(v):
        for ig, lugares in enumerate(grupos):
            for il, lugar in enumerate(lugares):
                if v in lugar:
                    return ig, il, lugar.index(v)
        raise ErroRotacao("Vaga inexistente.")
    g1, l1, p1 = localizar(v1)
    g2, l2, p2 = localizar(v2)
    if g1 != g2:
        raise ErroRotacao("As unidades estão em blocos diferentes; a troca desfaria o controle local do bloco.")
    if cas.arranjo is Arranjo.SUBDIVIDIDA:
        if l1 == l2:
            raise ErroRotacao("As duas subparcelas são da mesma parcela principal.")
        # troca as parcelas principais inteiras
        def ordem(ig, lugares):
            if ig != g1:
                return list(lugares)
            out = list(lugares)
            out[l1], out[l2] = out[l2], out[l1]
            return out
        return _permutar(mapa, cas, croqui, ordem)
    novo = dict(mapa)
    novo[unidade_1], novo[unidade_2] = v2, v1
    return novo


def deslocar_eixo(mapa, cas, croqui, eixo: str, k: int = 1) -> dict[int, int]:
    """Quadrado latino: desloca linhas (ou colunas) inteiras em k posições, ciclicamente."""
    if cas.delineamento is not Delineamento.QL:
        raise ErroRotacao("Deslocamento de linhas/colunas inteiras é exclusivo do quadrado latino.")
    t = cas.n_tratamentos
    por_vaga = {c.vaga: (c.linha, c.coluna) for c in croqui.celulas}
    vaga_em = {lc: v for v, lc in por_vaga.items()}
    novo = {}
    for n, v in mapa.items():
        lin, col = por_vaga[v]
        if eixo == "linhas":
            lin = (lin + k) % t
        else:
            col = (col + k) % t
        novo[n] = vaga_em[(lin, col)]
    return novo


def aplicar_tipo(tipo: str, mapa, cas, croqui, k: int = 1, semente: int = 0, rodada: int = 1,
                 unidades: tuple[int, int] | None = None) -> dict[int, int]:
    if tipo not in tipos_permitidos(cas):
        raise ErroRotacao("Este tipo de movimento não é permitido para o delineamento do experimento.")
    if tipo == "deslocamento":
        return deslocar(mapa, cas, croqui, k)
    if tipo == "inversao":
        return inverter(mapa, cas, croqui)
    if tipo == "sorteio":
        return sortear(mapa, cas, croqui, semente, rodada)
    if tipo == "troca":
        if not unidades:
            raise ErroRotacao("Informe as duas unidades a trocar.")
        return trocar(mapa, cas, croqui, *unidades)
    return deslocar_eixo(mapa, cas, croqui, tipo, k)


def verificar_mapa(mapa: dict[int, int], cas: Casualizacao, croqui: Croqui) -> list[str]:
    """Confere se um mapa de posições respeita as restrições do delineamento."""
    erros: list[str] = []
    numeros = sorted(u.numero for u in cas.unidades)
    if sorted(mapa) != numeros or sorted(mapa.values()) != numeros:
        return ["O mapa deve posicionar cada unidade em exatamente uma vaga."]
    por_num = {u.numero: u for u in cas.unidades}
    bloco_da_vaga = _blocos_das_vagas(croqui)
    if cas.delineamento is Delineamento.DBC:
        fora = [n for n, v in mapa.items() if bloco_da_vaga[v] != por_num[n].bloco]
        if fora:
            erros.append(f"{len(fora)} unidade(s) fora das vagas do próprio bloco.")
    if cas.arranjo is Arranjo.SUBDIVIDIDA:
        pp_da_vaga = {c.vaga: (c.bloco, c.principal) for c in croqui.celulas}
        for (bl, pp) in {(u.bloco, u.principal) for u in cas.unidades}:
            destinos = {pp_da_vaga[mapa[u.numero]] for u in cas.unidades if (u.bloco, u.principal) == (bl, pp)}
            if len(destinos) != 1:
                erros.append(f"A parcela principal {pp} (bloco {bl}) foi separada.")
                break
    if cas.delineamento is Delineamento.QL:
        lc = {c.vaga: (c.linha, c.coluna) for c in croqui.celulas}
        t = cas.n_tratamentos
        for eixo in (0, 1):
            grupos: dict[int, list[int]] = {}
            for n, v in mapa.items():
                grupos.setdefault(lc[v][eixo], []).append(por_num[n].tratamento)
            if any(sorted(g) != list(range(1, t + 1)) for g in grupos.values()):
                erros.append("A nova disposição não preserva o quadrado latino.")
                break
    return erros


def posicao_atual(cas: Casualizacao, movimentos: list[dict]) -> dict[int, int]:
    """Mapa vigente após a sequência de movimentos registrados (o último prevalece)."""
    return dict(movimentos[-1]["mapa"]) if movimentos else mapa_inicial(cas)
