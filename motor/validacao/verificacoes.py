"""Verificações de integridade da casualização e da consistência croqui–dados.

As funções retornam listas de mensagens de erro (vazia = íntegro). São usadas
pelos testes automatizados e também na interface, antes de salvar ou exportar.
"""

from __future__ import annotations

from collections import Counter

from motor.dominio import Casualizacao, Delineamento


def verificar_casualizacao(c: Casualizacao) -> list[str]:
    erros: list[str] = []
    t, r = c.n_tratamentos, c.n_repeticoes
    us = c.unidades
    if len(us) != t * r:
        erros.append(f"Esperadas {t * r} unidades experimentais; encontradas {len(us)}.")
    contagem = Counter(u.tratamento for u in us)
    for trat in range(1, t + 1):
        if contagem.get(trat, 0) != r:
            erros.append(f"Tratamento {trat} aparece {contagem.get(trat, 0)} vez(es); esperado {r}.")
    extras = set(contagem) - set(range(1, t + 1))
    if extras:
        erros.append(f"Tratamentos inexistentes na casualização: {sorted(extras)}.")
    if sorted(u.numero for u in us) != list(range(1, len(us) + 1)):
        erros.append("A numeração das unidades não é contínua de 1 a N.")
    if len({u.parcela for u in us}) != len(us):
        erros.append("Há rótulos de parcela duplicados.")
    codigos = [u.codigo for u in us if u.codigo]
    if codigos and len(set(codigos)) != len(codigos):
        erros.append("Há identificadores (códigos) duplicados.")
    pares = Counter((u.tratamento, u.repeticao) for u in us)
    if any(v > 1 for v in pares.values()):
        erros.append("Há pares tratamento–repetição duplicados.")

    if c.delineamento is Delineamento.DBC:
        blocos: dict[int, list[int]] = {}
        for u in us:
            if u.bloco is None:
                erros.append(f"Unidade {u.numero} sem bloco em um DBC.")
                continue
            blocos.setdefault(u.bloco, []).append(u.tratamento)
        if sorted(blocos) != list(range(1, r + 1)):
            erros.append(f"Esperados blocos 1..{r}; encontrados {sorted(blocos)}.")
        for b, trats in sorted(blocos.items()):
            if sorted(trats) != list(range(1, t + 1)):
                erros.append(f"O bloco {b} não contém cada tratamento exatamente uma vez.")
            posicoes = sorted(u.posicao for u in us if u.bloco == b)
            if posicoes != list(range(1, t + 1)):
                erros.append(f"Posições inconsistentes no bloco {b}.")
        for u in us:
            if u.bloco is not None and u.repeticao != u.bloco:
                erros.append(f"No DBC, a repetição deve coincidir com o bloco (unidade {u.numero}).")
                break
    else:
        if any(u.bloco is not None for u in us):
            erros.append(f"O delineamento {c.delineamento.value} não deve conter blocos.")
        if sorted(u.posicao for u in us) != list(range(1, len(us) + 1)):
            erros.append(f"Posições inconsistentes no {c.delineamento.value}.")
    erros += _verificar_estrutura(c)
    return erros


def _verificar_estrutura(c: Casualizacao) -> list[str]:
    """Restrições próprias do quadrado latino, das subdivididas e das faixas."""
    from motor.dominio import Arranjo

    erros: list[str] = []
    us = c.unidades
    if c.delineamento is Delineamento.QL:
        t = c.n_tratamentos
        for eixo, nome in (("linha", "linha"), ("coluna", "coluna")):
            grupos: dict[int, list[int]] = {}
            for u in us:
                grupos.setdefault(getattr(u, eixo), []).append(u.tratamento)
            if sorted(grupos) != list(range(1, t + 1)) or any(sorted(v) != list(range(1, t + 1))
                                                               for v in grupos.values()):
                erros.append(f"Quadrado latino: cada tratamento deve aparecer uma vez em cada {nome}.")
    if c.arranjo is Arranjo.CONVENCIONAL:
        return erros
    b = c.niveis_b

    def nivel_a(trat: int) -> int:
        return (trat - 1) // b + 1

    def nivel_b(trat: int) -> int:
        return (trat - 1) % b + 1

    if c.arranjo is Arranjo.SUBDIVIDIDA:
        principais: dict[tuple, list] = {}
        for u in us:
            principais.setdefault((u.bloco, u.principal), []).append(u)
        for (bl, pp), sub in principais.items():
            if len({nivel_a(u.tratamento) for u in sub}) != 1:
                erros.append(f"Parcela principal {pp} (bloco {bl}) com mais de um nível de A.")
            if sorted(nivel_b(u.tratamento) for u in sub) != list(range(1, b + 1)):
                erros.append(f"Parcela principal {pp} (bloco {bl}) não contém cada nível de B uma vez.")
            if sorted(u.sub for u in sub) != list(range(1, b + 1)):
                erros.append(f"Subparcelas inconsistentes na parcela principal {pp} (bloco {bl}).")
        if c.delineamento is Delineamento.DBC:
            for bl in {u.bloco for u in us}:
                niveis = sorted(nivel_a(sub[0].tratamento) for (bb, _), sub in principais.items() if bb == bl)
                if niveis != list(range(1, c.niveis_a + 1)):
                    erros.append(f"No bloco {bl}, cada nível de A deve ocupar uma parcela principal.")
        else:
            cont: dict[int, int] = {}
            for sub in principais.values():
                cont[nivel_a(sub[0].tratamento)] = cont.get(nivel_a(sub[0].tratamento), 0) + 1
            if set(cont.values()) != {c.n_repeticoes}:
                erros.append("Cada nível de A deve ocupar o mesmo número de parcelas principais.")
    elif c.arranjo is Arranjo.FAIXAS:
        for bl in {u.bloco for u in us}:
            du = [u for u in us if u.bloco == bl]
            for eixo, f, nome in (("linha", nivel_a, "linha (faixa de A)"), ("coluna", nivel_b, "coluna (faixa de B)")):
                grupos: dict[int, set] = {}
                for u in du:
                    grupos.setdefault(getattr(u, eixo), set()).add(f(u.tratamento))
                if any(len(v) != 1 for v in grupos.values()):
                    erros.append(f"Bloco {bl}: cada {nome} deve ter um único nível.")
    return erros


def verificar_croqui(c: Casualizacao, croqui) -> list[str]:
    """Confere se o croqui representa exatamente as unidades da casualização."""
    erros: list[str] = []
    nums_croqui = [cel.numero for cel in croqui.celulas]
    if sorted(nums_croqui) != sorted(u.numero for u in c.unidades):
        erros.append("O croqui não representa exatamente as unidades da casualização.")
    por_num = {u.numero: u for u in c.unidades}
    for cel in croqui.celulas:
        u = por_num.get(cel.numero)
        if u is not None and cel.bloco != u.bloco:
            erros.append(f"Unidade {u.numero}: bloco do croqui difere do bloco casualizado.")
            break
    return erros
