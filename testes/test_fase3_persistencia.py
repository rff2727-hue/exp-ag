"""Fase 3 — persistência de áreas, georreferenciamento e vínculos do Drive; migração a partir da Fase 2."""

import shutil

import pytest
from shapely.geometry import Polygon
from tests_util import RAIZ_APP

from aplicacao.exemplos import cenario_a
from dados.banco import criar_engine, fabrica_sessoes, migrar
from dados.repositorios.experimentos import ErroRepositorio, RepositorioExperimentos
from motor.gis.georref import Georreferencia

AREA = Polygon([(-54.81, -22.28), (-54.80, -22.28), (-54.80, -22.27), (-54.81, -22.27)])


def test_areas(repo):
    pid = repo.criar_projeto("P", "Projeto")
    a1 = repo.salvar_area("Talhão 7", AREA, projeto_id=pid, origem="talhao7.kml", autor="RF")
    a2 = repo.salvar_area("Cupinzeiro", AREA.buffer(-0.004), tipo="evitar", projeto_id=pid)
    a3 = repo.salvar_area("Área geral", AREA)
    lista = repo.listar_areas(pid)
    assert {x["id"] for x in lista} == {a1, a2, a3}
    assert [x["id"] for x in repo.listar_areas(pid, tipo="evitar")] == [a2]
    d = repo.carregar_area(a1)
    assert d["nome"] == "Talhão 7" and d["geometria"].equals_exact(AREA, 1e-12)
    assert 110 < d["area_ha"] < 115
    repo.renomear_area(a1, "Talhão 7A")
    assert repo.carregar_area(a1)["nome"] == "Talhão 7A"
    with pytest.raises(ErroRepositorio):
        repo.salvar_area("", AREA)
    with pytest.raises(ErroRepositorio):
        repo.salvar_area("x", AREA, tipo="outro")


def test_georreferencia_ida_e_volta_e_historico(repo):
    pid = repo.criar_projeto("P", "Projeto")
    eid = repo.salvar_novo(pid, cenario_a())
    assert repo.carregar_georreferencia(eid) is None
    aid = repo.salvar_area("Talhão", AREA, projeto_id=pid)
    ev = repo.salvar_area("Brejo", AREA.buffer(-0.004), tipo="evitar", projeto_id=pid)
    g = Georreferencia(lat=-22.275, lon=-54.805, azimute=33.3, modo="arraste")
    repo.salvar_georreferencia(eid, g, aid, [ev], autor="RF")
    repo.salvar_georreferencia(eid, g, aid, [ev], autor="RF")          # sem mudança: não duplica histórico
    d = repo.carregar_georreferencia(eid)
    assert d["geo"] == g and d["area_id"] == aid and d["evitar_ids"] == [ev] and d["atualizado_por"] == "RF"
    hist = [h for h in repo.historico(eid) if h["acao"] == "georreferenciamento"]
    assert len(hist) == 1 and "azimute 33.30°" in hist[0]["detalhe"]
    # excluir a área a evitar limpa a referência; excluir o perímetro zera area_id
    repo.excluir_area(ev)
    repo.excluir_area(aid)
    d = repo.carregar_georreferencia(eid)
    assert d["evitar_ids"] == [] and d["area_id"] is None
    repo.remover_georreferencia(eid)
    assert repo.carregar_georreferencia(eid) is None


def test_georreferencia_sai_com_o_experimento(repo):
    pid = repo.criar_projeto("P", "Projeto")
    eid = repo.salvar_novo(pid, cenario_a())
    repo.salvar_georreferencia(eid, Georreferencia(lat=-22.2, lon=-54.8))
    repo.salvar_vinculo_drive(f"exp:{eid}", "pasta123", "https://drive.google.com/drive/folders/pasta123",
                              {"relatorio": "arq1"})
    repo.excluir(eid)
    assert repo.vinculo_drive(f"exp:{eid}") is None
    eid2 = repo.salvar_novo(pid, cenario_a())
    assert repo.carregar_georreferencia(eid2) is None


def test_vinculo_drive(repo):
    assert repo.vinculo_drive("exp:1") is None
    repo.salvar_vinculo_drive("exp:1", "p1", "u1", {"a": "1"})
    repo.salvar_vinculo_drive("exp:1", "p1", "u1", {"a": "1", "b": "2"})
    v = repo.vinculo_drive("exp:1")
    assert v["arquivos"] == {"a": "1", "b": "2"}
    repo.remover_vinculo_drive("exp:1")
    assert repo.vinculo_drive("exp:1") is None


def test_banco_da_fase_1_migra_ate_a_fase_3(tmp_path):
    origem = RAIZ_APP / "testes" / "dados" / "banco_fase1.sqlite"
    destino = tmp_path / "fase1.sqlite"
    shutil.copy(origem, destino)
    eng = criar_engine(f"sqlite:///{destino}")
    migrar(eng)
    repo = RepositorioExperimentos(fabrica_sessoes(eng))
    lista = repo.listar(incluir_arquivados=True)
    assert lista
    eid = lista[0].id
    repo.salvar_georreferencia(eid, Georreferencia(lat=-22.2, lon=-54.8))
    assert repo.carregar_georreferencia(eid)["geo"].lat == -22.2
    eng.dispose()
