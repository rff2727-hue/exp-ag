"""Biblioteca de modelos de experimentos frequentes."""

from __future__ import annotations

import streamlit as st

from aplicacao.rascunho import aplicar_modelo, listar_modelos, rascunho_vazio
from componentes.visual import cartao
from ui.estado import PAGINAS

st.title("Biblioteca de modelos")
st.markdown("<span class='ae-nota'>Pontos de partida já configurados. Tudo pode ser ajustado no assistente "
            "antes de salvar.</span>", unsafe_allow_html=True)

modelos = listar_modelos()
for i in range(0, len(modelos), 3):
    cols = st.columns(3)
    for col, m in zip(cols, modelos[i:i + 3]):
        with col:
            cartao(m["nome"], m["descricao"])
            if st.button("Usar este modelo", key=f"mod_{m['arquivo']}", width="stretch"):
                st.session_state["rascunho"] = aplicar_modelo(m, rascunho_vazio())
                st.session_state["rascunho_v"] = st.session_state.get("rascunho_v", 0) + 1
                st.session_state["passo"] = 0
                st.switch_page(PAGINAS["novo"])
            st.write("")

