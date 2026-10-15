"""Renderização estática do croqui (PNG, SVG, PDF) com Matplotlib.

Estilo de publicação: Roboto, sem grade, sem negrito, linhas finas,
paleta segura para daltonismo e rótulos sempre presentes (a cor nunca é o
único portador de informação).
"""

from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Circle, Patch, Polygon, Rectangle  # noqa: E402

from motor.dominio import Casualizacao, Tratamento  # noqa: E402
from motor.exportacao.estilo import (  # noqa: E402
    CHUMBO,
    LINHA,
    OCRE,
    PALETA_SEGURA_MAX,
    PASTA_FONTES,
    PETROLEO,
    PRETO_SUAVE,
    OpcoesVisuais,
    atribuir_cores,
    cor_texto,
    desenho_cota,
    escala_redonda,
    fmt_m,
    fmt_num,
    limites_com_cotas,
    romano,
    texto_rotulo,
)
from motor.geometria.layout import Croqui  # noqa: E402

CM = 1 / 2.54
PAGINAS = {"A4": (29.7, 21.0), "A3": (42.0, 29.7)}  # paisagem, cm
_FONTE_REGISTRADA = False


def registrar_fontes() -> str:
    """Registra Roboto (incluída no repositório). Retorna o nome da família."""
    global _FONTE_REGISTRADA
    if not _FONTE_REGISTRADA:
        for ttf in PASTA_FONTES.glob("*.ttf"):
            font_manager.fontManager.addfont(str(ttf))
        _FONTE_REGISTRADA = True
    familias = {f.name for f in font_manager.fontManager.ttflist}
    familia = "Roboto" if "Roboto" in familias else "DejaVu Sans"
    plt.rcParams.update(
        {
            "font.family": familia,
            "font.weight": "normal",
            "axes.titleweight": "normal",
            "svg.fonttype": "none",  # texto editável no SVG
            "pdf.fonttype": 42,  # TrueType embutida
            "axes.grid": False,
        }
    )
    return familia


def desenhar_croqui(
    cas: Casualizacao,
    tratamentos: list[Tratamento],
    croqui: Croqui,
    opcoes: OpcoesVisuais,
    formato: str = "figura",
    rodape: str = "",
):
    registrar_fontes()
    por_num_u = {u.numero: u for u in cas.unidades}
    por_num_t = {t.numero: t for t in tratamentos}
    cores, _, legenda = atribuir_cores(cas, tratamentos, opcoes.colorir_por)
    if opcoes.modo == "operacional" and opcoes.colorir_por == "nenhum":
        legenda = []

    x0, y0, x1, y1 = limites_com_cotas(croqui, opcoes.mostrar_dimensoes)
    ext = max(x1 - x0, y1 - y0)
    pad = 0.05 * ext
    rotulos_bloco = opcoes.mostrar_blocos and croqui.blocos
    topo = 0.06 * ext if rotulos_bloco else 0.0
    esq = 0.07 * ext if (rotulos_bloco and croqui.config.arranjo_blocos == "vertical") else 0.0
    base = 0.07 * ext if (opcoes.mostrar_escala or opcoes.mostrar_plantio) else 0.0
    dir_ = 0.09 * ext if opcoes.mostrar_norte else 0.0
    xl = (x0 - pad - esq, x1 + pad + dir_)
    yl = (y0 - pad - base, y1 + pad + topo)
    aspecto = (yl[1] - yl[0]) / (xl[1] - xl[0])

    n_leg = len(legenda)
    ncol = 1 if n_leg == 0 else min(n_leg, 3 if max(len(r) for r, _ in legenda) > 28 else 4)
    linhas_leg = math.ceil(n_leg / ncol) if n_leg else 0
    leg_h_cm = 0.42 * linhas_leg + (0.5 if n_leg else 0)
    rod_h_cm = 0.6 if rodape else 0.0
    tit_h_cm = 0.8 if opcoes.titulo else 0.0

    if formato in PAGINAS:
        pw, ph = PAGINAS[formato]
        if aspecto > 1.15:
            pw, ph = ph, pw
        margem = 1.5
        area_w = pw - 2 * margem
        area_h = ph - 2 * margem - leg_h_cm - rod_h_cm - tit_h_cm
        ax_w = min(area_w, area_h / aspecto)
        ax_h = ax_w * aspecto
        fig_w, fig_h = pw, ph
        ax_left = (pw - ax_w) / 2
        ax_bottom = margem + leg_h_cm + rod_h_cm + (area_h - ax_h) / 2
    else:
        fig_w = 17.4
        ax_w = fig_w - 1.0
        ax_h = ax_w * aspecto
        if ax_h > 22:
            ax_h = 22
            ax_w = ax_h / aspecto
        fig_h = ax_h + leg_h_cm + rod_h_cm + tit_h_cm + 0.8
        ax_left = (fig_w - ax_w) / 2
        ax_bottom = 0.4 + leg_h_cm + rod_h_cm

    fig = plt.figure(figsize=(fig_w * CM, fig_h * CM))
    ax = fig.add_axes((ax_left / fig_w, ax_bottom / fig_h, ax_w / fig_w, ax_h / fig_h))
    ax.set_xlim(*xl)
    ax.set_ylim(*yl)
    ax.set_aspect("equal")
    ax.axis("off")

    pts_por_m = ax_w * CM * 72 / (xl[1] - xl[0])
    cfg = croqui.config
    rot = cfg.rotacao_graus
    rot_txt = ((rot + 90) % 180) - 90

    # blocos (sob as parcelas)
    if opcoes.mostrar_blocos:
        for cb in croqui.blocos:
            if not croqui.bancadas:
                ax.add_patch(Polygon(cb.poligono, closed=True, fill=False, ec=CHUMBO, lw=0.7, ls=(0, (4, 2)),
                                     zorder=1))
            dx, dy = _deslocamento_rotulo_bloco(cfg, ext)
            px, py = cb.rotulo_em
            ax.text(px + dx, py + dy, f"Bloco {romano(cb.bloco)}", ha="center", va="center",
                    fontsize=8, color=CHUMBO, rotation=rot_txt, zorder=5)

    # bancadas (casa de vegetação), sob tudo
    for bc in croqui.bancadas:
        ax.add_patch(Polygon(bc.poligono, closed=True, fc="#E6DFD0", ec=CHUMBO, lw=0.6, zorder=0.5))
        ax.text(bc.rotulo_em[0], bc.rotulo_em[1] - 0.012 * ext, f"Bancada {bc.bloco}", ha="center", va="top",
                fontsize=6.5, color=CHUMBO, rotation=rot_txt, zorder=5)

    # unidades
    textos = {}
    for cel in croqui.celulas:
        u = por_num_u[cel.numero]
        t = por_num_t[u.tratamento]
        cor = cores.get(u.numero, "#FFFFFF")
        if cfg.tipo == "vasos":
            ax.add_patch(Circle(cel.centro, cel.raio, fc=cor, ec=LINHA, lw=0.6, zorder=2))
        else:
            ax.add_patch(Polygon(cel.poligono, closed=True, fc=cor, ec=LINHA, lw=0.6, zorder=2))
            if opcoes.mostrar_area_util and cel.poligono_util:
                ax.add_patch(Polygon(cel.poligono_util, closed=True, fill=False, ec=LINHA,
                                     lw=0.35, ls=(0, (2, 1.5)), zorder=3))
        textos[cel.numero] = (cel.centro, texto_rotulo(u, t, opcoes.rotulo), cor)

    w_pt = cfg.largura_efetiva * pts_por_m
    h_pt = cfg.comprimento_efetivo * pts_por_m
    if cfg.tipo == "vasos":
        w_pt = h_pt = cfg.diametro_vaso * pts_por_m * 0.78
    maior = max((max(len(s) for s in tx.split("\n")) for _, tx, _ in textos.values()), default=1)
    n_lin = max((tx.count("\n") + 1 for _, tx, _ in textos.values()), default=1)
    if abs(rot_txt) > 45:
        w_pt, h_pt = h_pt, w_pt
    fs = min(9.0, w_pt * 0.74 / (0.56 * maior), h_pt * 0.62 / (1.2 * n_lin))
    fs = max(fs, 3.0)
    for centro, tx, cor in textos.values():
        ax.text(*centro, tx, ha="center", va="center", fontsize=fs, color=cor_texto(cor),
                rotation=rot_txt, linespacing=1.1, zorder=6)

    # parcelas principais (subdivididas) e rótulos de linhas/colunas (faixas e quadrado latino)
    for poli in croqui.principais:
        ax.add_patch(Polygon(poli, closed=True, fill=False, ec=PETROLEO, lw=1.5, zorder=4))
    for r in croqui.rotulos:
        ax.text(*r.ponto, r.texto, ha="center", va="center", fontsize=min(8.0, max(fs, 5.0)), color=PETROLEO,
                rotation=rot_txt, zorder=5)

    if opcoes.mostrar_dimensoes:
        _cotas(ax, croqui, ext)
    if opcoes.mostrar_escala:
        _barra_escala(ax, x0, y0 - pad * 0.6 - base * 0.55, ext)
    if opcoes.mostrar_norte:
        _seta_norte(ax, x1 + pad + dir_ * 0.5, y1 - 0.06 * ext, 0.07 * ext, cfg.azimute_norte)
    if opcoes.mostrar_plantio and cfg.tipo == "parcelas":
        _seta_plantio(ax, x1 - 0.12 * ext, y0 - pad * 0.6 - base * 0.5, 0.06 * ext, rot)

    if opcoes.titulo:
        fig.text(0.5, 1 - 0.35 / fig_h, opcoes.titulo,
                 ha="center", va="top", fontsize=10, color=PRETO_SUAVE)
    if legenda:
        handles = [Patch(fc=c, ec=LINHA, lw=0.5, label=r) for r, c in legenda]
        fig.legend(handles=handles, loc="upper center", ncol=ncol, frameon=False, fontsize=7,
                   bbox_to_anchor=(0.5, (ax_bottom - 0.15) / fig_h), handlelength=1.4,
                   handleheight=1.0, columnspacing=1.4, borderaxespad=0)
    if rodape:
        fig.text(0.5, (ax_bottom - leg_h_cm - 0.25) / fig_h, rodape, ha="center", va="top",
                 fontsize=6.5, color=CHUMBO)
    return fig


def _deslocamento_rotulo_bloco(cfg, ext: float) -> tuple[float, float]:
    d = 0.025 * ext
    ang = math.radians(cfg.rotacao_graus)
    if cfg.arranjo_blocos == "horizontal":
        vx, vy = 0.0, d  # para cima
    else:
        vx, vy = -d * 1.6, 0.0  # para a esquerda
    return vx * math.cos(ang) - vy * math.sin(ang), vx * math.sin(ang) + vy * math.cos(ang)


def _cotas(ax, croqui: Croqui, ext: float) -> None:
    from matplotlib.collections import LineCollection

    segs = []
    for ct in croqui.cotas:
        s_, (tx, ty), ang = desenho_cota(ct, ext)
        segs += s_
        ax.text(tx, ty, ct.texto, ha="center", va="center", rotation=ang, rotation_mode="anchor",
                fontsize=6.6 if ct.nivel == "geral" else 5.8, color=PETROLEO if ct.nivel == "geral" else CHUMBO,
                zorder=8, bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.85))
    ax.add_collection(LineCollection(segs, colors=CHUMBO, linewidths=0.45, zorder=7))


def _barra_escala(ax, x: float, y: float, ext: float) -> None:
    comp = escala_redonda(ext)
    h = 0.012 * ext
    metade = comp / 2
    ax.add_patch(Rectangle((x, y), metade, h, fc=PRETO_SUAVE, ec=PRETO_SUAVE, lw=0.5, zorder=6))
    ax.add_patch(Rectangle((x + metade, y), metade, h, fc="white", ec=PRETO_SUAVE, lw=0.5, zorder=6))
    for xi, rot in ((x, "0"), (x + metade, fmt_m(metade)), (x + comp, f"{fmt_m(comp)} m")):
        ax.text(xi, y - 0.008 * ext, rot, ha="center", va="top", fontsize=6.5, color=PRETO_SUAVE)


def _seta_norte(ax, x: float, y: float, comp: float, azimute: float) -> None:
    a = math.radians(azimute)
    dx, dy = comp * math.sin(a), comp * math.cos(a)
    ax.annotate("", xy=(x + dx / 2, y + dy / 2), xytext=(x - dx / 2, y - dy / 2),
                arrowprops=dict(arrowstyle="-|>,head_width=0.35,head_length=0.7", color=PRETO_SUAVE, lw=1.0))
    ax.text(x + dx * 0.85, y + dy * 0.85, "N", ha="center", va="center", fontsize=8, color=PRETO_SUAVE)


def _seta_plantio(ax, x: float, y: float, comp: float, rot: float) -> None:
    a = math.radians(rot)
    dx, dy = -comp * math.sin(a), comp * math.cos(a)
    ax.annotate("", xy=(x + dx / 2, y + dy / 2), xytext=(x - dx / 2, y - dy / 2),
                arrowprops=dict(arrowstyle="<|-|>,head_width=0.25,head_length=0.5", color=OCRE, lw=0.9))
    ax.text(x + comp * 0.7, y, "linhas de\nplantio", ha="left", va="center", fontsize=6, color=OCRE)


def rodape_padrao(croqui: Croqui) -> str:
    m = croqui.metricas
    if croqui.config.tipo == "vasos":
        return (f"{m['n_unidades']} vasos · Ø {fmt_m(m['diametro_vaso_m'] * 100)} cm · "
                f"área ocupada {fmt_m(m['largura_total_m'])} × {fmt_m(m['comprimento_total_m'])} m")
    partes = [
        f"{m['n_unidades']} parcelas de {fmt_m(m['largura_parcela_m'])} × {fmt_m(m['comprimento_parcela_m'])} m "
        f"({fmt_num(m['area_parcela_m2'])} m²)",
    ]
    if m["area_util_m2"] < m["area_parcela_m2"]:
        partes.append(f"área útil {fmt_m(m['largura_util_m'])} × {fmt_m(m['comprimento_util_m'])} m "
                      f"({fmt_num(m['area_util_m2'])} m²)")
    partes.append(f"área total {fmt_m(m['largura_total_m'])} × {fmt_m(m['comprimento_total_m'])} m "
                  f"= {fmt_num(m['area_total_m2'])} m²")
    return " · ".join(partes)


def figura_para_bytes(fig, formato: str, dpi: int = 300) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format=formato, dpi=dpi, facecolor="white",
                metadata={"Creator": "Exp-Ag"} if formato in ("pdf", "svg") else None)
    plt.close(fig)
    return buf.getvalue()


def exportar_croqui(cas, tratamentos, croqui, opcoes, formato_arquivo: str,
                    pagina: str = "figura", dpi: int = 300, com_rodape: bool = True) -> bytes:
    """``formato_arquivo``: png | svg | pdf. ``pagina``: figura | A4 | A3."""
    if formato_arquivo not in ("png", "svg", "pdf"):
        raise ValueError("Formato deve ser png, svg ou pdf.")
    fig = desenhar_croqui(cas, tratamentos, croqui, opcoes, pagina,
                          rodape_padrao(croqui) if com_rodape else "")
    return figura_para_bytes(fig, formato_arquivo, dpi)


def aviso_paleta(n_cores: int) -> str | None:
    if n_cores > PALETA_SEGURA_MAX:
        return (f"Com {n_cores} cores, a distinção apenas pela cor fica limitada (inclusive para "
                "daltonismo); os rótulos permanecem como identificação principal.")
    return None
