"""Fase 2: parcelas subdivididas, faixas e quadrado latino — casualização, GL, geometria, persistência."""

from collections import Counter

import pytest

from motor.casualizacao.casualizador import ErroCasualizacao, casualizar
from motor.dominio import Arranjo, EstruturaTratamentos, Fator, Nivel, TratamentoAdicional
from motor.estatistica.delineamentos import avisos_planejamento, quadro_gl
from motor.exportacao.projeto_json import exportar_json, importar_json
from motor.geometria.layout import ConfigLayout
from motor.planejamento import ErroPlanejamento, Metadados, planejar
from motor.validacao.verificacoes import verificar_casualizacao, verificar_croqui


def fat(nome, n):
    return Fator(nome, [Nivel(f"{nome[0]}{i}") for i in range(1, n + 1)])


def E(a=3, b=2):
    return EstruturaTratamentos([fat("Adubo", a), fat("Biológico", b)])


def nivel_a(t, b):
    return (t - 1) // b + 1


# ------------------------------------------------------------------ subdivididas
@pytest.mark.parametrize("a,b,r", [(3, 2, 4), (2, 5, 3), (4, 3, 2)])
def test_subdividida_dbc_estrutura(a, b, r):
    c = casualizar("DBC", a * b, r, 77, "bloco", "subdividida", (a, b))
    assert verificar_casualizacao(c) == []
    assert len(c.unidades) == a * b * r
    for bl in range(1, r + 1):
        pps = {}
        for u in c.unidades:
            if u.bloco == bl:
                pps.setdefault(u.principal, []).append(u)
        assert sorted(pps) == list(range(1, a + 1))
        assert sorted({nivel_a(s[0].tratamento, b) for s in pps.values()}) == list(range(1, a + 1))
        for s in pps.values():
            assert len({nivel_a(u.tratamento, b) for u in s}) == 1                # A constante na parcela principal
            assert sorted((u.tratamento - 1) % b + 1 for u in s) == list(range(1, b + 1))
    assert c.unidades[0].parcela.startswith("101.")


def test_subdividida_dic():
    c = casualizar("DIC", 6, 4, 5, "sequencial", "subdividida", (3, 2))
    assert verificar_casualizacao(c) == []
    pps = Counter()
    for u in c.unidades:
        if u.sub == 1:
            pps[nivel_a(u.tratamento, 2)] += 1
    assert pps == {1: 4, 2: 4, 3: 4}


def test_subdividida_e_reproduzivel_e_sorteia_as_duas_etapas():
    a = casualizar("DBC", 6, 4, 9, "bloco", "subdividida", (3, 2))
    b = casualizar("DBC", 6, 4, 9, "bloco", "subdividida", (3, 2))
    assert [u.tratamento for u in a.unidades] == [u.tratamento for u in b.unidades]
    ordens_a, ordens_b = set(), set()
    for s in range(200):
        c = casualizar("DBC", 6, 2, s, "bloco", "subdividida", (3, 2))
        u = [x for x in c.unidades if x.bloco == 1]
        ordens_a.add(tuple(nivel_a(x.tratamento, 2) for x in u if x.sub == 1))
        ordens_b.add(tuple((x.tratamento - 1) % 2 + 1 for x in u if x.principal == 1))
    assert len(ordens_a) == 6 and len(ordens_b) == 2                           # todas as permutações aparecem


def test_adulteracao_entre_parcelas_principais_e_detectada():
    c = casualizar("DBC", 6, 3, 3, "bloco", "subdividida", (3, 2))
    u1 = next(u for u in c.unidades if u.bloco == 1 and u.principal == 1 and u.sub == 1)
    u2 = next(u for u in c.unidades if u.bloco == 1 and u.principal == 2 and u.sub == 1)
    u1.tratamento, u2.tratamento = u2.tratamento, u1.tratamento
    assert any("Parcela principal" in e for e in verificar_casualizacao(c))


# ------------------------------------------------------------------ faixas
def test_faixas_linhas_e_colunas_constantes():
    a, b, r = 3, 4, 3
    c = casualizar("DBC", 12, r, 21, "bloco", "faixas", (a, b))
    assert verificar_casualizacao(c) == []
    for bl in range(1, r + 1):
        us = [u for u in c.unidades if u.bloco == bl]
        assert sorted(u.tratamento for u in us) == list(range(1, 13))
        for i in range(1, a + 1):
            assert len({nivel_a(u.tratamento, b) for u in us if u.linha == i}) == 1
        for j in range(1, b + 1):
            assert len({(u.tratamento - 1) % b + 1 for u in us if u.coluna == j}) == 1
    u = c.unidades[0]
    u.tratamento = c.unidades[1].tratamento
    assert verificar_casualizacao(c)


# ------------------------------------------------------------------ quadrado latino
@pytest.mark.parametrize("t", list(range(3, 13)))
def test_quadrado_latino_propriedade(t):
    c = casualizar("QL", t, 0, 1000 + t)
    assert c.n_repeticoes == t and len(c.unidades) == t * t
    assert verificar_casualizacao(c) == []


def test_quadrado_latino_uniforme_na_primeira_celula():
    t, n = 4, 2000
    cont = Counter(casualizar("QL", t, 0, s).unidades[0].tratamento for s in range(n))
    chi2 = sum((cont[i] - n / t) ** 2 / (n / t) for i in range(1, t + 1))
    assert chi2 < 16.27                                                       # gl 3, p = 0,001


def test_combinacoes_invalidas():
    with pytest.raises(ErroCasualizacao):
        casualizar("DIC", 6, 3, 1, "sequencial", "faixas", (3, 2))
    with pytest.raises(ErroCasualizacao):
        casualizar("QL", 2, 0, 1)
    with pytest.raises(ErroCasualizacao):
        casualizar("DBC", 6, 3, 1, "bloco", "subdividida", (2, 2))
    with pytest.raises(ErroPlanejamento):
        planejar(Metadados("X", "t"), "DBC", EstruturaTratamentos([fat("A", 2), fat("B", 2), fat("C", 2)]), 3, 1,
                 ConfigLayout(), "{exp}-P{parcela}", arranjo="subdividida")
    with pytest.raises(ErroPlanejamento):
        planejar(Metadados("X", "t"), "DBC", EstruturaTratamentos([fat("A", 2), fat("B", 2)],
                                                                   [TratamentoAdicional("Test")]), 3, 1,
                 ConfigLayout(), "{exp}-P{parcela}", arranjo="faixas")


# ------------------------------------------------------------------ graus de liberdade
def _gl(*args, **kw):
    return {g.fonte.strip(): g.gl for g in quadro_gl(*args, **kw)}


def test_gl_subdividida_dbc():
    g = _gl("DBC", E(3, 2), 4, "subdividida")
    assert g == {"Blocos": 3, "Adubo (A)": 2, "Resíduo (a)": 6, "Parcelas principais": 11, "Biológico (B)": 1,
                 "Adubo × Biológico": 2, "Resíduo (b)": 9, "Total": 23}
    assert g["Blocos"] + g["Adubo (A)"] + g["Resíduo (a)"] == g["Parcelas principais"]


def test_gl_subdividida_dic():
    g = _gl("DIC", E(3, 2), 4, "subdividida")
    assert g["Resíduo (a)"] == 9 and g["Resíduo (b)"] == 9 and g["Total"] == 23


def test_gl_faixas_e_quadrado_latino():
    g = _gl("DBC", E(3, 4), 3, "faixas")
    assert (g["Resíduo (a)"], g["Resíduo (b)"], g["Resíduo (c)"], g["Total"]) == (4, 6, 12, 35)
    assert sum(v for k, v in g.items() if k != "Total") == 35
    q = _gl("QL", EstruturaTratamentos([fat("T", 5)]), 0)
    assert q == {"Linhas": 4, "Colunas": 4, "T": 4, "Resíduo": 12, "Total": 24}


def test_avisos_da_subdividida():
    msgs = [a.mensagem for a in avisos_planejamento("DBC", E(2, 3), 3, "subdividida")]
    assert any("resíduo (a)" in m for m in msgs) and any("estrato" in m for m in msgs)


# ------------------------------------------------------------------ geometria
def test_geometria_subdividida():
    p = planejar(Metadados("SUB", "t"), "DBC", E(3, 2), 4, 7,
                 ConfigLayout(largura=3, comprimento=6, espaco_x=1, espaco_sub=0.2, colunas_por_bloco=3),
                 "{exp}-P{parcela}", "bloco", arranjo="subdividida")
    cr = p.croqui
    assert len(cr.principais) == 12 and verificar_croqui(p.casualizacao, cr) == []
    por_num = {c.numero: c for c in cr.celulas}
    for u in p.casualizacao.unidades:
        if u.sub == 1:
            irma = next(x for x in p.casualizacao.unidades if x.bloco == u.bloco and x.principal == u.principal
                        and x.sub == 2)
            dx = abs(por_num[u.numero].centro[0] - por_num[irma.numero].centro[0])
            assert dx == pytest.approx(3.2)                                     # subparcelas lado a lado
    assert p.croqui.metricas["largura_total_m"] == pytest.approx(4 * (3 * 6.2 + 2 * 1) + 3 * 2)


def test_geometria_quadrado_latino_em_vasos_com_bancada():
    p = planejar(Metadados("QL", "t"), "QL", EstruturaTratamentos([fat("T", 5)]), 0, 3,
                 ConfigLayout(tipo="vasos", bancadas=True), "{exp}-L{lin}C{col}-T{trat}")
    cr = p.croqui
    assert {(c.linha, c.coluna) for c in cr.celulas} == {(i, j) for i in range(5) for j in range(5)}
    assert len(cr.bancadas) == 1 and len(cr.rotulos) == 10
    assert p.casualizacao.unidades[0].codigo == "QL-L01C01-T" + f"{p.casualizacao.unidades[0].tratamento:02d}"


def test_bancadas_no_dic_respeitam_parcelas_principais():
    p = planejar(Metadados("V", "t"), "DIC", E(2, 3), 4, 3,
                 ConfigLayout(tipo="vasos", bancadas=True, vasos_por_bancada=10), "{exp}-P{parcela}",
                 arranjo="subdividida")
    cr = p.croqui
    assert len(cr.bancadas) == 3                                     # 24 vasos; 9 por bancada (3 parcelas principais)
    for pp in {c.principal for c in cr.celulas}:
        assert len({c.bancada for c in cr.celulas if c.principal == pp}) == 1


# ------------------------------------------------------------------ persistência e JSON
@pytest.mark.parametrize("delin,arr,est,r", [("DBC", "subdividida", E(3, 2), 3), ("DBC", "faixas", E(2, 3), 3),
                                             ("QL", "convencional", EstruturaTratamentos([fat("T", 4)]), 0),
                                             ("DIC", "subdividida", E(2, 2), 3)])
def test_persistencia_e_json(repo, delin, arr, est, r):
    p = planejar(Metadados("EXP-" + arr[:3].upper() + delin, "t"), delin, est, r, 11, ConfigLayout(),
                 "{exp}-P{parcela}", "bloco" if delin == "DBC" else "sequencial", arranjo=arr)
    pid = repo.criar_projeto("P", "Projeto")
    eid = repo.salvar_novo(pid, p)
    q = repo.carregar(eid)
    chave = lambda pl: [(u.numero, u.parcela, u.tratamento, u.bloco, u.principal, u.sub, u.linha, u.coluna,  # noqa: E731
                         u.codigo) for u in pl.casualizacao.unidades]
    assert chave(q) == chave(p) and q.arranjo == Arranjo(arr) and q.verificar() == []
    assert chave(importar_json(exportar_json(q))) == chave(p)
