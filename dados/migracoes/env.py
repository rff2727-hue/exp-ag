"""Ambiente Alembic. Usa a conexão fornecida por ``dados.banco.migrar`` quando
houver; caso contrário, a URL de ``alembic.ini``/``DATABASE_URL``."""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dados.modelos.orm import Base  # noqa: E402

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    from dados.banco import url_banco

    return config.get_main_option("sqlalchemy.url") or url_banco()


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conexao = config.attributes.get("connection")
    if conexao is not None:
        context.configure(connection=conexao, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    secao = config.get_section(config.config_ini_section, {})
    secao["sqlalchemy.url"] = _url()
    engine = engine_from_config(secao, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
