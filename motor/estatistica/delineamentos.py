"""Regras por delineamento: quadro de graus de liberdade esperado e avisos de planejamento.

O quadro de GL descreve a ANOVA *esperada* para o plano, antes da coleta de dados. Além de conferir se há graus de
liberdade suficientes para o resíduo, ele documenta os **estratos de erro** que a análise (Fase 5) deverá
respeitar: em parcelas subdivididas, A é testado contra o resíduo (a) e B e A×B contra o resíduo (b); em faixas,
há três resíduos.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from motor.dominio import Arranjo, Delineamento, EstruturaTratamentos
from motor.estatistica.tratamentos import contar_tratamentos

GL_RESIDUO_MINIMO = 10  # recomendação usual na experimentação agrícola (Pimentel-Gomes)
UNIDADES_MINIMAS = 20


@dataclass(frozen=True)
class LinhaGL:
    fonte: str
    gl: int
    estrato: str = "parcela"  # nível de erro a que a fonte pertence
    residuo: bool = False


@dataclass(frozen=True)
class Aviso:
    nivel: str  # "erro" | "alerta" | "info"
    mensagem: str


def quadro_gl(delineamento: Delineamento, estrutura: EstruturaTratamentos, repeticoes: int,
              arranjo: Arranjo | str = Arranjo.CONVENCIONAL) -> list[LinhaGL]:
    delineamento, arranjo = Delineamento(delineamento), Arranjo(arranjo)
    t = contar_tratamentos(estrutura)
    if delineamento is Delineamento.QL:
        repeticoes = t
    r = repeticoes
    if arranjo is Arranjo.SUBDIVIDIDA:
        return _gl_subdividida(delineamento, estrutura, r)
    if arranjo is Arranjo.FAIXAS:
        return _gl_faixas(estrutura, r)
    n = t * r
    linhas: list[LinhaGL] = []
    if delineamento is Delineamento.DBC:
        linhas.append(LinhaGL("Blocos", r - 1, "bloco"))
    if delineamento is Delineamento.QL:
        linhas += [LinhaGL("Linhas", t - 1, "linha"), LinhaGL("Colunas", t - 1, "coluna")]
    linhas.extend(_decompor_tratamentos(estrutura, t))
    usados = sum(x.gl for x in linhas if not x.fonte.startswith("  "))
    linhas.append(LinhaGL("Resíduo", n - 1 - usados, residuo=True))
    linhas.append(LinhaGL("Total", n - 1, ""))
    return linhas


def _gl_subdividida(delineamento: Delineamento, e: EstruturaTratamentos, r: int) -> list[LinhaGL]:
    fa, fb = e.fatores
    a, b = len(fa.niveis), len(fb.niveis)
    linhas: list[LinhaGL] = []
    if delineamento is Delineamento.DBC:
        linhas.append(LinhaGL("Blocos", r - 1, "bloco"))
        res_a = (a - 1) * (r - 1)
    else:
        res_a = a * (r - 1)
    linhas += [
        LinhaGL(f"{fa.nome} (A)", a - 1, "parcela principal"),
        LinhaGL("Resíduo (a)", res_a, "parcela principal", True),
        LinhaGL("Parcelas principais", a * r - 1, "parcela principal"),
        LinhaGL(f"{fb.nome} (B)", b - 1, "subparcela"),
        LinhaGL(f"{fa.nome} × {fb.nome}", (a - 1) * (b - 1), "subparcela"),
        LinhaGL("Resíduo (b)", a * (r - 1) * (b - 1), "subparcela", True),
        LinhaGL("Total", a * b * r - 1, ""),
    ]
    return linhas


def _gl_faixas(e: EstruturaTratamentos, r: int) -> list[LinhaGL]:
    fa, fb = e.fatores
    a, b = len(fa.niveis), len(fb.niveis)
    return [
        LinhaGL("Blocos", r - 1, "bloco"),
        LinhaGL(f"{fa.nome} (A)", a - 1, "faixa horizontal"),
        LinhaGL("Resíduo (a)", (r - 1) * (a - 1), "faixa horizontal", True),
        LinhaGL(f"{fb.nome} (B)", b - 1, "faixa vertical"),
        LinhaGL("Resíduo (b)", (r - 1) * (b - 1), "faixa vertical", True),
        LinhaGL(f"{fa.nome} × {fb.nome}", (a - 1) * (b - 1), "cruzamento"),
        LinhaGL("Resíduo (c)", (r - 1) * (a - 1) * (b - 1), "cruzamento", True),
        LinhaGL("Total", a * b * r - 1, ""),
    ]


def _decompor_tratamentos(estrutura: EstruturaTratamentos, t: int) -> list[LinhaGL]:
    fat = estrutura.fatores
    adic = estrutura.adicionais
    if len(fat) <= 1 and not adic:
        return [LinhaGL(fat[0].nome if fat else "Tratamentos", t - 1)]
    linhas: list[LinhaGL] = [LinhaGL("Tratamentos", t - 1)]
    if len(fat) >= 2:
        nomes = [f.nome for f in fat]
        gls = [len(f.niveis) - 1 for f in fat]
        for k in range(1, len(fat) + 1):
            for comb in combinations(range(len(fat)), k):
                gl = 1
                for i in comb:
                    gl *= gls[i]
                linhas.append(LinhaGL("  " + " × ".join(nomes[i] for i in comb), gl))
    elif len(fat) == 1 and adic:
        linhas.append(LinhaGL(f"  {fat[0].nome}", len(fat[0].niveis) - 1))
    if adic and fat:
        linhas.append(LinhaGL("  Fatorial vs. adicional(is)", 1))
    if len(adic) >= 2:
        linhas.append(LinhaGL("  Entre adicionais", len(adic) - 1))
    return linhas


def avisos_planejamento(delineamento: Delineamento, estrutura: EstruturaTratamentos, repeticoes: int,
                        arranjo: Arranjo | str = Arranjo.CONVENCIONAL) -> list[Aviso]:
    delineamento, arranjo = Delineamento(delineamento), Arranjo(arranjo)
    avisos: list[Aviso] = []
    t = contar_tratamentos(estrutura)
    from motor.dominio import COMBINACOES_VALIDAS

    if (delineamento, arranjo) not in COMBINACOES_VALIDAS:
        return [Aviso("erro", f"O arranjo em {arranjo.nome} não é suportado no {delineamento.value}.")]
    if arranjo is not Arranjo.CONVENCIONAL:
        if len(estrutura.fatores) != 2 or estrutura.adicionais:
            return [Aviso("erro", f"O arranjo em {arranjo.nome} exige exatamente dois fatores e nenhum tratamento "
                                  "adicional. O primeiro fator vai para as parcelas principais (ou faixas "
                                  "horizontais) e o segundo para as subparcelas (ou faixas verticais).")]
        if min(len(f.niveis) for f in estrutura.fatores) < 2:
            return [Aviso("erro", "Cada fator precisa de ao menos 2 níveis.")]
    if delineamento is Delineamento.QL:
        if not 3 <= t <= 12:
            return [Aviso("erro", f"O quadrado latino exige de 3 a 12 tratamentos (há {t}).")]
        repeticoes = t
        avisos.append(Aviso("info", f"No quadrado latino o número de repetições é igual ao de tratamentos: "
                                    f"{t} linhas × {t} colunas = {t * t} unidades."))
    elif repeticoes < 2:
        return [Aviso("erro", "São necessárias ao menos 2 repetições para estimar o erro experimental.")]
    elif repeticoes > 50:
        return [Aviso("erro", "Número de repetições acima do limite suportado (50).")]
    quadro = quadro_gl(delineamento, estrutura, repeticoes, arranjo)
    for linha in quadro:
        if linha.residuo and linha.gl < 1:
            avisos.append(Aviso("erro", f"{linha.fonte} sem graus de liberdade: aumente o número de repetições."))
            return avisos
    residuos = [x for x in quadro if x.residuo]
    principal = residuos[-1]
    if principal.gl < GL_RESIDUO_MINIMO:
        avisos.append(Aviso("alerta", f"O {principal.fonte.lower()} terá {principal.gl} graus de liberdade. "
                                      f"Recomenda-se ao menos {GL_RESIDUO_MINIMO} para estimativas estáveis do erro."))
    if arranjo is not Arranjo.CONVENCIONAL:
        ra = residuos[0]
        if ra.gl < 6:
            avisos.append(Aviso("alerta", f"O resíduo (a) terá apenas {ra.gl} GL: os efeitos do fator nas "
                                          f"{'parcelas principais' if arranjo is Arranjo.SUBDIVIDIDA else 'faixas'} "
                                          "serão testados com pouca precisão. Considere mais repetições."))
        avisos.append(Aviso("info", "Estrutura com mais de um estrato de erro: a análise deverá usar o resíduo "
                                    "correspondente a cada fonte de variação (ver quadro)."))
    if t * repeticoes < UNIDADES_MINIMAS:
        avisos.append(Aviso("alerta", f"O experimento terá {t * repeticoes} unidades experimentais; recomenda-se "
                                      f"ao menos {UNIDADES_MINIMAS}."))
    for f in estrutura.fatores:
        if len(f.niveis) == 1:
            avisos.append(Aviso("alerta", f"O fator '{f.nome}' tem um único nível e não gera contraste."))
        if f.tipo.value == "quantitativo" and len(f.niveis) < 3:
            avisos.append(Aviso("info", f"O fator quantitativo '{f.nome}' tem {len(f.niveis)} níveis; com menos de "
                                        "3 não é possível ajustar regressão além da linear."))
        if f.tipo.value == "quantitativo" and len(f.niveis) >= 3:
            avisos.append(Aviso("info", f"Com {len(f.niveis)} níveis, '{f.nome}' permite regressão até o grau "
                                        f"{len(f.niveis) - 1} (na prática, linear, quadrática ou modelos não lineares)."))
    if delineamento is Delineamento.DBC and arranjo is Arranjo.CONVENCIONAL and t > 20:
        avisos.append(Aviso("info", f"Blocos com {t} parcelas podem perder homogeneidade. Para muitos tratamentos, "
                                    "considere blocos incompletos (alfa-látice), previstos para uma fase futura."))
    return avisos
