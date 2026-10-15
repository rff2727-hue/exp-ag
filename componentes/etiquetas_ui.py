"""Aba "Etiquetas": vasos, amostras e placas de parcela com QR Code e código de barras."""

from __future__ import annotations

import streamlit as st

from componentes.visual import secao
from motor.exportacao.estilo import romano
from motor.exportacao.etiquetas import MODELOS, etiquetas_unidades, gerar_pdf
from motor.planejamento import Planejamento


def _url_publica() -> str:
    try:
        return str(st.secrets.get("app", {}).get("url_publica", "")).strip()
    except Exception:  # noqa: BLE001
        return ""


def aba_etiquetas(p: Planejamento, exp_id: int) -> None:
    secao("O que imprimir")
    c1, c2 = st.columns([2, 1])
    modelo = c1.selectbox("Modelo", list(MODELOS), format_func=lambda k: MODELOS[k].nome, key=f"et_mod_{exp_id}")
    ordem = c2.radio("Ordem", ["implantacao", "numero"], horizontal=True, key=f"et_ord_{exp_id}",
                     format_func={"implantacao": "Implantação (bloco a bloco)", "numero": "Número da unidade"}.get)
    blocos_exist = sorted({u.bloco for u in p.casualizacao.unidades if u.bloco is not None})
    blocos = []
    if blocos_exist:
        blocos = st.multiselect("Blocos (vazio = todos)", blocos_exist, format_func=lambda b: f"Bloco {romano(b)}",
                                key=f"et_bl_{exp_id}")
    amostras = []
    if not MODELOS[modelo].placa:
        with st.expander("Etiquetas de amostras (uma por unidade e tipo de amostra)"):
            txt = st.text_area("Um tipo por linha, no formato  sufixo; descrição", key=f"et_am_{exp_id}",
                               placeholder="S020; Solo 0–20 cm\nS2040; Solo 20–40 cm\nF; Folha diagnóstica", height=100)
            for linha in txt.splitlines():
                if ";" in linha:
                    suf, desc = (x.strip() for x in linha.split(";", 1))
                    if suf:
                        amostras.append((suf.replace(" ", ""), desc))
            st.caption("O código da amostra é o código da unidade seguido do sufixo (ex.: …-T05-R03-S020), o que a "
                       "vincula à unidade experimental de origem.")
    secao("QR Code")
    url = st.text_input("Endereço público do aplicativo (opcional)", _url_publica(), key=f"et_url_{exp_id}",
                        placeholder="https://seu-app.streamlit.app",
                        help="Com o endereço, o QR abre o experimento com a unidade destacada (exige acesso ao app). "
                             "Sem ele, o QR contém o código da unidade em texto. Pode ser fixado em Secrets: "
                             "[app] url_publica = \"…\".")
    c1, c2, c3 = st.columns(3)
    barras = c1.toggle("Código de barras (Code 128)", True, key=f"et_cb_{exp_id}",
                       disabled=MODELOS[modelo].placa or MODELOS[modelo].largura < 60)
    bordas = c2.toggle("Contorno de corte", True, key=f"et_borda_{exp_id}", disabled=MODELOS[modelo].placa)
    m = MODELOS[modelo]
    pular = int(c3.number_input("Posições já usadas na 1ª folha", 0, m.colunas * m.linhas - 1, 0,
                                key=f"et_pular_{exp_id}", help="Para reaproveitar folhas de etiquetas já iniciadas."))
    et = etiquetas_unidades(p, url, exp_id, blocos or None, amostras or None, ordem)
    por_folha = m.colunas * m.linhas
    folhas = -(-(len(et) + pular) // por_folha)
    st.markdown(f"<span class='ae-nota'>{len(et)} etiqueta(s) em {folhas} folha(s) A4. Imprima em escala 100% "
                "(sem “ajustar à página”).</span>", unsafe_allow_html=True)
    st.download_button("Gerar e baixar etiquetas (PDF)", lambda: gerar_pdf(et, modelo, p.meta.codigo, barras, bordas,
                                                                         pular),
                       f"{p.meta.codigo}_etiquetas_{modelo}.pdf", "application/pdf", type="primary",
                       key=f"et_pdf_{exp_id}", icon=":material/qr_code_2:", disabled=not et)
