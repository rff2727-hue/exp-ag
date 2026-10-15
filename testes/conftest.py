import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def _limpar_postgres(url: str) -> None:
    from sqlalchemy import text

    from dados.banco import criar_engine, normalizar_url

    eng = criar_engine(normalizar_url(url))
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    eng.dispose()


@pytest.fixture
def url_temp(tmp_path):
    """SQLite temporário; ou PostgreSQL limpo se TESTE_POSTGRES_URL estiver definida (CI)."""
    pg = os.environ.get("TESTE_POSTGRES_URL")
    if pg:
        _limpar_postgres(pg)
        from dados.banco import normalizar_url

        return normalizar_url(pg)
    return f"sqlite:///{tmp_path / 'teste.db'}"


@pytest.fixture
def repo(url_temp):
    from dados.banco import criar_engine, fabrica_sessoes, migrar
    from dados.repositorios.experimentos import RepositorioExperimentos

    eng = criar_engine(url_temp)
    migrar(eng)
    yield RepositorioExperimentos(fabrica_sessoes(eng))
    eng.dispose()
