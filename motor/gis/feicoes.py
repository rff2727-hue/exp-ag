"""Camadas georreferenciadas do experimento (UTM), prontas para exportação e para o mapa.

Camadas: experimento (contorno), blocos (ou bancadas), parcelas, area_util, centroides, piquetes e, quando houver,
perimetro (área de implantação) e evitar (áreas a evitar). Todos os atributos vêm do planejamento: código, parcela,
bloco, repetição, tratamento e níveis dos fatores — prontos para cruzar com dados de colheita, drone ou mapas de
produtividade.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import Point, Polygon

from motor.exportacao.estilo import atribuir_cores, romano
from motor.geometria.layout import Croqui
from motor.gis import crs
from motor.gis.georref import Georreferencia, Transformacao, croqui_local
from motor.gis.locacao import piquetes
from motor.planejamento import Planejamento


@dataclass
class Camada:
    nome: str
    titulo: str
    tipo: str  # "Polygon" | "Point" | "LineString"
    feicoes: list[tuple[object, dict]] = field(default_factory=list)  # (geometria UTM, atributos)


@dataclass
class ConjuntoGeo:
    epsg: int
    geo: Georreferencia
    transformacao: Transformacao
    croqui: Croqui
    camadas: dict[str, Camada]

    def camada_wgs84(self, nome: str) -> list[tuple[object, dict]]:
        tg = crs.para_geo(self.epsg)
        return [(shapely.transform(g, lambda c: np.column_stack(tg.transform(c[:, 0], c[:, 1]))), a)
                for g, a in self.camadas[nome].feicoes]

    @property
    def centro_geo(self) -> tuple[float, float]:
        """(lon, lat) do centro do experimento."""
        return self.transformacao.ponto_geo((self.croqui.largura_total / 2, self.croqui.altura_total / 2))


def nome_campo(nome: str, usados: set[str], limite: int = 10) -> str:
    """Nome de campo seguro para shapefile (≤10 caracteres, ASCII, único)."""
    t = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9_]", "_", t).strip("_").lower() or "campo"
    if t[0].isdigit():
        t = "f_" + t
    base = t[:limite]
    cand, i = base, 1
    while cand in usados:
        suf = str(i)
        cand = base[: limite - len(suf)] + suf
        i += 1
    usados.add(cand)
    return cand


def montar(p: Planejamento, geo: Georreferencia, perimetro_wgs84=None, evitar_wgs84=None,
           opcoes_cor: str = "tratamento", piquetes_de_parcela: bool = True) -> ConjuntoGeo:
    cr = croqui_local(p.casualizacao, p.layout)
    t = Transformacao(geo, cr.largura_total, cr.altura_total)
    por_u = {u.numero: u for u in p.casualizacao.unidades}
    por_t = {x.numero: x for x in p.tratamentos}
    cores, _, _ = atribuir_cores(p.casualizacao, p.tratamentos, opcoes_cor)
    fatores = [f.nome for f in p.estrutura.fatores] if p.estrutura.e_fatorial else []
    usados = {"codigo", "parcela", "bloco", "rep", "trat_num", "trat_cod", "trat_nome", "pp", "sp", "linha",
              "coluna", "largura_m", "compr_m", "area_m2", "cor", "exp"}
    campos_fator = {f: nome_campo(f, usados) for f in fatores}

    camadas: dict[str, Camada] = {}
    W, H = cr.largura_total, cr.altura_total
    camadas["experimento"] = Camada("experimento", "Experimento", "Polygon", [(
        t.geometria_utm(Polygon(cr.contorno)),
        {"exp": p.meta.codigo, "titulo": p.meta.titulo, "largura_m": round(W, 3), "compr_m": round(H, 3),
         "area_m2": round(W * H, 2), "azimute": round(geo.azimute, 3), "epsg": t.epsg})])
    grupos = Camada("blocos", "Bancadas" if cr.bancadas else "Blocos", "Polygon")
    for cb in (cr.bancadas or cr.blocos):
        pol = Polygon(cb.poligono)
        grupos.feicoes.append((t.geometria_utm(pol), {"exp": p.meta.codigo, "bloco": cb.bloco,
                                                      "rotulo": f"{'Bancada' if cr.bancadas else 'Bloco'} "
                                                                f"{romano(cb.bloco) if not cr.bancadas else cb.bloco}",
                                                      "area_m2": round(pol.area, 2)}))
    camadas["blocos"] = grupos
    parcelas = Camada("parcelas", "Parcelas" if p.layout.tipo == "parcelas" else "Vasos", "Polygon")
    util = Camada("area_util", "Área útil", "Polygon")
    cent = Camada("centroides", "Centros das unidades", "Point")
    for c in sorted(cr.celulas, key=lambda c: c.numero):
        u = por_u[c.numero]
        tr = por_t[u.tratamento]
        pol = Polygon(c.poligono)
        xs = [q[0] for q in c.poligono]
        ys = [q[1] for q in c.poligono]
        attrs = {"exp": p.meta.codigo, "codigo": u.codigo, "parcela": u.parcela, "bloco": u.bloco,
                 "rep": u.repeticao, "trat_num": tr.numero, "trat_cod": tr.codigo, "trat_nome": tr.rotulo,
                 "pp": u.principal, "sp": u.sub, "linha": u.linha, "coluna": u.coluna,
                 "largura_m": round(max(xs) - min(xs), 3), "compr_m": round(max(ys) - min(ys), 3),
                 "area_m2": round(pol.area, 3), "cor": cores.get(u.numero, "#FFFFFF")}
        for f, campo in campos_fator.items():
            attrs[campo] = tr.niveis.get(f, "")
        parcelas.feicoes.append((t.geometria_utm(pol), attrs))
        if c.poligono_util:
            pu = Polygon(c.poligono_util)
            util.feicoes.append((t.geometria_utm(pu), {"exp": p.meta.codigo, "codigo": u.codigo,
                                                       "parcela": u.parcela, "trat_cod": tr.codigo,
                                                       "area_m2": round(pu.area, 3)}))
        E, N = t.ponto_utm(c.centro)
        lon, lat = t.ponto_geo(c.centro)
        cent.feicoes.append((Point(E, N), {**{k: attrs[k] for k in ("exp", "codigo", "parcela", "bloco", "rep",
                                                                     "trat_num", "trat_cod", "trat_nome")},
                                           "e_utm": round(E, 3), "n_utm": round(N, 3),
                                           "lat": round(lat, 8), "lon": round(lon, 8)}))
    camadas["parcelas"] = parcelas
    if util.feicoes:
        camadas["area_util"] = util
    camadas["centroides"] = cent
    pq = Camada("piquetes", "Piquetes de locação", "Point")
    for q in piquetes(cr, p.casualizacao, t, incluir_parcelas=piquetes_de_parcela):
        pq.feicoes.append((Point(q.E, q.N), {"id": q.id, "tipo": q.tipo, "x_local": round(q.x, 3),
                                             "y_local": round(q.y, 3), "e_utm": round(q.E, 3), "n_utm": round(q.N, 3),
                                             "lat": round(q.lat, 8), "lon": round(q.lon, 8), "refs": q.referencias}))
    camadas["piquetes"] = pq
    tu = crs.para_utm(t.epsg)

    def utm(g):
        return shapely.transform(g, lambda c: np.column_stack(tu.transform(c[:, 0], c[:, 1])))

    if perimetro_wgs84 is not None:
        g = utm(perimetro_wgs84)
        camadas["perimetro"] = Camada("perimetro", "Área de implantação", "Polygon",
                                      [(g, {"nome": "Área de implantação", "area_ha": round(g.area / 1e4, 4)})])
    if evitar_wgs84:
        camadas["evitar"] = Camada("evitar", "Áreas a evitar", "Polygon",
                                   [(utm(g), {"nome": f"Área a evitar {i}", "area_m2": round(utm(g).area, 1)})
                                    for i, g in enumerate(evitar_wgs84, start=1)])
    return ConjuntoGeo(t.epsg, geo, t, cr, camadas)
