"""Fase 3 — personalização do croqui: blocos em grade, corredores, bordaduras por lado, canto inicial,
deslocamentos manuais de blocos e cotas."""

import math

import pytest

from motor.casualizacao.casualizador import casualizar
from motor.geometria.layout import ConfigLayout, gerar_croqui, texto_medida
from motor.validacao.verificacoes import verificar_croqui


def _caixa(poli):
    xs, ys = [p[0] for p in poli], [p[1] for p in poli]
    return min(xs), min(ys), max(xs), max(ys)


def _celula(cr, numero):
    return next(c for c in cr.celulas if c.numero == numero)


def test_padroes_reproduzem_layout_anterior():
    c = casualizar("DBC", 6, 4, 11)
    base = gerar_croqui(c, ConfigLayout(colunas_por_bloco=3))
    novo = gerar_croqui(c, ConfigLayout.de_dict({**ConfigLayout(colunas_por_bloco=3).para_dict(),
                                                 "deslocamentos_blocos": {}}))
    assert [x.poligono for x in base.celulas] == [x.poligono for x in novo.celulas]
    assert base.conflitos == []


def test_blocos_em_grade_2x2():
    c = casualizar("DBC", 5, 4, 3)
    cfg = ConfigLayout(largura=3, comprimento=5, espaco_x=0.5, espaco_y=1, espaco_blocos=2, colunas_por_bloco=5,
                       blocos_por_fileira=2, espaco_fileiras_blocos=4, bordadura_externa=1)
    cr = gerar_croqui(c, cfg)
    larg_bloco = 5 * 3 + 4 * 0.5
    assert cr.largura_total == pytest.approx(2 * larg_bloco + 2 + 2)
    assert cr.altura_total == pytest.approx(2 * 5 + 4 + 2)
    caixas = {g: _caixa(p) for g, p in cr.caixas.items()}
    assert caixas[1][1] == pytest.approx(caixas[2][1])                 # bloco II ao lado do I
    assert caixas[3][3] == pytest.approx(caixas[1][1] - 4)             # bloco III na fileira de baixo
    assert caixas[3][0] == pytest.approx(caixas[1][0])
    assert verificar_croqui(c, cr) == []


def test_serpentina_de_blocos():
    c = casualizar("DBC", 3, 4, 3)
    cr = gerar_croqui(c, ConfigLayout(blocos_por_fileira=2, ordem_blocos="serpentina"))
    caixas = {g: _caixa(p) for g, p in cr.caixas.items()}
    assert caixas[3][0] > caixas[4][0]                                 # 2ª fileira volta da direita p/ esquerda
    assert caixas[3][0] == pytest.approx(caixas[2][0])


def test_corredores_internos():
    c = casualizar("DIC", 4, 3, 5)
    cfg = ConfigLayout(largura=2, comprimento=4, espaco_x=0.5, espaco_y=0.5, colunas_por_bloco=6,
                       corredor_a_cada_colunas=3, largura_corredor_colunas=4,
                       corredor_a_cada_linhas=1, largura_corredor_linhas=2)
    cr = gerar_croqui(c, cfg)
    assert cr.largura_total == pytest.approx(6 * 2 + 5 * 0.5 + 4)
    assert cr.altura_total == pytest.approx(2 * 4 + 0.5 + 2)
    xs = sorted({round(_caixa(x.poligono)[0], 6) for x in cr.celulas})
    passos = [b - a for a, b in zip(xs, xs[1:])]
    assert passos.count(pytest.approx(2.5)) == 4 and passos.count(pytest.approx(6.5)) == 1
    assert any(ct.valor == pytest.approx(4) for ct in cr.cotas)       # cota do corredor


def test_bordaduras_por_lado():
    c = casualizar("DIC", 3, 2, 1)
    cfg = ConfigLayout(largura=2, comprimento=3, espaco_x=0, espaco_y=0, colunas_por_bloco=3, bordadura_externa=1,
                       bordadura_esquerda=5, bordadura_topo=0)
    cr = gerar_croqui(c, cfg)
    assert cr.largura_total == pytest.approx(6 + 5 + 1)
    assert cr.altura_total == pytest.approx(6 + 0 + 1)
    x0, y0, x1, y1 = _caixa([p for x in cr.celulas for p in x.poligono])
    assert (x0, y0) == pytest.approx((5, 1)) and y1 == pytest.approx(cr.altura_total)


@pytest.mark.parametrize("canto", ["sup_esq", "sup_dir", "inf_esq", "inf_dir"])
def test_canto_inicial(canto):
    c = casualizar("DBC", 4, 3, 9)
    cr = gerar_croqui(c, ConfigLayout(colunas_por_bloco=2, canto_inicial=canto))
    W, H = cr.largura_total, cr.altura_total
    primeira = min(cr.celulas, key=lambda x: (x.bloco, next(u for u in c.unidades if u.numero == x.numero).posicao))
    cx, cy = primeira.centro
    assert (cx < W / 2) == canto.endswith("esq")
    assert (cy > H / 2) == canto.startswith("sup")
    assert verificar_croqui(c, cr) == []
    assert all(r.ponto for r in cr.rotulos)
    # o rótulo do bloco fica sempre acima do bloco
    for cb in cr.blocos:
        assert cb.rotulo_em[1] >= _caixa(cb.poligono)[3] - 1e-9


def test_deslocamento_manual_de_bloco_e_conflito():
    c = casualizar("DBC", 4, 3, 2)
    cfg = ConfigLayout(largura=2, comprimento=4, espaco_x=0.5, espaco_blocos=2, colunas_por_bloco=4,
                       deslocamentos_blocos={"2": [0, -10]})
    cr = gerar_croqui(c, cfg)
    caixas = {g: _caixa(p) for g, p in cr.caixas.items()}
    assert caixas[2][3] == pytest.approx(caixas[1][3] - 10)
    assert cr.altura_total == pytest.approx(4 + 10)
    assert cr.conflitos == []
    # puxar o bloco III sobre o II gera conflito
    cr2 = gerar_croqui(c, ConfigLayout(**{**cfg.para_dict(), "deslocamentos_blocos": {"3": [-5, 0]}}))
    assert (2, 3) in cr2.conflitos
    assert cr2.metricas["sobreposicoes"] == 1


def test_deslocamento_invalido_rejeitado():
    with pytest.raises(ValueError):
        ConfigLayout(deslocamentos_blocos={"1": [float("nan"), 0]})


def test_para_dict_omite_deslocamentos_nulos():
    d = ConfigLayout(deslocamentos_blocos={"1": [0, 0], "2": [1.5, 0]}).para_dict()
    assert d["deslocamentos_blocos"] == {"2": [1.5, 0.0]}


def test_cotas_principais():
    c = casualizar("DBC", 4, 2, 1)
    cfg = ConfigLayout(largura=3, comprimento=6, espaco_x=0.5, espaco_y=1, espaco_blocos=2.5, colunas_por_bloco=2,
                       bordadura_externa=1.5)
    cr = gerar_croqui(c, cfg)
    valores = sorted(round(ct.valor, 6) for ct in cr.cotas)
    for v in (cr.largura_total, cr.altura_total, 3, 6, 0.5, 1, 2.5, 1.5):
        assert round(v, 6) in valores, v
    gerais = [ct for ct in cr.cotas if ct.nivel == "geral"]
    assert len(gerais) == 2
    # a linha de cota é paralela ao segmento medido e com o mesmo comprimento
    for ct in cr.cotas:
        assert math.dist(ct.q1, ct.q2) == pytest.approx(ct.valor)


def test_cotas_acompanham_rotacao():
    c = casualizar("DIC", 3, 2, 1)
    cr = gerar_croqui(c, ConfigLayout(colunas_por_bloco=3, rotacao_graus=30))
    for ct in cr.cotas:
        assert math.dist(ct.p1, ct.p2) == pytest.approx(ct.valor)


def test_texto_medida():
    assert texto_medida(0.25) == "25 cm"
    assert texto_medida(3) == "3,00 m"
    assert texto_medida(25.5) == "25,5 m"
    assert texto_medida(40) == "40 m"


def test_vasos_bancadas_em_grade():
    c = casualizar("DBC", 6, 4, 4)
    cfg = ConfigLayout(tipo="vasos", bancadas=True, blocos_por_fileira=2, colunas_por_bloco=3, espaco_blocos=0.6)
    cr = gerar_croqui(c, cfg)
    assert len(cr.bancadas) == 4 and cr.conflitos == []
    assert verificar_croqui(c, cr) == []
