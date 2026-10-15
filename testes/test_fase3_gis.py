"""Fase 3 — motor GIS: referência UTM, georreferenciamento, encaixe, pontos de controle, locação, leitura e
exportação."""

import io
import json
import math
import zipfile

import numpy as np
import pyogrio
import pytest
import shapely
from shapely import affinity
from shapely.geometry import Polygon
from tests_util import RAIZ_APP

from motor.exportacao.projeto_json import importar_json
from motor.gis import crs, exportar, feicoes, leitura
from motor.gis.controle import PontoControle, ajustar, avaliar_ajuste
from motor.gis.encaixe import conferir, encaixar
from motor.gis.georref import Georreferencia, Transformacao, com_referencia, croqui_local, deslocar
from motor.gis.locacao import diagonais, piquetes, pontos_notaveis, roteiro_trena

LAT, LON = -22.2735, -54.8091   # Dourados (MS)


@pytest.fixture(scope="module")
def plano():
    return importar_json((RAIZ_APP / "exemplos" / "cenario_a_dbc_campo.json").read_bytes())


@pytest.fixture(scope="module")
def croqui(plano):
    return croqui_local(plano.casualizacao, plano.layout)


def _retangulo_geo(W, H, azimute, lat=LAT, lon=LON, margem=0.0):
    """Retângulo (W+2m) × (H+2m) no terreno, com o eixo +Y no azimute verdadeiro dado, centrado em lat/lon."""
    epsg = crs.epsg_utm(lon, lat)
    E0, N0 = crs.para_utm(epsg).transform(lon, lat)
    k = crs.fator_escala(lon, lat, epsg)
    conv = crs.azimute_norte_quadricula(lon, lat, epsg)
    w, h = W + 2 * margem, H + 2 * margem
    r = Polygon([(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)])
    r = affinity.rotate(affinity.scale(r, k, k, origin=(0, 0)), -(azimute + conv), origin=(0, 0))
    r = affinity.translate(r, E0, N0)
    tg = crs.para_geo(epsg)
    return shapely.transform(r, lambda c: np.column_stack(tg.transform(c[:, 0], c[:, 1])))


def _dif_ang(a, b):
    d = (a - b) % 360
    return min(d, 360 - d)


# ------------------------------------------------------------------------------------------- referência
def test_zona_utm_sirgas():
    assert crs.epsg_utm(LON, LAT) == 31981                 # SIRGAS 2000 / UTM 21S
    assert crs.epsg_utm(-47.9, -15.8) == 31983             # Brasília, 23S
    assert crs.epsg_utm(10.0, 50.0) == 32632               # fora do Brasil: WGS 84 / UTM 32N
    assert "SIRGAS 2000" in crs.nome_crs(31981)


@pytest.mark.parametrize("texto", ["-22.2735, -54.8091", "-22,2735 -54,8091", "-22,2735, -54,8091",
                                   "22°16'24.6\"S 54°48'32.76\"W"])
def test_ler_coordenada(texto):
    lat, lon = crs.ler_coordenada(texto)
    assert lat == pytest.approx(LAT, abs=1e-4) and lon == pytest.approx(LON, abs=1e-4)


def test_ler_coordenada_invalida():
    with pytest.raises(ValueError):
        crs.ler_coordenada("100, 200")
    with pytest.raises(ValueError):
        crs.ler_coordenada("")


@pytest.mark.parametrize("lon", [LON, -51.02, -56.98])      # meio e bordas da zona (convergência e escala extremas)
@pytest.mark.parametrize("az", [0.0, 37.5, 251.0])
def test_transformacao_preserva_distancias_e_azimutes(lon, az):
    g = Georreferencia(lat=LAT, lon=lon, azimute=az, referencia="inf_esq")
    t = Transformacao(g, 200, 120)
    a, b, c = t.ponto_geo((0, 0)), t.ponto_geo((0, 150)), t.ponto_geo((150, 0))
    assert crs.distancia(*a, *b) == pytest.approx(150, abs=0.002)        # 2 mm em 150 m
    assert crs.distancia(*a, *c) == pytest.approx(150, abs=0.002)
    assert _dif_ang(crs.azimute_verdadeiro(*a, *b), az) < 1e-4
    assert _dif_ang(crs.azimute_verdadeiro(*a, *c), az + 90) < 1e-4
    x, y = t.local_de_geo(*t.ponto_geo((37.2, 81.9)))
    assert (float(x), float(y)) == pytest.approx((37.2, 81.9), abs=1e-6)


def test_referencia_e_deslocamento():
    g = Georreferencia(lat=LAT, lon=LON, azimute=12)
    g2 = com_referencia(g, "sup_dir", 80, 40)
    t1, t2 = Transformacao(g, 80, 40), Transformacao(g2, 80, 40)
    for p in ((0, 0), (80, 40), (13, 7)):
        assert t1.ponto_utm(p) == pytest.approx(t2.ponto_utm(p), abs=1e-3)   # k e convergência locais
    g3 = deslocar(g, 30, -40, 80, 40)
    assert crs.distancia(g.lon, g.lat, g3.lon, g3.lat) == pytest.approx(50, abs=1e-3)


def test_georreferencia_valida_e_serializa():
    g = Georreferencia(lat=LAT, lon=LON, azimute=-30, modo="arraste")
    assert g.azimute == pytest.approx(330)
    assert Georreferencia.de_dict(g.para_dict()) == g
    with pytest.raises(ValueError):
        Georreferencia(lat=95, lon=0)
    with pytest.raises(ValueError):
        Georreferencia(lat=0, lon=0, referencia="meio")


# ------------------------------------------------------------------------------------------- encaixe
def test_encaixe_encontra_orientacao_e_folga(croqui):
    W, H = croqui.largura_total, croqui.altura_total
    area = _retangulo_geo(W, H, 37.0, margem=2.0)
    r = encaixar(croqui, area)
    assert r.cabe
    assert r.folga_m == pytest.approx(2.0, abs=0.1)
    assert min(_dif_ang(r.geo.azimute, 37.0), _dif_ang(r.geo.azimute, 217.0)) < 0.5
    c = conferir(croqui, r.geo, area)
    assert c["dentro"] and c["parcelas_fora"] == [] and c["fracao_dentro"] == pytest.approx(1)


def test_encaixe_com_azimute_fixo(croqui):
    W, H = croqui.largura_total, croqui.altura_total
    area = _retangulo_geo(W * 3, H * 6, 0.0)
    r = encaixar(croqui, area, azimute_fixo=90.0)
    assert r.cabe and r.geo.azimute == pytest.approx(90.0, abs=1e-6)


def test_encaixe_nao_cabe(croqui):
    W, H = croqui.largura_total, croqui.altura_total
    area = _retangulo_geo(W * 0.7, H * 0.9, 10.0)
    r = encaixar(croqui, area)
    assert not r.cabe and 0 < r.fracao_dentro < 1 and r.folga_m < 0
    assert "não cabe" in r.mensagem


def test_encaixe_evita_obstaculo(croqui):
    W, H = croqui.largura_total, croqui.altura_total
    area = _retangulo_geo(W + 10, 3 * H + 30, 0.0)
    obst = _retangulo_geo(W + 20, H, 0.0)                  # faixa atravessando o meio da área
    r = encaixar(croqui, area, evitar_wgs84=[obst])
    assert r.cabe
    c = conferir(croqui, r.geo, area, [obst])
    assert c["dentro"] and c["parcelas_em_obstaculo"] == []


def test_conferir_aponta_parcelas_fora(croqui):
    W, H = croqui.largura_total, croqui.altura_total
    area = _retangulo_geo(W, H, 0.0)
    g = Georreferencia(lat=LAT, lon=LON, azimute=0.0)
    g = deslocar(g, W / 2, 0, W, H)                         # metade para fora, a leste
    c = conferir(croqui, g, area)
    assert not c["dentro"] and len(c["parcelas_fora"]) > 0 and c["folga_m"] < 0


# ------------------------------------------------------------------------------------------- pontos de controle
def test_pontos_de_controle_recuperam_posicao(croqui, plano):
    W, H = croqui.largura_total, croqui.altura_total
    verdade = Georreferencia(lat=LAT, lon=LON, azimute=123.4)
    t = Transformacao(verdade, W, H)
    nomes = pontos_notaveis(croqui, plano.casualizacao)
    escolhidos = ["Experimento — canto inferior esquerdo", "Experimento — canto superior direito",
                  "Bloco II — canto inferior direito", "Experimento — canto inferior direito"]
    rng = np.random.default_rng(1)
    pts = []
    for n in escolhidos:
        lon, lat = t.ponto_geo(nomes[n])
        dE, dN = rng.normal(0, 0.02, 2)                     # 2 cm (RTK)
        lon2, lat2, _ = crs.GEOD.fwd(lon, lat, math.degrees(math.atan2(dE, dN)), math.hypot(dE, dN))
        pts.append(PontoControle(n, *nomes[n], lat2, lon2))
    g = ajustar(pts, W, H)
    assert g.modo == "pontos"
    assert g.azimute == pytest.approx(123.4, abs=0.05)
    assert crs.distancia(g.lon, g.lat, verdade.lon, verdade.lat) < 0.05
    assert g.residuo_rms < 0.06 and len(g.pontos_controle) == 4
    assert g.escala_estimada == pytest.approx(1, abs=0.002)
    assert avaliar_ajuste(g) == []


def test_pontos_de_controle_erro_grosseiro_e_minimo(croqui):
    W, H = croqui.largura_total, croqui.altura_total
    t = Transformacao(Georreferencia(lat=LAT, lon=LON, azimute=0), W, H)
    pts = [PontoControle("A", 0, 0, *reversed(t.ponto_geo((0, 0)))),
           PontoControle("B", W, 0, *reversed(t.ponto_geo((W, 0)))),
           PontoControle("C", W, H, *reversed(t.ponto_geo((W + 4, H))))]   # C medido 4 m deslocado
    g = ajustar(pts, W, H)
    assert g.residuo_rms > 1 and any("maior resíduo" in a for a in avaliar_ajuste(g))
    with pytest.raises(ValueError):
        ajustar(pts[:1], W, H)


# ------------------------------------------------------------------------------------------- locação
def test_piquetes_sem_repeticao_e_coordenadas(plano, croqui):
    t = Transformacao(Georreferencia(lat=LAT, lon=LON, azimute=15), croqui.largura_total, croqui.altura_total)
    pq = piquetes(croqui, plano.casualizacao, t)
    chaves = {(round(q.x, 3), round(q.y, 3)) for q in pq}
    assert len(chaves) == len(pq)
    assert len({q.id for q in pq}) == len(pq)
    assert sum(q.tipo == "experimento" for q in pq) == 4
    q = pq[0]
    assert (q.E, q.N) == pytest.approx(t.ponto_utm((q.x, q.y)))
    # sem parcelas: só experimento e blocos
    assert len(piquetes(croqui, plano.casualizacao, t, incluir_parcelas=False)) <= 4 + 4 * len(croqui.blocos)


def test_piquetes_parcelas_contiguas():
    from motor.casualizacao.casualizador import casualizar
    from motor.geometria.layout import ConfigLayout, gerar_croqui

    c = casualizar("DIC", 2, 2, 1)
    cr = gerar_croqui(c, ConfigLayout(largura=2, comprimento=2, espaco_x=0, espaco_y=0, colunas_por_bloco=2,
                                      bordadura_lateral=0.2, bordadura_cabeceira=0.2))
    assert len(piquetes(cr, c)) == 9                       # grade 2 × 2 sem espaços: 3 × 3 cantos


def test_diagonais_e_roteiro(croqui):
    d = diagonais(croqui)
    assert d[0]["Diagonal (m)"] == pytest.approx(math.hypot(croqui.largura_total, croqui.altura_total), abs=0.01)
    t = Transformacao(Georreferencia(lat=LAT, lon=LON, azimute=20), croqui.largura_total, croqui.altura_total)
    passos = roteiro_trena(t)
    assert "110,0°" in passos[1] and "20,0°" in passos[2]


# ------------------------------------------------------------------------------------------- exportação
@pytest.fixture(scope="module")
def conjunto(plano):
    area = _retangulo_geo(200, 200, 0)
    return feicoes.montar(plano, Georreferencia(lat=LAT, lon=LON, azimute=20), perimetro_wgs84=area)


def test_camadas_e_atributos(conjunto, plano):
    cj = conjunto
    assert len(cj.camadas["parcelas"].feicoes) == plano.casualizacao.n_unidades
    assert {"perimetro", "experimento", "blocos", "parcelas", "area_util", "centroides", "piquetes"} <= set(cj.camadas)
    _, a = cj.camadas["parcelas"].feicoes[0]
    assert {"codigo", "parcela", "bloco", "rep", "trat_cod", "trat_nome", "area_m2"} <= set(a)
    for g, a in cj.camadas["parcelas"].feicoes:
        assert g.area == pytest.approx(a["area_m2"] * Transformacao(cj.geo, 1, 1).k ** 2, rel=1e-6)


def test_nome_de_campo_shapefile():
    usados = set()
    assert feicoes.nome_campo("Adubação fosfatada", usados) == "adubacao_f"
    assert feicoes.nome_campo("Adubação fosfatada (2)", usados) == "adubacao_1"
    assert feicoes.nome_campo("1º fator", usados).startswith("f_")


def test_exporta_formatos_legiveis(conjunto, tmp_path):
    cj = conjunto
    n = len(cj.camadas["parcelas"].feicoes)
    shp = tmp_path / "exp.zip"
    shp.write_bytes(exportar.shapefile_zip(cj))
    info = pyogrio.read_info(f"/vsizip/{shp}/parcelas.shp")
    assert info["features"] == n and info["crs"] == "EPSG:31981"
    assert all(len(f) <= 10 for f in info["fields"])
    gp = tmp_path / "exp.gpkg"
    gp.write_bytes(exportar.geopackage(cj))
    camadas = {c for c, _ in pyogrio.list_layers(gp)}
    assert {"parcelas", "piquetes", "perimetro"} <= camadas
    gj = json.loads(exportar.geojson(cj))
    assert sum(f["properties"]["camada"] == "parcelas" for f in gj["features"]) == n
    x, y = gj["features"][0]["geometry"]["coordinates"][0][0]
    assert -180 <= x <= 180 and -90 <= y <= 90
    k = tmp_path / "exp.kmz"
    k.write_bytes(exportar.kmz(cj))
    with zipfile.ZipFile(k) as z:
        txt = z.read("doc.kml").decode()
    assert txt.count("<Placemark>") >= n and "<LookAt>" in txt
    gpx = exportar.gpx(cj)
    assert gpx.count("<wpt") == len(cj.camadas["piquetes"].feicoes) + n
    import ezdxf

    d = ezdxf.read(io.StringIO(exportar.dxf(cj).decode()))
    camadas_dxf = {e.dxf.layer for e in d.modelspace()}
    assert {"PARCELAS", "BLOCOS", "ROTULOS", "PIQUETES", "COTAS"} <= camadas_dxf
    csv = exportar.csv_camada(cj, "piquetes").decode("utf-8-sig")
    assert csv.splitlines()[0].startswith("id;tipo;x_local")


def test_ida_e_volta_pelo_shapefile_e_kmz(conjunto):
    cj = conjunto
    originais = [g for g, _ in cj.camada_wgs84("parcelas")]
    lidas = [a for a in leitura.ler(exportar.shapefile_zip(cj), "exp.zip") if a.origem == "camada parcelas"]
    assert len(lidas) == len(originais)
    for a, b in zip(lidas, originais):
        assert a.geometria.symmetric_difference(b).area < 1e-14
    kmz_areas = leitura.ler(exportar.kmz(cj), "exp.kmz")
    assert len(kmz_areas) >= len(originais)


def test_link_google_earth():
    u = exportar.link_google_earth(LON, LAT, 500, 30)
    assert u.startswith("https://earth.google.com/web/@-22.2735000,-54.8091000,") and "500d" in u and "30.0h" in u


# ------------------------------------------------------------------------------------------- leitura
def test_leitura_kml_poligono_linha_e_pontos():
    anel = "-54.80,-22.27,0 -54.79,-22.27,0 -54.79,-22.26,0 -54.80,-22.26,0 -54.80,-22.27,0"
    kml_ = f"""<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
      <Placemark><name>Talhão 1</name><Polygon><outerBoundaryIs><LinearRing><coordinates>{anel}</coordinates>
      </LinearRing></outerBoundaryIs></Polygon></Placemark>
      <Placemark><name>Caminhamento</name><LineString><coordinates>{anel}</coordinates></LineString></Placemark>
    </Document></kml>""".encode()
    areas = leitura.ler(kml_, "a.kml")
    assert [a.nome for a in areas] == ["Talhão 1", "Caminhamento"]
    assert areas[0].area_ha == pytest.approx(areas[1].area_ha) and 100 < areas[0].area_ha < 125
    pts = "".join(f"<Placemark><Point><coordinates>{c}</coordinates></Point></Placemark>"
                  for c in anel.split()[:4])
    areas = leitura.ler(f"<kml><Document>{pts}</Document></kml>".encode(), "pontos.kml")
    assert len(areas) == 1 and "4 pontos" in areas[0].origem


def test_leitura_geojson_projetado():
    t = crs.para_utm(31981)
    E, N = t.transform(LON, LAT)
    gj = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::31981"}},
          "features": [{"type": "Feature", "properties": {"nome": "Área A"},
                        "geometry": {"type": "Polygon", "coordinates": [[[E, N], [E + 100, N], [E + 100, N + 100],
                                                                         [E, N + 100], [E, N]]]}}]}
    a = leitura.ler(json.dumps(gj).encode(), "a.geojson")[0]
    assert a.nome == "Área A" and a.area_ha == pytest.approx(1.0, rel=1e-3)
    assert a.geometria.exterior.coords[0] == pytest.approx((LON, LAT), abs=1e-7)


def test_leitura_csv_pt_br():
    csv = "ponto;latitude;longitude\n1;-22,2700;-54,8000\n2;-22,2700;-54,7990\n3;-22,2690;-54,7990\n4;-22,2690;-54,8000\n"
    a = leitura.ler(csv.encode("latin-1"), "gps.csv")[0]
    assert a.area_ha == pytest.approx(1.14, rel=0.05)


def test_leitura_gpx_trilha(tmp_path):
    seg = "".join(f"<trkpt lat='{la}' lon='{lo}'/>" for lo, la in
                  [(-54.80, -22.27), (-54.79, -22.27), (-54.79, -22.26), (-54.80, -22.26), (-54.80, -22.27)])
    gpx = f"<?xml version='1.0'?><gpx version='1.1' creator='t' xmlns='http://www.topografix.com/GPX/1/1'><trk><name>Volta</name><trkseg>{seg}</trkseg></trk></gpx>"
    areas = leitura.ler(gpx.encode(), "volta.gpx")
    assert len(areas) >= 1 and areas[0].area_ha > 100


def test_leitura_erros():
    with pytest.raises(leitura.ErroLeitura):
        leitura.ler(b"x", "area.shp")
    with pytest.raises(leitura.ErroLeitura):
        leitura.ler(b"x", "area.docx")
    with pytest.raises(leitura.ErroLeitura):
        leitura.ler(b"<kml><Document></Document></kml>", "vazio.kml")
    with pytest.raises(leitura.ErroLeitura):
        leitura.ler(b"a;b\n1;2\n", "sem.csv")


def test_para_kml_ida_e_volta():
    area = _retangulo_geo(100, 50, 30)
    a = leitura.ler(leitura.para_kml(area, "Talhão"), "t.kml")[0]
    assert a.geometria.symmetric_difference(area).area < 1e-10          # 8 casas decimais ≈ 1 mm


def test_reancorar_mantem_bloco_parado(plano):
    from dataclasses import replace as rep

    from motor.gis.georref import reancorar

    antigo = croqui_local(plano.casualizacao, plano.layout)
    lay = rep(plano.layout, deslocamentos_blocos={"3": [0.0, -12.0]})
    novo = croqui_local(plano.casualizacao, lay)
    g = Georreferencia(lat=LAT, lon=LON, azimute=40)
    g2 = reancorar(g, antigo, novo, 1)
    t1 = Transformacao(g, antigo.largura_total, antigo.altura_total)
    t2 = Transformacao(g2, novo.largura_total, novo.altura_total)
    for p1, p2 in zip(antigo.caixas[1], novo.caixas[1]):
        assert t1.ponto_utm(p1) == pytest.approx(t2.ponto_utm(p2), abs=1e-4)
    # o bloco III desceu 12 m no plano do croqui
    a = t1.ponto_utm(antigo.caixas[3][0])
    b = t2.ponto_utm(novo.caixas[3][0])
    assert math.dist(a, b) == pytest.approx(12 * t1.k, abs=1e-4)
