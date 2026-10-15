"""Mapa interativo do experimento (componente Streamlit v2 com Leaflet embutido, sem CDN).

O mesmo componente serve a dois usos:

* ``modo="geo"`` — o croqui sobre a imagem de satélite: arrastar e girar o experimento, arrastar blocos,
  desenhar perímetros e áreas a evitar, clicar para posicionar;
* ``modo="local"`` — o croqui num plano em metros, sem mapa: é o editor de disposição por arraste dos blocos.

O Leaflet 1.9.4 (licença BSD-2, ``vendor/LICENSE-leaflet.txt``) vai embutido no código do componente, para que o
mapa funcione mesmo quando a rede bloqueia CDNs; só as imagens de fundo (Esri, OpenStreetMap) vêm da internet.
"""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

from motor.exportacao.estilo import atribuir_cores, cor_texto, desenho_cota, romano, texto_rotulo
from motor.geometria.layout import Croqui

PASTA = Path(__file__).parent


@st.cache_resource(show_spinner=False)
def _componente():
    js = (PASTA / "vendor" / "leaflet.js").read_text(encoding="utf-8") + "\n" + \
        (PASTA / "mapa.js").read_text(encoding="utf-8")
    css = (PASTA / "vendor" / "leaflet.css").read_text(encoding="utf-8") + "\n" + \
        (PASTA / "mapa.css").read_text(encoding="utf-8")
    return st.components.v2.component("expag_mapa", html="", css=css, js=js, isolate_styles=True)


def dados_mapa(p, croqui: Croqui, *, modo: str = "geo", ref: tuple[float, float] | None = None,
               azimute: float = 0.0, editar: str = "nenhum", fundo: str = "satelite", rotulo: str = "parcela_tratamento",
               colorir_por: str = "tratamento", camadas: dict | None = None, areas: list | None = None,
               piquetes: list | None = None, versao: int = 0, ajustar: int = 0, altura: int = 560,
               vista: tuple[float, float, float] | None = None) -> dict:
    """Monta os dados do componente a partir do planejamento e do croqui local (sem rotação de desenho).

    ``ref`` = (lat, lon) do **centro** do croqui; ``areas`` = [{"tipo": "perimetro"|"evitar", "geometria": shapely}].
    """
    por_u = {u.numero: u for u in p.casualizacao.unidades}
    por_t = {t.numero: t for t in p.tratamentos}
    cores, _, _ = atribuir_cores(p.casualizacao, p.tratamentos, colorir_por)
    cfg = croqui.config
    unidades = []
    textos = []
    for c in croqui.celulas:
        u = por_u[c.numero]
        t = por_t[u.tratamento]
        txt = texto_rotulo(u, t, rotulo)
        textos.append(txt)
        cor = cores.get(c.numero, "#FFFFFF")
        dica = [f"<b>{html.escape(u.codigo or u.parcela)}</b>", f"Parcela {html.escape(u.parcela)}",
                f"{html.escape(t.codigo)} — {html.escape(t.rotulo)}"]
        if u.bloco is not None:
            dica.append(f"Bloco {romano(u.bloco)} · repetição {u.repeticao}")
        if cfg.tipo == "parcelas":
            dica.append(f"{cfg.largura_efetiva:.2f} × {cfg.comprimento_efetivo:.2f} m".replace(".", ","))
        unidades.append({"g": c.grupo, "p": [list(q) for q in c.poligono],
                         "u": [list(q) for q in c.poligono_util] if c.poligono_util else None,
                         "c": list(c.centro), "cor": cor, "tc": cor_texto(cor),
                         "rot": html.escape(txt).replace("\n", "<br>"), "dica": "<br>".join(dica)})
    grupos = []
    rot_bloco = {cb.bloco: cb for cb in croqui.blocos}
    rot_banc = {bc.bloco: bc for bc in croqui.bancadas}
    for gid, caixa in croqui.caixas.items():
        cel = next((c for c in croqui.celulas if c.grupo == gid), None)
        cb = rot_bloco.get(cel.bloco) if (cel is not None and cel.bloco is not None and not croqui.bancadas) else None
        bc = rot_banc.get(cel.bancada) if (cel is not None and cel.bancada is not None) else None
        if bc is not None:
            rotulo_g, contorno, em = f"Bancada {bc.bloco}", bc.poligono, bc.rotulo_em
        elif cb is not None:
            rotulo_g, contorno, em = f"Bloco {romano(cb.bloco)}", cb.poligono, cb.rotulo_em
        else:
            rotulo_g, contorno, em = ("Experimento" if len(croqui.caixas) == 1 else f"Grupo {gid}"), None, None
        grupos.append({"id": gid, "rotulo": rotulo_g, "caixa": [list(q) for q in caixa],
                       "contorno": [list(q) for q in contorno] if contorno else None,
                       "rotulo_em": list(em) if em else None})
    ext = max(croqui.largura_total, croqui.altura_total)
    cotas = []
    for ct in croqui.cotas:
        segs, pos, ang = desenho_cota(ct, ext)
        cotas.append({"segs": [[list(a), list(b)] for a, b in segs], "pos": list(pos), "ang": ang, "txt": ct.texto,
                      "v": ct.valor, "geral": ct.nivel == "geral"})
    aneis = []
    for a in areas or []:
        g = a["geometria"]
        for pol in getattr(g, "geoms", [g]):
            aneis.append({"tipo": a["tipo"], "aneis": [[[y, x] for x, y in pol.exterior.coords]]
                          + [[[y, x] for x, y in r.coords] for r in pol.interiors]})
    cam = {"rotulos": True, "blocos": True, "util": cfg.tipo == "parcelas", "cotas": False, "piquetes": False}
    cam.update(camadas or {})
    return {
        "modo": modo, "ref": {"lat": ref[0], "lon": ref[1]} if ref else {"lat": 0.0, "lon": 0.0},
        "azimute": float(azimute), "W": croqui.largura_total, "H": croqui.altura_total,
        "contorno": [list(q) for q in croqui.contorno], "grupos": grupos, "unidades": unidades, "cotas": cotas,
        "piquetes": piquetes or [], "areas": aneis, "camadas": cam, "editar": editar, "fundo": fundo,
        "desloc": {str(k): list(v) for k, v in (cfg.deslocamentos_blocos or {}).items()},
        "dim": [cfg.largura_efetiva, cfg.comprimento_efetivo],
        "maxLinhas": max((t.count("\n") + 1 for t in textos), default=1),
        "maxChars": max((max(len(s) for s in t.split("\n")) for t in textos), default=1),
        "versao": versao, "ajustar": ajustar, "altura": altura, "ocultar": modo == "geo" and ref is None,
        "vista": list(vista) if vista else None,
    }


def mapa_experimento(dados: dict, key: str):
    """Monta o componente; devolve o resultado (``.posicao``, ``.desenho``, ``.clique``)."""
    comp = _componente()
    return comp(key=key, data=dados, on_posicao_change=lambda: None, on_desenho_change=lambda: None,
                on_clique_change=lambda: None, height=int(dados.get("altura", 560)) + 4)
