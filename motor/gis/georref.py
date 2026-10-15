"""Georreferenciamento do croqui: do sistema local (metros no terreno) para UTM e coordenadas geográficas.

O croqui é desenhado num plano local: origem no canto inferior esquerdo do contorno, X para a direita e Y para cima
(ver :mod:`motor.geometria.layout`). Para levá-lo ao terreno bastam três números: a posição de um ponto de
referência do croqui (latitude e longitude), o **azimute verdadeiro** do eixo +Y do croqui ("para cima" do desenho)
e, implicitamente, a zona UTM. A rotação de desenho do croqui (``rotacao_graus``) não entra aqui: no mapa, quem orienta
o experimento é o azimute.

Transformação (E, N em UTM; β = azimute de quadrícula do eixo +Y; k = fator de escala; (x₀, y₀) = referência)::

    E = E₀ + k·[(x − x₀)·cos β + (y − y₀)·sin β]
    N = N₀ + k·[−(x − x₀)·sin β + (y − y₀)·cos β]

É uma rotação rígida (o croqui e a grade UTM são sistemas dextrógiros) com escala k, que converte as distâncias do
terreno em distâncias da grade.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace

import numpy as np

from motor.geometria.layout import ConfigLayout, Croqui, gerar_croqui
from motor.gis import crs

REFERENCIAS = {
    "centro": "Centro do experimento",
    "inf_esq": "Canto inferior esquerdo do croqui",
    "inf_dir": "Canto inferior direito do croqui",
    "sup_esq": "Canto superior esquerdo do croqui",
    "sup_dir": "Canto superior direito do croqui",
}

MODOS = {
    "arraste": "Arrastado no mapa",
    "perimetro": "Encaixado no perímetro",
    "pontos": "Pontos de controle (GPS)",
    "manual": "Coordenadas informadas",
}


@dataclass
class Georreferencia:
    lat: float
    lon: float
    azimute: float = 0.0  # azimute verdadeiro do eixo +Y do croqui (graus, horário a partir do Norte)
    referencia: str = "centro"  # ponto do croqui que fica em (lat, lon)
    modo: str = "manual"
    epsg: int = 0  # 0 = UTM SIRGAS 2000 automático
    pontos_controle: list = field(default_factory=list)  # [{"nome", "x", "y", "lat", "lon", "residuo_m"}]
    residuo_rms: float | None = None
    escala_estimada: float | None = None
    folga_m: float | None = None  # encaixe no perímetro: menor distância do experimento à divisa

    def __post_init__(self) -> None:
        if not (-90 <= self.lat <= 90 and -180 <= self.lon <= 180):
            raise ValueError("Coordenada de referência fora dos limites.")
        if not math.isfinite(self.azimute):
            raise ValueError("Azimute inválido.")
        self.azimute = self.azimute % 360.0
        if self.referencia not in REFERENCIAS:
            raise ValueError(f"Referência desconhecida: {self.referencia}")

    @property
    def epsg_efetivo(self) -> int:
        return self.epsg or crs.epsg_utm(self.lon, self.lat)

    def para_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def de_dict(cls, d: dict) -> Georreferencia:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def croqui_local(casualizacao, layout: ConfigLayout) -> Croqui:
    """Croqui no plano local, sem a rotação de desenho (a orientação no terreno vem do azimute)."""
    return gerar_croqui(casualizacao, replace(layout, rotacao_graus=0.0))


def ponto_referencia(referencia: str, W: float, H: float) -> tuple[float, float]:
    return {"centro": (W / 2, H / 2), "inf_esq": (0.0, 0.0), "inf_dir": (W, 0.0), "sup_esq": (0.0, H),
            "sup_dir": (W, H)}[referencia]


class Transformacao:
    """Local (x, y) ↔ UTM (E, N) ↔ geográfico (lon, lat) para um croqui georreferenciado."""

    def __init__(self, geo: Georreferencia, W: float, H: float) -> None:
        self.geo = geo
        self.W, self.H = W, H
        self.epsg = geo.epsg_efetivo
        self.x0, self.y0 = ponto_referencia(geo.referencia, W, H)
        self.E0, self.N0 = crs.para_utm(self.epsg).transform(geo.lon, geo.lat)
        self.k = crs.fator_escala(geo.lon, geo.lat, self.epsg)
        self.convergencia = crs.azimute_norte_quadricula(geo.lon, geo.lat, self.epsg)
        self.beta = math.radians(geo.azimute + self.convergencia)
        self._c, self._s = math.cos(self.beta), math.sin(self.beta)

    # --------------------------------------------------------------- diretas
    def utm(self, x, y):
        dx = np.asarray(x, dtype=float) - self.x0
        dy = np.asarray(y, dtype=float) - self.y0
        E = self.E0 + self.k * (dx * self._c + dy * self._s)
        N = self.N0 + self.k * (-dx * self._s + dy * self._c)
        return E, N

    def geo_(self, x, y):
        E, N = self.utm(x, y)
        return crs.para_geo(self.epsg).transform(E, N)

    def ponto_utm(self, p: tuple[float, float]) -> tuple[float, float]:
        E, N = self.utm(p[0], p[1])
        return float(E), float(N)

    def ponto_geo(self, p: tuple[float, float]) -> tuple[float, float]:
        """(lon, lat)"""
        lon, lat = self.geo_(p[0], p[1])
        return float(lon), float(lat)

    # -------------------------------------------------------------- inversas
    def local_de_utm(self, E, N):
        dE = (np.asarray(E, dtype=float) - self.E0) / self.k
        dN = (np.asarray(N, dtype=float) - self.N0) / self.k
        return self.x0 + dE * self._c - dN * self._s, self.y0 + dE * self._s + dN * self._c

    def local_de_geo(self, lon, lat):
        E, N = crs.para_utm(self.epsg).transform(lon, lat)
        return self.local_de_utm(E, N)

    # ------------------------------------------------------------- shapely
    def geometria_utm(self, geom):
        import shapely

        return shapely.transform(geom, lambda c: np.column_stack(self.utm(c[:, 0], c[:, 1])))

    def geometria_geo(self, geom):
        import shapely

        return shapely.transform(geom, lambda c: np.column_stack(self.geo_(c[:, 0], c[:, 1])))

    @property
    def azimute_eixo_x(self) -> float:
        """Azimute verdadeiro do eixo +X do croqui."""
        return (self.geo.azimute + 90.0) % 360.0


def com_referencia(geo: Georreferencia, nova_ref: str, W: float, H: float) -> Georreferencia:
    """Mesma posição no terreno, descrita por outro ponto de referência do croqui."""
    if nova_ref == geo.referencia:
        return geo
    t = Transformacao(geo, W, H)
    lon, lat = t.ponto_geo(ponto_referencia(nova_ref, W, H))
    return replace(geo, lat=lat, lon=lon, referencia=nova_ref)


def deslocar(geo: Georreferencia, dE: float, dN: float, W: float, H: float) -> Georreferencia:
    """Translada o experimento dE, dN metros no terreno (Leste, Norte verdadeiros)."""
    az = math.degrees(math.atan2(dE, dN)) if (dE or dN) else 0.0
    lon, lat, _ = crs.GEOD.fwd(geo.lon, geo.lat, az, math.hypot(dE, dN))
    return replace(geo, lat=lat, lon=lon)


def reancorar(geo: Georreferencia, antigo: Croqui, novo: Croqui, grupo: int) -> Georreferencia:
    """Ajusta a referência depois de mudar a disposição (ex.: um bloco arrastado), para que o grupo indicado — um que
    não se moveu — continue exatamente no mesmo lugar do terreno.

    Mover um bloco muda o retângulo envolvente do croqui e, com ele, o centro usado como referência; sem esta
    correção, todo o experimento "pularia" no mapa.
    """
    if grupo not in antigo.caixas or grupo not in novo.caixas:
        return geo
    p_ant = antigo.caixas[grupo][0]
    p_nov = novo.caixas[grupo][0]
    t_ant = Transformacao(geo, antigo.largura_total, antigo.altura_total)
    E_alvo, N_alvo = t_ant.ponto_utm(p_ant)
    t_tmp = Transformacao(geo, novo.largura_total, novo.altura_total)
    E_atual, N_atual = t_tmp.ponto_utm(p_nov)
    E_ref = t_tmp.E0 + (E_alvo - E_atual)
    N_ref = t_tmp.N0 + (N_alvo - N_atual)
    lon, lat = crs.para_geo(t_tmp.epsg).transform(E_ref, N_ref)
    return replace(geo, lat=float(lat), lon=float(lon), epsg=geo.epsg or t_tmp.epsg)
