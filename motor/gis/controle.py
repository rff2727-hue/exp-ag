"""Georreferenciamento por pontos de controle: pontos do croqui medidos no campo com GPS.

Com dois ou mais pares (ponto do croqui ↔ coordenada medida), ajusta por mínimos quadrados a rotação e a translação
rígidas (Procrustes 2D) que levam o croqui à grade UTM, com a escala fixada no fator de escala da projeção (as medidas
do croqui são distâncias no terreno). Devolve os resíduos de cada ponto e o erro médio quadrático, e também a escala
que se obteria deixando-a livre — se ela se afastar de 1, as medidas do croqui não batem com o que foi implantado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from motor.gis import crs
from motor.gis.georref import Georreferencia, Transformacao


@dataclass
class PontoControle:
    nome: str
    x: float  # croqui (m)
    y: float
    lat: float
    lon: float


def ajustar(pontos: list[PontoControle], W: float, H: float, epsg: int = 0) -> Georreferencia:
    if len(pontos) < 2:
        raise ValueError("Informe pelo menos dois pontos de controle (três ou mais permitem conferir o ajuste).")
    lon_m = float(np.mean([p.lon for p in pontos]))
    lat_m = float(np.mean([p.lat for p in pontos]))
    epsg = epsg or crs.epsg_utm(lon_m, lat_m)
    t = crs.para_utm(epsg)
    P = np.array([[p.x, p.y] for p in pontos], dtype=float)
    Q = np.column_stack(t.transform([p.lon for p in pontos], [p.lat for p in pontos]))
    if np.ptp(P, axis=0).max() < 1e-6:
        raise ValueError("Os pontos de controle do croqui coincidem: escolha pontos distintos.")
    k = crs.fator_escala(lon_m, lat_m, epsg)
    pc, qc = P.mean(axis=0), Q.mean(axis=0)
    p0, q0 = (P - pc) * k, Q - qc
    # rotação φ (anti-horária) que melhor leva p0 em q0
    num = float(np.sum(p0[:, 0] * q0[:, 1] - p0[:, 1] * q0[:, 0]))
    den = float(np.sum(p0[:, 0] * q0[:, 0] + p0[:, 1] * q0[:, 1]))
    phi = math.atan2(num, den)
    escala_livre = math.hypot(num, den) / float(np.sum(p0 ** 2)) if np.sum(p0 ** 2) > 0 else 1.0
    beta = -phi                                     # azimute de quadrícula do eixo +Y
    # posição do centro do croqui
    c, s = math.cos(beta), math.sin(beta)
    dx, dy = (W / 2 - pc[0]) * k, (H / 2 - pc[1]) * k
    E = qc[0] + dx * c + dy * s
    N = qc[1] - dx * s + dy * c
    lon, lat = crs.para_geo(epsg).transform(E, N)
    conv = crs.azimute_norte_quadricula(lon, lat, epsg)
    geo = Georreferencia(lat=float(lat), lon=float(lon), azimute=(math.degrees(beta) - conv) % 360.0,
                         referencia="centro", modo="pontos", epsg=epsg)
    tr = Transformacao(geo, W, H)
    E_aj, N_aj = tr.utm(P[:, 0], P[:, 1])
    res = np.hypot(E_aj - Q[:, 0], N_aj - Q[:, 1])
    geo.pontos_controle = [{"nome": p.nome, "x": p.x, "y": p.y, "lat": p.lat, "lon": p.lon,
                            "residuo_m": round(float(r), 3)} for p, r in zip(pontos, res)]
    geo.residuo_rms = round(float(np.sqrt(np.mean(res ** 2))), 3)
    geo.escala_estimada = round(escala_livre, 6)
    return geo


def avaliar_ajuste(geo: Georreferencia, tolerancia_m: float = 0.5) -> list[str]:
    """Avisos sobre a qualidade do ajuste (resíduos e escala)."""
    av = []
    if geo.residuo_rms is not None and geo.residuo_rms > tolerancia_m:
        pior = max(geo.pontos_controle, key=lambda p: p["residuo_m"])
        av.append(f"Erro médio de {geo.residuo_rms:.2f} m, acima de {tolerancia_m:.2f} m. O maior resíduo é o do "
                  f"ponto {pior['nome']} ({pior['residuo_m']:.2f} m): confira se ele corresponde ao ponto do croqui "
                  "indicado e a precisão do GPS (receptores de navegação erram de 3 a 5 m; RTK, centímetros).")
    if geo.escala_estimada is not None and abs(geo.escala_estimada - 1) > 0.01:
        av.append(f"Com escala livre, o ajuste pediria {100 * (geo.escala_estimada - 1):+.1f}% nas distâncias: as "
                  "medidas do croqui podem não corresponder às implantadas.")
    if len(geo.pontos_controle) == 2:
        av.append("Com dois pontos o ajuste é exato e não há como conferir erros; use três ou mais.")
    return av
