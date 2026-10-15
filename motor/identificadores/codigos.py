"""Geração de identificadores únicos e estáveis para unidades experimentais.

O padrão é um texto com marcadores entre chaves:

``{exp}``      código do experimento
``{parcela}``  rótulo da parcela/vaso (congelado na casualização)
``{bloco}``    número do bloco (``0`` em DIC)
``{trat}``     número do tratamento
``{rep}``      repetição
``{n}``        número sequencial da unidade (1..N)
``{pp}``       parcela principal (subdivididas)
``{sp}``       subparcela dentro da parcela principal (subdivididas)
``{lin}``      linha no bloco ou no quadrado (faixas e quadrado latino)
``{col}``      coluna no bloco ou no quadrado (faixas e quadrado latino)

Números recebem zeros à esquerda automaticamente, conforme o maior valor
(ex.: 40 parcelas → ``P01``…``P40``). O código identifica a *unidade*, não sua
posição física: se um vaso for movido, o código permanece.
"""

from __future__ import annotations

import re

from motor.dominio import Arranjo, Casualizacao, Delineamento

MARCADORES = ("exp", "parcela", "bloco", "trat", "rep", "n", "pp", "sp", "lin", "col")
_RE_MARCADOR = re.compile(r"\{([a-z]+)\}")
_RE_CODIGO_EXP = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,23}$")

PADRAO_DIC = "{exp}-P{parcela}-T{trat}-R{rep}"
PADRAO_DBC = "{exp}-P{parcela}-B{bloco}-T{trat}"
PADRAO_QL = "{exp}-L{lin}C{col}-T{trat}"


class ErroIdentificador(ValueError):
    pass


def padrao_sugerido(delineamento: Delineamento | str, arranjo: Arranjo | str = Arranjo.CONVENCIONAL) -> str:
    d = Delineamento(delineamento)
    if d is Delineamento.QL:
        return PADRAO_QL
    return PADRAO_DBC if d is Delineamento.DBC else PADRAO_DIC


def validar_codigo_experimento(codigo: str) -> str:
    codigo = codigo.strip()
    if not _RE_CODIGO_EXP.match(codigo):
        raise ErroIdentificador(
            "Código do experimento: use até 24 caracteres (letras, números, '-', '_' ou '.'), "
            "começando por letra ou número, sem espaços."
        )
    return codigo


def validar_padrao(padrao: str) -> None:
    if not padrao or not padrao.strip():
        raise ErroIdentificador("O padrão de identificação não pode ser vazio.")
    desconhecidos = [m for m in _RE_MARCADOR.findall(padrao) if m not in MARCADORES]
    if desconhecidos:
        raise ErroIdentificador(
            f"Marcador(es) desconhecido(s): {', '.join('{' + d + '}' for d in desconhecidos)}. "
            f"Use: {', '.join('{' + m + '}' for m in MARCADORES)}."
        )
    resto = _RE_MARCADOR.sub("", padrao)
    if "{" in resto or "}" in resto:
        raise ErroIdentificador("Chaves desbalanceadas no padrão de identificação.")
    if re.search(r"\s", padrao):
        raise ErroIdentificador("O padrão não deve conter espaços (dificulta leitura de etiquetas).")


def aplicar_codigos(casualizacao: Casualizacao, codigo_exp: str, padrao: str) -> None:
    """Preenche ``unidade.codigo``. Lança erro se houver códigos repetidos."""
    validar_padrao(padrao)
    codigo_exp = validar_codigo_experimento(codigo_exp)
    us = casualizacao.unidades
    larg = {
        "parcela": max(2, max(len(u.parcela) for u in us)),
        "bloco": max(2, len(str(max((u.bloco or 0) for u in us)))),
        "trat": max(2, len(str(casualizacao.n_tratamentos))),
        "rep": max(2, len(str(max(u.repeticao for u in us)))),
        "n": max(2, len(str(len(us)))),
        "pp": max(2, len(str(max((u.principal or 0) for u in us)))),
        "sp": max(1, len(str(max((u.sub or 0) for u in us)))),
        "lin": max(2, len(str(max((u.linha or 0) for u in us)))),
        "col": max(2, len(str(max((u.coluna or 0) for u in us)))),
    }
    for u in us:
        valores = {
            "exp": codigo_exp,
            "parcela": u.parcela.zfill(larg["parcela"]),
            "bloco": str(u.bloco or 0).zfill(larg["bloco"]),
            "trat": str(u.tratamento).zfill(larg["trat"]),
            "rep": str(u.repeticao).zfill(larg["rep"]),
            "n": str(u.numero).zfill(larg["n"]),
            "pp": str(u.principal or 0).zfill(larg["pp"]),
            "sp": str(u.sub or 0).zfill(larg["sp"]),
            "lin": str(u.linha or 0).zfill(larg["lin"]),
            "col": str(u.coluna or 0).zfill(larg["col"]),
        }
        u.codigo = _RE_MARCADOR.sub(lambda m, v=valores: v[m.group(1)], padrao)
    vistos: dict[str, int] = {}
    for u in us:
        if u.codigo in vistos:
            raise ErroIdentificador(
                f"O padrão '{padrao}' gera códigos repetidos (ex.: {u.codigo}). "
                "Inclua {parcela} ou {n}, ou a combinação {trat} e {rep}."
            )
        vistos[u.codigo] = u.numero
