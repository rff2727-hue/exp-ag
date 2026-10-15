"""Construção da matriz de tratamentos a partir dos fatores cadastrados."""

from __future__ import annotations

import itertools

from motor.dominio import (
    EstruturaTratamentos,
    Fator,
    TipoTratamento,
    Tratamento,
)


class ErroEstrutura(ValueError):
    """Estrutura de tratamentos inválida."""


def validar_estrutura(estrutura: EstruturaTratamentos) -> None:
    if not estrutura.fatores and not estrutura.adicionais:
        raise ErroEstrutura("Cadastre ao menos um fator ou tratamento.")
    nomes = [f.nome.strip() for f in estrutura.fatores]
    if any(not n for n in nomes):
        raise ErroEstrutura("Todo fator precisa de um nome.")
    if len(set(n.casefold() for n in nomes)) != len(nomes):
        raise ErroEstrutura("Os nomes dos fatores devem ser distintos.")
    for f in estrutura.fatores:
        _validar_fator(f)
    rot_ad = [a.rotulo.strip() for a in estrutura.adicionais]
    if any(not r for r in rot_ad):
        raise ErroEstrutura("Todo tratamento adicional precisa de um rótulo.")
    if len(set(r.casefold() for r in rot_ad)) != len(rot_ad):
        raise ErroEstrutura("Os rótulos dos tratamentos adicionais devem ser distintos.")
    if len(estrutura.fatores) == 0 and len(estrutura.adicionais) < 2:
        raise ErroEstrutura("São necessários ao menos dois tratamentos.")
    n_fat = 1
    for f in estrutura.fatores:
        n_fat *= len(f.niveis)
    total = (n_fat if estrutura.fatores else 0) + len(estrutura.adicionais)
    if total < 2:
        raise ErroEstrutura("São necessários ao menos dois tratamentos.")
    if total > 999:
        raise ErroEstrutura("Limite de 999 tratamentos excedido.")


def _validar_fator(f: Fator) -> None:
    if len(f.niveis) < 1:
        raise ErroEstrutura(f"O fator '{f.nome}' não tem níveis.")
    # Fator com um único nível é aceito (avisado em validacao.verificacoes).
    rot = [n.rotulo.strip() for n in f.niveis]
    if any(not r for r in rot):
        raise ErroEstrutura(f"Há nível sem rótulo no fator '{f.nome}'.")
    if len(set(r.casefold() for r in rot)) != len(rot):
        raise ErroEstrutura(f"Os níveis do fator '{f.nome}' devem ser distintos.")
    if f.tipo.value == "quantitativo":
        faltando = [n.rotulo for n in f.niveis if n.valor is None]
        if faltando:
            raise ErroEstrutura(
                f"Fator quantitativo '{f.nome}': informe o valor numérico de "
                f"{', '.join(faltando)}."
            )


def gerar_tratamentos(estrutura: EstruturaTratamentos) -> list[Tratamento]:
    """Fatorial completo (ordem lexicográfica dos níveis) seguido dos adicionais.

    Os números dos tratamentos são estáveis para uma mesma estrutura: o
    primeiro fator varia mais lentamente (A1B1, A1B2, A2B1, ...), convenção
    usual em tabelas de tratamentos.
    """
    validar_estrutura(estrutura)
    tratamentos: list[Tratamento] = []
    total = _contar(estrutura)
    largura = max(2, len(str(total)))
    n = 0
    if estrutura.fatores:
        listas = [f.niveis for f in estrutura.fatores]
        for combinacao in itertools.product(*listas):
            n += 1
            niveis = {f.nome: nv.rotulo for f, nv in zip(estrutura.fatores, combinacao)}
            rotulo = " × ".join(rotulo_nivel(f, nv) for f, nv in zip(estrutura.fatores, combinacao))
            tratamentos.append(
                Tratamento(
                    numero=n,
                    codigo=f"T{n:0{largura}d}",
                    rotulo=rotulo,
                    tipo=TipoTratamento.FATORIAL,
                    niveis=niveis,
                )
            )
    for ad in estrutura.adicionais:
        n += 1
        tratamentos.append(
            Tratamento(
                numero=n,
                codigo=f"T{n:0{largura}d}",
                rotulo=ad.rotulo,
                tipo=TipoTratamento.ADICIONAL,
                niveis={},
                papel=ad.papel,
                descricao=ad.descricao,
            )
        )
    return tratamentos


def rotulo_nivel(f: Fator, nv) -> str:
    """Rótulo do nível com a unidade, para fatores quantitativos (ex.: '50 kg ha⁻¹')."""
    if f.tipo.value == "quantitativo" and f.unidade and f.unidade not in nv.rotulo:
        return f"{nv.rotulo} {f.unidade}"
    return nv.rotulo


def _contar(estrutura: EstruturaTratamentos) -> int:
    n = 1 if estrutura.fatores else 0
    for f in estrutura.fatores:
        n *= len(f.niveis)
    return n + len(estrutura.adicionais)


def contar_tratamentos(estrutura: EstruturaTratamentos) -> int:
    return _contar(estrutura)


def descrever_tipo(t: Tratamento, e_fatorial: bool) -> str:
    """Rótulo de exibição: 'fatorial' só quando há 2+ fatores; 'regular' no caso unifatorial."""
    if t.tipo is TipoTratamento.ADICIONAL:
        return "adicional"
    return "fatorial" if e_fatorial else "regular"
