"""Rotação e remanejamento de vasos: identidade preservada, restrições do delineamento respeitadas."""

import pytest

from motor.dominio import EstruturaTratamentos, Fator, Nivel
from motor.geometria.layout import ConfigLayout, aplicar_posicoes
from motor.geometria.rotacao import (
    ErroRotacao,
    aplicar_tipo,
    mapa_inicial,
    posicao_atual,
    tipos_permitidos,
    verificar_mapa,
)
from motor.planejamento import Metadados, planejar
from motor.validacao.verificacoes import verificar_croqui


def fat(nome, n):
    return Fator(nome, [Nivel(f"{nome[0]}{i}") for i in range(1, n + 1)])


def plano(delin="DBC", arranjo="convencional", est=None, r=4):
    est = est or EstruturaTratamentos([fat("Trat", 6)])
    return planejar(Metadados("ROT", "t", ambiente="casa de vegetação"), delin, est, r, 5,
                    ConfigLayout(tipo="vasos", bancadas=True, arranjo_blocos="vertical"), "{exp}-P{parcela}",
                    "bloco" if delin == "DBC" else "sequencial", arranjo=arranjo)


@pytest.mark.parametrize("delin,arr,est,r", [
    ("DIC", "convencional", None, 4),
    ("DBC", "convencional", None, 4),
    ("DBC", "subdividida", EstruturaTratamentos([fat("A", 3), fat("B", 2)]), 3),
    ("DIC", "subdividida", EstruturaTratamentos([fat("A", 2), fat("B", 3)]), 3),
])
@pytest.mark.parametrize("tipo", ["deslocamento", "inversao", "sorteio"])
def test_movimentos_respeitam_o_delineamento(delin, arr, est, r, tipo):
    p = plano(delin, arr, est, r)
    m0 = mapa_inicial(p.casualizacao)
    m1 = aplicar_tipo(tipo, m0, p.casualizacao, p.croqui, k=1, semente=9, rodada=1)
    assert verificar_mapa(m1, p.casualizacao, p.croqui) == []
    assert m1 != m0
    novo = aplicar_posicoes(p.croqui, m1)
    assert verificar_croqui(p.casualizacao, novo) == []                       # bloco do croqui = bloco casualizado
    por_vaga = {c.vaga: c.centro for c in p.croqui.celulas}
    for c in novo.celulas:
        assert c.centro == por_vaga[m1[c.numero]]                              # a unidade está na vaga indicada
    assert [u.codigo for u in p.casualizacao.unidades] == [u.codigo for u in plano(delin, arr, est, r).casualizacao.unidades]


def test_deslocamento_completo_volta_ao_inicio():
    p = plano("DBC")
    m = mapa_inicial(p.casualizacao)
    for _ in range(6):                                                         # 6 vasos por bloco
        m = aplicar_tipo("deslocamento", m, p.casualizacao, p.croqui, k=1)
    assert m == mapa_inicial(p.casualizacao)


def test_sorteio_reprodutivel():
    p = plano("DIC")
    m0 = mapa_inicial(p.casualizacao)
    a = aplicar_tipo("sorteio", m0, p.casualizacao, p.croqui, semente=3, rodada=2)
    b = aplicar_tipo("sorteio", m0, p.casualizacao, p.croqui, semente=3, rodada=2)
    c = aplicar_tipo("sorteio", m0, p.casualizacao, p.croqui, semente=3, rodada=3)
    assert a == b and a != c


def test_troca_dentro_e_fora_do_bloco():
    p = plano("DBC")
    us = p.casualizacao.unidades
    m0 = mapa_inicial(p.casualizacao)
    mesmo = [u.numero for u in us if u.bloco == 1][:2]
    m1 = aplicar_tipo("troca", m0, p.casualizacao, p.croqui, unidades=tuple(mesmo))
    assert m1[mesmo[0]] == m0[mesmo[1]] and verificar_mapa(m1, p.casualizacao, p.croqui) == []
    outro = next(u.numero for u in us if u.bloco == 2)
    with pytest.raises(ErroRotacao):
        aplicar_tipo("troca", m0, p.casualizacao, p.croqui, unidades=(mesmo[0], outro))


def test_troca_na_subdividida_move_parcelas_principais_inteiras():
    p = plano("DBC", "subdividida", EstruturaTratamentos([fat("A", 3), fat("B", 2)]), 3)
    us = p.casualizacao.unidades
    u1 = next(u for u in us if u.bloco == 1 and u.principal == 1 and u.sub == 1)
    u2 = next(u for u in us if u.bloco == 1 and u.principal == 3 and u.sub == 2)
    m1 = aplicar_tipo("troca", mapa_inicial(p.casualizacao), p.casualizacao, p.croqui, unidades=(u1.numero, u2.numero))
    assert verificar_mapa(m1, p.casualizacao, p.croqui) == []
    irmao = next(u for u in us if u.bloco == 1 and u.principal == 1 and u.sub == 2)
    assert {m1[u1.numero], m1[irmao.numero]} == {mapa_inicial(p.casualizacao)[u.numero] for u in us
                                                  if u.bloco == 1 and u.principal == 3}


def test_quadrado_latino_so_linhas_e_colunas():
    p = planejar(Metadados("QLR", "t"), "QL", EstruturaTratamentos([fat("Trat", 5)]), 0, 2,
                 ConfigLayout(tipo="vasos"), "{exp}-P{parcela}")
    assert tipos_permitidos(p.casualizacao) == ["linhas", "colunas"]
    m = mapa_inicial(p.casualizacao)
    for tipo, k in (("linhas", 2), ("colunas", 1), ("linhas", 4)):
        m = aplicar_tipo(tipo, m, p.casualizacao, p.croqui, k=k)
        assert verificar_mapa(m, p.casualizacao, p.croqui) == []
    errado = dict(m)
    a, b = list(errado)[:2]
    errado[a], errado[b] = errado[b], errado[a]
    assert verificar_mapa(errado, p.casualizacao, p.croqui)


def test_faixas_nao_tem_rotacao():
    p = planejar(Metadados("FX", "t"), "DBC", EstruturaTratamentos([fat("A", 2), fat("B", 2)]), 3, 1,
                 ConfigLayout(), "{exp}-P{parcela}", "bloco", arranjo="faixas")
    assert tipos_permitidos(p.casualizacao) == []


def test_movimentos_persistidos_e_desfeitos(repo):
    p = plano("DBC")
    eid = repo.salvar_novo(repo.criar_projeto("P", "Projeto"), p)
    assert posicao_atual(p.casualizacao, repo.movimentos(eid)) == mapa_inicial(p.casualizacao)
    m1 = aplicar_tipo("deslocamento", mapa_inicial(p.casualizacao), p.casualizacao, p.croqui, k=2)
    repo.registrar_movimento(eid, m1, "deslocamento", "k = 2", "2026-10-20", "RF")
    m2 = aplicar_tipo("inversao", m1, p.casualizacao, p.croqui)
    repo.registrar_movimento(eid, m2, "inversao", "", "2026-11-03")
    movs = repo.movimentos(eid)
    assert [m["ordem"] for m in movs] == [1, 2] and posicao_atual(p.casualizacao, movs) == m2
    repo.desfazer_movimento(eid)
    assert posicao_atual(p.casualizacao, repo.movimentos(eid)) == m1
    from dados.repositorios.experimentos import ErroRepositorio
    with pytest.raises(ErroRepositorio):
        repo.registrar_movimento(eid, {1: 1}, "x")
    assert repo.carregar(eid).verificar() == []                              # casualização intacta
