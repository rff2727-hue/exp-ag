"""Exp-Ag — planejamento, casualização e croquis de experimentos agronômicos.

Execução local:  streamlit run app.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st

from componentes.visual import aplicar_estilo, selo_futuro
from ui.estado import PAGINAS, aviso_armazenamento, mensagem_pendente, verificar_acesso

__version__ = "0.3.0"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

st.set_page_config(
    page_title="Exp-Ag",
    page_icon=str(Path(__file__).parent / "assets" / "icone.png"),
    layout="wide",
    initial_sidebar_state="expanded",
)
aplicar_estilo()
st.logo(str(Path(__file__).parent / "assets" / "logo_expag.png"), size="large",
        icon_image=str(Path(__file__).parent / "assets" / "icone_expag.png"))

if not verificar_acesso():
    st.stop()

navegacao = st.navigation(
    {
        "": [st.Page(PAGINAS["inicio"], title="Painel", icon=":material/space_dashboard:", default=True)],
        "Experimentos": [
            st.Page(PAGINAS["projetos"], title="Meus projetos", icon=":material/folder_open:"),
            st.Page(PAGINAS["novo"], title="Novo experimento", icon=":material/add_box:"),
            st.Page(PAGINAS["experimento"], title="Experimento aberto", icon=":material/grid_on:"),
            st.Page(PAGINAS["modelos"], title="Biblioteca de modelos", icon=":material/library_books:"),
        ],
        "Áreas": [st.Page(PAGINAS["satelites"], title="Diagnóstico por satélite", icon=":material/satellite_alt:")],
        "Sistema": [st.Page(PAGINAS["configuracoes"], title="Configurações", icon=":material/tune:")],
    }
)

with st.sidebar:
    st.text_input("Seu nome (registro de autoria)", key="autor", placeholder="Ex.: R. F. Firmano",
                  help="Gravado no histórico de alterações dos experimentos.")
    st.markdown(
        "<div class='ae-secao'>Próximos módulos</div><div class='ae-roteiro'>"
        + "".join(f"<div>{selo_futuro(f)}<span>{t}</span></div>" for f, t in (
            ("fase 4", "Avaliações e coletas"), ("fase 4", "Planilhas de campo preenchidas"),
            ("fase 4", "Cálculo de insumos"), ("fase 5", "Análises estatísticas")))
        + "</div>",
        unsafe_allow_html=True,
    )
    st.caption(f"Versão {__version__}")

aviso_armazenamento()
mensagem_pendente()
navegacao.run()
