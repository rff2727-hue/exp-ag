"""Descrição metodológica gerada exclusivamente a partir das configurações reais.

Nenhuma informação é inventada: trechos cujos dados não foram informados
(cultivar, local, linhas de plantio etc.) são simplesmente omitidos.
"""

from __future__ import annotations

from motor.dominio import Arranjo, Delineamento, TipoFator
from motor.exportacao.estilo import fmt_m, fmt_num
from motor.planejamento import Planejamento

_EXT_M = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez"]
_EXT_F = ["zero", "uma", "duas", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez"]
_EXT_EN = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


def _n(v: int, fem: bool = False) -> str:
    tab = _EXT_F if fem else _EXT_M
    return tab[v] if 0 <= v <= 10 else str(v)


def _ne(v: int) -> str:
    return _EXT_EN[v] if 0 <= v <= 10 else str(v)


def _lista(itens: list[str], conj: str = "e") -> str:
    itens = [i for i in itens if i]
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + f" {conj} " + itens[-1]


def _niveis_txt(f) -> str:
    if f.tipo is TipoFator.QUANTITATIVO:
        vals = [fmt_m(n.valor) if n.valor is not None else n.rotulo for n in f.niveis]
        return _lista(vals) + (f" {f.unidade}" if f.unidade else "")
    return _lista([n.rotulo for n in f.niveis])


def _niveis_txt_en(f) -> str:
    if f.tipo is TipoFator.QUANTITATIVO:
        vals = [f"{n.valor:g}" if n.valor is not None else n.rotulo for n in f.niveis]
        return _lista(vals, "and") + (f" {f.unidade}" if f.unidade else "")
    return _lista([n.rotulo for n in f.niveis], "and")


def descricao_pt(p: Planejamento) -> str:
    m = p.meta
    e = p.estrutura
    t = len(p.tratamentos)
    r = p.repeticoes
    n = p.casualizacao.n_unidades
    vasos = p.layout.tipo == "vasos"
    ue = "vasos" if vasos else "parcelas"
    par: list[str] = []

    amb = {"campo": "em condições de campo", "casa de vegetação": "em casa de vegetação",
           "laboratório": "em laboratório"}.get(m.ambiente, "")
    lugar = []
    if m.local:
        lugar.append(m.local)
    if m.municipio:
        lugar.append(m.municipio + (f", {m.uf}" if m.uf else ""))
    frase = "O experimento foi conduzido"
    frase += f" {amb}" if amb else ""
    frase += f", em {', '.join(lugar)}" if lugar else ""
    frase += f", na safra {m.safra}" if m.safra else ""
    if m.cultura:
        frase += f", com a cultura {m.cultura}" + (f" (cultivar {m.cultivar})" if m.cultivar else "")
    if frase != "O experimento foi conduzido":
        par.append(frase + ".")

    sig = p.delineamento.value
    nome_del = p.delineamento.nome[0].lower() + p.delineamento.nome[1:]
    arr = p.arranjo
    if p.delineamento is Delineamento.QL:
        par.append(f"Adotou-se o {nome_del} ({sig}) {t} × {t}: {_n(t)} tratamentos dispostos em {_n(t, True)} linhas e "
                   f"{_n(t, True)} colunas, de modo que cada tratamento ocorreu uma vez em cada linha e em cada coluna, "
                   f"totalizando {n} unidades experimentais ({ue}).")
    elif arr is Arranjo.SUBDIVIDIDA:
        fa, fb = e.fatores
        par.append(f"Adotou-se o {nome_del} ({sig}) em parcelas subdivididas, com {_n(r, True)} repetições"
                   + (" (blocos)" if p.delineamento is Delineamento.DBC else "")
                   + f": os níveis de {fa.nome} ({_niveis_txt(fa)}) foram alocados às parcelas principais e os de "
                   f"{fb.nome} ({_niveis_txt(fb)}) às subparcelas, totalizando {len(fa.niveis) * r} parcelas "
                   f"principais e {n} subparcelas" + (" (vasos)." if vasos else "."))
    elif arr is Arranjo.FAIXAS:
        fa, fb = e.fatores
        par.append(f"Adotou-se o {nome_del} ({sig}) com parcelas em faixas e {_n(r)} blocos: em cada bloco, os níveis "
                   f"de {fa.nome} ({_niveis_txt(fa)}) foram dispostos em faixas horizontais e os de {fb.nome} "
                   f"({_niveis_txt(fb)}) em faixas verticais, totalizando {n} unidades experimentais "
                   f"(cruzamentos das faixas).")
    else:
        rep_txt = f"{_n(r, True)} repetições" + (" (blocos)" if p.delineamento is Delineamento.DBC else "")
        par.append(f"Adotou-se o {nome_del} ({sig}), com {_n(t)} tratamentos e {rep_txt}, "
                   f"totalizando {n} unidades experimentais ({ue}).")

    if arr is Arranjo.CONVENCIONAL and e.fatores:
        if len(e.fatores) >= 2:
            fatores = _lista([f"{f.nome} ({_niveis_txt(f)})" for f in e.fatores])
            s = f"Os tratamentos foram arranjados em esquema fatorial {e.esquema}, combinando {fatores}"
        else:
            f = e.fatores[0]
            if f.tipo is TipoFator.QUANTITATIVO:
                s = f"Os tratamentos corresponderam a {_n(len(f.niveis))} níveis de {f.nome} ({_niveis_txt(f)})"
            else:
                s = f"Os tratamentos foram: {_niveis_txt(f)}"
        if e.adicionais:
            ad = _lista([a.rotulo + (f" ({a.papel.value})" if a.papel.value else "") for a in e.adicionais])
            s += (f", mais {_n(len(e.adicionais))} tratamento{'s' if len(e.adicionais) > 1 else ''} "
                  f"adiciona{'is' if len(e.adicionais) > 1 else 'l'}: {ad}")
        par.append(s + ".")
    elif arr is Arranjo.CONVENCIONAL and e.adicionais:
        par.append(f"Os tratamentos foram: {_lista([a.rotulo for a in e.adicionais])}.")

    cr = p.croqui
    mt = cr.metricas
    lay = p.layout
    if not vasos:
        s = (f"Cada {'subparcela' if arr is Arranjo.SUBDIVIDIDA else 'parcela'} mediu "
             f"{fmt_m(mt['largura_parcela_m'])} m × {fmt_m(mt['comprimento_parcela_m'])} m "
             f"({fmt_num(mt['area_parcela_m2'])} m²)")
        if lay.usa_linhas:
            s += f", com {_n(lay.n_linhas_plantio, True)} linhas espaçadas de {fmt_m(lay.espacamento_linhas)} m"
        if mt["area_util_m2"] < mt["area_parcela_m2"]:
            desc = []
            if lay.descarte_lateral > 0:
                if lay.usa_linhas:
                    desc.append(f"{_n(lay.linhas_bordadura, True)} linha{'s' if lay.linhas_bordadura > 1 else ''} "
                                "de cada lado")
                else:
                    desc.append(f"{fmt_m(lay.descarte_lateral)} m de cada lado")
            if lay.bordadura_cabeceira > 0:
                desc.append(f"{fmt_m(lay.bordadura_cabeceira)} m em cada extremidade")
            s += (f". A área útil, de {fmt_m(mt['largura_util_m'])} m × {fmt_m(mt['comprimento_util_m'])} m "
                  f"({fmt_num(mt['area_util_m2'])} m²), desconsiderou como bordadura {_lista(desc)}")
        s += f". O experimento ocupou {fmt_m(mt['largura_total_m'])} m × {fmt_m(mt['comprimento_total_m'])} m " \
             f"({fmt_num(mt['area_total_m2'])} m²)."
        par.append(s)

    if p.delineamento is Delineamento.QL:
        modo = ("por permutação aleatória das linhas, das colunas e dos tratamentos de um quadrado latino cíclico, "
                "procedimento que preserva as restrições de linha e coluna")
    elif arr is Arranjo.SUBDIVIDIDA:
        fa, fb = e.fatores
        onde = "em cada bloco, " if p.delineamento is Delineamento.DBC else ""
        modo = (f"em duas etapas — {onde}os níveis de {fa.nome} foram sorteados entre as parcelas principais e, "
                f"dentro de cada parcela principal, os níveis de {fb.nome} foram sorteados entre as subparcelas")
    elif arr is Arranjo.FAIXAS:
        fa, fb = e.fatores
        modo = (f"em cada bloco, sorteando de forma independente os níveis de {fa.nome} entre as faixas horizontais "
                f"e os de {fb.nome} entre as faixas verticais")
    elif p.delineamento is Delineamento.DBC:
        modo = "de forma independente dentro de cada bloco, de modo que cada bloco recebeu todos os tratamentos uma única vez"
    else:
        modo = "sem restrições, sobre o conjunto de todas as unidades experimentais"
    par.append(
        f"A casualização foi realizada {modo}, no aplicativo Exp-Ag (algoritmo "
        f"{p.casualizacao.algoritmo}, semente {p.casualizacao.semente}), o que permite reproduzi-la integralmente."
    )
    return " ".join(par)


def descricao_en(p: Planejamento) -> str:
    m = p.meta
    e = p.estrutura
    t = len(p.tratamentos)
    r = p.repeticoes
    n = p.casualizacao.n_unidades
    vasos = p.layout.tipo == "vasos"
    par: list[str] = []
    amb = {"campo": "under field conditions", "casa de vegetação": "in a greenhouse",
           "laboratório": "in the laboratory"}.get(m.ambiente, "")
    lugar = [x for x in (m.local, (m.municipio + (f", {m.uf}" if m.uf else "")) if m.municipio else "") if x]
    frase = "The experiment was carried out"
    frase += f" {amb}" if amb else ""
    frase += f" at {', '.join(lugar)}" if lugar else ""
    frase += f" in the {m.safra} season" if m.safra else ""
    if m.cultura:
        frase += f" with {m.cultura}" + (f" (cultivar {m.cultivar})" if m.cultivar else "")
    if frase != "The experiment was carried out":
        par.append(frase + ".")
    blocos = " (blocks)" if p.delineamento is Delineamento.DBC else ""
    sig = p.delineamento.sigla_en
    arr = p.arranjo
    ue = "pots" if vasos else "plots"
    if p.delineamento is Delineamento.QL:
        par.append(f"A {t} × {t} {p.delineamento.nome_en} ({sig}) was used: {_ne(t)} treatments arranged in {_ne(t)} "
                   f"rows and {_ne(t)} columns, each treatment occurring once in every row and column, totalling {n} "
                   f"experimental units ({ue}).")
    elif arr is not Arranjo.CONVENCIONAL:
        fa, fb = e.fatores
        if arr is Arranjo.SUBDIVIDIDA:
            par.append(f"A {p.delineamento.nome_en} ({sig}) in a split-plot arrangement was used, with {_ne(r)} "
                       f"replicates{blocos}: {fa.nome} ({_niveis_txt_en(fa)}) was assigned to main plots and "
                       f"{fb.nome} ({_niveis_txt_en(fb)}) to subplots, totalling {n} subplots ({ue}).")
        else:
            par.append(f"A {p.delineamento.nome_en} ({sig}) in a strip-plot arrangement was used, with {_ne(r)} "
                       f"blocks: {fa.nome} ({_niveis_txt_en(fa)}) was applied to horizontal strips and {fb.nome} "
                       f"({_niveis_txt_en(fb)}) to vertical strips, totalling {n} experimental units.")
    else:
        par.append(f"A {p.delineamento.nome_en} ({sig}) was used, with {_ne(t)} treatments and {_ne(r)} "
                   f"replicates{blocos}, totalling {n} experimental units ({ue}).")
    if arr is Arranjo.CONVENCIONAL and e.fatores:
        if len(e.fatores) >= 2:
            fat = _lista([f"{f.nome} ({_niveis_txt_en(f)})" for f in e.fatores], "and")
            s = f"Treatments were arranged in a {e.esquema.replace('×', 'x')} factorial scheme combining {fat}"
        else:
            f = e.fatores[0]
            s = (f"Treatments consisted of {_ne(len(f.niveis))} levels of {f.nome} ({_niveis_txt_en(f)})"
                 if f.tipo is TipoFator.QUANTITATIVO else f"Treatments were: {_niveis_txt_en(f)}")
        if e.adicionais:
            s += f", plus {_ne(len(e.adicionais))} additional treatment{'s' if len(e.adicionais) > 1 else ''} " \
                 f"({_lista([a.rotulo for a in e.adicionais], 'and')})"
        par.append(s + ".")
    if not vasos:
        mt = p.croqui.metricas
        s = (f"Each plot measured {mt['largura_parcela_m']:g} m × {mt['comprimento_parcela_m']:g} m "
             f"({mt['area_parcela_m2']:.2f} m²)")
        if mt["area_util_m2"] < mt["area_parcela_m2"]:
            s += (f", with a harvest area of {mt['largura_util_m']:g} m × {mt['comprimento_util_m']:g} m "
                  f"({mt['area_util_m2']:.2f} m²)")
        par.append(s + ".")
    if p.delineamento is Delineamento.QL:
        modo = "by randomly permuting the rows, columns and treatment symbols of a cyclic Latin square"
    elif arr is Arranjo.SUBDIVIDIDA:
        modo = "in two stages (main-plot levels among main plots, then subplot levels within each main plot)"
    elif arr is Arranjo.FAIXAS:
        modo = "independently for the horizontal and vertical strips within each block"
    elif p.delineamento is Delineamento.DBC:
        modo = "independently within each block"
    else:
        modo = "without restriction across all experimental units"
    par.append(
        f"Randomization was performed {modo} using Exp-Ag (algorithm {p.casualizacao.algoritmo}, "
        f"seed {p.casualizacao.semente}), allowing full reproduction."
    )
    return " ".join(par)
