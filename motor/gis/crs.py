"""Sistemas de referência: UTM SIRGAS 2000 (Brasil) com recurso ao UTM WGS 84 fora das zonas cobertas.

Toda a geometria do experimento é calculada em UTM, que é conforme (preserva ângulos) e em metros. Duas grandezas
locais ligam o croqui (medidas no terreno) à grade UTM:

* **convergência meridiana** — ângulo entre o Norte verdadeiro e o Norte da quadrícula UTM; o usuário informa e vê
  azimutes verdadeiros (os do Google Earth e da bússola corrigida da declinação), e o motor os converte;
* **fator de escala** — distância na grade ÷ distância no elipsoide (0,9996 no meridiano central a ~1,001 nas bordas
  da zona). Sem ele, uma parcela de 100 m sairia até 10 cm curta ou longa no GPS.

O fator de elevação (altitude do terreno) é desprezado: a 1.000 m de altitude ele vale 1 − 1,6·10⁻⁴ (1,6 cm em 100 m).
"""

from __future__ import annotations

import functools
import math

from pyproj import CRS, Geod, Proj, Transformer

GEOD = Geod(ellps="WGS84")


def zona_utm(lon: float) -> int:
    return int((lon + 180) // 6) % 60 + 1


@functools.lru_cache(maxsize=64)
def _nome_crs(epsg: int) -> str:
    try:
        return CRS.from_epsg(epsg).name
    except Exception:  # noqa: BLE001
        return ""


def epsg_utm(lon: float, lat: float) -> int:
    """EPSG do UTM SIRGAS 2000 da posição; fora das zonas SIRGAS cadastradas, UTM WGS 84."""
    z = zona_utm(lon)
    h = "S" if lat < 0 else "N"
    sirgas = (31960 + z) if lat < 0 else (31954 + z)
    if f"UTM zone {z}{h}" in _nome_crs(sirgas) and "SIRGAS 2000" in _nome_crs(sirgas):
        return sirgas
    return (32700 if lat < 0 else 32600) + z


def nome_crs(epsg: int) -> str:
    return _nome_crs(epsg) or f"EPSG:{epsg}"


@functools.lru_cache(maxsize=64)
def para_utm(epsg: int) -> Transformer:
    return Transformer.from_crs(4326, epsg, always_xy=True)


@functools.lru_cache(maxsize=64)
def para_geo(epsg: int) -> Transformer:
    return Transformer.from_crs(epsg, 4326, always_xy=True)


def fator_escala(lon: float, lat: float, epsg: int) -> float:
    """Fator de escala pontual da projeção (conforme: igual em todas as direções)."""
    f = Proj(CRS.from_epsg(epsg)).get_factors(lon, lat)
    return float(f.meridional_scale)


def azimute_norte_quadricula(lon: float, lat: float, epsg: int) -> float:
    """Azimute de quadrícula (graus) da direção do Norte verdadeiro no ponto.

    Uma direção de azimute verdadeiro α tem azimute de quadrícula α + este valor. Calculado numericamente (desloca
    100 m para o Norte sobre o elipsoide e mede na grade), sem depender de convenção de sinal.
    """
    lon2, lat2, _ = GEOD.fwd(lon, lat, 0.0, 100.0)
    t = para_utm(epsg)
    e1, n1 = t.transform(lon, lat)
    e2, n2 = t.transform(lon2, lat2)
    return math.degrees(math.atan2(e2 - e1, n2 - n1))


def azimute_verdadeiro(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    az, _, _ = GEOD.inv(lon1, lat1, lon2, lat2)
    return az % 360.0


def distancia(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    return float(GEOD.inv(lon1, lat1, lon2, lat2)[2])


def ler_coordenada(texto: str) -> tuple[float, float]:
    """Lê "lat, lon" em graus decimais (como o Google Maps copia) ou em graus, minutos e segundos.

    Aceita: "-22.2735, -54.8091" · "-22,2735 -54,8091" · "22°16'24.6\"S 54°48'32.8\"W".
    Retorna (lat, lon).
    """
    import re

    t = texto.strip().replace("’", "'").replace("″", '"').replace("′", "'")
    if not t:
        raise ValueError("Informe a coordenada.")
    dms = re.findall(r"(\d+(?:[.,]\d+)?)\s*°\s*(?:(\d+(?:[.,]\d+)?)\s*')?\s*(?:(\d+(?:[.,]\d+)?)\s*\"?)?\s*([NSEWLOnsewlo])",
                     t)
    if len(dms) == 2:
        vals = []
        for g, m, s, h in dms:
            v = float(g.replace(",", ".")) + float((m or "0").replace(",", ".")) / 60 \
                + float((s or "0").replace(",", ".")) / 3600
            if h.upper() in ("S", "W", "O"):
                v = -v
            vals.append((h.upper(), v))
        lat = next((v for h, v in vals if h in ("N", "S")), None)
        lon = next((v for h, v in vals if h in ("E", "W", "L", "O")), None)
        if lat is None or lon is None:
            raise ValueError("Coordenada em graus, minutos e segundos sem hemisférios N/S e L/O.")
    else:
        if t.count(",") == 1 and " " in t.strip() and "." in t:          # "-22.27, -54.80"
            partes = [x for x in t.replace(",", " ").split() if x]
        elif t.count(",") == 1 and "." not in t and " " not in t:        # "-22,27,-54,80"? ambíguo
            raise ValueError("Use ponto como separador decimal ou separe latitude e longitude por espaço.")
        elif t.count(",") >= 2:                                           # "-22,27, -54,80" (vírgula decimal)
            partes = [x.replace(",", ".") for x in re.split(r"[;\s]+|,\s+", t) if x]
        else:
            partes = [x.replace(",", ".") for x in re.split(r"[;\s]+", t.replace(", ", " ")) if x]
        if len(partes) != 2:
            raise ValueError("Informe latitude e longitude separadas por vírgula ou espaço.")
        lat, lon = float(partes[0]), float(partes[1])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Coordenada fora dos limites (latitude ±90°, longitude ±180°).")
    return lat, lon
