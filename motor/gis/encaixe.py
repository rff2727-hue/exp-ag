"""Encaixe automático do experimento numa área (perímetro), com conferência de folga e de obstáculos.

Procura a posição e a orientação em que o experimento inteiro (incluindo a bordadura externa) cabe na área com a
**maior folga mínima** até a divisa e até as áreas a evitar. A busca é em duas etapas, em UTM:

1. grade grosseira de ângulos (passo de 3°, mais as direções dos lados do retângulo mínimo da área) × posições
   dentro da área; testa primeiro os vértices do experimento (vetorizado) e só depois a inclusão exata;
2. refinamento local em torno das melhores soluções (ângulo ±3° em passos de 0,25°; posição em grade fina).

Com ``azimute_fixo``, só a posição é otimizada (útil para alinhar o experimento às linhas de plantio ou ao
terraceamento). Se o experimento não couber, devolve a posição que deixa a maior fração dentro da área e quanto
falta.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from motor.geometria.layout import Croqui
from motor.gis import crs
from motor.gis.georref import Georreferencia


@dataclass
class ResultadoEncaixe:
    geo: Georreferencia
    cabe: bool
    folga_m: float  # menor distância do experimento à divisa/obstáculos (negativa = invade)
    fracao_dentro: float
    area_experimento_m2: float
    area_disponivel_m2: float
    mensagem: str


def pegada_local(croqui: Croqui) -> Polygon | MultiPolygon:
    """Área ocupada pelo experimento no plano local: o contorno (com bordaduras); com blocos deslocados à mão, a
    união das caixas dos grupos ampliadas pela bordadura externa."""
    cfg = croqui.config
    if not cfg.deslocamentos_blocos:
        return Polygon(croqui.contorno)
    b = max(cfg.bordadura(lado) for lado in ("esquerda", "direita", "topo", "base"))
    caixas = [Polygon(c) for c in croqui.caixas.values()]
    return unary_union([c.buffer(b, join_style="mitre") if b > 0 else c for c in caixas])


def _angulos_do_retangulo_minimo(area: Polygon) -> list[float]:
    """Azimutes de quadrícula dos lados do retângulo mínimo da área (0–180)."""
    r = area.minimum_rotated_rectangle
    c = np.asarray(r.exterior.coords)[:4]
    out = []
    for a, b in zip(c, np.roll(c, -1, axis=0)):
        out.append(math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])) % 180.0)
    return out


def _lado_mais_longo(area: Polygon) -> float:
    c = np.asarray(area.exterior.coords)
    seg = np.diff(c, axis=0)
    i = int(np.argmax(np.hypot(seg[:, 0], seg[:, 1])))
    return math.degrees(math.atan2(seg[i, 0], seg[i, 1])) % 180.0


def _colocar(peg: Polygon | MultiPolygon, ang_q: float, centro: tuple[float, float]):
    """Pegada (centrada na origem local) rotacionada para o azimute de quadrícula ang_q do eixo +Y e transladada."""
    g = affinity.rotate(peg, -ang_q, origin=(0, 0), use_radians=False)
    return affinity.translate(g, centro[0], centro[1])


def _invasao(g, area) -> float:
    """Quanto a geometria avança além da área: maior distância de um ponto de g fora da área até ela (m)."""
    fora = g.difference(area)
    if fora.is_empty:
        return 0.0
    pts = shapely.points(shapely.get_coordinates(fora.segmentize(1.0)))
    return float(shapely.distance(area, pts).max())


def _polir(peg, livre, borda, folga, ang, ctr, girar: bool):
    """Ajuste fino contínuo (Nelder–Mead) da posição e do ângulo, mantendo a pegada dentro da área."""
    from scipy.optimize import minimize

    def custo(v):
        a = v[2] if girar else ang
        g = _colocar(peg, a, (v[0], v[1]))
        if not livre.contains(g):
            return 1e6 + _invasao(g, livre)
        return -borda.distance(g)

    x0 = np.array([ctr[0], ctr[1], ang]) if girar else np.array([ctr[0], ctr[1]])
    try:
        r = minimize(custo, x0, method="Nelder-Mead",
                     options={"xatol": 0.01, "fatol": 0.005, "maxiter": 400, "initial_simplex": None})
    except Exception:  # noqa: BLE001
        return folga, ang, ctr
    if r.fun < -folga:
        a = float(r.x[2]) % 360.0 if girar else ang
        return float(-r.fun), a, (float(r.x[0]), float(r.x[1]))
    return folga, ang, ctr


def encaixar(
    croqui: Croqui,
    area_wgs84: Polygon | MultiPolygon,
    evitar_wgs84: list | None = None,
    azimute_fixo: float | None = None,
    alinhar_lado_longo: bool = False,
    folga_desejada: float = 0.0,
) -> ResultadoEncaixe:
    lon_c, lat_c = area_wgs84.centroid.x, area_wgs84.centroid.y
    epsg = crs.epsg_utm(lon_c, lat_c)
    t = crs.para_utm(epsg)
    area = shapely.transform(area_wgs84, lambda c: np.column_stack(t.transform(c[:, 0], c[:, 1])))
    if not area.is_valid:
        area = area.buffer(0)
    obst = []
    for o in evitar_wgs84 or []:
        g = shapely.transform(o, lambda c: np.column_stack(t.transform(c[:, 0], c[:, 1])))
        obst.append(g if g.is_valid else g.buffer(0))
    livre = area.difference(unary_union(obst)) if obst else area
    if folga_desejada > 0:
        livre_teste = livre.buffer(-folga_desejada)
    else:
        livre_teste = livre
    if livre_teste.is_empty:
        livre_teste = livre
    k = crs.fator_escala(lon_c, lat_c, epsg)
    conv = crs.azimute_norte_quadricula(lon_c, lat_c, epsg)

    W, H = croqui.largura_total, croqui.altura_total
    peg_local = pegada_local(croqui)
    peg = affinity.scale(affinity.translate(peg_local, -W / 2, -H / 2), k, k, origin=(0, 0))
    area_exp = float(peg_local.area)
    shapely.prepare(livre_teste)
    borda = livre.boundary

    if azimute_fixo is not None:
        angulos = [(azimute_fixo + conv) % 360.0]
    elif alinhar_lado_longo:
        a = _lado_mais_longo(area)
        angulos = [a, (a + 90) % 360, (a + 180) % 360, (a + 270) % 360]
    else:
        angulos = sorted({round(a, 4) for a in list(np.arange(0, 360, 3.0))
                          + [x + d for x in _angulos_do_retangulo_minimo(area) for d in (0, 90, 180, 270)]})

    # candidatos a centro: grade dentro da área livre
    minx, miny, maxx, maxy = livre.bounds
    passo = max(math.sqrt(max(livre.area, 1.0)) / 28, 0.5)
    xs = np.arange(minx + passo / 2, maxx, passo)
    ys = np.arange(miny + passo / 2, maxy, passo)
    gx, gy = np.meshgrid(xs, ys)
    pts = np.column_stack([gx.ravel(), gy.ravel()])
    dentro = shapely.contains_xy(livre, pts[:, 0], pts[:, 1])
    pts = pts[dentro]
    if len(pts) == 0:
        rp = livre.representative_point()
        pts = np.array([[rp.x, rp.y]])
    # condição necessária: a distância do centro à divisa deve ser ≥ o raio do maior círculo da pegada em torno do
    # centro (a pegada contém esse disco)
    r_in = float(peg.boundary.distance(shapely.Point(0, 0))) if peg.contains(shapely.Point(0, 0)) else 0.0
    d_borda = shapely.distance(borda, shapely.points(pts))
    candidatos = pts[d_borda >= r_in - 1e-6] if r_in > 0 else pts

    vert = np.asarray(peg.convex_hull.exterior.coords)[:-1]

    def avaliar(ang: float, centros: np.ndarray) -> list[tuple[float, float, tuple[float, float]]]:
        """[(folga, ang, centro)] dos centros em que a pegada cabe."""
        if len(centros) == 0:
            return []
        a = math.radians(ang)
        c, s = math.cos(a), math.sin(a)
        rot = np.column_stack([vert[:, 0] * c + vert[:, 1] * s, -vert[:, 0] * s + vert[:, 1] * c])
        todos = (centros[:, None, :] + rot[None, :, :]).reshape(-1, 2)
        ok_v = shapely.contains_xy(livre_teste, todos[:, 0], todos[:, 1]).reshape(len(centros), -1).all(axis=1)
        out = []
        for ctr in centros[ok_v]:
            g = _colocar(peg, ang, (float(ctr[0]), float(ctr[1])))
            if livre_teste.contains(g):
                out.append((float(borda.distance(g)), ang, (float(ctr[0]), float(ctr[1]))))
        return out

    achados: list[tuple[float, float, tuple[float, float]]] = []
    for ang in angulos:
        achados += avaliar(ang, candidatos)
    if achados:
        achados.sort(key=lambda r: -r[0])
        melhores = achados[:4]
        refinados = list(melhores)
        for _folga0, ang0, ctr0 in melhores:
            angs = [ang0] if (azimute_fixo is not None or alinhar_lado_longo) else \
                [ang0 + d for d in np.arange(-3, 3.01, 0.25)]
            p2 = passo / 4
            off = np.arange(-2 * passo, 2 * passo + 1e-9, p2)
            ox, oy = np.meshgrid(off, off)
            centros = np.column_stack([ctr0[0] + ox.ravel(), ctr0[1] + oy.ravel()])
            for a in angs:
                refinados += avaliar(a % 360.0, centros)
        folga, ang_q, ctr = max(refinados, key=lambda r: r[0])
        folga, ang_q, ctr = _polir(peg, livre_teste, borda, folga, ang_q, ctr,
                                   girar=azimute_fixo is None and not alinhar_lado_longo)
        cabe, fracao = True, 1.0
    else:
        # não cabe: maximiza a fração dentro da área (busca mais grosseira)
        melhor = (-1.0, angulos[0], (float(pts[0][0]), float(pts[0][1])))
        amostra = pts if len(pts) <= 400 else pts[np.linspace(0, len(pts) - 1, 400).astype(int)]
        angs = angulos if len(angulos) <= 40 else angulos[::3]
        for a in angs:
            for ctr in amostra:
                g = _colocar(peg, a, (float(ctr[0]), float(ctr[1])))
                fr = g.intersection(livre).area / g.area
                if fr > melhor[0]:
                    melhor = (fr, a, (float(ctr[0]), float(ctr[1])))
        fracao, ang_q, ctr = melhor
        g = _colocar(peg, ang_q, ctr)
        folga = -_invasao(g, livre)
        cabe = False

    lon, lat = crs.para_geo(epsg).transform(ctr[0], ctr[1])
    conv_c = crs.azimute_norte_quadricula(lon, lat, epsg)
    azimute = azimute_fixo % 360.0 if azimute_fixo is not None else (ang_q - conv_c) % 360.0
    geo = Georreferencia(lat=float(lat), lon=float(lon), azimute=azimute, referencia="centro",
                         modo="perimetro", epsg=epsg, folga_m=round(folga, 3))
    if cabe:
        msg = (f"O experimento cabe na área com folga mínima de {folga:.1f} m até a divisa"
               + (" e as áreas a evitar" if obst else "") + ".")
    else:
        msg = (f"O experimento não cabe inteiro na área: na melhor posição, {100 * fracao:.0f}% dele fica dentro. "
               "Reduza espaços, bordaduras ou dimensões, mude o número de blocos por fileira ou desloque blocos.")
    return ResultadoEncaixe(geo, cabe, folga, fracao, area_exp, float(livre.area), msg)


def conferir(croqui: Croqui, geo: Georreferencia, area_wgs84=None, evitar_wgs84=None) -> dict:
    """Conferência de uma posição qualquer: dentro da área? folga? parcelas sobre áreas a evitar?"""
    from motor.gis.georref import Transformacao

    t = Transformacao(geo, croqui.largura_total, croqui.altura_total)
    peg = t.geometria_utm(pegada_local(croqui))
    tu = crs.para_utm(t.epsg)

    def utm(g):
        return shapely.transform(g, lambda c: np.column_stack(tu.transform(c[:, 0], c[:, 1])))

    out = {"area_experimento_m2": float(pegada_local(croqui).area), "dentro": None, "folga_m": None,
           "fracao_dentro": None, "parcelas_fora": [], "parcelas_em_obstaculo": []}
    if area_wgs84 is not None:
        area = utm(area_wgs84)
        area = area if area.is_valid else area.buffer(0)
        out["dentro"] = bool(area.contains(peg))
        out["fracao_dentro"] = float(peg.intersection(area).area / peg.area) if peg.area else 0.0
        out["folga_m"] = float(area.boundary.distance(peg)) if out["dentro"] else -_invasao(peg, area)
        out["area_disponivel_m2"] = float(area.area)
        for cel in croqui.celulas:
            if not area.contains(t.geometria_utm(Polygon(cel.poligono))):
                out["parcelas_fora"].append(cel.numero)
    if evitar_wgs84:
        obst = unary_union([utm(o) for o in evitar_wgs84])
        for cel in croqui.celulas:
            if t.geometria_utm(Polygon(cel.poligono)).intersects(obst):
                out["parcelas_em_obstaculo"].append(cel.numero)
        if out["folga_m"] is not None and out["dentro"]:
            out["folga_m"] = min(out["folga_m"], float(obst.distance(peg)))
        if not obst.disjoint(peg):
            out["dentro"] = False
    return out


__all__ = ["ResultadoEncaixe", "conferir", "encaixar", "pegada_local", "replace"]
