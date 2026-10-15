"""Testes da interface com o AppTest do Streamlit (sem navegador)."""

import pytest
from streamlit.testing.v1 import AppTest
from tests_util import RAIZ_APP


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'ui.db'}")
    monkeypatch.chdir(RAIZ_APP)
    at = AppTest.from_file(str(RAIZ_APP / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def _botao(at, rotulo):
    return next(b for b in at.button if b.label == rotulo)


@pytest.mark.parametrize("pagina", ["ui/inicio.py", "ui/projetos.py", "ui/novo_experimento.py",
                                    "ui/experimento.py", "ui/modelos.py", "ui/configuracoes.py",
                                    "ui/satelites.py"])
def test_paginas_abrem_sem_erro(app, pagina):
    app.switch_page(pagina).run()
    assert not app.exception, app.exception


def test_exemplos_e_experimento_aberto(app):
    app.switch_page("ui/configuracoes.py").run()
    _botao(app, "Carregar exemplos").click().run()
    assert not app.exception
    app.switch_page("ui/experimento.py").run()
    assert not app.exception, app.exception
    assert any("EX-" in t.value for t in app.title)
    app.switch_page("ui/projetos.py").run()
    assert not app.exception
    assert any("Abrir" == b.label for b in app.button)


def test_assistente_completo(app):
    app.switch_page("ui/novo_experimento.py").run()
    app.text_input(key="nx0_npc").input("PRJ-UI").run()
    app.text_input(key="nx0_npt").input("Projeto via interface").run()
    app.text_input(key="nx0_meta_cod").input("UI-01").run()
    app.text_input(key="nx0_meta_tit").input("Experimento criado pelo assistente").run()
    for _ in range(5):
        assert not app.exception, app.exception
        assert not app.error, [e.value for e in app.error]
        _botao(app, "Avançar →").click().run()
    assert not app.exception, app.exception
    _botao(app, "Salvar experimento").click().run()
    assert not app.exception, app.exception
    assert any("UI-01" in t.value for t in app.title)


def test_modelo_preenche_assistente(app):
    app.switch_page("ui/modelos.py").run()
    _botao(app, "Usar este modelo").click().run()
    assert not app.exception, app.exception
    assert any("Partindo do modelo" in c.value for c in app.caption)


def test_assistente_parcelas_subdivididas(app):
    app.switch_page("ui/novo_experimento.py").run()
    app.text_input(key="nx0_npc").input("PRJ-SUB").run()
    app.text_input(key="nx0_npt").input("Projeto subdivididas").run()
    app.text_input(key="nx0_meta_cod").input("SUB-UI").run()
    app.text_input(key="nx0_meta_tit").input("Subdivididas pelo assistente").run()
    _botao(app, "Avançar →").click().run()
    app.radio(key="nx0_del_arr_DBC").set_value("subdividida").run()
    assert not app.exception, app.exception
    for _ in range(4):
        assert not app.exception, app.exception
        assert not app.error, [e.value for e in app.error]
        _botao(app, "Avançar →").click().run()
    _botao(app, "Salvar experimento").click().run()
    assert not app.exception, app.exception
    assert any("SUB-UI" in t.value for t in app.title)


def test_rotacao_e_etiquetas_no_experimento(app, monkeypatch):
    app.switch_page("ui/configuracoes.py").run()
    _botao(app, "Carregar exemplos").click().run()
    import os

    from dados.banco import criar_engine, fabrica_sessoes
    from dados.repositorios.experimentos import RepositorioExperimentos
    repo = RepositorioExperimentos(fabrica_sessoes(criar_engine(os.environ["DATABASE_URL"])))
    vasos = next(e for e in repo.listar() if e.codigo == "EX-VASOS")
    app.query_params["exp"] = str(vasos.id)
    app.query_params["ue"] = "EX-VASOS-P07-" + repo.carregar(vasos.id).casualizacao.unidades[6].codigo.split("P07-")[1]
    app.session_state["exp_id"] = vasos.id
    app.switch_page("ui/experimento.py").run()
    assert not app.exception, app.exception
    assert any("EX-VASOS-P07" in s.value for s in app.success)                # QR Code abriu a unidade
    _botao(app, "Registrar movimento").click().run()
    assert not app.exception, app.exception
    assert len(repo.movimentos(vasos.id)) == 1
    assert repo.carregar(vasos.id).verificar() == []


def test_mapa_e_locacao_com_area_e_posicao(app):
    """Aba Mapa e locação: encaixe automático no perímetro salvo, conferência e saídas sem erro."""
    from shapely.geometry import Polygon

    from dados.banco import criar_engine, fabrica_sessoes, url_banco
    from dados.repositorios.experimentos import RepositorioExperimentos

    app.switch_page("ui/configuracoes.py").run()
    _botao(app, "Carregar exemplos").click().run()
    repo = RepositorioExperimentos(fabrica_sessoes(criar_engine(url_banco())))
    exp = next(e for e in repo.listar() if e.codigo == "EX-CAMPO")
    pid = repo.projeto_de(exp.id)
    area = Polygon([(-54.8112, -22.2748), (-54.8079, -22.2752), (-54.8074, -22.2731), (-54.8098, -22.2722)])
    aid = repo.salvar_area("Talhão 12", area, projeto_id=pid)
    from motor.gis.georref import Georreferencia

    repo.salvar_georreferencia(exp.id, Georreferencia(lat=-22.2738, lon=-54.8093, azimute=15, modo="manual"), aid)
    app.session_state["exp_id"] = exp.id
    app.switch_page("ui/experimento.py").run()
    assert not app.exception, app.exception
    assert any("Plano de locação" in b.label for b in app.get("download_button"))
    assert any("Google Earth" in str(getattr(b, "label", "")) for b in app.get("download_button"))
    assert any("Na área" in m.value for m in app.markdown if hasattr(m, "value"))
    # encaixe automático
    app.segmented_control(key=f"gm{exp.id}_1_como").set_value("perimetro").run()
    assert not app.exception, app.exception
    _botao(app, "Encaixar").click().run()
    assert not app.exception, app.exception
    assert any("cabe na área" in s.value for s in app.success)
    _botao(app, "Salvar posição").click().run()
    assert not app.exception, app.exception
    assert repo.carregar_georreferencia(exp.id)["geo"].modo == "perimetro"
