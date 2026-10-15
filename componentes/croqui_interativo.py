"""Croqui interativo (Plotly): zoom, arraste do mapa, informações ao passar o
mouse e seleção de unidades por clique. Usa a mesma geometria e as mesmas
regras de cor/rótulo das exportações estáticas.
"""

from __future__ import annotations

import math

import plotly.graph_objects as go

from motor.dominio import Casualizacao, Tratamento
from motor.exportacao.estilo import (
    CHUMBO,
    LINHA,
    OCRE,
    PETROLEO,
    PRETO_SUAVE,
    OpcoesVisuais,
    atribuir_cores,
    cor_texto,
    desenho_cota,
    escala_redonda,
    fmt_m,
    limites_com_cotas,
    romano,
    texto_rotulo,
)
from motor.geometria.layout import Croqui

FONTE = "Roboto, 'Helvetica Neue', Arial, sans-serif"


def _fechar(p):
    xs = [q[0] for q in p] + [p[0][0], None]
    ys = [q[1] for q in p] + [p[0][1], None]
    return xs, ys


def figura_croqui(
    cas: Casualizacao,
    tratamentos: list[Tratamento],
    croqui: Croqui,
    opcoes: OpcoesVisuais,
    destacar: set[int] | None = None,
    altura_max: int = 720,
    largura_px: int = 980,
) -> go.Figure:
    destacar = destacar or set()
    por_u = {u.numero: u for u in cas.unidades}
    por_t = {t.numero: t for t in tratamentos}
    cores, grupos, legenda = atribuir_cores(cas, tratamentos, opcoes.colorir_por)
    cfg = croqui.config
    fig = go.Figure()

    # blocos
    if opcoes.mostrar_blocos and croqui.blocos and not croqui.bancadas:
        xs, ys = [], []
        for cb in croqui.blocos:
            a, b = _fechar(cb.poligono)
            xs += a
            ys += b
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=CHUMBO, width=1, dash="dash"),
                                 hoverinfo="skip", showlegend=False))

    # bancadas (casa de vegetação)
    for bc in croqui.bancadas:
        a, b = _fechar(bc.poligono)
        fig.add_trace(go.Scatter(x=a, y=b, mode="lines", fill="toself", fillcolor="#E6DFD0",
                                 line=dict(color=CHUMBO, width=1), hoverinfo="skip", showlegend=False))

    # unidades agrupadas por cor (uma entrada de legenda por grupo)
    ordem_grupos = [r for r, _ in legenda] or ["Unidades"]
    por_grupo: dict[str, list] = {g: [] for g in ordem_grupos}
    for cel in croqui.celulas:
        por_grupo.setdefault(grupos.get(cel.numero, "Unidades"), []).append(cel)
    for g, cels in por_grupo.items():
        if not cels:
            continue
        xs, ys = [], []
        for cel in cels:
            a, b = _fechar(cel.poligono)
            xs += a
            ys += b
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines", fill="toself", fillcolor=cores[cels[0].numero],
            line=dict(color=LINHA, width=1), name=g, hoverinfo="skip", legendgroup=g, showlegend=False,
        ))
        if legenda:  # marcador quadrado apenas para a legenda
            fig.add_trace(go.Scatter(
                x=[None], y=[None], mode="markers", name=g, legendgroup=g, hoverinfo="skip",
                marker=dict(symbol="square", size=13, color=cores[cels[0].numero], line=dict(color=LINHA, width=1)),
            ))

    if opcoes.mostrar_area_util and cfg.tipo == "parcelas":
        xs, ys = [], []
        for cel in croqui.celulas:
            if cel.poligono_util:
                a, b = _fechar(cel.poligono_util)
                xs += a
                ys += b
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=LINHA, width=0.6, dash="dot"),
                                     hoverinfo="skip", showlegend=False))

    # parcelas principais (subdivididas)
    if croqui.principais:
        xs, ys = [], []
        for poli in croqui.principais:
            a, b = _fechar(poli)
            xs += a
            ys += b
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=PETROLEO, width=2.4),
                                 hoverinfo="skip", showlegend=False))

    # destaque das unidades selecionadas
    if destacar:
        xs, ys = [], []
        for cel in croqui.celulas:
            if cel.numero in destacar:
                a, b = _fechar(cel.poligono)
                xs += a
                ys += b
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=OCRE, width=3.5),
                                 hoverinfo="skip", showlegend=False))

    # rótulos + pontos de interação
    x0, y0, x1, y1 = limites_com_cotas(croqui, opcoes.mostrar_dimensoes)
    ext = max(x1 - x0, y1 - y0)
    pad = 0.06 * ext
    xr = [x0 - pad, x1 + pad + 0.1 * ext]
    yr = [y0 - 0.14 * ext, y1 + pad + 0.04 * ext]
    # altura proporcional ao desenho (largura útil estimada do contêiner)
    n_leg = len(legenda)
    leg_px = (math.ceil(n_leg / max(1, largura_px // 190)) * 24 + 16) if n_leg else 0
    desenho_px = min(max(largura_px * (yr[1] - yr[0]) / (xr[1] - xr[0]), 260), altura_max - leg_px)
    altura_px = int(desenho_px + leg_px + 20)
    px_por_m = min(largura_px / (xr[1] - xr[0]), desenho_px / (yr[1] - yr[0]))
    w_px = cfg.largura_efetiva * px_por_m
    h_px = cfg.comprimento_efetivo * px_por_m
    textos = [texto_rotulo(por_u[c.numero], por_t[por_u[c.numero].tratamento], opcoes.rotulo) for c in croqui.celulas]
    maior = max(max(len(s) for s in t.split("\n")) for t in textos)
    n_lin = max(t.count("\n") + 1 for t in textos)
    if cfg.tipo == "vasos":
        w_px = h_px = cfg.diametro_vaso * px_por_m * 0.75
    if abs(((cfg.rotacao_graus + 90) % 180) - 90) > 45:
        w_px, h_px = h_px, w_px
    tam = max(6, min(14, w_px * 0.78 / (0.6 * maior), h_px * 0.62 / (1.25 * n_lin)))
    custom, hover = [], []
    for cel in croqui.celulas:
        u = por_u[cel.numero]
        t = por_t[u.tratamento]
        custom.append(u.numero)
        linhas = [f"<b>{u.codigo or u.parcela}</b>", f"Parcela {u.parcela}", f"{t.codigo} — {t.rotulo}"]
        for f, nv in t.niveis.items():
            if len(t.niveis) > 1:
                linhas.append(f"{f}: {nv}")
        if u.bloco is not None:
            linhas.append(f"Bloco {romano(u.bloco)}")
        linhas.append(f"Repetição {u.repeticao}")
        hover.append("<br>".join(linhas))
    fig.add_trace(go.Scatter(
        x=[c.centro[0] for c in croqui.celulas], y=[c.centro[1] for c in croqui.celulas],
        mode="markers+text", text=[t.replace("\n", "<br>") for t in textos],
        textfont=dict(family=FONTE, size=tam, color=[cor_texto(cores[c.numero]) for c in croqui.celulas]),
        marker=dict(size=max(8, min(w_px, h_px) * 0.9), color="rgba(0,0,0,0)", symbol="square"),
        customdata=custom, hovertext=hover, hoverinfo="text", showlegend=False, name="unidades",
    ))

    anot = []
    for r in croqui.rotulos:
        anot.append(dict(x=r.ponto[0], y=r.ponto[1], text=r.texto, showarrow=False,
                         font=dict(family=FONTE, size=12, color=PETROLEO)))
    for bc in croqui.bancadas:
        anot.append(dict(x=bc.rotulo_em[0], y=bc.rotulo_em[1], text=f"Bancada {bc.bloco}", showarrow=False,
                         yanchor="top", font=dict(family=FONTE, size=11, color=CHUMBO)))
    if opcoes.mostrar_blocos:
        ang = math.radians(cfg.rotacao_graus)
        d = 0.03 * ext
        vx, vy = (0, d) if cfg.arranjo_blocos == "horizontal" else (-d * 1.7, 0)
        dx, dy = vx * math.cos(ang) - vy * math.sin(ang), vx * math.sin(ang) + vy * math.cos(ang)
        for cb in croqui.blocos:
            anot.append(dict(x=cb.rotulo_em[0] + dx, y=cb.rotulo_em[1] + dy, text=f"Bloco {romano(cb.bloco)}",
                             showarrow=False, font=dict(family=FONTE, size=13, color=CHUMBO)))
    shapes = []
    if opcoes.mostrar_dimensoes and croqui.cotas:
        xs, ys = [], []
        for ct in croqui.cotas:
            segs, (tx, ty), ang = desenho_cota(ct, ext)
            for a, b in segs:
                xs += [a[0], b[0], None]
                ys += [a[1], b[1], None]
            anot.append(dict(x=tx, y=ty, text=ct.texto, showarrow=False, textangle=-ang, bgcolor="rgba(255,255,255,0.85)",
                             font=dict(family=FONTE, size=11 if ct.nivel == "geral" else 10,
                                       color=PETROLEO if ct.nivel == "geral" else CHUMBO)))
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=CHUMBO, width=0.8), hoverinfo="skip",
                                 showlegend=False))
    if opcoes.mostrar_escala:
        comp = escala_redonda(ext)
        yb = y0 - 0.08 * ext
        shapes += [
            dict(type="rect", x0=x0, x1=x0 + comp / 2, y0=yb, y1=yb + 0.012 * ext, fillcolor=PRETO_SUAVE,
                 line=dict(color=PRETO_SUAVE, width=1)),
            dict(type="rect", x0=x0 + comp / 2, x1=x0 + comp, y0=yb, y1=yb + 0.012 * ext, fillcolor="white",
                 line=dict(color=PRETO_SUAVE, width=1)),
        ]
        anot.append(dict(x=x0 + comp, y=yb - 0.01 * ext, text=f"{fmt_m(comp)} m", showarrow=False,
                         yanchor="top", font=dict(family=FONTE, size=11, color=PRETO_SUAVE)))
        anot.append(dict(x=x0, y=yb - 0.01 * ext, text="0", showarrow=False, yanchor="top",
                         font=dict(family=FONTE, size=11, color=PRETO_SUAVE)))
    if opcoes.mostrar_norte:
        a = math.radians(cfg.azimute_norte)
        cx, cy, L = x1 + 0.07 * ext, y1 - 0.05 * ext, 0.06 * ext
        anot.append(dict(x=cx + L / 2 * math.sin(a), y=cy + L / 2 * math.cos(a),
                         ax=cx - L / 2 * math.sin(a), ay=cy - L / 2 * math.cos(a),
                         xref="x", yref="y", axref="x", ayref="y", showarrow=True, arrowhead=2,
                         arrowsize=1.2, arrowwidth=1.6, arrowcolor=PRETO_SUAVE, text=""))
        anot.append(dict(x=cx + L * 0.85 * math.sin(a), y=cy + L * 0.85 * math.cos(a), text="N",
                         showarrow=False, font=dict(family=FONTE, size=13, color=PRETO_SUAVE)))

    fig.update_layout(
        height=altura_px,
        margin=dict(l=10, r=10, t=10, b=10 + leg_px),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family=FONTE, color=PRETO_SUAVE),
        xaxis=dict(visible=False, range=xr),
        yaxis=dict(visible=False, scaleanchor="x", scaleratio=1, range=yr),
        legend=dict(orientation="h", yanchor="top", y=-0.01, x=0, font=dict(size=11), yref="paper",
                    itemclick=False, itemdoubleclick=False),
        annotations=anot,
        shapes=shapes,
        dragmode="pan",
        hoverlabel=dict(bgcolor="white", font=dict(family=FONTE, size=12)),
        clickmode="event+select",
    )
    return fig
