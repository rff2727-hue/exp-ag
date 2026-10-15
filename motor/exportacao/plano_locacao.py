"""Plano de locação em PDF: o experimento no terreno, com todas as medidas, para implantar no campo.

Conteúdo: capa; resumo do georreferenciamento e medidas; mapa em UTM (imagem de satélite ao fundo quando disponível)
com parcelas, blocos, cotas, piquetes e perímetro; diagonais e roteiro de locação com trena; tabela de piquetes
(coordenadas locais, UTM e geográficas) e tabela dos centros das parcelas.
"""

from __future__ import annotations

import logging
import math

import numpy as np
import shapely
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, Spacer

from motor.exportacao.capa import capa_do_plano
from motor.exportacao.croqui_estatico import CM, figura_para_bytes, registrar_fontes
from motor.exportacao.estilo import (
    CHUMBO,
    LINHA,
    OCRE,
    PETROLEO,
    PRETO_SUAVE,
    TRAVA_MPL,
    atribuir_cores,
    cor_texto,
    escala_redonda,
    fmt_num,
    romano,
    texto_rotulo,
)
from motor.exportacao.relatorio_pdf import _cabecalho, _doc_para_bytes, _estilos, _juntar, _numerar, _tabela
from motor.geometria.layout import texto_medida
from motor.gis import crs
from motor.gis.feicoes import ConjuntoGeo
from motor.gis.georref import MODOS
from motor.gis.locacao import diagonais, roteiro_trena

log = logging.getLogger(__name__)


def _br(v: float, casas: int = 2) -> str:
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fundo_imagem(cj: ConjuntoGeo, x0, y0, x1, y1):
    """Imagem de satélite reprojetada para a UTM do experimento: (array RGB, extent, crédito) ou None."""
    try:
        from rasterio.transform import array_bounds, from_bounds
        from rasterio.warp import Resampling, calculate_default_transform, reproject

        from motor.sat import externos

        tg = crs.para_geo(cj.epsg)
        lons, lats = tg.transform([x0, x1, x0, x1], [y0, y0, y1, y1])
        r = externos.imagem_satelite(min(lons), min(lats), max(lons), max(lats), "Esri World Imagery", max_px=2000,
                                     timeout=8)
        if r is None:
            return None
        img, (xa, xb, yb, ya), cred = r
        h, w = img.shape[:2]
        src_t = from_bounds(xa, yb, xb, ya, w, h)
        dst_t, dw, dh = calculate_default_transform(3857, cj.epsg, w, h, left=xa, bottom=yb, right=xb, top=ya)
        dst = np.zeros((3, dh, dw), dtype=np.uint8)
        for b in range(3):
            reproject(img[:, :, b], dst[b], src_transform=src_t, src_crs="EPSG:3857", dst_transform=dst_t,
                      dst_crs=f"EPSG:{cj.epsg}", resampling=Resampling.bilinear)
        sul, oeste, norte, leste = array_bounds(dh, dw, dst_t)
        return np.moveaxis(dst, 0, -1), (oeste, leste, sul, norte), cred
    except Exception as e:  # noqa: BLE001 — sem rede ou sem fonte: o mapa sai sem fundo
        log.info("Plano de locação sem imagem de fundo: %s", e)
        return None


def _poligono_mpl(ax, g, **kw):
    from matplotlib.patches import Polygon as MPoly

    for pol in getattr(g, "geoms", [g]):
        ax.add_patch(MPoly(np.asarray(pol.exterior.coords)[:, :2], closed=True, **kw))


def figura_mapa(p, cj: ConjuntoGeo, com_fundo: bool = True, mostrar_piquetes: bool = True, pagina: str = "A4",
                vista: str = "detalhe") -> bytes:
    """Mapa do experimento em UTM. ``vista="detalhe"``: só o experimento, com rótulos, cotas e piquetes;
    ``vista="situacao"``: o experimento dentro da área de implantação."""
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.ticker import FuncFormatter

    from motor.exportacao.estilo import desenho_cota

    with TRAVA_MPL:
        registrar_fontes()
        t = cj.transformacao
        cr = cj.croqui
        detalhe = vista == "detalhe"
        geoms = [g for g, _ in cj.camadas["experimento"].feicoes]
        if detalhe:
            geoms += [shapely.LineString([t.ponto_utm(ct.q1), t.ponto_utm(ct.q2)]) for ct in cr.cotas]
        elif "perimetro" in cj.camadas:
            geoms += [g for g, _ in cj.camadas["perimetro"].feicoes]
        xs = [c for g in geoms for c in (g.bounds[0], g.bounds[2])]
        ys = [c for g in geoms for c in (g.bounds[1], g.bounds[3])]
        ext_exp = max(cr.largura_total, cr.altura_total)
        pad = max(0.06 * (max(xs) - min(xs) + max(ys) - min(ys)) / 2, 0.05 * ext_exp, 3)
        x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
        larg, alt = x1 - x0, y1 - y0
        paisagem = larg >= alt
        pw, ph = (29.7, 21.0) if paisagem else (21.0, 29.7)
        if pagina == "A3":
            pw, ph = pw * math.sqrt(2), ph * math.sqrt(2)
        mg_esq, mg_dir, mg_topo, mg_base = 2.2, 1.2, 2.0, 1.6
        cores, _, legenda = atribuir_cores(p.casualizacao, p.tratamentos, "tratamento")
        if not detalhe:
            legenda = []
        leg_h = 0.0
        if legenda:
            ncol = 4 if paisagem else 3
            leg_h = 0.42 * math.ceil(len(legenda) / ncol) + 0.2
        eixo_x = 1.15                                            # rótulos e título do eixo E
        aw, ah = pw - mg_esq - mg_dir, ph - mg_topo - mg_base - leg_h - eixo_x
        esc = min(aw / larg, ah / alt)                           # cm de papel por metro
        aw2, ah2 = larg * esc, alt * esc
        fig = plt.figure(figsize=(pw * CM, ph * CM))
        ax_base = mg_base + leg_h + eixo_x + (ah - ah2) / 2
        ax = fig.add_axes(((mg_esq + (aw - aw2) / 2) / pw, ax_base / ph, aw2 / pw, ah2 / ph))
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_aspect("equal")
        cred = ""
        if com_fundo:
            fundo = fundo_imagem(cj, x0, y0, x1, y1)
            if fundo is not None:
                img, extent, cred = fundo
                ax.imshow(img, extent=extent, zorder=0, interpolation="bilinear")
                ax.set_xlim(x0, x1)
                ax.set_ylim(y0, y1)
        claro = bool(cred)
        cor_linha = "#FFFFFF" if claro else LINHA
        if "perimetro" in cj.camadas:
            for g, _ in cj.camadas["perimetro"].feicoes:
                _poligono_mpl(ax, g, fill=False, ec=OCRE, lw=1.6, zorder=2)
        if "evitar" in cj.camadas:
            for g, _ in cj.camadas["evitar"].feicoes:
                _poligono_mpl(ax, g, fc="#B23A2E", alpha=0.3, ec="#B23A2E", lw=0.8, zorder=2)
        for g, _ in cj.camadas["experimento"].feicoes:
            _poligono_mpl(ax, g, fill=False, ec=PETROLEO, lw=1.3, zorder=3)
        for g, _ in cj.camadas["blocos"].feicoes:
            _poligono_mpl(ax, g, fill=False, ec=cor_linha, lw=0.7, ls=(0, (4, 2)), zorder=3)
        pts_por_m = esc * 72 / 2.54
        por_t = {x.numero: x for x in p.tratamentos}
        por_cod = {u.codigo: u for u in p.casualizacao.unidades}
        textos = []
        for g, a in (cj.camadas["parcelas"].feicoes if detalhe else []):
            u = por_cod.get(a["codigo"]) or next(x for x in p.casualizacao.unidades if x.parcela == a["parcela"])
            cor = cores.get(u.numero, "#FFFFFF")
            _poligono_mpl(ax, g, fc=cor, ec=PRETO_SUAVE, lw=0.45, alpha=0.92 if claro else 1.0, zorder=4)
            textos.append((g.centroid, texto_rotulo(u, por_t[u.tratamento], "parcela_tratamento"), cor))
        if not detalhe:
            for g, _ in cj.camadas["blocos"].feicoes or cj.camadas["experimento"].feicoes:
                _poligono_mpl(ax, g, fc=PETROLEO, alpha=0.55, ec="none", zorder=4)
        if "area_util" in cj.camadas and detalhe:
            for g, _ in cj.camadas["area_util"].feicoes:
                _poligono_mpl(ax, g, fill=False, ec=LINHA, lw=0.3, ls=(0, (2, 1.5)), zorder=5)
        cfg = cr.config
        w_pt = cfg.largura_efetiva * pts_por_m
        h_pt = cfg.comprimento_efetivo * pts_por_m
        maior = max((max(len(s) for s in tx.split("\n")) for _, tx, _ in textos), default=1)
        fs = max(min(8.0, w_pt * 0.74 / (0.56 * maior), h_pt * 0.6 / 2.4), 0)
        rot_txt = -(cj.geo.azimute + t.convergencia)
        rot_txt = ((rot_txt + 90) % 180) - 90
        if fs >= 3.2:
            for c, tx, cor in textos:
                ax.text(c.x, c.y, tx, ha="center", va="center", fontsize=fs, color=cor_texto(cor), rotation=rot_txt,
                        rotation_mode="anchor", linespacing=1.05, zorder=6)
        for cb in (cr.blocos if detalhe else []):
            ex, ny = t.ponto_utm((cb.rotulo_em[0], cb.rotulo_em[1] + 0.012 * ext_exp))
            ax.text(ex, ny, f"Bloco {romano(cb.bloco)}", ha="center", va="bottom", fontsize=7.5,
                    color="white" if claro else CHUMBO, rotation=rot_txt, rotation_mode="anchor", zorder=7,
                    bbox=dict(fc=PETROLEO, ec="none", pad=1.2, alpha=0.85) if claro else None)
        # cotas no terreno
        segs = []
        for ct in (cr.cotas if detalhe else []):
            s_, pos, ang = desenho_cota(ct, ext_exp)
            for a_, b_ in s_:
                segs.append((t.ponto_utm(a_), t.ponto_utm(b_)))
            ex, ny = t.ponto_utm(pos)
            ang_mapa = ((ang + rot_txt) + 90) % 180 - 90
            ax.text(ex, ny, ct.texto, ha="center", va="center", rotation=ang_mapa, rotation_mode="anchor",
                    fontsize=6.4 if ct.nivel == "geral" else 5.6, color=PETROLEO if ct.nivel == "geral" else PRETO_SUAVE,
                    zorder=9, bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.88))
        ax.add_collection(LineCollection(segs, colors=cor_linha, linewidths=0.5, zorder=8))
        # piquetes
        pq = cj.camadas["piquetes"].feicoes
        if mostrar_piquetes and pq and detalhe:
            ax.scatter([g.x for g, _ in pq], [g.y for g, _ in pq], s=7, c="#F4F0E8", edgecolors=OCRE, linewidths=0.6,
                       zorder=10)
            # rótulos: todos, se houver espaço; senão só os cantos do experimento e dos blocos (a tabela tem todos)
            xy = np.array([[g.x, g.y] for g, _ in pq])
            dmin = min((np.sort(np.hypot(*(xy - q).T))[1] for q in xy), default=0) if len(xy) > 1 else 1e9
            todos = dmin * pts_por_m >= 16
            for g, a in pq:
                if todos or a["tipo"] != "parcela":
                    ax.text(g.x, g.y, " " + a["id"], fontsize=4.6, color=OCRE if not claro else "#FFE9C2",
                            ha="left", va="bottom", zorder=11)
        # moldura de coordenadas
        fmt = FuncFormatter(lambda v, _: _br(v, 0))
        ax.xaxis.set_major_formatter(fmt)
        ax.yaxis.set_major_formatter(fmt)
        ax.tick_params(labelsize=6.5, colors=CHUMBO, length=3, width=0.5, direction="out")
        for lado in ax.spines.values():
            lado.set_linewidth(0.6)
            lado.set_color(CHUMBO)
        plt.setp(ax.get_yticklabels(), rotation=90, va="center")
        ax.set_xlabel("E (m)", fontsize=7, color=CHUMBO)
        ax.set_ylabel("N (m)", fontsize=7, color=CHUMBO)
        # escala e norte
        comp = escala_redonda(larg)
        bx, by = x0 + 0.04 * larg, y0 + 0.04 * alt
        h_b = 0.012 * alt
        from matplotlib.patches import Rectangle

        ax.add_patch(Rectangle((bx, by), comp / 2, h_b, fc=PRETO_SUAVE, ec=PRETO_SUAVE, lw=0.4, zorder=12))
        ax.add_patch(Rectangle((bx + comp / 2, by), comp / 2, h_b, fc="white", ec=PRETO_SUAVE, lw=0.4, zorder=12))
        ax.text(bx + comp, by + 2.2 * h_b, f"{_br(comp, 0)} m", fontsize=6.5, ha="right", va="bottom",
                color="white" if claro else PRETO_SUAVE, zorder=12)
        nx, ny0 = x1 - 0.05 * larg, y1 - 0.13 * alt
        ax.annotate("", xy=(nx, ny0 + 0.08 * alt), xytext=(nx, ny0),
                    arrowprops=dict(arrowstyle="-|>,head_width=0.35,head_length=0.7",
                                    color="white" if claro else PRETO_SUAVE, lw=1.0), zorder=12)
        ax.text(nx, ny0 + 0.095 * alt, "NQ", ha="center", va="bottom", fontsize=7,
                color="white" if claro else PRETO_SUAVE, zorder=12)
        exp = cj.camadas["experimento"].feicoes[0][1]
        titulo = "Detalhe do experimento" if detalhe else "Situação na área de implantação"
        fig.text(mg_esq / pw, 1 - 0.85 / ph, f"{titulo} — {exp['exp']}", fontsize=11, color=PRETO_SUAVE,
                 ha="left", va="top")
        fig.text(mg_esq / pw, 1 - 1.35 / ph,
                 f"{crs.nome_crs(cj.epsg)} (EPSG:{cj.epsg}) · NQ = Norte da quadrícula; o Norte verdadeiro está a "
                 f"{_br(-t.convergencia, 3)}° dele · azimute verdadeiro do eixo Y do croqui {_br(cj.geo.azimute, 2)}° · "
                 f"escala 1:{_br(100 / esc, 0)}", fontsize=6.6, color=CHUMBO, ha="left", va="top")
        if legenda:
            from matplotlib.patches import Patch

            hs = [Patch(fc=c, ec=LINHA, lw=0.4, label=r) for r, c in legenda]
            fig.legend(handles=hs, loc="upper left", ncol=4 if paisagem else 3, frameon=False, fontsize=6.6,
                       bbox_to_anchor=(mg_esq / pw, (mg_base + leg_h) / ph), handlelength=1.3,
                       columnspacing=1.2, borderaxespad=0)
        rod = "Imagem de fundo: " + cred if cred else "Sem imagem de fundo (serviço de imagens indisponível no momento)"
        fig.text(1 - mg_dir / pw, 1 - 1.35 / ph, rod, fontsize=5.8, color=CHUMBO, ha="right", va="top")
        return figura_para_bytes(fig, "pdf")


def plano_locacao(p, cj: ConjuntoGeo, com_fundo: bool = True, capa: bool = True) -> bytes:
    est = _estilos()
    larg = A4[0] - 4 * cm
    t = cj.transformacao
    geo = cj.geo
    cr = cj.croqui
    lon_c, lat_c = cj.centro_geo
    Ec, Nc = t.ponto_utm((cr.largura_total / 2, cr.altura_total / 2))
    h: list = _cabecalho(p, "Plano de locação", est)
    n = iter(range(1, 20))

    def tit(txt):
        return Paragraph(f"{next(n)}. {txt}", est["h"])

    h.append(tit("Posição no terreno"))
    linhas = [
        ["Centro do experimento", f"lat {_br(lat_c, 7)} · lon {_br(lon_c, 7)}"],
        ["Centro em UTM", f"E {_br(Ec, 2)} m · N {_br(Nc, 2)} m"],
        ["Sistema de referência", f"{crs.nome_crs(t.epsg)} (EPSG:{t.epsg})"],
        ["Azimute verdadeiro do eixo Y (comprimento)", f"{_br(geo.azimute, 2)}°"],
        ["Azimute verdadeiro do eixo X (largura)", f"{_br(t.azimute_eixo_x, 2)}°"],
        ["Convergência meridiana · fator de escala", f"{_br(t.convergencia, 4)}° · {t.k:.6f}".replace(".", ",")],
        ["Como foi posicionado", MODOS.get(geo.modo, geo.modo)],
    ]
    if geo.residuo_rms is not None:
        linhas.append(["Erro médio dos pontos de controle", f"{_br(geo.residuo_rms, 3)} m"])
    if geo.folga_m is not None and geo.modo == "perimetro":
        linhas.append(["Folga mínima até a divisa (encaixe)", f"{_br(geo.folga_m, 2)} m"])
    if "perimetro" in cj.camadas:
        a = cj.camadas["perimetro"].feicoes[0]
        linhas.append(["Área de implantação", f"{_br(a[1]['area_ha'], 4)} ha"])
    h.append(_tabela(["Item", "Valor"], linhas, [6.5 * cm, larg - 6.5 * cm], est))
    h.append(tit("Medidas"))
    m = cr.metricas
    cfg = cr.config
    med = [["Largura total (eixo X) × comprimento total (eixo Y)",
            f"{texto_medida(cr.largura_total)} × {texto_medida(cr.altura_total)} = {fmt_num(m['area_total_m2'])} m²"]]
    if cfg.tipo == "parcelas":
        med += [["Parcela", f"{texto_medida(m['largura_parcela_m'])} × {texto_medida(m['comprimento_parcela_m'])}"],
                ["Área útil da parcela", f"{texto_medida(m['largura_util_m'])} × {texto_medida(m['comprimento_util_m'])}"],
                ["Espaço entre parcelas (lateral · entre linhas)",
                 f"{texto_medida(cfg.espaco_x)} · {texto_medida(cfg.espaco_y)}"]]
    if cr.blocos:
        med.append(["Carreador entre blocos", texto_medida(cfg.espaco_blocos)])
        if 0 < cfg.blocos_por_fileira < len(cr.blocos):
            med.append(["Entre fileiras de blocos", texto_medida(cfg.espaco_fileiras)])
    if cfg.corredor_a_cada_colunas and cfg.largura_corredor_colunas:
        med.append([f"Corredor a cada {cfg.corredor_a_cada_colunas} unidades na linha",
                    texto_medida(cfg.largura_corredor_colunas)])
    if cfg.corredor_a_cada_linhas and cfg.largura_corredor_linhas:
        med.append([f"Corredor a cada {cfg.corredor_a_cada_linhas} linhas", texto_medida(cfg.largura_corredor_linhas)])
    bs = [cfg.bordadura(x) for x in ("esquerda", "direita", "topo", "base")]
    med.append(["Bordadura externa (esq. · dir. · topo · base)", " · ".join(texto_medida(v) if v else "0" for v in bs)])
    if cfg.deslocamentos_blocos:
        med.append(["Blocos deslocados à mão", "; ".join(f"{k}: {_br(v[0], 2)} m → , {_br(v[1], 2)} m ↑"
                                                         for k, v in cfg.deslocamentos_blocos.items())])
    h.append(_tabela(["Item", "Medida"], med, [7.5 * cm, larg - 7.5 * cm], est))
    h.append(KeepTogether([tit("Diagonais para conferir o esquadro"),
                           _tabela(["Elemento", "Lados (m)", "Diagonal (m)"],
                                   [[d["Elemento"], d["Lados (m)"].replace(".", ","), _br(d["Diagonal (m)"], 2)]
                                    for d in diagonais(cr)], [6 * cm, 5 * cm, 3 * cm], est, direita={2})]))
    h.append(PageBreak())
    h.append(tit("Roteiro de locação"))
    h.append(Paragraph("As coordenadas locais (X, Y) partem do canto inferior esquerdo do croqui e servem para locar com "
                       "trena; as UTM, para estação total ou GPS RTK; latitude e longitude, para GPS de navegação. "
                       "Todas descrevem os mesmos pontos (tabela de piquetes).", est["nota"]))
    h.append(Spacer(1, 4))
    for i, passo in enumerate(roteiro_trena(t), start=1):
        h.append(Paragraph(f"{i}. {passo}", est["p"]))
        h.append(Spacer(1, 3))

    h2: list = [tit("Piquetes de locação")]
    pq = cj.camadas["piquetes"].feicoes
    h2.append(_tabela(["Piquete", "X (m)", "Y (m)", "E UTM (m)", "N UTM (m)", "Latitude", "Longitude", "Pertence a"],
                      [[a["id"], _br(a["x_local"], 2), _br(a["y_local"], 2), _br(a["e_utm"], 2), _br(a["n_utm"], 2),
                        _br(a["lat"], 7), _br(a["lon"], 7), a["refs"]] for _, a in pq],
                      [1.4 * cm, 1.3 * cm, 1.3 * cm, 2.0 * cm, 2.2 * cm, 2.0 * cm, 2.0 * cm, larg - 12.2 * cm], est,
                      direita={1, 2, 3, 4, 5, 6}))
    h2.append(PageBreak())
    h2.append(tit("Centros das unidades"))
    h2.append(_tabela(["Unidade", "Parcela", "Bloco", "Trat.", "E UTM (m)", "N UTM (m)", "Latitude", "Longitude"],
                      [[a["codigo"], a["parcela"], romano(a["bloco"]) if a["bloco"] else "—", a["trat_cod"],
                        _br(a["e_utm"], 2), _br(a["n_utm"], 2), _br(a["lat"], 7), _br(a["lon"], 7)]
                       for _, a in cj.camadas["centroides"].feicoes],
                      [larg - 13.2 * cm, 1.4 * cm, 1.2 * cm, 1.2 * cm, 2.2 * cm, 2.4 * cm, 2.4 * cm, 2.4 * cm], est,
                      direita={4, 5, 6, 7}))
    partes = [_doc_para_bytes(h)]
    if "perimetro" in cj.camadas:
        partes.append(figura_mapa(p, cj, com_fundo, vista="situacao"))
    partes += [figura_mapa(p, cj, com_fundo, vista="detalhe"), _doc_para_bytes(h2)]
    if capa:
        partes.insert(0, capa_do_plano(p, "Plano de locação"))
    return _numerar(_juntar(partes), f"Exp-Ag · {p.meta.codigo} · plano de locação", capa)


__all__ = ["figura_mapa", "fundo_imagem", "plano_locacao", "PETROLEO"]
