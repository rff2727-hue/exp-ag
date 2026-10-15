"""Identidade visual e regras de cor/rótulo compartilhadas pelos renderizadores.

As mesmas funções alimentam o croqui interativo (Plotly) e as exportações
(Matplotlib/ReportLab), garantindo que tela e papel mostrem o mesmo conteúdo.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from motor.dominio import Casualizacao, Tratamento

RAIZ = Path(__file__).resolve().parents[2]
PASTA_FONTES = RAIZ / "assets" / "fonts"

# Identidade Exp-Ag (cores medidas no logotipo)
OCRE = "#AE7E2F"  # destaque
PETROLEO = "#174A51"  # cor principal (molduras, títulos, botões)
VERDE_AGUA = "#67A89D"  # apoio
TINTA = "#121714"  # texto do logotipo
GRAFITE = "#2E3134"
CHUMBO = "#5B6166"
PRETO_SUAVE = "#1C1D1F"
BEGE = "#F4F0E8"
LINHA = "#3A3D40"

# Paletas qualitativas seguras para daltonismo, com fundo claro (texto preto legível).
# Paul Tol "light" (9) seguida de Okabe–Ito clareadas.
PALETA = [
    "#77AADD", "#EE8866", "#EEDD88", "#FFAABB", "#99DDFF",
    "#44BB99", "#BBCC33", "#AAAA00", "#DDDDDD",
    "#F2C47E", "#9ED3F2", "#7FD0B7", "#F6EE9A", "#7FB2DA",
    "#EBA77F", "#E6B6D3", "#C9C9C9", "#B3C6E8", "#D9E3A1", "#F5C6B8",
]
PALETA_SEGURA_MAX = 9
PALETA_BLOCOS = ["#F1ECE2", "#E3E9DD", "#ECE3D6", "#DFE6EA", "#EFE6E0", "#E6E3EC"]

ROMANOS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
           "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"]


def romano(n: int) -> str:
    return ROMANOS[n - 1] if 1 <= n <= len(ROMANOS) else str(n)


@dataclass(frozen=True)
class OpcoesVisuais:
    modo: str = "estatistico"  # estatistico | operacional | cientifico
    colorir_por: str = "tratamento"  # tratamento | bloco | nenhum | fator:<nome>
    rotulo: str = "parcela_tratamento"  # parcela | tratamento | codigo | rotulo | parcela_tratamento
    mostrar_area_util: bool = True
    mostrar_blocos: bool = True
    mostrar_escala: bool = True
    mostrar_norte: bool = True
    mostrar_plantio: bool = False
    mostrar_dimensoes: bool = False
    titulo: str = ""


PREDEFINICOES = {
    "estatistico": OpcoesVisuais("estatistico", "tratamento", "parcela_tratamento", True, True, True, True, False, False),
    "operacional": OpcoesVisuais("operacional", "bloco", "parcela_tratamento", True, True, True, True, True, True),
    "cientifico": OpcoesVisuais("cientifico", "tratamento", "tratamento", False, True, True, True, False, False),
}

NOMES_MODOS = {
    "estatistico": "Estatístico",
    "operacional": "Operacional",
    "cientifico": "Científico",
}

NOMES_ROTULOS = {
    "parcela_tratamento": "Parcela + tratamento",
    "parcela": "Número da parcela",
    "tratamento": "Código do tratamento",
    "rotulo": "Nome do tratamento",
    "codigo": "Identificador completo",
}


def cor_texto(hex_cor: str) -> str:
    h = hex_cor.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return PRETO_SUAVE if lum > 0.36 else "#FFFFFF"


def atribuir_cores(
    cas: Casualizacao, tratamentos: list[Tratamento], colorir_por: str
) -> tuple[dict[int, str], dict[int, str], list[tuple[str, str]]]:
    """Retorna (cor por unidade, grupo por unidade, legenda [(rótulo, cor)])."""
    por_num = {t.numero: t for t in tratamentos}
    cor: dict[int, str] = {}
    grupo: dict[int, str] = {}
    legenda: list[tuple[str, str]] = []
    if colorir_por == "tratamento":
        for i, t in enumerate(tratamentos):
            legenda.append((f"{t.codigo} — {t.rotulo}", PALETA[i % len(PALETA)]))
        mapa = {t.numero: PALETA[i % len(PALETA)] for i, t in enumerate(tratamentos)}
        for u in cas.unidades:
            cor[u.numero] = mapa[u.tratamento]
            grupo[u.numero] = f"{por_num[u.tratamento].codigo} — {por_num[u.tratamento].rotulo}"
    elif colorir_por == "bloco":
        blocos = sorted({u.bloco for u in cas.unidades if u.bloco is not None})
        for b in blocos:
            legenda.append((f"Bloco {romano(b)}", PALETA_BLOCOS[(b - 1) % len(PALETA_BLOCOS)]))
        for u in cas.unidades:
            if u.bloco is None:
                cor[u.numero], grupo[u.numero] = "#FFFFFF", "Unidades"
            else:
                cor[u.numero] = PALETA_BLOCOS[(u.bloco - 1) % len(PALETA_BLOCOS)]
                grupo[u.numero] = f"Bloco {romano(u.bloco)}"
        if not blocos:
            legenda = []
    elif colorir_por.startswith("fator:"):
        nome = colorir_por.split(":", 1)[1]

        def grupo_de(t: Tratamento) -> str:
            # adicionais (fora do fatorial) formam grupos próprios
            return f"{nome}: {t.niveis[nome]}" if nome in t.niveis else t.rotulo

        grupos_ord: list[str] = []
        for t in tratamentos:
            g = grupo_de(t)
            if g not in grupos_ord:
                grupos_ord.append(g)
        mapa_g = {g: PALETA[i % len(PALETA)] for i, g in enumerate(grupos_ord)}
        legenda = list(mapa_g.items())
        for u in cas.unidades:
            g = grupo_de(por_num[u.tratamento])
            cor[u.numero], grupo[u.numero] = mapa_g[g], g
    else:
        for u in cas.unidades:
            cor[u.numero], grupo[u.numero] = "#FFFFFF", "Unidades"
    return cor, grupo, legenda


def texto_rotulo(u, t: Tratamento, rotulo: str) -> str:
    if rotulo == "parcela":
        return u.parcela
    if rotulo == "tratamento":
        return t.codigo
    if rotulo == "rotulo":
        return t.rotulo
    if rotulo == "codigo":
        return u.codigo or u.parcela
    return f"{u.parcela}\n{t.codigo}"


def escala_redonda(extensao: float) -> float:
    """Comprimento 'redondo' (1, 2, 5 × 10ⁿ) próximo de 1/5 da extensão."""
    import math

    alvo = max(extensao / 5, 1e-6)
    e = 10 ** math.floor(math.log10(alvo))
    for f in (1, 2, 5, 10):
        if f * e >= alvo:
            return f * e
    return 10 * e


def fmt_num(v: float, casas: int = 2) -> str:
    """Formato brasileiro: vírgula decimal, ponto de milhar."""
    s = f"{v:,.{casas}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def fmt_m(v: float) -> str:
    casas = 0 if abs(v - round(v)) < 1e-9 else (1 if abs(v * 10 - round(v * 10)) < 1e-9 else 2)
    return fmt_num(v, casas)


# O Matplotlib não é seguro para uso simultâneo em várias sessões do Streamlit: toda montagem de figura
# (croquis, relatórios, diagnóstico por satélite) passa por esta trava.
import threading as _threading  # noqa: E402

TRAVA_MPL = _threading.RLock()


def desenho_cota(ct, ext: float) -> tuple[list[tuple[tuple[float, float], tuple[float, float]]],
                                          tuple[float, float], float]:
    """Traços de uma cota (linhas de chamada, linha de cota e tiques a 45°), posição e ângulo do texto.

    Compartilhado pelo croqui estático, pelo interativo e pelo mapa, para que as medidas apareçam iguais.
    """
    import math

    (x1, y1), (x2, y2) = ct.q1, ct.q2
    L = math.hypot(x2 - x1, y2 - y1) or 1.0
    ux, uy = (x2 - x1) / L, (y2 - y1) / L
    segs = []
    # sentido "para fora" do objeto: da peça (p) para a linha de cota (q); sem afastamento, a normal à esquerda
    ox, oy = ct.q1[0] - ct.p1[0], ct.q1[1] - ct.p1[1]
    d_off = math.hypot(ox, oy)
    if d_off > 1e-9:
        nx, ny = ox / d_off, oy / d_off
        extra = 0.006 * ext
        for p, q in ((ct.p1, ct.q1), (ct.p2, ct.q2)):
            ini = (p[0] + nx * 0.004 * ext, p[1] + ny * 0.004 * ext)
            segs.append((ini, (q[0] + nx * extra, q[1] + ny * extra)))
    else:
        nx, ny = -uy, ux
    segs.append((ct.q1, ct.q2))
    t = 0.0045 * ext                                            # tiques arquitetônicos (barra a 45°)
    dx, dy = (ux + nx) * t, (uy + ny) * t
    for q in (ct.q1, ct.q2):
        segs.append(((q[0] - dx, q[1] - dy), (q[0] + dx, q[1] + dy)))
    ang = math.degrees(math.atan2(uy, ux))
    if ang > 90:
        ang -= 180
    elif ang <= -90:
        ang += 180
    afast = 0.026 * ext if L < 0.03 * ext else 0.009 * ext     # cotas curtas: texto mais afastado, sem colidir
    meio = ((x1 + x2) / 2 + nx * afast, (y1 + y2) / 2 + ny * afast)
    return segs, meio, ang


def limites_com_cotas(croqui, com_cotas: bool) -> tuple[float, float, float, float]:
    """Limites do desenho incluindo as cotas, quando exibidas."""
    x0, y0, x1, y1 = croqui.limites()
    if com_cotas and croqui.cotas:
        ext = max(x1 - x0, y1 - y0)
        xs = [p[0] for c in croqui.cotas for p in (c.q1, c.q2)]
        ys = [p[1] for c in croqui.cotas for p in (c.q1, c.q2)]
        m = 0.025 * ext
        x0, y0, x1, y1 = min(x0, min(xs) - m), min(y0, min(ys) - m), max(x1, max(xs) + m), max(y1, max(ys) + m)
    return x0, y0, x1, y1
