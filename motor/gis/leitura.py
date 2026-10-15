"""Leitura de perímetros e áreas: KML/KMZ, GeoJSON, Shapefile (ZIP), GeoPackage, GPX e CSV de pontos.

Tudo é devolvido em WGS 84 (longitude, latitude). Linhas fechadas — o caminhamento do perímetro com GPS — viram
polígonos; uma sequência de pontos (CSV, GPX de pontos ou pontos num KML) também, na ordem do arquivo.
"""

from __future__ import annotations

import io
import json
import re
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union

EXTENSOES = ["kml", "kmz", "geojson", "json", "zip", "gpkg", "gpx", "csv", "txt"]


@dataclass
class AreaLida:
    nome: str
    geometria: Polygon | MultiPolygon  # WGS 84
    origem: str  # descrição (camada, tipo de feição)
    atributos: dict = field(default_factory=dict)

    @property
    def area_ha(self) -> float:
        from motor.gis import crs

        c = self.geometria.centroid
        t = crs.para_utm(crs.epsg_utm(c.x, c.y))
        g = shapely.transform(self.geometria, lambda xy: np.column_stack(t.transform(xy[:, 0], xy[:, 1])))
        return g.area / 1e4


class ErroLeitura(ValueError):
    pass


def _valido(g):
    if g is None or g.is_empty:
        return None
    if not g.is_valid:
        g = shapely.make_valid(g)
        polys = [p for p in getattr(g, "geoms", [g]) if p.geom_type in ("Polygon", "MultiPolygon")]
        if not polys:
            return None
        g = unary_union(polys)
    return g if g.geom_type in ("Polygon", "MultiPolygon") and g.area > 0 else None


def _de_linha(coords) -> Polygon | None:
    c = [tuple(p[:2]) for p in coords]
    if len(c) >= 3:
        return _valido(Polygon(c))
    return None


def _poligonos_de(g, nome: str, origem: str, attrs: dict) -> list[AreaLida]:
    out = []
    if g is None or g.is_empty:
        return out
    if g.geom_type in ("Polygon", "MultiPolygon"):
        v = _valido(g)
        if v is not None:
            out.append(AreaLida(nome, v, origem, attrs))
    elif g.geom_type in ("LineString", "LinearRing"):
        v = _de_linha(list(g.coords))
        if v is not None:
            out.append(AreaLida(nome, v, origem + " (linha fechada em polígono)", attrs))
    elif g.geom_type in ("MultiLineString",):
        for i, ln in enumerate(g.geoms, start=1):
            out += _poligonos_de(ln, f"{nome} {i}", origem, attrs)
    elif g.geom_type == "GeometryCollection":
        for i, sub in enumerate(g.geoms, start=1):
            out += _poligonos_de(sub, f"{nome} {i}" if len(g.geoms) > 1 else nome, origem, attrs)
    return out


# ------------------------------------------------------------------------------------------------- KML
def _ler_kml(conteudo: bytes, nome_arq: str) -> list[AreaLida]:
    from motor.sat.geo import _coords, _dados_extras, _sem_ns, _txt_kml

    texto = re.sub(r"(\sxmlns(?::\w+)?=)'([^']*)'", r'\1"\2"', _txt_kml(conteudo, nome_arq))
    raiz = _sem_ns(texto)
    out: list[AreaLida] = []
    pontos = []
    for i, pm in enumerate(raiz.iter("Placemark"), start=1):
        nm = (pm.findtext("name") or "").strip() or f"Feição {i}"
        extra = _dados_extras(pm)
        for pg in pm.iter("Polygon"):
            ext = _coords(pg.findtext("outerBoundaryIs/LinearRing/coordinates"))
            furos = [_coords(r.findtext("coordinates")) for r in pg.findall("innerBoundaryIs/LinearRing")]
            if len(ext) >= 3:
                v = _valido(Polygon(ext, [f for f in furos if len(f) >= 3]))
                if v is not None:
                    out.append(AreaLida(nm, v, "polígono", extra))
        for ln in list(pm.iter("LineString")) + list(pm.iter("LinearRing")):
            if ln in [r for pg in pm.iter("Polygon") for r in pg.iter("LinearRing")]:
                continue
            c = _coords(ln.findtext("coordinates"))
            v = _de_linha(c)
            if v is not None:
                out.append(AreaLida(nm, v, "linha fechada em polígono", extra))
        for pt in pm.iter("Point"):
            c = _coords(pt.findtext("coordinates"))
            if c:
                pontos.append(c[0])
    if len(pontos) >= 3 and not out:
        v = _de_linha(pontos)
        if v is not None:
            out.append(AreaLida(Path(nome_arq).stem, v, f"{len(pontos)} pontos ligados na ordem do arquivo"))
    return out


# ------------------------------------------------------------------------------------------------- GeoJSON
def _ler_geojson(conteudo: bytes, nome_arq: str) -> list[AreaLida]:
    try:
        d = json.loads(conteudo.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ErroLeitura(f"{nome_arq}: GeoJSON inválido ({e}).") from e
    epsg = None
    nome_crs = (((d.get("crs") or {}).get("properties") or {}).get("name") or "") if isinstance(d, dict) else ""
    m = re.search(r"EPSG:+(\d+)", nome_crs)
    if m and m.group(1) not in ("4326", "4674"):
        epsg = int(m.group(1))
    feats = d.get("features") if d.get("type") == "FeatureCollection" else (
        [d] if d.get("type") == "Feature" else [{"type": "Feature", "geometry": d, "properties": {}}])
    out = []
    for i, f in enumerate(feats, start=1):
        if not f.get("geometry"):
            continue
        props = f.get("properties") or {}
        nm = str(props.get("name") or props.get("nome") or props.get("Name") or f"Feição {i}")
        out += _poligonos_de(shape(f["geometry"]), nm, "GeoJSON", props)
    if epsg:
        out = _reprojetar(out, epsg)
    return out


def _reprojetar(areas: list[AreaLida], epsg: int | str) -> list[AreaLida]:
    from pyproj import Transformer

    t = Transformer.from_crs(epsg, 4326, always_xy=True)
    for a in areas:
        a.geometria = shapely.transform(a.geometria, lambda c: np.column_stack(t.transform(c[:, 0], c[:, 1])))
    return areas


# ------------------------------------------------------------------------------------------------- OGR (pyogrio)
def _ler_ogr(caminho: str, nome_arq: str, camadas: list[str] | None = None) -> list[AreaLida]:
    import pyogrio
    import pyogrio.raw as raw

    try:
        lista = pyogrio.list_layers(caminho)
    except Exception as e:  # noqa: BLE001
        raise ErroLeitura(f"{nome_arq}: não foi possível abrir ({e}).") from e
    out: list[AreaLida] = []
    pontos_soltos = []
    for nome_camada, _tipo in lista:
        if camadas and nome_camada not in camadas:
            continue
        try:
            meta, _, geoms, valores = raw.read(caminho, layer=nome_camada)
        except Exception:  # noqa: BLE001
            continue
        crs_txt = meta.get("crs")
        nomes_campos = list(meta.get("fields", []))
        parcial = []
        for i, wkb in enumerate(geoms):
            if wkb is None:
                continue
            g = shapely.from_wkb(wkb)
            attrs = {c: (v[i].item() if hasattr(v[i], "item") else v[i]) for c, v in zip(nomes_campos, valores)}
            nm = str(attrs.get("name") or attrs.get("Name") or attrs.get("nome") or attrs.get("NOME")
                     or f"{nome_camada} {i + 1}")
            if g.geom_type == "Point":
                pontos_soltos.append((g.x, g.y, crs_txt))
                continue
            if g.geom_type == "MultiPoint":
                pontos_soltos += [(p.x, p.y, crs_txt) for p in g.geoms]
                continue
            parcial += _poligonos_de(shapely.force_2d(g), nm, f"camada {nome_camada}", attrs)
        if crs_txt and not re.search(r"EPSG:(4326|4674)\b", str(crs_txt)):
            parcial = _reprojetar(parcial, crs_txt)
        out += parcial
    if not out and len(pontos_soltos) >= 3:
        crs_txt = pontos_soltos[0][2]
        v = _de_linha([(x, y) for x, y, _ in pontos_soltos])
        if v is not None:
            a = [AreaLida(Path(nome_arq).stem, v, f"{len(pontos_soltos)} pontos ligados na ordem do arquivo")]
            if crs_txt and not re.search(r"EPSG:(4326|4674)\b", str(crs_txt)):
                a = _reprojetar(a, crs_txt)
            out += a
    return out


def _ler_zip(conteudo: bytes, nome_arq: str) -> list[AreaLida]:
    try:
        z = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile as e:
        raise ErroLeitura(f"{nome_arq}: ZIP inválido.") from e
    nomes = z.namelist()
    shp = [n for n in nomes if n.lower().endswith(".shp") and not n.startswith("__MACOSX")]
    kmls = [n for n in nomes if n.lower().endswith((".kml", ".geojson", ".json", ".gpkg", ".gpx"))]
    if not shp and not kmls:
        raise ErroLeitura(f"{nome_arq}: o ZIP não contém shapefile (.shp), KML, GeoJSON, GeoPackage ou GPX.")
    out: list[AreaLida] = []
    with tempfile.TemporaryDirectory() as d:
        z.extractall(d)
        for s in shp:
            base = Path(d) / s
            if not base.with_suffix(".dbf").exists() and not base.with_suffix(".DBF").exists():
                raise ErroLeitura(f"{s}: faltam os arquivos .dbf/.shx do shapefile dentro do ZIP.")
            out += _ler_ogr(str(base), s)
        for k in kmls:
            out += ler(Path(d, k).read_bytes(), k)
    for a in out:
        minx, miny, maxx, maxy = a.geometria.bounds
        if abs(minx) > 180 or abs(maxx) > 180 or abs(miny) > 90 or abs(maxy) > 90:
            raise ErroLeitura(f"{nome_arq}: coordenadas projetadas sem arquivo .prj — inclua o .prj do shapefile.")
    return out


# ------------------------------------------------------------------------------------------------- CSV
def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower().strip()


def _ler_csv(conteudo: bytes, nome_arq: str) -> list[AreaLida]:
    txt = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            txt = conteudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sep = ";" if txt.count(";") > txt.count(",") / 2 else ","
    df = pd.read_csv(io.StringIO(txt), sep=sep, decimal="," if sep == ";" else ".", dtype=str)
    cols = {_sem_acento(c): c for c in df.columns}
    lat = next((cols[c] for c in ("lat", "latitude", "y_lat", "lat_dd") if c in cols), None)
    lon = next((cols[c] for c in ("lon", "long", "longitude", "lng", "x_lon", "lon_dd") if c in cols), None)
    if lat is None or lon is None:
        wkt = next((cols[c] for c in ("wkt", "geometria", "geometry") if c in cols), None)
        if wkt:
            out = []
            for i, v in enumerate(df[wkt].dropna(), start=1):
                out += _poligonos_de(shapely.from_wkt(v), f"Feição {i}", "WKT", {})
            return out
        raise ErroLeitura(f"{nome_arq}: o CSV precisa das colunas latitude e longitude (ou uma coluna WKT).")

    def num(s):
        return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")

    y, x = num(df[lat]), num(df[lon])
    ok = x.notna() & y.notna()
    pts = list(zip(x[ok], y[ok]))
    if len(pts) < 3:
        raise ErroLeitura(f"{nome_arq}: são necessários pelo menos 3 pontos para formar a área.")
    v = _de_linha(pts)
    if v is None:
        raise ErroLeitura(f"{nome_arq}: os pontos não formam um polígono válido (verifique a ordem).")
    return [AreaLida(Path(nome_arq).stem, v, f"{len(pts)} pontos ligados na ordem do arquivo")]


# ------------------------------------------------------------------------------------------------- entrada
def ler(conteudo: bytes, nome_arq: str) -> list[AreaLida]:
    """Áreas (polígonos) contidas no arquivo, em WGS 84."""
    ext = Path(nome_arq).suffix.lower().lstrip(".")
    if ext in ("kml", "kmz"):
        out = _ler_kml(conteudo, nome_arq)
    elif ext in ("geojson", "json"):
        out = _ler_geojson(conteudo, nome_arq)
    elif ext == "zip":
        out = _ler_zip(conteudo, nome_arq)
    elif ext in ("gpkg", "gpx"):
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / f"entrada.{ext}"
            arq.write_bytes(conteudo)
            camadas = ["tracks", "routes", "waypoints", "track_points"] if ext == "gpx" else None
            out = _ler_ogr(str(arq), nome_arq, camadas)
    elif ext in ("csv", "txt"):
        out = _ler_csv(conteudo, nome_arq)
    elif ext == "shp":
        raise ErroLeitura("Envie o shapefile compactado em ZIP, com os arquivos .shp, .shx, .dbf e .prj.")
    else:
        raise ErroLeitura(f"Formato não suportado: .{ext}. Use KML, KMZ, GeoJSON, Shapefile (ZIP), GeoPackage, "
                          "GPX ou CSV.")
    if not out:
        raise ErroLeitura(f"{nome_arq}: nenhuma área (polígono, linha fechada ou sequência de pontos) encontrada.")
    for a in out:
        minx, miny, maxx, maxy = a.geometria.bounds
        if not (-180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90):
            raise ErroLeitura(f"{nome_arq}: coordenadas fora do intervalo geográfico.")
    return out


def para_kml(area: Polygon | MultiPolygon, nome: str = "Área") -> bytes:
    """KML simples da área (para enviar ao diagnóstico por satélite)."""
    from html import escape

    def anel(r):
        return " ".join(f"{x:.8f},{y:.8f},0" for x, y in np.asarray(r.coords)[:, :2])

    polys = getattr(area, "geoms", [area])
    corpo = "".join(
        "<Polygon><outerBoundaryIs><LinearRing><coordinates>" + anel(p.exterior) + "</coordinates></LinearRing>"
        "</outerBoundaryIs>" + "".join("<innerBoundaryIs><LinearRing><coordinates>" + anel(r)
                                       + "</coordinates></LinearRing></innerBoundaryIs>" for r in p.interiors)
        + "</Polygon>" for p in polys)
    if len(polys) > 1:
        corpo = "<MultiGeometry>" + corpo + "</MultiGeometry>"
    return ("<?xml version='1.0' encoding='UTF-8'?><kml xmlns=\"http://www.opengis.net/kml/2.2\"><Document>"
            f"<Placemark><name>{escape(nome)}</name>{corpo}</Placemark></Document></kml>").encode()
