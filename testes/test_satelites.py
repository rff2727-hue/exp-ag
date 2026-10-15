"""Testes do módulo Satélites (dados sintéticos; sem internet).

Portados da recomenda-solo v17 (tests/test_sat.py e a parte de satélite de tests/test_v17.py) para garantir que
o módulo se comporta da mesma forma na Exp-Ag."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from motor.sat import clima, fontes, historico, lavoura, relevo, termico
from motor.sat.base import Area, grade_da_area
from motor.sat.diagnostico import reamostrar


def _area(lado=1000.0):
    p = box(500000, 7500000, 500000 + lado, 7500000 + lado)
    from motor.sat.geo import projetar
    return Area("teste", projetar(p, 31982, inverso=True), p, 31982)


def test_nomes_dos_tiles_copernicus():
    h = fontes.tiles_cop_dem((-54.6, -22.4, -54.2, -22.1))
    assert h == ["https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_S23_00_W055_00_DEM/"
                 "Copernicus_DSM_COG_10_S23_00_W055_00_DEM.tif"]
    assert len(fontes.tiles_cop_dem((-54.6, -22.4, -53.8, -21.9))) == 4


def test_lavoura_estabilidade_e_pontos():
    A = _area()
    g = grade_da_area(A, 10.0)
    X, Y = g.malha()
    mancha = ((X - 500250) ** 2 + (Y - 7500700) ** 2) < 150 ** 2
    cenas = []
    rng = np.random.default_rng(0)
    for k in range(36):
        d = date(2023, 7, 15) + timedelta(days=30 * k)
        fase = 0.3 + 0.5 * max(0.0, np.sin(2 * np.pi * (d.timetuple().tm_yday - 280) / 365))
        ndvi = np.full(X.shape, fase) + rng.normal(0, 0.01, X.shape)
        ndvi[mancha] -= 0.2 * fase
        cenas.append(lavoura.Cena(d, {"ndvi": ndvi, "ndre": ndvi * 0.6, "ndmi": ndvi * 0.5, "msavi2": ndvi}))
    L = lavoura.analisar(g, cenas)
    assert len(L.picos) >= 2
    assert L.estab_area["Baixo e estável"] == pytest.approx(np.pi * 0.15 ** 2 * 100, rel=0.35)
    assert len(L.pontos) >= 1 and L.pontos.iloc[0]["Tipo"] == "Baixo vigor persistente"
    lon, lat = L.pontos.iloc[0][["Longitude", "Latitude"]]
    x, y = __import__("pyproj").Transformer.from_crs(4326, 31982, always_xy=True).transform(lon, lat)
    assert abs(x - 500250) < 60 and abs(y - 7500700) < 60
    assert b"<Placemark>" in lavoura.kml_pontos(L.pontos)


def test_relevo_escoa_para_o_lado_baixo():
    A = _area(900)
    g = grade_da_area(A, 30.0, buffer_m=300)
    X, Y = g.malha()
    z = 500 + 0.05 * (X - X.min())                      # sobe para leste → água vai para oeste
    R = relevo.analisar(A, g, z, "teste")
    assert R.estat["amplitude"] > 20
    assert R.decliv_ha["Suave ondulado (3–8%)"] == pytest.approx(A.area_ha, rel=0.05)
    j_max = np.unravel_index(np.argmax(R.acumulacao), R.acumulacao.shape)[1]
    assert j_max == 0                                   # acumulação máxima na borda oeste
    assert len(R.saidas) >= 1


def test_clima_veranicos_e_estacao():
    idx = pd.date_range("1990-01-01", "2020-12-31", freq="D")
    chuva = pd.Series(0.0, index=idx)
    chuva[(idx.month >= 11) | (idx.month <= 2)] = 8.0          # chove todo dia de nov a fev
    for a in range(1990, 2021):                               # veranico de 12 dias em janeiro
        chuva[pd.Timestamp(a, 1, 10):pd.Timestamp(a, 1, 21)] = 0
    df = pd.DataFrame({"chuva": chuva, "tmax": 30.0, "tmin": 18.0})
    C = clima.analisar(df)
    v = C.veranicos.set_index("Mês")
    assert v.loc["Jan", "≥ 10 dias secos (%)"] == pytest.approx(100)
    assert v.loc["Dez", "≥ 10 dias secos (%)"] == pytest.approx(0)
    est = clima.texto_estacao(C)
    assert est["Início"]["mediana"] in ("30/10", "31/10", "01/11")
    assert C.anual["Chuva (mm)"].iloc[0] == pytest.approx((120 - 12) * 8, rel=0.02)


def test_historico_eventos():
    anos = list(range(1985, 2025))
    g = pd.DataFrame({"Vegetação nativa": [100 if a < 2000 else 10 for a in anos],
                      "Pastagem": [0 if a < 2000 else (90 if a < 2010 else 0) for a in anos],
                      "Agricultura": [0 if a < 2010 else 90 for a in anos]}, index=anos, dtype=float)
    ev = dict(historico.eventos(g, pd.DataFrame(index=anos), 100))
    assert "2000" in ev["Abertura provável"]
    assert "2010" in ev["Conversão para lavoura"]


def test_qa_landsat_e_reamostragem():
    qa = np.array([21824, 22280, 23888, 1], float)            # claro, nuvem, sombra/nuvem, sem dado
    assert termico.mascara_qa(qa).tolist() == [True, False, False, False]
    A = _area()
    g1, g2 = grade_da_area(A, 10.0), grade_da_area(A, 30.0)
    X, Y = g1.malha()
    v = reamostrar((X - X.min()) / 10, g1, g2)
    X2, _ = g2.malha()
    ok = np.isfinite(v)
    assert np.allclose(v[ok], ((X2 - X.min()) / 10)[ok], atol=1.0)


def test_historico_anos_em_ordem_mesmo_com_classes_diferentes():
    """No pandas 2.x o from_dict mandava para o fim o ano sem a classe da 1ª coluna (bug visto em campo)."""
    g = grade_da_area(_area(300), 30.0)
    mapas = {}
    for ano in range(1985, 2026):
        m = np.full(g.mascara.shape, 39.0)
        if ano != 2017:
            m[0, :] = 3.0
        mapas[ano] = m
    grupos, classes = historico.composicao(dict(sorted(mapas.items(), key=lambda kv: -kv[0])), g.mascara, 0.09)
    assert list(grupos.index) == list(range(1985, 2026))
    assert list(classes.index) == list(range(1985, 2026))


def test_chirps_em_blocos_de_ate_10_anos():
    blocos = fontes.blocos_de_anos(date(1981, 1, 1), date(2026, 9, 26))
    assert all((b - a).days < 366 * 10 for a, b in blocos)
    assert blocos[0][0] == date(1981, 1, 1) and blocos[-1][1] == date(2026, 9, 26)
    pedidos = []

    def falso(geom, a, b, t):
        pedidos.append((a, b))
        return {pd.Timestamp(d): 1.0 for d in pd.date_range(a, b)}
    s = fontes.chirps_climateserv(-51, -22, date(1981, 1, 1), date(2026, 9, 26), pedir=falso)
    assert len(pedidos) == len(blocos) and s.index.is_unique and len(s) == (date(2026, 9, 26) - date(1981, 1, 1)).days + 1
    assert fontes.chirps_climateserv(-51, -22, date(1981, 1, 1), date(2026, 9, 26), pedir=lambda *a: None) is None


def test_vento_rosa_e_janelas():
    from motor.sat import vento
    idx = pd.date_range("2022-01-01", "2023-12-31 23:00", freq="h")
    h = idx.hour.values
    dia = (h >= 7) & (h <= 17)
    df = pd.DataFrame({"vel": np.where(dia, 14.0, 6.0), "dir": np.full(len(idx), 135.0),
                       "t": np.where(dia, 32.0, 22.0), "ur": np.where(dia, 40.0, 80.0)}, index=idx)
    v = vento.analisar(df)
    assert v.predominante == "SE" and v.predominante_pct == pytest.approx(100)
    assert v.rosa.values.sum() == pytest.approx(100)
    assert v.janela.loc[1, 6] == pytest.approx(100) and v.janela.loc[1, 12] == pytest.approx(0)
    assert "18h" in vento.melhores_horas(v)
    assert set(vento.tabelas(v)) >= {"Vento mensal", "Rosa dos ventos (%)", "Janelas pulverização (%)"}


def test_solo_so_granulometria_e_camada_ponderada():
    from motor.sat import solo
    linhas = []
    for prop, v in (("clay", 40), ("sand", 40), ("silt", 20), ("soc", 99)):
        for k, p in enumerate(["0-5cm", "5-15cm", "15-30cm", "30-60cm"]):
            val = v + (10 * k if prop == "clay" else 0)
            linhas.append({"propriedade": prop, "profundidade": p, "media": val, "q05": val - 5, "q95": val + 5,
                           "ponto": 0})
    S = solo.resumir(pd.DataFrame(linhas), [(0, 0)])
    assert set(S.tabela["propriedade"]) == {"clay", "sand", "silt"}
    # argila 0–30 ponderada: (40·5 + 50·10 + 60·15) / 30
    assert S.camada["clay"][0] == pytest.approx((40 * 5 + 50 * 10 + 60 * 15) / 30)
    assert S.textura.startswith("argilosa")


def test_termico_superficie_suave():
    A = _area(600)
    g = grade_da_area(A, 30.0, buffer_m=90)
    X, Y = g.malha()
    quente = np.exp(-(((X - 500200) ** 2 + (Y - 7500300) ** 2) / (2 * 100 ** 2)))
    cenas = [termico.CenaTermica(date(2024, 1, 1) + timedelta(days=16 * k), 30 + 2 * quente + k * 0.1, 1.0)
             for k in range(5)]
    T = termico.analisar(g, cenas)
    fino, ext, res = termico.superficie(T)
    assert fino.shape == (g.altura * 3, g.largura * 3) and np.isfinite(fino).all()
    rs = termico.resumo_superficie(T, fino, ext, res, A)
    assert 0.5 < rs["amplitude"] < 2.5 and rs["quente_ha"] > 0


# ------------------------------------------------------------ portados de test_v17.py
import io  # noqa: E402
from datetime import datetime  # noqa: E402

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from motor.sat import agua, nisar  # noqa: E402


def test_titulo_e_texto_corrido_cabem():
    from types import SimpleNamespace

    from motor.sat import moldura as bk
    ctx = SimpleNamespace(marca=bk.MARCAS["Exp-Ag"])
    fig = plt.figure(figsize=bk.A4)
    bk.base(fig, ctx, 1)
    nomes = ", ".join(f"Gleba Santo Antônio da Serra {i}" for i in range(1, 12))
    bk.titulo(fig, ctx, "POTÁSSIO · 1ª APLICAÇÃO - " + nomes.upper(), "KCl (60% K₂O)  ·  " + nomes, tam=18)
    bk.texto_corrido(fig, 0.13, 0.12, "; ".join(f"TH {i:02d}: P, K, S, B, Zn, Mn, Cu" for i in range(1, 40)) + ".",
                     larg=0.75, y_min=bk.MOLD_Y0 + 0.018)
    fig.canvas.draw()
    r, inv = fig.canvas.get_renderer(), fig.transFigure.inverted()
    for t in fig.texts:
        (x0, y0), (x1, y1) = inv.transform(t.get_window_extent(r))
        assert 0.07 < x0 and x1 < 0.93, t.get_text()[:30]
        assert y0 > bk.MOLD_Y0 or t.get_text().isdigit(), t.get_text()[:30]         # nada abaixo da moldura
    assert fig._cor_marca == ctx.marca["cor"]                                       # cor da barra de escala
    plt.close(fig)


def test_msavi2_tem_a_legenda_invertida():
    from motor.sat.relatorio import CMAP_INDICE, LEGENDA_INDICE
    baixo, alto = CMAP_INDICE["msavi2"](0.0), CMAP_INDICE["msavi2"](1.0)
    assert baixo[0] > 0.9 and baixo[1] > 0.8 and alto[2] > alto[1]                  # amarelo → roxo
    assert LEGENDA_INDICE["msavi2"].startswith("amarelo")


# ------------------------------------------------------------------ balanço hídrico
def _power(fim, dias=200, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(fim - timedelta(days=dias - 1), fim, freq="D")
    tmax = 31 + rng.normal(0, 1.5, len(idx))
    return pd.DataFrame({"T2M_MAX": tmax, "T2M_MIN": tmax - 11, "RH2M": 65.0, "WS2M": 2.0,
                         "ALLSKY_SFC_SW_DWN": 21.0, "PS": 96.0,
                         "PRECTOTCORR": np.where(rng.random(len(idx)) < 0.25, rng.gamma(1.2, 14, len(idx)), 0.0)},
                        index=idx)


def test_et0_penman_monteith_exemplo_da_fao():
    """FAO-56, exemplo 18 (Bruxelas, 6 de julho): ET0 = 3,9 mm/dia. Aqui a umidade entra como média diária
    (o exemplo usa máxima e mínima), então aceita-se ±0,3."""
    df = pd.DataFrame({"T2M_MAX": [21.5], "T2M_MIN": [12.3], "RH2M": [73.5], "WS2M": [2.078],
                       "ALLSKY_SFC_SW_DWN": [22.07], "PS": [100.1]}, index=pd.to_datetime(["2015-07-06"]))
    e = agua.et0_fao56(df, 50.8, 100)
    assert e["metodo"].iloc[0] == "PM" and abs(e["et0"].iloc[0] - 3.9) < 0.3
    sem_rad = agua.et0_fao56(df.assign(ALLSKY_SFC_SW_DWN=np.nan), 50.8, 100)
    assert sem_rad["metodo"].iloc[0] == "HS" and 2.5 < sem_rad["et0"].iloc[0] < 5.5
    sem_temp = agua.et0_fao56(df.assign(T2M_MAX=np.nan), 50.8, 100)
    assert sem_temp["metodo"].iloc[0] == "" and np.isnan(sem_temp["et0"].iloc[0])


def test_balanco_nao_trata_dado_ausente_como_zero_e_separa_fontes():
    fim = date(2026, 10, 4)
    pw = _power(fim)
    chirps = pw["PRECTOTCORR"].iloc[:-40] * 1.1
    pw.loc[pw.index[-20:-15], ["PRECTOTCORR", "T2M_MAX"]] = np.nan                  # 5 dias sem nada
    a = agua.analisar(pw, chirps, -22.2, 400, agua.ParametrosAgua(), fim)
    r = a.resumo
    assert r["dias"] == 90 and r["dias_chuva"] == 85 and r["dias_et0"] == 85 and r["dias_saldo"] == 85
    assert r["dias_chirps"] == 50 and r["dias_power"] == 35
    assert abs(r["saldo"] - (r["chuva_dias_saldo"] - r["et0_dias_saldo"])) < 1e-6
    assert a.serie["chuva"].isna().sum() == 5 and any("sem dado de chuva" in x for x in a.avisos)
    # sem parâmetros do usuário: nada de armazenamento
    assert a.armazenamento is None and "cultura" in a.motivo_sem_armazenamento and not a.cenario


def test_armazenamento_so_com_parametros_e_cenarios_de_irrigacao():
    fim = date(2026, 10, 4)
    pw = _power(fim)
    incompleto = agua.ParametrosAgua("soja", date(2026, 9, 1), None, 60, None)
    assert agua.analisar(pw, None, -22.2, 400, incompleto, fim).armazenamento is None
    par = agua.ParametrosAgua("soja", date(2026, 9, 1), None, 60, 1.2)
    a = agua.analisar(pw, None, -22.2, 400, par, fim)
    arm = a.armazenamento
    assert a.cad_total == 72 and len(arm) == 90 and arm["arm"].between(0, 72).all()
    assert "SEM irrigação" in a.cenario and "não informada" in a.cenario             # desconhecida ≠ inexistente
    assert (arm["arm_min"] <= arm["arm"] + 1e-9).all() and (arm["arm"] <= arm["arm_max"] + 1e-9).all()
    assert arm["kc"].iloc[0] == agua.KC_SEM_CULTURA and arm["fase"].iloc[-1] == "desenvolvimento"
    seq = agua.analisar(pw, None, -22.2, 400, agua.ParametrosAgua("soja", date(2026, 9, 1), None, 60, 1.2,
                                                                  "sequeiro"), fim)
    assert seq.cenario.startswith("sequeiro") and seq.armazenamento["arm"].equals(arm["arm"])
    irr = agua.analisar(pw, None, -22.2, 400, agua.ParametrosAgua(
        "soja", date(2026, 9, 1), None, 60, 1.2, "irrigado", ((date(2026, 9, 28), 25.0),)), fim)
    assert "irrigações informadas" in irr.cenario
    assert irr.armazenamento["arm"].iloc[-1] >= arm["arm"].iloc[-1]
    assert irr.armazenamento.loc["2026-09-28", "irrigacao"] == 25.0
    # muitos dias sem dado: não apresenta
    pw2 = pw.copy()
    pw2.loc[pw2.index[-30:-15], "PRECTOTCORR"] = np.nan
    falho = agua.analisar(pw2, None, -22.2, 400, par, fim)
    assert falho.armazenamento is None and "sem chuva ou ET" in falho.motivo_sem_armazenamento


def test_balanco_fecha_e_estresse_reduz_consumo():
    idx = pd.date_range("2026-01-01", periods=60, freq="D")
    s = pd.DataFrame({"chuva": 0.0, "et0": 5.0}, index=idx)
    s.loc[idx[30], "chuva"] = 200.0
    r = agua.simular(s, pd.Series(1.0, index=idx), 100.0, 0.5, 0.0)
    assert r["ks"].iloc[5] == 1.0 and r["ks"].iloc[25] < 1.0 and r["arm"].iloc[29] > 0
    assert r["arm"].iloc[30] == 100.0 and r["excedente"].iloc[30] > 50
    # conservação: variação do armazenamento = entradas − consumo − excedente
    assert abs((r["arm"].iloc[-1] - 100.0) - (200.0 - r["eta"].sum() - r["excedente"].sum())) < 1e-6


# ------------------------------------------------------------------ NISAR
def _h5(pol, valor=0.27, invalido=0.0, res=200.0):
    import h5py
    x0, y0, x1, y1 = pol.bounds
    xs = np.arange(np.floor(x0 / res) * res - 5 * res + res / 2, x1 + 5 * res, res)
    ys = np.arange(np.ceil(y1 / res) * res + 5 * res - res / 2, y0 - 5 * res, -res)
    rng = np.random.default_rng(0)
    sm = np.full((len(ys), len(xs)), valor, "f4")
    flag = np.zeros(sm.shape, "u2")
    ruim = rng.random(sm.shape) < invalido
    flag[ruim], sm[ruim] = 6, -9999
    b = io.BytesIO()
    with h5py.File(b, "w") as f:
        g = f.create_group(nisar.GRUPO)
        g.create_dataset("soilMoisture", data=sm).attrs["_FillValue"] = np.float32(-9999)
        g.create_dataset("soilMoistureUncertainty", data=np.full(sm.shape, 0.04, "f4"))
        g.create_dataset("retrievalQualityFlag", data=flag)
        g.create_dataset("surfaceQualityFlag", data=np.zeros(sm.shape, "i2"))
        g.create_dataset("xCoordinates", data=xs)
        g.create_dataset("yCoordinates", data=ys)
    return b.getvalue()


def _area_ll(lado_m=1500):
    from shapely.geometry import box

    from motor.sat.base import Area
    from motor.sat.geo import epsg_utm_sirgas, projetar
    d = lado_m / 111000
    ll = box(-54.80, -22.20, -54.80 + d, -22.20 + d)
    ep = epsg_utm_sirgas(-54.8, -22.2)
    return Area("TH", ll, projetar(ll, ep), ep)


def _granulos(fim, n=4):
    out = []
    for k in range(n):
        d = datetime.combine(fim - timedelta(days=2 + 6 * k), datetime.min.time())
        nome = f"NISAR_L3_PR_SME2_{30 - k:03d}_082_D_100_2005_DHDH_A_{d:%Y%m%dT%H%M%S}_{d:%Y%m%dT%H%M%S}_P05023_N_F_J_001"
        out.append({"nome": nome, "data": d, "url": f"mem://{k}", "chave": f"{30 - k:03d}-082-D",
                    "passagem": nisar._passagem(nome)[1]})
    return out


def test_nisar_usa_mascara_de_qualidade_e_conta_pixels_de_borda():
    from motor.sat.geo import projetar
    A = _area_ll(1500)
    pol = projetar(A.poligono_ll, nisar.EPSG_GRADE)
    fim = date(2026, 10, 4)
    arqs = {"mem://0": _h5(pol, 0.21, 1.0), "mem://1": _h5(pol, 0.25, 0.3), "mem://2": _h5(pol, 0.29),
            "mem://3": _h5(pol, 0.31)}
    n = nisar.obter(A, 90, fim, buscar=lambda *a, **k: _granulos(fim), abrir=lambda g: io.BytesIO(arqs[g["url"]]))
    assert n.situacao == "ok" and len(n.observacoes) == 4 and n.catalogados == 4
    assert not n.observacoes[-1].valida                              # passagem mais recente: tudo mascarado
    u = n.ultima_valida                                              # a válida mais recente é a anterior
    assert abs(u.mediana - 0.25) < 1e-6 and 0 < u.n_validos < u.n_pixels and u.passagem.startswith("trilha 082")
    assert 0 < u.n_inteiros < u.n_pixels and abs(u.incerteza - 0.04) < 1e-6
    assert 40 <= u.n_pixels <= 70                                    # ~225 ha ÷ 4 ha por pixel
    assert np.isnan(u.grade["sm"][~u.grade["valido"]]).all()         # preenchimento nunca vira valor


def test_nisar_indisponivel_informa_sem_observacao_valida():
    A = _area_ll(300)                                                   # talhão de 9 ha
    fim = date(2026, 10, 4)
    assert nisar.obter(A, 90, fim, buscar=lambda *a, **k: []).mensagem.startswith(nisar.SEM_OBS)
    sem_login = nisar.obter(A, 90, fim, buscar=lambda *a, **k: _granulos(fim))
    assert sem_login.situacao == "sem_credencial" and sem_login.catalogados == 4
    assert sem_login.mensagem.startswith(nisar.SEM_OBS) and "login Earthdata" in sem_login.mensagem
    assert sem_login.ultima_valida is None
    from motor.sat.geo import projetar
    pol = projetar(A.poligono_ll, nisar.EPSG_GRADE)
    tudo_ruim = nisar.obter(A, 90, fim, buscar=lambda *a, **k: _granulos(fim, 2),
                            abrir=lambda g: io.BytesIO(_h5(pol, 0.2, 1.0)))
    assert tudo_ruim.situacao == "sem_valido" and tudo_ruim.mensagem.startswith(nisar.SEM_OBS)
    pequeno = nisar.obter(A, 90, fim, buscar=lambda *a, **k: _granulos(fim, 1),
                          abrir=lambda g: io.BytesIO(_h5(pol, 0.2)))
    assert pequeno.situacao == "ok" and any("pixel" in a for a in pequeno.avisos)   # talhão pequeno: aviso


def test_nisar_catalogo_e_leitura_por_faixas():
    js = {"feed": {"entry": [{
        "producer_granule_id": "NISAR_L3_PR_SME2_032_010_D_100_2005_DHDH_A_20260930T215706_20260930T215741_P05023_N_F_J_001",
        "time_start": "2026-09-30T21:57:06.000Z",
        "links": [{"href": "s3://x/a.h5"}, {"href": "https://nisar.asf.earthdatacloud.nasa.gov/a/a_QA_STATS.h5"},
                  {"href": "https://nisar.asf.earthdatacloud.nasa.gov/a/a.h5"}]}]}}
    visto = {}
    g = nisar.buscar_granulos((-55, -23, -54, -22), date(2026, 7, 1), date(2026, 10, 4),
                              pedir=lambda p: visto.update(p) or js)
    assert visto["collection_concept_id"] == nisar.COLECAO and visto["sort_key"] == "-start_date"
    assert g[0]["url"].endswith("/a.h5") and g[0]["chave"] == "032-010-D" and "descendente" in g[0]["passagem"]
    from motor.sat.geo import projetar
    pol = projetar(_area_ll(1500).poligono_ll, nisar.EPSG_GRADE)
    dados = _h5(pol, 0.3)

    class Resp:
        def __init__(self, a, b):
            self.content, self.status_code, self.url = dados[a:b + 1], 206, "https://nisar.asf.exemplo/a.h5"
            self.headers = {"Content-Range": f"bytes {a}-{b}/{len(dados)}"}

        def raise_for_status(self):
            pass

    class Sessao:
        pedidos = 0

        def get(self, url, headers=None, **k):
            a, b = map(int, headers["Range"].split("=")[1].split("-"))
            Sessao.pedidos += 1
            return Resp(a, b)
    f = nisar.ArquivoRemoto("https://nisar.asf.exemplo/a.h5", Sessao(), bloco=64 * 1024)
    o = nisar.extrair(f, pol, g[0])
    assert o.valida and abs(o.mediana - 0.3) < 1e-6 and Sessao.pedidos >= 2 and f.baixado <= len(dados) + 65536


def test_pagina_de_agua_entra_no_relatorio_e_na_planilha():
    from motor.sat import exportar, relatorio
    from motor.sat.diagnostico import MODULOS, Diagnostico
    assert "agua" in MODULOS
    A = _area_ll(1500)
    fim = date(2026, 10, 4)
    D = Diagnostico(A)
    D.agua = agua.analisar(_power(fim), None, -22.2, 400, agua.ParametrosAgua(), fim,
                           nisar.Nisar("sem_granulo", nisar.SEM_OBS + " — teste."))
    pdf = relatorio.montar(D, relatorio.DadosRelatorio(talhao="TH"))
    assert pdf[:4] == b"%PDF"
    t = exportar.tabelas(D)
    assert len(t["Água – balanço diário"]) == 90 and "Água – armazenamento" not in t
    assert nisar.SEM_OBS in t["NISAR – umidade superficial"]["Situação"].iloc[0]


# ------------------------------------------------------------ relatório completo com a marca Exp-Ag
def test_relatorio_completo_exp_ag():
    from pypdf import PdfReader
    from sat_sintetico import diagnostico_completo

    from motor.sat import exportar, relatorio

    D = diagnostico_completo()
    pdf = relatorio.montar(D, relatorio.DadosRelatorio(produtor="Fazenda", propriedade="Área", talhao="Talhão 7",
                                                       municipio="Dourados (MS)", data="15/10/2026"))
    leitor = PdfReader(io.BytesIO(pdf))
    assert len(leitor.pages) == 16                     # capa, sumário e as 14 páginas de todas as frentes
    texto = "".join(p.extract_text() for p in leitor.pages[1:4])
    assert "EXP-AG" in texto and "ATRIA" not in texto.upper()
    assert leitor.metadata["/Author"] == "EXP-AG"
    t = exportar.tabelas(D)
    assert len(t) >= 10
    assert exportar.excel(D)[:2] == b"PK"
