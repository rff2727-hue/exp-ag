"""Matriz de tratamentos, quadro de GL e avisos."""

import pytest

from motor.dominio import EstruturaTratamentos, Fator, Nivel, TratamentoAdicional
from motor.estatistica.delineamentos import avisos_planejamento, quadro_gl
from motor.estatistica.tratamentos import ErroEstrutura, gerar_tratamentos


def fat(nome, *niveis, **kw):
    return Fator(nome, [Nivel(n) if isinstance(n, str) else Nivel(str(n), n) for n in niveis], **kw)


def test_fatorial_3x2_gera_6_combinacoes_em_ordem():
    e = EstruturaTratamentos([fat("Fonte", "A", "B", "C"), fat("Inoc", "Sem", "Com")])
    ts = gerar_tratamentos(e)
    assert len(ts) == 6
    assert [t.niveis["Fonte"] for t in ts] == ["A", "A", "B", "B", "C", "C"]
    assert [t.niveis["Inoc"] for t in ts] == ["Sem", "Com"] * 3
    assert [t.codigo for t in ts] == [f"T0{i}" for i in range(1, 7)]
    assert len({t.rotulo for t in ts}) == 6


def test_fatorial_com_adicional():
    e = EstruturaTratamentos([fat("F", "a", "b", "c"), fat("G", "x", "y")],
                             [TratamentoAdicional("Testemunha", papel="testemunha")])
    ts = gerar_tratamentos(e)
    assert len(ts) == 7 and ts[-1].tipo.value == "adicional" and ts[-1].niveis == {}
    assert e.esquema == "3 × 2 + 1"
    gl = {g.fonte.strip(): g.gl for g in quadro_gl("DBC", e, 4)}
    assert gl == {"Blocos": 3, "Tratamentos": 6, "F": 2, "G": 1, "F × G": 2, "Fatorial vs. adicional(is)": 1,
                  "Resíduo": 18, "Total": 27}


def test_fatorial_triplo_gl():
    e = EstruturaTratamentos([fat("A", "1", "2"), fat("B", "1", "2", "3"), fat("C", "1", "2")])
    gl = {g.fonte.strip(): g.gl for g in quadro_gl("DIC", e, 3)}
    assert gl["A × B × C"] == 2 and gl["Tratamentos"] == 11 and gl["Resíduo"] == 24 and gl["Total"] == 35


def test_gl_soma_total():
    e = EstruturaTratamentos([fat("T", *[f"t{i}" for i in range(10)])])
    gl = quadro_gl("DBC", e, 4)
    d = {g.fonte: g.gl for g in gl}
    assert d["Blocos"] + d["T"] + d["Resíduo"] == d["Total"] == 39


def test_quantitativo_exige_valor_e_mostra_unidade():
    with pytest.raises(ErroEstrutura):
        gerar_tratamentos(EstruturaTratamentos([Fator("Dose", [Nivel("0", 0), Nivel("alta")], "quantitativo")]))
    ts = gerar_tratamentos(EstruturaTratamentos([fat("Dose", 0, 50, tipo="quantitativo", unidade="kg ha⁻¹")]))
    assert ts[1].rotulo == "50 kg ha⁻¹"


@pytest.mark.parametrize("estrutura", [
    EstruturaTratamentos([fat("A", "x", "x")]),
    EstruturaTratamentos([fat("A", "x", "y"), fat("a", "z", "w")]),
    EstruturaTratamentos([fat("A", "x")]),
    EstruturaTratamentos([]),
])
def test_estruturas_invalidas(estrutura):
    with pytest.raises(ErroEstrutura):
        gerar_tratamentos(estrutura)


def test_avisos():
    e = EstruturaTratamentos([fat("T", "a", "b", "c")])
    niveis = {a.nivel for a in avisos_planejamento("DIC", e, 3)}
    assert "alerta" in niveis  # resíduo com 6 GL e só 9 unidades
    assert any(a.nivel == "erro" for a in avisos_planejamento("DIC", e, 1))
