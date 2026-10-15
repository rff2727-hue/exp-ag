"""Identidade visual da interface: estilos CSS e pequenos componentes HTML.

Linguagem Exp-Ag: minimalista, técnica e cartográfica — papel bege, petróleo como
cor principal, ocre como destaque e verde-água como apoio (cores do logotipo),
botões com "relevo" discreto de instrumento analógico e mostradores em Roboto Mono.
"""

from __future__ import annotations

import html

import streamlit as st

from motor.exportacao.estilo import BEGE, CHUMBO, GRAFITE, OCRE, PETROLEO, PRETO_SUAVE, VERDE_AGUA

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500&family=Roboto+Mono:wght@400&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input, textarea, select {{
  font-family: 'Roboto', 'Helvetica Neue', Arial, sans-serif !important;
}}
.stApp {{ background: {BEGE}; }}
h1 {{ font-weight: 300 !important; letter-spacing: -0.01em; color: {PETROLEO}; }}
h2, h3, h4 {{ font-weight: 400 !important; color: {PRETO_SUAVE}; }}
section[data-testid="stSidebar"] {{ background: #E8E4D8; border-right: 3px solid {PETROLEO}; }}
section[data-testid="stSidebar"] * {{ color: {GRAFITE}; }}
/* botões com relevo discreto */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
  border: 1px solid {GRAFITE}; border-radius: 3px; background: #FBF9F4; color: {PRETO_SUAVE};
  box-shadow: 0 2px 0 {GRAFITE}; transition: transform .05s, box-shadow .05s; font-weight: 400;
}}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {{
  border-color: {OCRE}; color: {OCRE}; background: #FFFDF8;
}}
.stButton > button:active, .stDownloadButton > button:active, .stFormSubmitButton > button:active {{
  transform: translateY(2px); box-shadow: 0 0 0 {GRAFITE};
}}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"] {{
  background: {PETROLEO}; color: #FFFFFF; border-color: #0E3036; box-shadow: 0 2px 0 {OCRE};
}}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {{ color: #FFFFFF; background: #1F5F68; border-color: {OCRE}; }}
/* abas */
.stTabs [data-baseweb="tab-list"] {{ gap: 1.4rem; border-bottom: 1px solid #CFC6B5; }}
.stTabs [aria-selected="true"] {{ color: {OCRE} !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: {OCRE}; }}
/* caixas de entrada */
.stTextInput input, .stNumberInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {{
  background: #FFFDF8 !important; border-radius: 3px !important;
}}
div[data-testid="stExpander"] {{ background: #FBF9F4; border: 1px solid #D8D0C0; border-radius: 3px; }}
/* componentes próprios */
.ae-secao {{ font-size: .72rem; letter-spacing: .16em; text-transform: uppercase; color: {PETROLEO};
  border-bottom: 1px solid {OCRE}; padding-bottom: .25rem; margin: 1.1rem 0 .6rem 0; }}
.ae-mostradores {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:.6rem; margin:.3rem 0 .8rem 0; }}
.ae-mostrador {{ border:1px solid {PETROLEO}; border-left:4px solid {OCRE}; border-radius:3px; background:#FBF9F4; padding:.45rem .7rem;
  box-shadow: inset 0 0 0 3px #FBF9F4, inset 0 0 0 4px #E2DACB; }}
.ae-mostrador .r {{ font-size:.66rem; letter-spacing:.14em; text-transform:uppercase; color:{CHUMBO}; }}
.ae-mostrador .v {{ font-family:'Roboto Mono', monospace; font-size:1.25rem; color:{PRETO_SUAVE}; white-space:nowrap; }}
.ae-mostrador .u {{ font-size:.75rem; color:{CHUMBO}; margin-left:.2rem; }}
.ae-passos {{ display:flex; gap:.3rem; flex-wrap:wrap; margin:.2rem 0 1rem 0; }}
.ae-passo {{ font-size:.74rem; padding:.22rem .6rem; border:1px solid #CFC6B5; border-radius:2px; color:{CHUMBO}; background:#FBF9F4; }}
.ae-passo.ativo {{ border-color:{PETROLEO}; color:#FFFFFF; background:{PETROLEO}; box-shadow: 0 2px 0 {OCRE}; }}
.ae-passo.feito {{ border-color:{VERDE_AGUA}; color:{PETROLEO}; }}
.ae-futuro {{ display:inline-block; font-size:.66rem; letter-spacing:.1em; text-transform:uppercase; color:{CHUMBO};
  border:1px dashed {CHUMBO}; border-radius:2px; padding:.05rem .4rem; margin-left:.4rem; }}
.ae-roteiro div {{ display:flex; align-items:center; gap:.45rem; margin:.28rem 0; font-size:.82rem; color:{CHUMBO}; }}
.ae-roteiro .ae-futuro {{ margin-left:0; min-width:3.6rem; text-align:center; }}
.ae-cartao {{ border:1px solid #D8D0C0; background:#FBF9F4; border-radius:3px; padding:.8rem 1rem; height:100%; }}
.ae-cartao h4 {{ margin:0 0 .3rem 0; font-size:1rem; }}
.ae-cartao p {{ color:{CHUMBO}; font-size:.86rem; margin:0; }}
.ae-nota {{ color:{CHUMBO}; font-size:.82rem; }}
</style>
"""


def aplicar_estilo() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def secao(texto: str) -> None:
    st.markdown(f'<div class="ae-secao">{html.escape(texto)}</div>', unsafe_allow_html=True)


def mostradores(itens: list[tuple[str, str, str]]) -> None:
    """Itens: (rótulo, valor, unidade)."""
    blocos = "".join(
        f'<div class="ae-mostrador"><div class="r">{html.escape(r)}</div>'
        f'<div class="v">{html.escape(v)}<span class="u">{html.escape(u)}</span></div></div>'
        for r, v, u in itens
    )
    st.markdown(f'<div class="ae-mostradores">{blocos}</div>', unsafe_allow_html=True)


def passos(nomes: list[str], atual: int) -> None:
    html_ = "".join(
        f'<span class="ae-passo {"ativo" if i == atual else "feito" if i < atual else ""}">'
        f'{i + 1}. {html.escape(n)}</span>'
        for i, n in enumerate(nomes)
    )
    st.markdown(f'<div class="ae-passos">{html_}</div>', unsafe_allow_html=True)


def selo_futuro(texto: str = "fase futura") -> str:
    return f'<span class="ae-futuro">{html.escape(texto)}</span>'


def cartao(titulo: str, texto: str) -> None:
    st.markdown(f'<div class="ae-cartao"><h4>{html.escape(titulo)}</h4><p>{html.escape(texto)}</p></div>',
                unsafe_allow_html=True)
