"""Painel inicial."""

from __future__ import annotations

import streamlit as st

from componentes.visual import mostradores, secao
from ui.estado import PAGINAS, abrir_experimento, repositorio

repo = repositorio()

st.title("Planejamento de experimentos agronômicos")
st.markdown(
    "<span class='ae-nota'>Delineamento, casualização reprodutível, croquis e documentação — "
    "do projeto ao campo.</span>",
    unsafe_allow_html=True,
)

projetos = repo.listar_projetos()
experimentos = repo.listar()
mostradores([
    ("Projetos", str(len(projetos)), ""),
    ("Experimentos ativos", str(len(experimentos)), ""),
    ("Unidades planejadas", str(sum(e.n_tratamentos * e.repeticoes for e in experimentos)), ""),
    ("Em campo", str(sum(e.status in ("implantado", "em condução") for e in experimentos)), ""),
])

c1, c2, c3 = st.columns(3)
if c1.button("Novo experimento", type="primary", width="stretch", icon=":material/add_box:"):
    st.session_state.pop("rascunho", None)
    st.switch_page(PAGINAS["novo"])
if c2.button("Partir de um modelo", width="stretch", icon=":material/library_books:"):
    st.switch_page(PAGINAS["modelos"])
if c3.button("Meus projetos", width="stretch", icon=":material/folder_open:"):
    st.switch_page(PAGINAS["projetos"])

secao("Experimentos recentes")
if not experimentos:
    st.info("Nenhum experimento ainda. Comece por **Novo experimento** ou escolha um modelo da biblioteca. "
            "Em **Configurações** você pode carregar experimentos de exemplo.")
for e in experimentos[:8]:
    c1, c2, c3, c4 = st.columns([1.2, 4, 2.2, 1])
    c1.markdown(f"**{e.codigo}**")
    c2.markdown(f"{e.titulo}  \n<span class='ae-nota'>{e.projeto} · {e.ambiente}"
                f"{' · ' + e.safra if e.safra else ''}{' · ' + e.local if e.local else ''}</span>",
                unsafe_allow_html=True)
    c3.markdown(f"<span class='ae-nota'>{e.delineamento} · {e.n_tratamentos} trat. × {e.repeticoes} rep. · "
                f"v{e.versao} · {e.status}</span>", unsafe_allow_html=True)
    if c4.button("Abrir", key=f"abrir_{e.id}", width="stretch"):
        abrir_experimento(e.id)
