"""Configuração do banco de dados e migrações.

Ordem de resolução da URL:
1. variável de ambiente ``DATABASE_URL``;
2. ``st.secrets["database"]["url"]`` (Streamlit Community Cloud);
3. SQLite local em ``dados_locais/agro_experimentos.db`` (desenvolvimento).

No Streamlit Community Cloud o disco é efêmero: um SQLite ali é apagado a cada
reinício. Para uso real, configure um PostgreSQL externo (ex.: Supabase ou
Neon, ambos com PostGIS disponível para a Fase 3).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker

RAIZ = Path(__file__).resolve().parents[1]
SQLITE_PADRAO = RAIZ / "dados_locais" / "agro_experimentos.db"
log = logging.getLogger(__name__)


def normalizar_url(url: str) -> str:
    url = url.strip()
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo):]
    return url


def url_banco() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        try:
            import streamlit as st

            url = str(st.secrets.get("database", {}).get("url", "")).strip()
        except Exception:  # sem secrets.toml ou fora do Streamlit
            url = ""
    if not url:
        SQLITE_PADRAO.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{SQLITE_PADRAO}"
    return normalizar_url(url)


def e_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def descrever_url(url: str) -> str:
    """Descrição sem credenciais, para exibição."""
    if e_sqlite(url):
        return f"SQLite local ({url.split('///', 1)[-1]})"
    from sqlalchemy.engine import make_url

    u = make_url(url)
    return f"PostgreSQL em {u.host}:{u.port or 5432}/{u.database}"


def criar_engine(url: str | None = None) -> Engine:
    url = url or url_banco()
    if e_sqlite(url):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _pragmas(conn, _):  # integridade referencial no SQLite
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    else:
        engine = create_engine(url, pool_pre_ping=True, pool_recycle=280)
    return engine


def migrar(engine: Engine) -> None:
    """Aplica as migrações Alembic pendentes (idempotente)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(RAIZ / "dados" / "migracoes"))
    cfg.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False).replace("%", "%%"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def fabrica_sessoes(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)
