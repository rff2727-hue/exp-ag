"""Locação no campo: piquetes (cantos a marcar), linha de base para trena, diagonais de conferência e pontos notáveis.

Cada piquete tem três descrições equivalentes:

* coordenadas locais (x, y) a partir do canto inferior esquerdo do contorno — para locar com trena e esquadro
  a partir de uma linha de base (eixo X) e de perpendiculares (eixo Y);
* UTM SIRGAS 2000 (E, N) — para estação total ou GPS RTK;
* latitude e longitude — para GPS de navegação e celular.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from motor.dominio import Casualizacao
from motor.exportacao.estilo import romano
from motor.geometria.layout import Croqui
from motor.gis.georref import Transformacao


@dataclass
class Piquete:
    id: str
    x: float
    y: float
    E: float
    N: float
    lat: float
    lon: float
    tipo: str  # "experimento" | "bloco" | "parcela"
    referencias: str  # unidades/blocos que usam o ponto


def _chave(p: tuple[float, float]) -> tuple[float, float]:
    return (round(p[0], 3), round(p[1], 3))


def piquetes(croqui: Croqui, cas: Casualizacao, t: Transformacao | None = None,
             incluir_parcelas: bool = True) -> list[Piquete]:
    """Cantos do experimento, dos blocos e (opcional) das parcelas, sem repetição; numerados em linhas de cima para
    baixo e da esquerda para a direita, como se caminha no campo."""
    codigo = {u.numero: u.codigo or u.parcela for u in cas.unidades}
    pontos: dict[tuple[float, float], dict] = {}

    def add(p, tipo, ref):
        k = _chave(p)
        d = pontos.setdefault(k, {"p": p, "tipos": set(), "refs": []})
        d["tipos"].add(tipo)
        if ref not in d["refs"]:
            d["refs"].append(ref)

    for p in croqui.contorno:
        add(p, "experimento", "Experimento")
    for cb in croqui.blocos:
        for p in cb.poligono:
            add(p, "bloco", f"Bloco {romano(cb.bloco)}")
    if incluir_parcelas:
        for c in croqui.celulas:
            if croqui.config.tipo == "parcelas":
                for p in c.poligono:
                    add(p, "parcela", codigo[c.numero])
            else:
                add(c.centro, "parcela", codigo[c.numero])
    ordem = sorted(pontos.values(), key=lambda d: (-round(d["p"][1], 2), round(d["p"][0], 2)))
    out = []
    largura = max(3, len(str(len(ordem))))
    for i, d in enumerate(ordem, start=1):
        x, y = d["p"]
        E = N = lat = lon = float("nan")
        if t is not None:
            E, N = t.ponto_utm((x, y))
            lon, lat = t.ponto_geo((x, y))
        tipo = "experimento" if "experimento" in d["tipos"] else ("bloco" if "bloco" in d["tipos"] else "parcela")
        out.append(Piquete(f"P{i:0{largura}d}", x, y, E, N, lat, lon, tipo, ", ".join(d["refs"][:6])
                           + (" …" if len(d["refs"]) > 6 else "")))
    return out


def diagonais(croqui: Croqui) -> list[dict]:
    """Diagonais para conferir o esquadro (retângulo perfeito ⇔ diagonais iguais)."""
    out = []
    W, H = croqui.largura_total, croqui.altura_total
    out.append({"Elemento": "Experimento (contorno)", "Lados (m)": f"{W:.2f} × {H:.2f}".replace(".", ","),
                "Diagonal (m)": round(math.hypot(W, H), 2)})
    for cb in croqui.blocos:
        xs = [p[0] for p in cb.poligono]
        ys = [p[1] for p in cb.poligono]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        out.append({"Elemento": f"Bloco {romano(cb.bloco)}", "Lados (m)": f"{w:.2f} × {h:.2f}".replace(".", ","),
                    "Diagonal (m)": round(math.hypot(w, h), 2)})
    if croqui.config.tipo == "parcelas":
        w, h = croqui.config.largura_efetiva, croqui.config.comprimento_efetivo
        out.append({"Elemento": "Parcela", "Lados (m)": f"{w:.2f} × {h:.2f}".replace(".", ","),
                    "Diagonal (m)": round(math.hypot(w, h), 2)})
    return out


def pontos_notaveis(croqui: Croqui, cas: Casualizacao) -> dict[str, tuple[float, float]]:
    """Pontos do croqui que podem servir de controle: cantos e centro do contorno, cantos dos blocos e das unidades."""
    W, H = croqui.largura_total, croqui.altura_total
    out = {
        "Experimento — canto inferior esquerdo": (0.0, 0.0),
        "Experimento — canto inferior direito": (W, 0.0),
        "Experimento — canto superior direito": (W, H),
        "Experimento — canto superior esquerdo": (0.0, H),
        "Experimento — centro": (W / 2, H / 2),
    }
    nomes = ("inferior esquerdo", "inferior direito", "superior direito", "superior esquerdo")
    for cb in croqui.blocos:
        xs = [p[0] for p in cb.poligono]
        ys = [p[1] for p in cb.poligono]
        cantos = ((min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys)))
        for n, p in zip(nomes, cantos):
            out[f"Bloco {romano(cb.bloco)} — canto {n}"] = p
    codigo = {u.numero: u.codigo or u.parcela for u in cas.unidades}
    for c in sorted(croqui.celulas, key=lambda c: c.numero):
        xs = [p[0] for p in c.poligono]
        ys = [p[1] for p in c.poligono]
        if croqui.config.tipo == "parcelas":
            cantos = ((min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys)))
            for n, p in zip(nomes, cantos):
                out[f"{codigo[c.numero]} — canto {n}"] = p
        out[f"{codigo[c.numero]} — centro"] = c.centro
    return out


def _br(v: float, casas: int) -> str:
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def roteiro_trena(t: Transformacao) -> list[str]:
    """Instruções de locação com trena a partir do canto de origem (local 0, 0)."""
    lon, lat = t.ponto_geo((0.0, 0.0))
    E, N = t.ponto_utm((0.0, 0.0))
    ax = t.azimute_eixo_x
    ay = t.geo.azimute
    return [
        f"Crave o piquete de origem no canto inferior esquerdo do croqui: latitude {_br(lat, 7)}, longitude "
        f"{_br(lon, 7)} (UTM E {_br(E, 2)} · N {_br(N, 2)}).",
        f"Linha de base (eixo X): a partir da origem, no azimute verdadeiro {_br(ax, 1)}°. Meça ao longo dela as "
        "distâncias X da tabela de piquetes.",
        f"Perpendiculares (eixo Y): em cada ponto da linha de base, levante a perpendicular (método 3-4-5) no "
        f"azimute verdadeiro {_br(ay, 1)}° e meça as distâncias Y.",
        "Confira o esquadro de cada bloco pelas diagonais: num retângulo correto, as duas diagonais têm o mesmo "
        "comprimento (tabela de diagonais).",
        "Com bússola: azimute magnético = azimute verdadeiro − declinação magnética. No Centro-Oeste a declinação é "
        "oeste (negativa, de cerca de −14° a −20°), ou seja, some esse valor ao azimute verdadeiro; consulte o valor "
        "atual do município.",
    ]
