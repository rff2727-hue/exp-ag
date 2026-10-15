"""Geometria do croqui e identificadores."""

import math

import pytest

from motor.casualizacao.casualizador import casualizar
from motor.geometria.layout import ConfigLayout, gerar_croqui, poligono_area
from motor.identificadores.codigos import ErroIdentificador, aplicar_codigos, validar_codigo_experimento
from motor.validacao.verificacoes import verificar_croqui


def _sobrepoe(a, b, tol=1e-9):
    ax, ay = [p[0] for p in a], [p[1] for p in a]
    bx, by = [p[0] for p in b], [p[1] for p in b]
    return min(ax) < max(bx) - tol and min(bx) < max(ax) - tol and min(ay) < max(by) - tol and min(by) < max(ay) - tol


def test_dimensoes_e_areas_dbc():
    c = casualizar("DBC", 10, 4, 1)
    cfg = ConfigLayout(largura=3, comprimento=6, espaco_x=0.5, espaco_y=1, espaco_blocos=2, colunas_por_bloco=5,
                       bordadura_lateral=0.5, bordadura_cabeceira=0.5, bordadura_externa=1)
    cr = gerar_croqui(c, cfg)
    m = cr.metricas
    assert m["largura_total_m"] == pytest.approx(4 * (5 * 3 + 4 * 0.5) + 3 * 2 + 2)
    assert m["comprimento_total_m"] == pytest.approx(2 * 6 + 1 + 2)
    assert m["area_parcela_m2"] == 18 and m["area_util_m2"] == pytest.approx(2 * 5)
    assert m["area_bordadura_parcela_m2"] == pytest.approx(8)
    assert m["area_total_m2"] == pytest.approx(m["largura_total_m"] * m["comprimento_total_m"])
    assert m["area_circulacao_m2"] == pytest.approx(m["area_total_m2"] - 40 * 18)
    for cel in cr.celulas:
        assert poligono_area(cel.poligono) == pytest.approx(18)
        assert poligono_area(cel.poligono_util) == pytest.approx(10)
    assert verificar_croqui(c, cr) == []


def test_sem_sobreposicao_e_dentro_do_contorno():
    c = casualizar("DBC", 7, 3, 2)
    cr = gerar_croqui(c, ConfigLayout(colunas_por_bloco=3, arranjo_blocos="vertical", ordem="serpentina"))
    x0, y0, x1, y1 = cr.limites()
    for i, a in enumerate(cr.celulas):
        for p in a.poligono:
            assert x0 - 1e-9 <= p[0] <= x1 + 1e-9 and y0 - 1e-9 <= p[1] <= y1 + 1e-9
        for b in cr.celulas[i + 1:]:
            assert not _sobrepoe(a.poligono, b.poligono)


def test_largura_por_linhas_de_plantio():
    c = casualizar("DIC", 4, 3, 1)
    cr = gerar_croqui(c, ConfigLayout(n_linhas_plantio=6, espacamento_linhas=0.45, linhas_bordadura=1,
                                      comprimento=5, bordadura_cabeceira=0.5))
    assert cr.metricas["largura_parcela_m"] == pytest.approx(2.7)
    assert cr.metricas["largura_util_m"] == pytest.approx(1.8)
    assert cr.metricas["linhas_uteis"] == 4


def test_serpentina_inverte_linhas_pares():
    c = casualizar("DIC", 3, 2, 1)
    cr = gerar_croqui(c, ConfigLayout(colunas_por_bloco=3, ordem="serpentina"))
    cols = {cel.numero: cel.coluna for cel in cr.celulas}
    assert [cols[i] for i in (1, 2, 3)] == [0, 1, 2]
    assert [cols[i] for i in (4, 5, 6)] == [2, 1, 0]


def test_rotacao_preserva_areas_e_distancias():
    c = casualizar("DBC", 5, 3, 4)
    a = gerar_croqui(c, ConfigLayout(rotacao_graus=0))
    b = gerar_croqui(c, ConfigLayout(rotacao_graus=37))
    for ca, cb in zip(a.celulas, b.celulas):
        assert poligono_area(ca.poligono) == pytest.approx(poligono_area(cb.poligono))
    d = lambda cr, i, j: math.dist(cr.celulas[i].centro, cr.celulas[j].centro)  # noqa: E731
    assert d(a, 0, 7) == pytest.approx(d(b, 0, 7))


def test_layout_fisico_nao_altera_casualizacao():
    c = casualizar("DBC", 6, 4, 9)
    antes = [(u.numero, u.tratamento, u.bloco) for u in c.unidades]
    for cfg in (ConfigLayout(colunas_por_bloco=2), ConfigLayout(arranjo_blocos="vertical", ordem="serpentina"),
                ConfigLayout(tipo="vasos")):
        cr = gerar_croqui(c, cfg)
        assert verificar_croqui(c, cr) == []
    assert [(u.numero, u.tratamento, u.bloco) for u in c.unidades] == antes


def test_vasos():
    c = casualizar("DIC", 6, 5, 1)
    cr = gerar_croqui(c, ConfigLayout(tipo="vasos", colunas_por_bloco=6, diametro_vaso=0.25, espaco_vasos=0.1))
    assert len(cr.celulas) == 30
    assert {cel.linha for cel in cr.celulas} == set(range(5))
    assert cr.metricas["largura_total_m"] == pytest.approx(6 * 0.25 + 5 * 0.1)


@pytest.mark.parametrize("kw", [dict(largura=0), dict(comprimento=1, bordadura_cabeceira=0.5),
                                dict(n_linhas_plantio=2, espacamento_linhas=0.5, linhas_bordadura=1),
                                dict(espaco_x=-1), dict(tipo="vasos", diametro_vaso=0)])
def test_layout_invalido(kw):
    with pytest.raises(ValueError):
        ConfigLayout(**kw)


def test_codigos_unicos_e_padronizados():
    c = casualizar("DBC", 10, 4, 1, "bloco")
    aplicar_codigos(c, "EXP", "{exp}-P{parcela}-B{bloco}-T{trat}")
    assert c.unidades[0].codigo.startswith("EXP-P101-B01-T")
    assert len({u.codigo for u in c.unidades}) == 40
    c = casualizar("DIC", 6, 5, 1)
    aplicar_codigos(c, "VASO", "{exp}-T{trat}-R{rep}")
    assert len({u.codigo for u in c.unidades}) == 30


def test_padrao_que_gera_duplicatas_e_rejeitado():
    c = casualizar("DBC", 4, 3, 1)
    with pytest.raises(ErroIdentificador):
        aplicar_codigos(c, "EXP", "{exp}-T{trat}")
    with pytest.raises(ErroIdentificador):
        aplicar_codigos(c, "EXP", "{exp}-{xyz}")
    with pytest.raises(ErroIdentificador):
        validar_codigo_experimento("com espaço")
