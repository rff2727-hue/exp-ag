"""Camada de identidade visual do relatório Satélites (Exp-Ag).

Contém exatamente as funções de página que o relatório usa do `book.py` da recomenda-solo (v17) —
moldura, título, texto corrido, norte, escala, caixa de mapa, capa e sumário —, com o mesmo
desenho e as mesmas medidas. Mudam apenas a marca (logotipo, ícone, nome), as cores (petróleo e
ocre do logotipo Exp-Ag) e a família tipográfica (Roboto, a mesma da plataforma).
"""
from __future__ import annotations

import functools
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.colors import to_rgb  # noqa: E402
from matplotlib.patches import FancyBboxPatch, PathPatch  # noqa: E402
from matplotlib.path import Path as MPath  # noqa: E402
from PIL import Image  # noqa: E402

from motor.exportacao.estilo import OCRE, PETROLEO  # noqa: E402

ASSETS = Path(__file__).resolve().parents[2] / "assets"
A4 = (8.27, 11.69)

# ------------------------------------------------------------------ fontes
# As famílias "Roboto Medium" e "Roboto Black" são cópias renomeadas dos pesos do Roboto (assets/sat/fontes),
# para que o relatório escolha o peso pelo nome da família, como fazia com a Montserrat no book original.
for _f in [*(ASSETS / "fonts").glob("Roboto-*.ttf"), *(ASSETS / "sat" / "fontes").glob("*.ttf")]:
    fm.fontManager.addfont(str(_f))
F_REG = ["Roboto", "DejaVu Sans"]
F_MED = ["Roboto Medium", "Roboto", "DejaVu Sans"]
F_SEMI = ["Roboto Medium", "Roboto", "DejaVu Sans"]
F_BOLD = ["Roboto", "DejaVu Sans"]
F_XB = ["Roboto Black", "Roboto", "DejaVu Sans"]


def aplicar_fontes() -> None:
    """Fonte padrão das páginas do relatório (chamada em cada montagem: o processo é compartilhado)."""
    plt.rcParams.update({"font.family": ["Roboto", "DejaVu Sans"], "font.weight": "normal", "pdf.fonttype": 42,
                         "mathtext.fontset": "custom", "mathtext.rm": "Roboto", "mathtext.bf": "Roboto:bold"})


aplicar_fontes()

MARCAS = {
    "Exp-Ag": {"nome": "EXP-AG", "cor": PETROLEO, "acento": OCRE,
               "logo": "logo_expag.png", "icone": "icone_expag.png"},
}
MARCA_PADRAO = "Exp-Ag"
CREME = "#FAF6E6"


def br(v, casas=1) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "–"
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ------------------------------------------------------------- elementos
def cor_texto(fundo: str) -> str:
    r, g, b = to_rgb(fundo)
    return "#1A1A1A" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.5 else "white"


@functools.lru_cache(maxsize=32)
def _img(nome):
    return np.asarray(Image.open(ASSETS / nome).convert("RGBA"))


def _imagem(fig, img, rect):
    """Desenha uma imagem na posição `rect` (fração da página) numa camada única por página."""
    ax = getattr(fig, "_camada_img", None)
    if ax is None:
        ax = fig.add_axes([0, 0, 1, 1], zorder=20)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_autoscale_on(False)
        ax.axis("off")
        fig._camada_img = ax
    L, B, W, H = rect
    ax.imshow(img, extent=[L, L + W, B, B + H], aspect="auto", zorder=1)


MOLD_Y0, MOLD_Y1 = 0.062, 0.968      # moldura (fração da página)


def base(fig, ctx, num: int | None, moldura=True):
    cor = ctx.marca["cor"]
    fig.patch.set_facecolor("white")
    fig._cor_marca = cor                      # usada pela barra de escala (mesma cor da moldura)
    if not moldura:
        return
    fig.add_artist(FancyBboxPatch((0.07, MOLD_Y0), 0.86, MOLD_Y1 - MOLD_Y0,
                                  boxstyle="round,pad=0,rounding_size=0.045", transform=fig.transFigure,
                                  fc="none", ec=cor, lw=2.6, mutation_aspect=A4[0] / A4[1]))
    fig.text(0.5, MOLD_Y1, ctx.marca["nome"], ha="center", va="center", fontsize=12, family=F_XB,
             color="#111111", bbox=dict(fc="white", ec="none", pad=6))
    ic = _img(ctx.marca["icone"])
    h = 0.032
    w = h * ic.shape[1] / ic.shape[0] * A4[1] / A4[0]
    _imagem(fig, ic, [0.5 - w / 2, (MOLD_Y0 - h) / 2 - 0.002, w, h])
    if num is not None:
        fig.text(0.93, MOLD_Y0 / 2, str(num), ha="right", va="center", color=cor, fontsize=10, family=F_SEMI)


LARG_TITULO, LARG_SUB = 0.66, 0.78       # largura máxima (fração da página) do título e do subtítulo


def _largura(fig, t) -> float:
    r = fig.canvas.get_renderer()
    return t.get_window_extent(r).width / (fig.get_figwidth() * fig.dpi)


def caber(fig, t, larg_max: float, fs_min: float) -> None:
    """Faz um texto caber na largura dada: reduz a fonte até `fs_min` e, se ainda não couber, encurta pelo meio."""
    while _largura(fig, t) > larg_max and t.get_fontsize() > fs_min:
        t.set_fontsize(max(fs_min, t.get_fontsize() - 0.5))
    txt = t.get_text()
    corte = len(txt)
    while _largura(fig, t) > larg_max and corte > 12:
        corte -= 2
        a = corte * 3 // 5
        t.set_text(txt[:a].rstrip(" ,·-") + " … " + txt[len(txt) - (corte - a):].lstrip(" ,·-"))


def titulo(fig, ctx, texto: str, sub: str = "", y=0.905, tam=24):
    """Título centralizado com os ícones da marca dos lados e subtítulo."""
    cor = ctx.marca["cor"]
    linhas = texto.split("\n")
    objs = [fig.text(0.5, y - i * 0.036, l, ha="center", va="center", fontsize=tam, family=F_XB, color=cor)
            for i, l in enumerate(linhas)]
    for t in objs:
        caber(fig, t, LARG_TITULO, 12)
    fs = min(t.get_fontsize() for t in objs)
    for t in objs:
        t.set_fontsize(fs)
    larg = max(_largura(fig, t) for t in objs) / 2 + 0.035
    yb = y - (len(linhas) - 1) * 0.018
    ic = _img(ctx.marca["icone"])
    h = 0.026
    w = h * ic.shape[1] / ic.shape[0] * A4[1] / A4[0]
    for xc in (0.5 - larg, 0.5 + larg):
        _imagem(fig, ic, [xc - w / 2, yb - h / 2, w, h])
    if sub:
        ts = fig.text(0.5, y - len(linhas) * 0.036 + 0.006, sub, ha="center", va="center", fontsize=12.5,
                      family=F_BOLD, weight="bold", color=ctx.marca["acento"])
        caber(fig, ts, LARG_SUB, 8)


def texto_corrido(fig, x, y, txt: str, larg: float, y_min: float, fs: float = 8.3, fs_min: float = 6.0,
                  cor="#333333", entre: float = 1.38) -> None:
    """Parágrafo quebrado em linhas dentro de `larg`, sem descer abaixo de `y_min`."""
    import textwrap
    alt_pag = fig.get_figheight() * 72
    larg_pt = larg * fig.get_figwidth() * 72
    while True:
        por_linha = max(20, int(larg_pt / (fs * 0.50)))      # ~0,50 em por caractere (Roboto)
        passo = fs * entre / alt_pag
        linhas = textwrap.wrap(txt, por_linha)
        cabem = max(1, int((y - y_min) / passo) + 1)
        if len(linhas) <= cabem or fs <= fs_min:
            break
        fs -= 0.3
    if len(linhas) > cabem:
        linhas = linhas[:cabem]
        linhas[-1] = linhas[-1][:max(0, por_linha - 2)].rstrip(" ;,") + " …"
    for i, l in enumerate(linhas):
        t = fig.text(x, y - i * passo, l, fontsize=fs, color=cor, va="center")
        caber(fig, t, larg, fs_min - 1)


def norte(fig, x=0.845, y=0.085, h=0.042):
    n = _img("sat/norte.png")
    w = h * n.shape[1] / n.shape[0] * A4[1] / A4[0]
    _imagem(fig, n, [x, y, w, h])


def escala(fig, ax, x, y, cor=None, alinhar="esq", frac=0.14, fs=7.5):
    """Barra de escala desenhada na página (fora do mapa), na mesma escala do mapa, na cor da moldura."""
    cor = cor or getattr(fig, "_cor_marca", "#222222")
    x0, x1 = ax.get_xlim()
    bb = ax.get_position()
    m_por_fig = (x1 - x0) / bb.width
    L = _redondo(m_por_fig * frac)
    w = L / m_por_fig
    xa = x if alinhar == "esq" else x - w
    kw = dict(transform=fig.transFigure, color=cor, lw=1.4, solid_capstyle="butt")
    fig.add_artist(plt.Line2D([xa, xa + w], [y, y], **kw))
    for xx in (xa, xa + w / 2, xa + w):
        fig.add_artist(plt.Line2D([xx, xx], [y - 0.004, y + 0.004], **{**kw, "lw": 1.0}))
    fig.text(xa + w / 2, y + 0.008, f"{L:,.0f} m".replace(",", "."), ha="center", va="bottom", fontsize=fs,
             family=F_SEMI, color=cor)
    return w


def _redondo(v):
    e = 10 ** math.floor(math.log10(v))
    return min((1, 2, 2.5, 5, 10), key=lambda m: abs(m * e - v)) * e


def _caixa_mapa(fig, ctx, rect_livre, xs):
    """Axes do mapa ajustado à caixa (fig coords) mantendo a proporção da área."""
    x0, y0, x1, y1 = xs
    dx, dy = x1 - x0, y1 - y0
    L, B, W, H = rect_livre
    asp_caixa = (H * A4[1]) / (W * A4[0])
    if dy / dx > asp_caixa:
        w = H * A4[1] / A4[0] * dx / dy
        rect = [L + (W - w) / 2, B, w, H]
    else:
        h = W * A4[0] / A4[1] * dy / dx
        rect = [L, B + (H - h) / 2, W, h]
    ax = fig.add_axes(rect)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    return ax


def _patch(geom, **kw):
    polys = geom.geoms if hasattr(geom, "geoms") else [geom]
    verts, codes = [], []
    for p in polys:
        for anel in [p.exterior, *p.interiors]:
            c = np.asarray(anel.coords)
            verts += c.tolist()
            codes += [MPath.MOVETO] + [MPath.LINETO] * (len(c) - 2) + [MPath.CLOSEPOLY]
    return PathPatch(MPath(verts, codes), **kw)


def _mistura(c1, c2, t):
    a, b = np.array(to_rgb(c1)), np.array(to_rgb(c2))
    return tuple(a + (b - a) * t)


def imagem_capa(ax, img, desce: float):
    """Arte na largura da página, com o topo `desce` abaixo da borda superior (sem "costura" na borda)."""
    h_pag = img.shape[0] / img.shape[1] * A4[0] / A4[1]
    topo = 1 - desce
    if desce > 0:
        n = int(np.ceil(desce / h_pag * img.shape[0])) + 2
        img = np.concatenate([np.repeat(img[:1], n, axis=0), img], axis=0)
        topo += n / (img.shape[0] - n) * h_pag
        h_pag = img.shape[0] / img.shape[1] * A4[0] / A4[1]
    ax.imshow(img, extent=(0, 1, topo - h_pag, topo), aspect="auto", interpolation="antialiased", zorder=0)


def pagina_sumario(pdf, ctx, itens: list[tuple[str, int, int]]):
    fig = plt.figure(figsize=A4)
    base(fig, ctx, None)
    titulo(fig, ctx, "SUMÁRIO")
    n = len(itens)
    ncol = 1 if n <= 34 else 2
    por_col = int(np.ceil(n / ncol))
    passo = min(0.022, 0.72 / max(por_col, 1))
    fs = max(6.5, min(10, passo * A4[1] * 72 * 0.62))
    larg = 0.74 / ncol
    for idx, (texto, pag, nivel) in enumerate(itens):
        c, r = idx // por_col, idx % por_col
        x0 = 0.13 + c * (larg + 0.02)
        y = 0.83 - r * passo
        x = x0 + 0.025 * nivel
        cor = ctx.marca["cor"] if nivel == 0 else "#333333"
        fam = F_BOLD if nivel == 0 else F_REG
        t = fig.text(x, y, texto, fontsize=fs if nivel else fs + 0.5, family=fam,
                     weight="bold" if nivel == 0 else "normal", color=cor, va="center")
        fim = x0 + larg - 0.03
        bb = t.get_window_extent(renderer=fig.canvas.get_renderer()).transformed(fig.transFigure.inverted())
        if bb.x1 + 0.01 < fim:
            fig.add_artist(plt.Line2D([bb.x1 + 0.01, fim], [y - 0.004] * 2, transform=fig.transFigure,
                                      color="#C8C8C8", lw=0.6, ls=(0, (1, 2))))
        fig.text(x0 + larg, y, str(pag), fontsize=fs, family=F_SEMI, color=ctx.marca["acento"], va="center",
                 ha="right")
    pdf.savefig(fig)
    plt.close(fig)


# ------------------------------------------------------------------ capa (arte Exp-Ag "Informações via satélites")
CAPA_ARTE = Path(__file__).resolve().parents[2] / "assets" / "capas" / "capa_satelites.jpg"


def pagina_capa(pdf, ctx, d, diag):
    """Capa com a arte do autor (marca e título já na imagem); a identificação da área vai na faixa clara entre o
    título e a paisagem, à esquerda do satélite."""
    fig = plt.figure(figsize=A4)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    if CAPA_ARTE.exists():
        ax.imshow(np.asarray(Image.open(CAPA_ARTE).convert("RGB")), extent=(0, 1, 0, 1), aspect="auto",
                  interpolation="antialiased", zorder=0)
    cor, ac = ctx.marca["cor"], ctx.marca["acento"]
    x, y = 0.098, 0.722
    ax.text(x, y, "DIAGNÓSTICO DA ÁREA", fontsize=8.5, family=F_SEMI, color=ac, va="center", zorder=3)
    ax.plot([x, x + 0.075], [y - 0.011] * 2, color=ac, lw=1.4, solid_capstyle="butt", zorder=3)
    y -= 0.04
    area_txt = f"{br(diag.area.area_ha, 1)} ha"
    principal = f"{d.talhao} · {area_txt}" if d.talhao else (f"{diag.area.nome} · {area_txt}" if getattr(
        diag.area, "nome", "") else area_txt)
    t = ax.text(x, y, principal, fontsize=19, family=F_REG, color=cor, va="center", zorder=3)
    caber(fig, t, 0.55, 12)
    y -= 0.033
    for val in (" · ".join(v for v in (d.propriedade, d.produtor) if v), d.municipio):
        if val:
            t = ax.text(x, y, val, fontsize=10, family=F_REG, color="#2E3134", va="center", zorder=3)
            caber(fig, t, 0.55, 7)
            y -= 0.02
    if d.data:
        ax.text(x, y - 0.003, f"Gerado em {d.data} · plataforma Exp-Ag", fontsize=7.8, family=F_REG,
                color="#5B6166", va="center", zorder=3)
    pdf.savefig(fig)
    plt.close(fig)
