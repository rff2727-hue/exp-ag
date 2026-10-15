"""Estado compartilhado da interface: repositório, autor, experimento ativo,
controle de acesso opcional e avisos de armazenamento."""

from __future__ import annotations

import hmac
import logging

import streamlit as st

from dados.banco import criar_engine, descrever_url, e_sqlite, fabrica_sessoes, migrar, url_banco
from dados.repositorios.experimentos import RepositorioExperimentos

log = logging.getLogger("agro_experimentos")

PAGINAS = {
    "inicio": "ui/inicio.py",
    "projetos": "ui/projetos.py",
    "novo": "ui/novo_experimento.py",
    "experimento": "ui/experimento.py",
    "modelos": "ui/modelos.py",
    "configuracoes": "ui/configuracoes.py",
    "satelites": "ui/satelites.py",
}


@st.cache_resource(show_spinner="Conectando ao banco de dados…")
def _recursos(url: str) -> RepositorioExperimentos:
    engine = criar_engine(url)
    migrar(engine)
    log.info("Banco pronto: %s", descrever_url(url))
    return RepositorioExperimentos(fabrica_sessoes(engine))


def repositorio() -> RepositorioExperimentos:
    return _recursos(url_banco())


def info_banco() -> tuple[str, bool]:
    url = url_banco()
    return descrever_url(url), not e_sqlite(url)


def em_nuvem() -> bool:
    """Heurística: o Streamlit Community Cloud monta o app em /mount/src."""
    import os

    return os.path.exists("/mount/src") or os.environ.get("STREAMLIT_RUNTIME_ENV", "") == "cloud"


def aviso_armazenamento() -> None:
    _, persistente = info_banco()
    if not persistente and em_nuvem():
        st.warning(
            "**Armazenamento temporário.** Este servidor usa SQLite em disco efêmero: os experimentos "
            "podem ser perdidos quando o app reiniciar. Configure um PostgreSQL em *Settings → Secrets* "
            "(veja o README) e, até lá, exporte cada experimento em JSON.",
            icon="⚠️",
        )


def autor() -> str:
    return st.session_state.get("autor", "")


def exp_ativo() -> int | None:
    if "exp_id" not in st.session_state:
        q = st.query_params.get("exp")
        st.session_state["exp_id"] = int(q) if q and q.isdigit() else None
    return st.session_state["exp_id"]


def definir_exp_ativo(exp_id: int | None) -> None:
    st.session_state["exp_id"] = exp_id
    if exp_id is None:
        st.query_params.pop("exp", None)
    else:
        st.query_params["exp"] = str(exp_id)


def abrir_experimento(exp_id: int) -> None:
    definir_exp_ativo(exp_id)
    st.switch_page(PAGINAS["experimento"])


def verificar_acesso() -> bool:
    """Senha compartilhada opcional (``[acesso] senha = "..."`` em secrets)."""
    try:
        senha = str(st.secrets.get("acesso", {}).get("senha", ""))
    except Exception:
        senha = ""
    if not senha or st.session_state.get("acesso_ok"):
        return True
    st.markdown("### Acesso restrito")
    with st.form("acesso"):
        digitada = st.text_input("Senha de acesso", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            if hmac.compare_digest(digitada.encode(), senha.encode()):
                st.session_state["acesso_ok"] = True
                st.rerun()
            st.error("Senha incorreta.")
    return False


def mensagem_pendente() -> None:
    """Exibe mensagens de sucesso que sobrevivem a um st.rerun/switch_page."""
    msg = st.session_state.pop("_msg", None)
    if msg:
        st.toast(msg, icon="✅")


def avisar_depois(msg: str) -> None:
    st.session_state["_msg"] = msg
