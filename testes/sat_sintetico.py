"""Diagnóstico de satélite completo com dados sintéticos (todas as frentes), para testar o relatório sem internet.

As análises são as mesmas do módulo real; só as entradas (cenas, DEM, séries de chuva…) são fabricadas.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from shapely.geometry import Polygon

from motor.sat import agua, clima, historico, lavoura, nisar, relevo, solo, termico, vento
from motor.sat.base import Area, grade_da_area
from motor.sat.diagnostico import Diagnostico, reamostrar
from motor.sat.geo import epsg_utm_sirgas, projetar


def area_irregular() -> Area:
    """Talhão de ~95 ha perto de Dourados (MS), com contorno irregular."""
    lon0, lat0 = -54.86, -22.23
    d = 1 / 111000
    pts = [(0, 0), (1150, -60), (1240, 520), (980, 860), (420, 940), (60, 700), (-40, 300)]
    ll = Polygon([(lon0 + x * d / np.cos(np.radians(lat0)), lat0 + y * d) for x, y in pts])
    ep = epsg_utm_sirgas(lon0, lat0)
    return Area("Talhão 7", ll, projetar(ll, ep), ep)


def diagnostico_completo(fim: date = date(2026, 10, 4)) -> Diagnostico:
    rng = np.random.default_rng(42)
    A = area_irregular()
    D = Diagnostico(A)

    # histórico: cerrado → pastagem (2001) → lavoura (2012)
    g30 = grade_da_area(A, 30.0, buffer_m=60)
    mapas = {}
    for ano in range(1985, 2026):
        cod = 4.0 if ano < 2001 else (15.0 if ano < 2012 else 39.0)
        m = np.full(g30.mascara.shape, cod)
        if 2001 <= ano < 2012:
            m[:4, :] = 4.0
        mapas[ano] = m
    D.historico = historico.montar(A, g30, "MapBiomas Coleção 11 (sintético)", mapas, prodes_ok=False)

    # lavoura: 5 anos de cenas mensais, mancha de baixo vigor persistente e anomalia recente
    g10 = grade_da_area(A, 10.0)
    X, Y = g10.malha()
    cx, cy = np.nanmean(X[g10.mascara]), np.nanmean(Y[g10.mascara])
    mancha = ((X - cx + 250) ** 2 + (Y - cy - 150) ** 2) < 140 ** 2
    gradiente = 0.08 * (X - cx) / 600
    cenas = []
    for k in range(60):
        d = date(2021, 8, 15) + timedelta(days=30.4 * k)
        fase = 0.25 + 0.6 * max(0.0, np.sin(2 * np.pi * (d.timetuple().tm_yday - 280) / 365))
        ndvi = np.clip(fase + gradiente + rng.normal(0, 0.015, X.shape), 0.05, 0.95)
        ndvi[mancha] -= 0.22 * fase
        if k == 59:
            ndvi[(X > cx + 250) & (Y < cy)] -= 0.25
        cenas.append(lavoura.Cena(d, {"ndvi": ndvi, "ndre": ndvi * 0.62, "ndmi": ndvi * 0.55 - 0.05,
                                      "msavi2": ndvi * 0.95}))
    D.lavoura = lavoura.analisar(g10, cenas)

    # relevo: rampa suave para sudoeste com uma ondulação
    gr = grade_da_area(A, 30.0, buffer_m=600)
    Xr, Yr = gr.malha()
    z = 420 + 0.035 * (Xr - Xr.min()) + 0.025 * (Yr - Yr.min()) + 6 * np.sin((Xr - Xr.min()) / 420)
    D.relevo = relevo.analisar(A, gr, z, "Copernicus DEM GLO-30 (sintético)")
    ndvi_medio = np.nanmean(np.stack([c.indices["ndvi"] for c in cenas]), axis=0)
    relevo.aplicar_cobertura(D.relevo, reamostrar(ndvi_medio, g10, gr))

    # clima: 1981 → fim, estação chuvosa out–abr com veranicos aleatórios
    idx = pd.date_range("1981-01-01", fim, freq="D")
    mes = idx.month.values
    p_chuva = np.where((mes >= 10) | (mes <= 4), 0.45, 0.08)
    chuva = np.where(rng.random(len(idx)) < p_chuva, rng.gamma(1.1, 13, len(idx)), 0.0)
    tmax = 31 + 3 * np.cos(2 * np.pi * (idx.dayofyear.values - 20) / 365) + rng.normal(0, 2, len(idx))
    df = pd.DataFrame({"chuva": chuva, "tmax": tmax, "tmin": tmax - 12 + rng.normal(0, 1.5, len(idx))}, index=idx)
    C = clima.analisar(df, "CHIRPS 2.0 (sintético)", "NASA POWER (sintético)")
    ih = pd.date_range(f"{fim.year - 5}-01-01", f"{fim.year - 1}-12-31 23:00", freq="h")
    h = ih.hour.values
    dia = (h >= 8) & (h <= 17)
    dv = pd.DataFrame({"vel": np.clip(np.where(dia, 11, 5) + rng.normal(0, 3, len(ih)), 0, None),
                       "dir": (110 + rng.normal(0, 40, len(ih))) % 360,
                       "t": np.where(dia, 30, 21) + rng.normal(0, 2, len(ih)),
                       "ur": np.where(dia, 52, 82) + rng.normal(0, 6, len(ih))}, index=ih)
    C.vento = vento.analisar(dv, fonte="NASA POWER horário (sintético)")
    D.clima = C

    # solo: três pontos SoilGrids sintéticos
    linhas = []
    for k in range(3):
        for prop, v in (("clay", 52), ("sand", 30), ("silt", 18)):
            for j, p in enumerate(["0-5cm", "5-15cm", "15-30cm", "30-60cm"]):
                val = v + (3 * j if prop == "clay" else -1.5 * j if prop == "sand" else 0) + k
                linhas.append({"propriedade": prop, "profundidade": p, "media": val, "q05": val - 7, "q95": val + 7,
                               "ponto": k})
    D.solo = solo.resumir(pd.DataFrame(linhas), [(-54.855, -22.226), (-54.852, -22.229), (-54.849, -22.224)])

    # temperatura de superfície (Landsat): 12 passagens com área quente recorrente
    gt = grade_da_area(A, 30.0, buffer_m=90)
    Xt, Yt = gt.malha()
    quente = np.exp(-(((Xt - cx - 200) ** 2 + (Yt - cy + 180) ** 2) / (2 * 140 ** 2)))
    ct = [termico.CenaTermica(date(2024, 1, 5) + timedelta(days=30 * k), 29 + 3 * quente + rng.normal(0, .3, Xt.shape),
                              0.95) for k in range(12)]
    D.termico = termico.analisar(gt, ct)

    # água: 200 dias de NASA POWER, CHIRPS e cultura informada (sem NISAR lido)
    ip = pd.date_range(fim - timedelta(days=199), fim, freq="D")
    tx = 31 + rng.normal(0, 1.5, len(ip))
    pw = pd.DataFrame({"T2M_MAX": tx, "T2M_MIN": tx - 11, "RH2M": 62.0, "WS2M": 2.1, "ALLSKY_SFC_SW_DWN": 21.5,
                       "PS": 96.0, "PRECTOTCORR": np.where(rng.random(len(ip)) < 0.22, rng.gamma(1.2, 15, len(ip)), 0.0)},
                      index=ip)
    par = agua.ParametrosAgua("soja", fim - timedelta(days=40), None, 60, 1.3, "sequeiro")
    D.agua = agua.analisar(pw, pw["PRECTOTCORR"].iloc[:-12] * 1.05, -22.23, 420, par, fim,
                           nisar.Nisar("sem_credencial", nisar.SEM_OBS + " — credencial Earthdata não configurada."))
    D.avisos.append("Dados sintéticos para conferência do relatório (sem consulta às bases).")
    return D
