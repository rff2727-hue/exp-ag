"""Motor de casualização: estrutura, reprodutibilidade e uniformidade."""

import hashlib
from collections import Counter

import pytest

from motor.casualizacao.casualizador import ErroCasualizacao, casualizar
from motor.casualizacao.gerador import ALGORITMO, GeradorDeterministico
from motor.validacao.verificacoes import verificar_casualizacao


def test_valores_de_referencia_congelados():
    """Se este teste falhar, o algoritmo mudou e casualizações antigas deixariam de ser reproduzíveis."""
    assert ALGORITMO == "FY-SHA256-v1"
    assert GeradorDeterministico(12345, "dic").permutacao(list(range(1, 11))) == [10, 7, 4, 6, 5, 3, 2, 9, 8, 1]
    g = GeradorDeterministico(12345, "bloco:1")
    assert [g.inteiro_abaixo(1000) for _ in range(5)] == [128, 228, 246, 823, 210]
    c = casualizar("DBC", 5, 3, 2026)
    assert [u.tratamento for u in c.unidades] == [2, 3, 4, 5, 1, 2, 4, 3, 5, 1, 2, 1, 4, 5, 3]


def _referencia_independente(semente: int, contexto: str, n: int) -> list[int]:
    """Reimplementação a partir apenas da documentação do algoritmo."""
    palavras, contador = [], 0

    def u64():
        nonlocal contador
        if not palavras:
            d = hashlib.sha256(f"{semente}|{contexto}|{contador}".encode()).digest()
            contador += 1
            palavras.extend(int.from_bytes(d[i:i + 8], "big") for i in (0, 8, 16, 24))
        return palavras.pop(0)

    a = list(range(1, n + 1))
    for i in range(n - 1, 0, -1):
        m = i + 1
        lim = 2**64 - (2**64 % m)
        while (x := u64()) >= lim:
            pass
        j = x % m
        a[i], a[j] = a[j], a[i]
    return a


@pytest.mark.parametrize("semente", [0, 1, 42, 987654321, 2**40])
def test_algoritmo_reproduzivel_pela_documentacao(semente):
    for n in (2, 7, 25):
        assert GeradorDeterministico(semente, "bloco:3").permutacao(list(range(1, n + 1))) == \
            _referencia_independente(semente, "bloco:3", n)


@pytest.mark.parametrize("delineamento", ["DIC", "DBC"])
def test_mesma_semente_mesmo_resultado(delineamento):
    a = casualizar(delineamento, 8, 4, 777)
    b = casualizar(delineamento, 8, 4, 777)
    assert [(u.tratamento, u.bloco, u.posicao) for u in a.unidades] == \
        [(u.tratamento, u.bloco, u.posicao) for u in b.unidades]


def test_sementes_diferentes_resultados_diferentes():
    a = casualizar("DBC", 10, 4, 1)
    b = casualizar("DBC", 10, 4, 2)
    assert [u.tratamento for u in a.unidades] != [u.tratamento for u in b.unidades]


@pytest.mark.parametrize("t,r", [(2, 2), (3, 5), (10, 4), (24, 3)])
def test_dbc_cada_bloco_contem_todos_os_tratamentos(t, r):
    c = casualizar("DBC", t, r, 99)
    assert verificar_casualizacao(c) == []
    for b in range(1, r + 1):
        assert sorted(u.tratamento for u in c.unidades if u.bloco == b) == list(range(1, t + 1))


@pytest.mark.parametrize("t,r", [(2, 2), (6, 5), (13, 3)])
def test_dic_contagens_e_repeticoes(t, r):
    c = casualizar("DIC", t, r, 5)
    assert verificar_casualizacao(c) == []
    assert Counter(u.tratamento for u in c.unidades) == {i: r for i in range(1, t + 1)}
    assert all(u.bloco is None for u in c.unidades)
    for trat in range(1, t + 1):
        assert sorted(u.repeticao for u in c.unidades if u.tratamento == trat) == list(range(1, r + 1))


def test_acrescentar_bloco_nao_altera_os_anteriores():
    a = casualizar("DBC", 6, 3, 31)
    b = casualizar("DBC", 6, 4, 31)
    assert [u.tratamento for u in a.unidades] == [u.tratamento for u in b.unidades[:18]]


def test_numeracao_por_bloco():
    c = casualizar("DBC", 10, 4, 3, "bloco")
    assert [u.parcela for u in c.unidades[:3]] == ["101", "102", "103"]
    assert c.unidades[-1].parcela == "410"
    c = casualizar("DBC", 120, 2, 3, "bloco")
    assert c.unidades[0].parcela == "1001"


def test_uniformidade_das_posicoes():
    """Qui-quadrado: cada tratamento deve ocupar cada posição com a mesma frequência."""
    t, n = 5, 4000
    cont = Counter()
    for s in range(n):
        for u in casualizar("DBC", t, 2, s).unidades:
            if u.bloco == 1:
                cont[(u.tratamento, u.posicao)] += 1
    esperado = n / t
    chi2 = sum((cont[(i, j)] - esperado) ** 2 / esperado for i in range(1, t + 1) for j in range(1, t + 1))
    # gl = (t-1)^2 = 16; valor crítico de 0,1% ≈ 39,25
    assert chi2 < 39.25, chi2


def test_entradas_invalidas():
    with pytest.raises(ErroCasualizacao):
        casualizar("DBC", 1, 4, 1)
    with pytest.raises(ErroCasualizacao):
        casualizar("DIC", 4, 1, 1)
    with pytest.raises(ErroCasualizacao):
        casualizar("DIC", 4, 3, 1, "bloco")
    with pytest.raises(ValueError):
        GeradorDeterministico(-1)
