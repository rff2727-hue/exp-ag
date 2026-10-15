"""Projetos de pesquisa e seus experimentos."""

from __future__ import annotations

import streamlit as st

from componentes.visual import secao
from dados.repositorios.experimentos import ErroRepositorio
from motor.exportacao.projeto_json import ErroImportacao, importar_json
from motor.planejamento import planejar
from ui.estado import PAGINAS, abrir_experimento, autor, avisar_depois, repositorio

repo = repositorio()
ss = st.session_state

st.title("Meus projetos")

c1, c2, c3 = st.columns([3, 1, 1])
busca = c1.text_input("Buscar experimentos", placeholder="código, título, cultura ou local",
                      label_visibility="collapsed")
arquivados = c2.toggle("Mostrar arquivados", False)
if c3.button("Novo experimento", type="primary", width="stretch"):
    ss.pop("rascunho", None)
    st.switch_page(PAGINAS["novo"])

with st.expander("Criar projeto de pesquisa"):
    with st.form("novo_projeto", clear_on_submit=True):
        c1, c2 = st.columns([1, 3])
        cod = c1.text_input("Código *", max_chars=40)
        tit = c2.text_input("Título *")
        c1, c2, c3 = st.columns(3)
        inst = c1.text_input("Instituição")
        prog = c2.text_input("Programa / linha de pesquisa")
        resp = c3.text_input("Responsável")
        desc = st.text_area("Descrição", height=70)
        if st.form_submit_button("Criar projeto", type="primary"):
            try:
                repo.criar_projeto(cod, tit, inst, prog, resp, desc)
                avisar_depois(f"Projeto {cod} criado.")
                st.rerun()
            except ErroRepositorio as exc:
                st.error(str(exc))

with st.expander("Importar experimento (arquivo JSON exportado pelo aplicativo)"):
    projetos_all = repo.listar_projetos(incluir_arquivados=True)
    if not projetos_all:
        st.info("Crie um projeto antes de importar.")
    else:
        arq = st.file_uploader("Arquivo .json", type=["json"], key="imp_json")
        destino = st.selectbox("Projeto de destino", [p["id"] for p in projetos_all],
                               format_func={p["id"]: f"{p['codigo']} — {p['titulo']}" for p in projetos_all}.get)
        if arq is not None:
            if arq.size > 20 * 1024 * 1024:
                st.error("Arquivo muito grande (limite de 20 MB).")
            else:
                try:
                    plano = importar_json(arq.getvalue())
                except ErroImportacao as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Arquivo válido: {plano.meta.codigo} — {plano.meta.titulo} "
                               f"({plano.casualizacao.n_unidades} unidades; casualização conferida pela semente).")
                    novo_cod = st.text_input("Código no destino", plano.meta.codigo, max_chars=24)
                    if st.button("Importar", type="primary"):
                        try:
                            if novo_cod.strip() != plano.meta.codigo:
                                # novo código altera os identificadores: reconstrói com a mesma semente
                                plano.meta.codigo = novo_cod.strip()
                                plano = planejar(plano.meta, plano.delineamento, plano.estrutura, plano.repeticoes,
                                                 plano.casualizacao.semente, plano.layout, plano.padrao_codigo,
                                                 plano.numeracao)
                            novo = repo.salvar_novo(destino, plano, autor(), "Importado de arquivo JSON")
                        except (ErroRepositorio, ValueError) as exc:
                            st.error(str(exc))
                        else:
                            avisar_depois(f"Experimento {plano.meta.codigo} importado.")
                            abrir_experimento(novo)

projetos = repo.listar_projetos(incluir_arquivados=arquivados)
experimentos = repo.listar(incluir_arquivados=arquivados, busca=busca)
if not projetos:
    st.info("Nenhum projeto cadastrado. Crie um projeto acima ou comece diretamente por **Novo experimento**.")

for proj in projetos:
    exps = [e for e in experimentos if e.projeto_id == proj["id"]]
    if busca and not exps:
        continue
    secao(f"{proj['codigo']} — {proj['titulo']}")
    info = " · ".join(x for x in (proj["instituicao"], proj["programa"], proj["responsavel"]) if x)
    if info:
        st.markdown(f"<span class='ae-nota'>{info}</span>", unsafe_allow_html=True)
    if not exps:
        st.caption("Sem experimentos neste projeto.")
    for e in exps:
        c1, c2, c3, c4 = st.columns([1.3, 4, 2.6, 1])
        c1.markdown(f"**{e.codigo}**" + (" 🗄" if e.arquivado else ""))
        c2.markdown(f"{e.titulo}  \n<span class='ae-nota'>{e.ambiente}"
                    f"{' · ' + e.safra if e.safra else ''}{' · ' + e.local if e.local else ''}</span>",
                    unsafe_allow_html=True)
        c3.markdown(f"<span class='ae-nota'>{e.delineamento} · {e.n_tratamentos} × {e.repeticoes} = "
                    f"{e.n_tratamentos * e.repeticoes} UE · v{e.versao} · {e.status} · "
                    f"{e.atualizado_em:%d/%m/%Y}</span>", unsafe_allow_html=True)
        if c4.button("Abrir", key=f"ab_{e.id}", width="stretch"):
            abrir_experimento(e.id)
    if not exps and proj["n_experimentos"] == 0:
        with st.popover("Excluir projeto vazio"):
            if st.button("Confirmar exclusão", key=f"exp_{proj['id']}"):
                repo.excluir_projeto(proj["id"])
                avisar_depois(f"Projeto {proj['codigo']} excluído.")
                st.rerun()
