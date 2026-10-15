"""Persistência, versões, duplicação e migrações."""

import pytest

from aplicacao.exemplos import carregar_exemplos, cenario_a, cenario_b
from dados.banco import criar_engine, fabrica_sessoes, migrar, normalizar_url
from dados.repositorios.experimentos import ErroRepositorio, RepositorioExperimentos
from motor.geometria.layout import ConfigLayout
from motor.planejamento import planejar


def _assinatura(p):
    return ([(u.numero, u.parcela, u.codigo, u.tratamento, u.bloco, u.repeticao) for u in p.casualizacao.unidades],
            [(t.codigo, t.rotulo) for t in p.tratamentos],
            [(c.numero, tuple(round(v, 9) for xy in c.poligono for v in xy)) for c in p.croqui.celulas],
            p.casualizacao.semente, p.layout.para_dict())


def test_migracao_idempotente(url_temp):
    eng = criar_engine(url_temp)
    migrar(eng)
    migrar(eng)
    eng.dispose()


def test_normalizar_url():
    assert normalizar_url("postgres://u:s@h/db").startswith("postgresql+psycopg://")
    assert normalizar_url("postgresql://u:s@h/db").startswith("postgresql+psycopg://")
    assert normalizar_url("sqlite:///x.db") == "sqlite:///x.db"


def test_codigos_duplicados_sao_recusados(repo):
    pid = repo.criar_projeto("P", "Projeto")
    repo.salvar_novo(pid, cenario_a())
    with pytest.raises(ErroRepositorio):
        repo.salvar_novo(pid, cenario_a())
    with pytest.raises(ErroRepositorio):
        repo.criar_projeto("p", "outro")


def test_layout_preserva_casualizacao(repo):
    pid = repo.criar_projeto("P", "Projeto")
    eid = repo.salvar_novo(pid, cenario_a())
    antes = repo.carregar(eid)
    repo.atualizar_layout(eid, ConfigLayout(colunas_por_bloco=10, largura=4, comprimento=8, ordem="serpentina"))
    depois = repo.carregar(eid)
    assert _assinatura(antes)[0] == _assinatura(depois)[0]
    assert depois.layout.largura == 4 and depois.versao == antes.versao


def test_versoes_e_restauracao(repo):
    pid = repo.criar_projeto("P", "Projeto")
    eid = repo.salvar_novo(pid, cenario_a())
    v1 = repo.carregar(eid)
    p2 = planejar(v1.meta, "DBC", v1.estrutura, 5, 4321, v1.layout, v1.padrao_codigo, v1.numeracao)
    assert repo.nova_versao(eid, p2, "Mais um bloco") == 2
    atual = repo.carregar(eid)
    assert atual.versao == 2 and atual.casualizacao.n_unidades == 50
    assert [(v.versao, v.ativa) for v in repo.versoes(eid)] == [(1, False), (2, True)]
    repo.restaurar_versao(eid, 1)
    assert _assinatura(repo.carregar(eid)) == _assinatura(v1)
    assert [h["acao"] for h in repo.historico(eid)][:3] == ["restauração", "nova versão", "criação"]


def test_duplicar(repo):
    pid = repo.criar_projeto("P", "Projeto")
    eid = repo.salvar_novo(pid, cenario_b())
    mesma = repo.carregar(repo.duplicar(eid, "EX-VASOS2", "Cópia", None))
    nova = repo.carregar(repo.duplicar(eid, "EX-VASOS3", "Cópia", 1))
    orig = repo.carregar(eid)
    assert [u.tratamento for u in mesma.casualizacao.unidades] == [u.tratamento for u in orig.casualizacao.unidades]
    assert mesma.casualizacao.unidades[0].codigo.startswith("EX-VASOS2-")
    assert [u.tratamento for u in nova.casualizacao.unidades] != [u.tratamento for u in orig.casualizacao.unidades]


def test_metadados_e_codigo_imutavel(repo):
    pid = repo.criar_projeto("P", "Projeto")
    eid = repo.salvar_novo(pid, cenario_a())
    p = repo.carregar(eid)
    p.meta.cultivar = "BRS 1074IPRO"
    repo.atualizar_metadados(eid, p.meta)
    assert repo.carregar(eid).meta.cultivar == "BRS 1074IPRO"
    p.meta.codigo = "OUTRO"
    with pytest.raises(ErroRepositorio):
        repo.atualizar_metadados(eid, p.meta)


def test_arquivar_listar_excluir(repo):
    criados = carregar_exemplos(repo)
    assert criados == ["EX-CAMPO", "EX-VASOS", "EX-FAT"]
    assert carregar_exemplos(repo) == []
    lista = repo.listar()
    assert len(lista) == 3 and len(repo.listar(busca="vasos")) == 1
    repo.arquivar(lista[0].id)
    assert len(repo.listar()) == 2 and len(repo.listar(incluir_arquivados=True)) == 3
    repo.excluir(lista[0].id)
    assert len(repo.listar(incluir_arquivados=True)) == 2


def test_banco_da_fase_1_migra_sem_perda(tmp_path):
    """Banco criado pela versão 0.1.0 (Fase 1, migração 0001) é atualizado para a 0002 e continua íntegro."""
    import shutil
    from pathlib import Path

    origem = Path(__file__).parent / "dados" / "banco_fase1.sqlite"
    destino = tmp_path / "antigo.sqlite"
    shutil.copy(origem, destino)
    eng = criar_engine(f"sqlite:///{destino}")
    migrar(eng)
    repo = RepositorioExperimentos(fabrica_sessoes(eng))
    lista = repo.listar()
    assert {e.codigo for e in lista} == {"EX-CAMPO", "EX-VASOS", "EX-FAT"}
    for e in lista:
        p = repo.carregar(e.id)
        assert p.verificar() == [] and p.arranjo.value == "convencional"
        assert repo.movimentos(e.id) == []
    eng.dispose()
