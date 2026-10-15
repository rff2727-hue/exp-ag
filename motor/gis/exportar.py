"""Exportação das camadas do experimento: KML/KMZ (Google Earth), GeoJSON, Shapefile, GeoPackage, GPX, CSV e DXF.

* Shapefile e GeoPackage: UTM SIRGAS 2000 (padrão de topografia e SIG) ou WGS 84, com o .prj/SRS correto; nomes de
  campo do shapefile com até 10 caracteres e texto em UTF-8 (.cpg).
* KML/KMZ: WGS 84 (exigência do formato), com estilos por tratamento, rótulos, piquetes e enquadramento inicial.
* GeoJSON: WGS 84 (RFC 7946), uma coleção com a camada de cada feição em ``camada``.
* GPX: piquetes e centros das parcelas como pontos de passagem, para GPS de navegação.
* DXF: UTM, em camadas de CAD (parcelas, área útil, blocos, rótulos, piquetes, cotas) — para o topógrafo.
"""

from __future__ import annotations

import io
import json
import math
import tempfile
import zipfile
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import mapping

from motor.exportacao.estilo import OCRE, PETROLEO, cor_texto
from motor.gis import crs
from motor.gis.feicoes import ConjuntoGeo

CAMPOS_PIQUETE = [("tipo", "Tipo"), ("refs", "Pertence a"), ("x_local", "X local (m)"), ("y_local", "Y local (m)"),
                  ("e_utm", "E UTM (m)"), ("n_utm", "N UTM (m)"), ("lat", "Latitude"), ("lon", "Longitude")]
ORDEM = ["perimetro", "evitar", "experimento", "blocos", "parcelas", "area_util", "centroides", "piquetes"]


def _limpo(v):
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if not math.isfinite(float(v)) else float(v)
    return v


# --------------------------------------------------------------------------- GeoJSON
def geojson(cj: ConjuntoGeo, camadas: list[str] | None = None) -> bytes:
    feats = []
    for nome in [c for c in ORDEM if c in cj.camadas and (camadas is None or c in camadas)]:
        for g, a in cj.camada_wgs84(nome):
            g = shapely.set_precision(g, 1e-9)
            feats.append({"type": "Feature", "geometry": mapping(g),
                          "properties": {"camada": nome, **{k: _limpo(v) for k, v in a.items()}}})
    fc = {"type": "FeatureCollection", "name": cj.camadas["experimento"].feicoes[0][1]["exp"], "features": feats}
    return json.dumps(fc, ensure_ascii=False, indent=1).encode("utf-8")


# --------------------------------------------------------------------------- KML
def _kml_cor(hex_: str, alfa: float = 1.0) -> str:
    """#RRGGBB → aabbggrr (KML)."""
    h = hex_.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"{int(round(alfa * 255)):02x}{b}{g}{r}".lower()


def _coords_kml(geom) -> str:
    return " ".join(f"{x:.8f},{y:.8f},0" for x, y in np.asarray(geom.coords)[:, :2])


def _poligono_kml(g) -> str:
    polys = getattr(g, "geoms", [g])
    partes = []
    for p in polys:
        furos = "".join(f"<innerBoundaryIs><LinearRing><coordinates>{_coords_kml(r)}</coordinates></LinearRing>"
                        "</innerBoundaryIs>" for r in p.interiors)
        partes.append(f"<Polygon><tessellate>1</tessellate><outerBoundaryIs><LinearRing><coordinates>"
                      f"{_coords_kml(p.exterior)}</coordinates></LinearRing></outerBoundaryIs>{furos}</Polygon>")
    return partes[0] if len(partes) == 1 else "<MultiGeometry>" + "".join(partes) + "</MultiGeometry>"


def _tabela_html(a: dict, campos: list[tuple[str, str]]) -> str:
    linhas = "".join(f"<tr><td style='color:#5B6166;padding-right:8px'>{escape(r)}</td>"
                     f"<td><b>{escape(str(a[k]))}</b></td></tr>" for k, r in campos if a.get(k) not in (None, ""))
    return f"<![CDATA[<table style='font-family:Roboto,Arial;font-size:12px'>{linhas}</table>]]>"


def _dados(a: dict) -> str:
    return "<ExtendedData>" + "".join(
        f"<Data name=\"{escape(str(k))}\"><value>{escape(str(_limpo(v)) if v is not None else '')}</value></Data>"
        for k, v in a.items()) + "</ExtendedData>"


def kml(cj: ConjuntoGeo, titulo: str = "", com_piquetes: bool = True) -> str:
    exp = cj.camadas["experimento"].feicoes[0][1]
    lon_c, lat_c = cj.centro_geo
    W, H = cj.croqui.largura_total, cj.croqui.altura_total
    alcance = max(W, H) * 2.2 + 60
    estilos = [
        f"<Style id='experimento'><LineStyle><color>{_kml_cor(PETROLEO)}</color><width>3</width></LineStyle>"
        f"<PolyStyle><fill>0</fill></PolyStyle></Style>",
        f"<Style id='bloco'><LineStyle><color>{_kml_cor('#FFFFFF')}</color><width>2</width></LineStyle>"
        f"<PolyStyle><fill>0</fill></PolyStyle></Style>",
        f"<Style id='util'><LineStyle><color>{_kml_cor('#FFFFFF', 0.8)}</color><width>1</width></LineStyle>"
        f"<PolyStyle><fill>0</fill></PolyStyle></Style>",
        f"<Style id='perimetro'><LineStyle><color>{_kml_cor(OCRE)}</color><width>3</width></LineStyle>"
        f"<PolyStyle><fill>0</fill></PolyStyle></Style>",
        f"<Style id='evitar'><LineStyle><color>{_kml_cor('#B23A2E')}</color><width>2</width></LineStyle>"
        f"<PolyStyle><color>{_kml_cor('#B23A2E', 0.35)}</color></PolyStyle></Style>",
        "<Style id='rotulo'><IconStyle><scale>0</scale></IconStyle><LabelStyle><scale>0.8</scale></LabelStyle></Style>",
        f"<Style id='piquete'><IconStyle><color>{_kml_cor(OCRE)}</color><scale>0.5</scale><Icon><href>"
        "http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle>"
        "<LabelStyle><scale>0.6</scale></LabelStyle></Style>",
    ]
    cores_vistas: dict[str, str] = {}
    for _, a in cj.camadas["parcelas"].feicoes:
        cor = a.get("cor", "#FFFFFF")
        if cor not in cores_vistas:
            sid = f"t{len(cores_vistas)}"
            cores_vistas[cor] = sid
            estilos.append(f"<Style id='{sid}'><LineStyle><color>{_kml_cor('#1C1D1F')}</color><width>1</width>"
                           f"</LineStyle><PolyStyle><color>{_kml_cor(cor, 0.62)}</color></PolyStyle></Style>")
    pastas = []

    def pasta(nome, conteudo, aberta=False, visivel=True):
        pastas.append(f"<Folder><name>{escape(nome)}</name><open>{int(aberta)}</open>"
                      f"<visibility>{int(visivel)}</visibility>{''.join(conteudo)}</Folder>")

    if "perimetro" in cj.camadas:
        pasta("Área de implantação", [f"<Placemark><name>{escape(a['nome'])}</name><styleUrl>#perimetro</styleUrl>"
                                      f"{_poligono_kml(g)}</Placemark>" for g, a in cj.camada_wgs84("perimetro")])
    if "evitar" in cj.camadas:
        pasta("Áreas a evitar", [f"<Placemark><name>{escape(a['nome'])}</name><styleUrl>#evitar</styleUrl>"
                                 f"{_poligono_kml(g)}</Placemark>" for g, a in cj.camada_wgs84("evitar")])
    campos_exp = [("titulo", "Título"), ("largura_m", "Largura (m)"), ("compr_m", "Comprimento (m)"),
                  ("area_m2", "Área (m²)"), ("azimute", "Azimute do eixo Y (°)")]
    pasta("Experimento", [f"<Placemark><name>{escape(a['exp'])}</name><styleUrl>#experimento</styleUrl>"
                          f"<description>{_tabela_html(a, campos_exp)}</description>{_poligono_kml(g)}</Placemark>"
                          for g, a in cj.camada_wgs84("experimento")])
    if cj.camadas["blocos"].feicoes:
        pasta(cj.camadas["blocos"].titulo, [f"<Placemark><name>{escape(a['rotulo'])}</name><styleUrl>#bloco</styleUrl>"
                                            f"{_poligono_kml(g)}</Placemark>" for g, a in cj.camada_wgs84("blocos")])
    campos = [("codigo", "Identificador"), ("parcela", "Parcela"), ("bloco", "Bloco"), ("rep", "Repetição"),
              ("trat_cod", "Tratamento"), ("trat_nome", "Descrição"), ("largura_m", "Largura (m)"),
              ("compr_m", "Comprimento (m)"), ("area_m2", "Área (m²)")]
    pasta(cj.camadas["parcelas"].titulo, [
        f"<Placemark><name>{escape(str(a['codigo'] or a['parcela']))}</name>"
        f"<styleUrl>#{cores_vistas[a.get('cor', '#FFFFFF')]}</styleUrl>"
        f"<description>{_tabela_html(a, campos)}</description>{_dados(a)}{_poligono_kml(g)}</Placemark>"
        for g, a in cj.camada_wgs84("parcelas")], aberta=False)
    if "area_util" in cj.camadas:
        pasta("Área útil", [f"<Placemark><name>{escape(str(a['codigo']))}</name><styleUrl>#util</styleUrl>"
                            f"{_poligono_kml(g)}</Placemark>" for g, a in cj.camada_wgs84("area_util")], visivel=False)
    pasta("Rótulos", [f"<Placemark><name>{escape(str(a['parcela']))} · {escape(str(a['trat_cod']))}</name>"
                      f"<styleUrl>#rotulo</styleUrl><Point><coordinates>{g.x:.8f},{g.y:.8f},0</coordinates></Point>"
                      "</Placemark>" for g, a in cj.camada_wgs84("centroides")])
    if com_piquetes:
        pasta("Piquetes de locação", [
            f"<Placemark><name>{escape(a['id'])}</name><styleUrl>#piquete</styleUrl>"
            f"<description>{_tabela_html(a, CAMPOS_PIQUETE)}</description>"
            f"<Point><coordinates>{g.x:.8f},{g.y:.8f},0</coordinates></Point></Placemark>"
            for g, a in cj.camada_wgs84("piquetes")], visivel=False)
    nome = titulo or f"{exp['exp']} — {exp['titulo']}"
    return ("<?xml version='1.0' encoding='UTF-8'?>\n<kml xmlns=\"http://www.opengis.net/kml/2.2\"><Document>"
            f"<name>{escape(nome)}</name><open>1</open>"
            f"<description>Gerado pela plataforma Exp-Ag. Sistema de referência das coordenadas: WGS 84 "
            f"(cálculo em {escape(crs.nome_crs(cj.epsg))}).</description>"
            f"<LookAt><longitude>{lon_c:.8f}</longitude><latitude>{lat_c:.8f}</latitude><altitude>0</altitude>"
            f"<heading>{cj.geo.azimute:.2f}</heading><tilt>0</tilt><range>{alcance:.0f}</range>"
            "<altitudeMode>relativeToGround</altitudeMode></LookAt>"
            + "".join(estilos) + "".join(pastas) + "</Document></kml>")


def kmz(cj: ConjuntoGeo, titulo: str = "") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml(cj, titulo))
    return buf.getvalue()


# --------------------------------------------------------------------------- Shapefile / GeoPackage (pyogrio)
def _tabela(cj: ConjuntoGeo, nome: str, wgs84: bool):
    feats = cj.camada_wgs84(nome) if wgs84 else cj.camadas[nome].feicoes
    geoms = [shapely.force_2d(g) for g, _ in feats]
    df = pd.DataFrame([{k: _limpo(v) for k, v in a.items()} for _, a in feats])
    return geoms, df


def _gravar(caminho: Path, driver: str, camada: str, geoms, df: pd.DataFrame, epsg: int, tipo: str,
            append: bool = False) -> None:
    import pyogrio.raw as raw

    campos, dados = [], []
    for col in df.columns:
        s = df[col]
        if s.isna().all():
            s = s.astype(object).where(s.notna(), "")
            dados.append(s.astype(str).to_numpy())
        elif pd.api.types.is_integer_dtype(s) or (pd.api.types.is_float_dtype(s) and s.dropna().apply(float.is_integer).all()
                                                 and col in ("bloco", "rep", "trat_num", "pp", "sp", "linha", "coluna", "epsg")):
            dados.append(s.fillna(0).astype("int64").to_numpy())
        elif pd.api.types.is_numeric_dtype(s):
            dados.append(s.astype("float64").to_numpy())
        else:
            dados.append(s.fillna("").astype(str).to_numpy())
        campos.append(col)
    tipo_ogr = {"Polygon": "MultiPolygon", "Point": "Point", "LineString": "LineString"}[tipo]
    if tipo_ogr == "MultiPolygon":
        geoms = [g if g.geom_type == "MultiPolygon" else shapely.MultiPolygon([g]) for g in geoms]
    kw = {"layer": camada, "driver": driver, "crs": f"EPSG:{epsg}", "geometry_type": tipo_ogr,
          "encoding": "UTF-8"} if driver == "ESRI Shapefile" else {"layer": camada, "driver": driver,
                                                                  "crs": f"EPSG:{epsg}", "geometry_type": tipo_ogr}
    raw.write(str(caminho), shapely.to_wkb(np.asarray(geoms, dtype=object)), dados, campos, append=append, **kw)


def shapefile_zip(cj: ConjuntoGeo, wgs84: bool = False) -> bytes:
    epsg = 4326 if wgs84 else cj.epsg
    buf = io.BytesIO()
    with tempfile.TemporaryDirectory() as d, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nome in [c for c in ORDEM if c in cj.camadas and cj.camadas[c].feicoes]:
            geoms, df = _tabela(cj, nome, wgs84)
            df.columns = [c[:10] for c in df.columns]
            _gravar(Path(d) / f"{nome}.shp", "ESRI Shapefile", nome, geoms, df, epsg, cj.camadas[nome].tipo)
        for f in sorted(Path(d).iterdir()):
            z.write(f, f.name)
        z.writestr("LEIA-ME.txt", _leiame(cj, epsg, "Shapefile"))
    return buf.getvalue()


def geopackage(cj: ConjuntoGeo, wgs84: bool = False) -> bytes:
    epsg = 4326 if wgs84 else cj.epsg
    with tempfile.TemporaryDirectory() as d:
        arq = Path(d) / "experimento.gpkg"
        primeiro = True
        for nome in [c for c in ORDEM if c in cj.camadas and cj.camadas[c].feicoes]:
            geoms, df = _tabela(cj, nome, wgs84)
            _gravar(arq, "GPKG", nome, geoms, df, epsg, cj.camadas[nome].tipo, append=not primeiro)
            primeiro = False
        return arq.read_bytes()


def _leiame(cj: ConjuntoGeo, epsg: int, formato: str) -> str:
    exp = cj.camadas["experimento"].feicoes[0][1]
    return (f"Experimento {exp['exp']} — {exp['titulo']}\nFormato: {formato}\nSistema de referência: "
            f"{crs.nome_crs(epsg)} (EPSG:{epsg})\nAzimute verdadeiro do eixo Y do croqui: {cj.geo.azimute:.3f}°\n"
            "Camadas: experimento, blocos, parcelas, area_util, centroides, piquetes, perimetro, evitar.\n"
            "Campos das parcelas: exp, codigo, parcela, bloco, rep, trat_num, trat_cod, trat_nome, pp (parcela "
            "principal), sp (subparcela), linha, coluna, largura_m, compr_m, area_m2, cor e um campo por fator.\n"
            "Gerado pela plataforma Exp-Ag.\n")


# --------------------------------------------------------------------------- GPX, CSV
def gpx(cj: ConjuntoGeo, com_parcelas: bool = True) -> str:
    pts = []
    for g, a in cj.camada_wgs84("piquetes"):
        pts.append(f"<wpt lat='{g.y:.8f}' lon='{g.x:.8f}'><name>{escape(a['id'])}</name>"
                   f"<desc>{escape(a['refs'])}</desc><sym>Flag, Blue</sym></wpt>")
    if com_parcelas:
        for g, a in cj.camada_wgs84("centroides"):
            pts.append(f"<wpt lat='{g.y:.8f}' lon='{g.x:.8f}'><name>{escape(str(a['codigo'] or a['parcela']))}</name>"
                       f"<desc>{escape(str(a['trat_cod']))} — {escape(str(a['trat_nome']))}</desc>"
                       "<sym>Pin, Green</sym></wpt>")
    exp = cj.camadas["experimento"].feicoes[0][1]
    return ("<?xml version='1.0' encoding='UTF-8'?>\n<gpx version=\"1.1\" creator=\"Exp-Ag\" "
            "xmlns=\"http://www.topografix.com/GPX/1/1\">"
            f"<metadata><name>{escape(exp['exp'])}</name></metadata>" + "".join(pts) + "</gpx>")


def csv_camada(cj: ConjuntoGeo, nome: str) -> bytes:
    df = pd.DataFrame([a for _, a in cj.camadas[nome].feicoes])
    return df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")


# --------------------------------------------------------------------------- DXF
def dxf(cj: ConjuntoGeo) -> bytes:
    import ezdxf

    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6  # metros
    msp = doc.modelspace()
    cores = {"EXPERIMENTO": 5, "BLOCOS": 8, "PARCELAS": 7, "AREA_UTIL": 9, "ROTULOS": 7, "PIQUETES": 30,
             "PERIMETRO": 30, "EVITAR": 1, "COTAS": 8}
    for n, c in cores.items():
        doc.layers.add(n, color=c)

    def anel(g, camada):
        for p in getattr(g, "geoms", [g]):
            msp.add_lwpolyline(np.asarray(p.exterior.coords)[:, :2].tolist(), close=True,
                               dxfattribs={"layer": camada})

    for nome, camada in (("perimetro", "PERIMETRO"), ("evitar", "EVITAR"), ("experimento", "EXPERIMENTO"),
                         ("blocos", "BLOCOS"), ("parcelas", "PARCELAS"), ("area_util", "AREA_UTIL")):
        if nome in cj.camadas:
            for g, _ in cj.camadas[nome].feicoes:
                anel(g, camada)
    alt = max(0.25, min(cj.croqui.config.largura_efetiva, cj.croqui.config.comprimento_efetivo) * 0.12)
    for g, a in cj.camadas["centroides"].feicoes:
        msp.add_text(f"{a['parcela']} {a['trat_cod']}", height=alt, rotation=-(cj.geo.azimute + cj.transformacao.convergencia),
                     dxfattribs={"layer": "ROTULOS"}).set_placement((g.x, g.y),
                                                                    align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    for g, a in cj.camadas["piquetes"].feicoes:
        msp.add_point((g.x, g.y), dxfattribs={"layer": "PIQUETES"})
        msp.add_text(a["id"], height=alt * 0.6, dxfattribs={"layer": "PIQUETES"}).set_placement(
            (g.x + alt * 0.3, g.y + alt * 0.3))
    t = cj.transformacao
    for ct in cj.croqui.cotas:
        p1, p2 = t.ponto_utm(ct.p1), t.ponto_utm(ct.p2)
        base = t.ponto_utm(ct.q1)
        ang = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))
        try:
            msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=ang, dxfattribs={"layer": "COTAS"},
                               override={"dimtxt": alt * 0.8, "dimasz": alt * 0.5, "dimdec": 2,
                                         "dimdsep": ord(",")}).render()
        except Exception:  # noqa: BLE001
            msp.add_line(p1, p2, dxfattribs={"layer": "COTAS"})
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


# --------------------------------------------------------------------------- Google Earth
def link_google_earth(lon: float, lat: float, alcance_m: float = 400.0, heading: float = 0.0) -> str:
    """Abre o Google Earth na Web voando para o ponto (vista de cima)."""
    alt = 0
    return (f"https://earth.google.com/web/@{lat:.7f},{lon:.7f},{alt}a,{alcance_m:.0f}d,35y,"
            f"{heading % 360:.1f}h,0t,0r")


def link_google_maps(lon: float, lat: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat:.7f},{lon:.7f}"


def cor_rotulo(hex_: str) -> str:
    return cor_texto(hex_)
