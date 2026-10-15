"""Geometria do croqui: posiciona as unidades casualizadas no espaço físico.

Sistema de coordenadas local, em metros: origem no canto inferior esquerdo do retângulo envolvente (incluindo a
bordadura externa), eixo X para a direita e eixo Y para cima. A primeira linha de parcelas fica no topo do
desenho. A rotação é aplicada em torno do centro do retângulo envolvente.

Este módulo traduz *posições lógicas* em células físicas e nunca altera a atribuição de tratamentos:

* convencional — a k-ésima unidade do bloco ocupa a k-ésima célula (linear ou em serpentina);
* parcelas subdivididas — cada parcela principal é um grupo de subparcelas lado a lado; as parcelas principais
  se distribuem no bloco como as parcelas convencionais;
* faixas e quadrado latino — a unidade ocupa a linha e a coluna sorteadas.

Mudar o arranjo físico (colunas, espaçamentos, serpentina, rotação) não exige nova casualização. A posição física
ocupada por cada unidade pode ainda ser trocada depois (rotação de vasos) com :func:`aplicar_posicoes`, sem
alterar a identidade da unidade.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace
from typing import Literal

from motor.dominio import Arranjo, Casualizacao, Delineamento

Ponto = tuple[float, float]


@dataclass
class ConfigLayout:
    tipo: Literal["parcelas", "vasos"] = "parcelas"
    # organização
    colunas_por_bloco: int = 0  # 0 = todas as unidades (ou parcelas principais) do bloco numa única linha
    arranjo_blocos: Literal["horizontal", "vertical"] = "horizontal"
    ordem: Literal["linear", "serpentina"] = "linear"
    rotacao_graus: float = 0.0  # rotação do croqui (sentido anti-horário)
    azimute_norte: float = 0.0  # direção do Norte, em graus a partir do "para cima" do desenho, horário
    # parcelas (m)
    largura: float = 3.0  # dimensão em X (através das linhas de plantio)
    comprimento: float = 5.0  # dimensão em Y (ao longo das linhas de plantio)
    espaco_x: float = 0.5  # entre parcelas vizinhas na mesma linha
    espaco_y: float = 1.0  # entre linhas de parcelas dentro do bloco
    espaco_blocos: float = 2.0  # carreador entre blocos
    espaco_sub: float = 0.0  # entre subparcelas da mesma parcela principal
    bordadura_externa: float = 0.0  # faixa ao redor de todo o experimento
    bordadura_lateral: float = 0.5  # descarte em cada lado da parcela
    bordadura_cabeceira: float = 0.5  # descarte em cada extremidade da parcela
    n_linhas_plantio: int = 0  # >0: largura = n_linhas × espaçamento
    espacamento_linhas: float = 0.0
    linhas_bordadura: int = 1  # linhas de descarte de cada lado (modo por linhas)
    # vasos (m)
    diametro_vaso: float = 0.25
    espaco_vasos: float = 0.10  # distância livre entre bordas de vasos vizinhos
    bancadas: bool = False  # desenhar bancadas (uma por bloco; no DIC, a cada `vasos_por_bancada`)
    vasos_por_bancada: int = 0  # DIC/QL: 0 = uma única bancada
    margem_bancada: float = 0.05  # da borda do vaso à borda da bancada (m)
    # disposição dos blocos (Fase 3)
    blocos_por_fileira: int = 0  # 0 = todos os blocos numa única fileira
    espaco_fileiras_blocos: float = -1.0  # entre fileiras de blocos; < 0 = igual ao carreador entre blocos
    ordem_blocos: Literal["linear", "serpentina"] = "linear"
    deslocamentos_blocos: dict = field(default_factory=dict)  # {"grupo": [dx, dy]} em m, ajuste fino/arraste
    # corredores internos (passagem de máquinas, acesso)
    corredor_a_cada_colunas: int = 0  # 0 = sem corredor; n = um corredor após cada n unidades (ou p. principais)
    largura_corredor_colunas: float = 0.0
    corredor_a_cada_linhas: int = 0
    largura_corredor_linhas: float = 0.0
    # bordadura externa por lado; < 0 = usa `bordadura_externa`
    bordadura_esquerda: float = -1.0
    bordadura_direita: float = -1.0
    bordadura_topo: float = -1.0
    bordadura_base: float = -1.0
    canto_inicial: Literal["sup_esq", "sup_dir", "inf_esq", "inf_dir"] = "sup_esq"  # onde ficam a unidade 1 e o bloco I

    def __post_init__(self) -> None:
        self.validar()

    def validar(self) -> None:
        erros = []
        if self.tipo not in ("parcelas", "vasos"):
            erros.append("Tipo de layout inválido.")
        if self.colunas_por_bloco < 0 or self.vasos_por_bancada < 0 or self.blocos_por_fileira < 0:
            erros.append("Colunas, vasos por bancada e blocos por fileira não podem ser negativos.")
        if self.corredor_a_cada_colunas < 0 or self.corredor_a_cada_linhas < 0:
            erros.append("A frequência dos corredores não pode ser negativa.")
        if self.largura_corredor_colunas < 0 or self.largura_corredor_linhas < 0:
            erros.append("A largura dos corredores não pode ser negativa.")
        if self.canto_inicial not in ("sup_esq", "sup_dir", "inf_esq", "inf_dir"):
            erros.append("Canto inicial inválido.")
        if self.ordem_blocos not in ("linear", "serpentina"):
            erros.append("Ordem dos blocos inválida.")
        for chave, v in (self.deslocamentos_blocos or {}).items():
            if not (isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)
                    and all(math.isfinite(x) for x in v)):
                erros.append(f"Deslocamento do bloco {chave} inválido.")
        for nome in ("espaco_x", "espaco_y", "espaco_blocos", "espaco_sub", "bordadura_externa",
                     "bordadura_lateral", "bordadura_cabeceira", "espaco_vasos", "margem_bancada"):
            if getattr(self, nome) < 0:
                erros.append(f"{nome} não pode ser negativo.")
        if self.tipo == "parcelas":
            if self.usa_linhas:
                if self.espacamento_linhas <= 0:
                    erros.append("Informe o espaçamento entre linhas de plantio.")
                if 2 * self.linhas_bordadura >= self.n_linhas_plantio:
                    erros.append("As linhas de bordadura consomem todas as linhas da parcela.")
            elif self.largura <= 0:
                erros.append("A largura da parcela deve ser positiva.")
            if self.comprimento <= 0:
                erros.append("O comprimento da parcela deve ser positivo.")
            if 2 * self.bordadura_cabeceira >= self.comprimento:
                erros.append("As bordaduras de cabeceira consomem todo o comprimento da parcela.")
            if not self.usa_linhas and 2 * self.bordadura_lateral >= self.largura:
                erros.append("As bordaduras laterais consomem toda a largura da parcela.")
        elif self.diametro_vaso <= 0:
            erros.append("O diâmetro do vaso deve ser positivo.")
        if erros:
            raise ValueError(" ".join(erros))

    @property
    def usa_linhas(self) -> bool:
        return self.tipo == "parcelas" and self.n_linhas_plantio > 0

    @property
    def largura_efetiva(self) -> float:
        if self.tipo == "vasos":
            return self.diametro_vaso
        if self.usa_linhas:
            return self.n_linhas_plantio * self.espacamento_linhas
        return self.largura

    @property
    def comprimento_efetivo(self) -> float:
        return self.diametro_vaso if self.tipo == "vasos" else self.comprimento

    @property
    def descarte_lateral(self) -> float:
        if self.usa_linhas:
            return self.linhas_bordadura * self.espacamento_linhas
        return self.bordadura_lateral

    @property
    def gap_x(self) -> float:
        return self.espaco_vasos if self.tipo == "vasos" else self.espaco_x

    @property
    def gap_y(self) -> float:
        return self.espaco_vasos if self.tipo == "vasos" else self.espaco_y

    @property
    def gap_sub(self) -> float:
        return self.espaco_vasos if self.tipo == "vasos" else self.espaco_sub

    @property
    def espaco_fileiras(self) -> float:
        return self.espaco_blocos if self.espaco_fileiras_blocos < 0 else self.espaco_fileiras_blocos

    def bordadura(self, lado: str) -> float:
        """Bordadura externa de um lado ("esquerda", "direita", "topo", "base")."""
        v = getattr(self, f"bordadura_{lado}")
        return self.bordadura_externa if v < 0 else v

    def deslocamento(self, grupo: int) -> tuple[float, float]:
        v = (self.deslocamentos_blocos or {}).get(str(grupo))
        return (float(v[0]), float(v[1])) if v else (0.0, 0.0)

    def para_dict(self) -> dict:
        d = asdict(self)
        d["deslocamentos_blocos"] = {str(k): [float(v[0]), float(v[1])]
                                     for k, v in (self.deslocamentos_blocos or {}).items()
                                     if abs(v[0]) > 1e-9 or abs(v[1]) > 1e-9}
        return d

    @classmethod
    def de_dict(cls, d: dict) -> ConfigLayout:
        conhecidos = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**conhecidos)


@dataclass
class Celula:
    numero: int  # número da unidade experimental que ocupa a célula
    bloco: int | None
    linha: int  # linha dentro do bloco (0 = topo)
    coluna: int  # coluna dentro do bloco (em unidades; subparcelas contam uma a uma)
    linha_grade: int  # linha na grade global (para planilhas)
    coluna_grade: int
    centro: Ponto
    poligono: list[Ponto]  # contorno da unidade (retângulo ou aproximação do círculo)
    poligono_util: list[Ponto] | None  # área útil (parcelas)
    raio: float | None = None  # vasos
    principal: int | None = None  # parcela principal (subdivididas)
    bancada: int | None = None  # vasos com bancadas
    vaga: int = 0  # posição física (1..N, na ordem inicial); muda só com aplicar_posicoes
    grupo: int = 1  # grupo físico (bloco ou bancada) — a unidade que se move junto no arraste


@dataclass
class ContornoBloco:
    bloco: int
    poligono: list[Ponto]
    rotulo_em: Ponto


@dataclass
class Rotulo:
    texto: str
    ponto: Ponto
    tipo: str = "eixo"  # "eixo" (linha/coluna, faixas) | "bancada"


@dataclass
class Cota:
    """Linha de cota: mede de `p1` a `p2`; a linha é desenhada entre `q1` e `q2` (deslocada do objeto)."""
    p1: Ponto
    p2: Ponto
    q1: Ponto
    q2: Ponto
    valor: float
    texto: str
    nivel: str = "detalhe"  # "geral" (dimensões externas) | "detalhe"


@dataclass
class Croqui:
    config: ConfigLayout
    celulas: list[Celula]
    blocos: list[ContornoBloco]
    contorno: list[Ponto]  # retângulo envolvente (com bordadura externa)
    largura_total: float  # dimensões antes da rotação
    altura_total: float
    metricas: dict = field(default_factory=dict)
    principais: list[list[Ponto]] = field(default_factory=list)  # contornos das parcelas principais
    bancadas: list[ContornoBloco] = field(default_factory=list)  # contornos das bancadas (vasos)
    rotulos: list[Rotulo] = field(default_factory=list)
    caixas: dict[int, list[Ponto]] = field(default_factory=dict)  # grupo -> retângulo ocupado (arraste, encaixe)
    cotas: list[Cota] = field(default_factory=list)
    conflitos: list[tuple[int, int]] = field(default_factory=list)  # grupos que se sobrepõem

    def limites(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.contorno]
        ys = [p[1] for p in self.contorno]
        return min(xs), min(ys), max(xs), max(ys)


@dataclass
class _Local:
    """Célula no sistema do grupo: x0 a partir da esquerda, y0 a partir do topo (para baixo)."""
    unidade: object
    x0: float
    y0: float
    linha: int
    coluna: int
    principal: int | None = None


def _ordem_serpentina(k: int, cols: int, serpentina: bool) -> tuple[int, int]:
    lin, col = divmod(k, cols)
    if serpentina and lin % 2 == 1:
        col = cols - 1 - col
    return lin, col


def _extra(i: int, a_cada: int, largura: float) -> float:
    """Espaço acumulado pelos corredores internos antes do item i (0-based)."""
    return (i // a_cada) * largura if (a_cada > 0 and largura > 0) else 0.0


def _px(cfg: ConfigLayout, col: int, passo: float) -> float:
    return col * passo + _extra(col, cfg.corredor_a_cada_colunas, cfg.largura_corredor_colunas)


def _py(cfg: ConfigLayout, lin: int, passo: float) -> float:
    return lin * passo + _extra(lin, cfg.corredor_a_cada_linhas, cfg.largura_corredor_linhas)


def _local_convencional(us, cfg: ConfigLayout, cols: int) -> list[_Local]:
    w, h, gx, gy = cfg.largura_efetiva, cfg.comprimento_efetivo, cfg.gap_x, cfg.gap_y
    out = []
    for k, u in enumerate(sorted(us, key=lambda u: u.posicao)):
        lin, col = _ordem_serpentina(k, cols, cfg.ordem == "serpentina")
        out.append(_Local(u, _px(cfg, col, w + gx), _py(cfg, lin, h + gy), lin, col))
    return out


def _local_subdividida(us, cfg: ConfigLayout, cols: int, b: int) -> list[_Local]:
    w, h, gx, gy, gs = cfg.largura_efetiva, cfg.comprimento_efetivo, cfg.gap_x, cfg.gap_y, cfg.gap_sub
    larg_pp = b * w + (b - 1) * gs
    principais = sorted({u.principal for u in us})
    out = []
    for k, pp in enumerate(principais):
        lin, col = _ordem_serpentina(k, cols, cfg.ordem == "serpentina")
        x_pp = _px(cfg, col, larg_pp + gx)
        for u in sorted((u for u in us if u.principal == pp), key=lambda u: u.sub):
            out.append(_Local(u, x_pp + (u.sub - 1) * (w + gs), _py(cfg, lin, h + gy), lin, col * b + u.sub - 1,
                              pp))
    return out


def _local_grade(us, cfg: ConfigLayout) -> list[_Local]:
    w, h, gx, gy = cfg.largura_efetiva, cfg.comprimento_efetivo, cfg.gap_x, cfg.gap_y
    return [_Local(u, _px(cfg, u.coluna - 1, w + gx), _py(cfg, u.linha - 1, h + gy), u.linha - 1, u.coluna - 1)
            for u in us]


def _grupos(cas: Casualizacao, cfg: ConfigLayout) -> list[tuple[int | None, int | None, list]]:
    """(bloco, bancada, unidades) em ordem de desenho."""
    us = sorted(cas.unidades, key=lambda u: ((u.bloco or 0), u.posicao))
    blocos = sorted({u.bloco for u in us}, key=lambda b: b or 0)
    if blocos != [None]:
        return [(b, b if (cfg.tipo == "vasos" and cfg.bancadas) else None, [u for u in us if u.bloco == b])
                for b in blocos]
    sem_grade = cas.arranjo is not Arranjo.FAIXAS and cas.delineamento is not Delineamento.QL
    if cfg.tipo == "vasos" and cfg.bancadas and cfg.vasos_por_bancada and sem_grade:
        n = cfg.vasos_por_bancada
        if cas.arranjo is Arranjo.SUBDIVIDIDA:            # nunca separa uma parcela principal entre bancadas
            n = max(cas.niveis_b, n - n % cas.niveis_b)
        return [(None, i // n + 1, us[i:i + n]) for i in range(0, len(us), n)]
    return [(None, 1 if (cfg.tipo == "vasos" and cfg.bancadas) else None, us)]


def _posicoes_grupos(ng: int, cfg: ConfigLayout, bw: float, bh: float) -> list[tuple[float, float]]:
    """Canto superior esquerdo de cada caixa de grupo (y para cima; a primeira caixa em (0, 0))."""
    por_fil = cfg.blocos_por_fileira if 0 < cfg.blocos_por_fileira < ng else ng
    eb, ef = cfg.espaco_blocos, cfg.espaco_fileiras
    out = []
    for ig in range(ng):
        f, j = divmod(ig, por_fil)
        if cfg.ordem_blocos == "serpentina" and f % 2 == 1:
            j = por_fil - 1 - j
        if cfg.arranjo_blocos == "horizontal":
            out.append((j * (bw + eb), -f * (bh + ef)))
        else:
            out.append((f * (bw + ef), -j * (bh + eb)))
    return out


def gerar_croqui(casualizacao: Casualizacao, config: ConfigLayout) -> Croqui:
    config.validar()
    cas, cfg = casualizacao, config
    grupos = _grupos(cas, cfg)
    w, h = cfg.largura_efetiva, cfg.comprimento_efetivo
    grade = cas.arranjo is Arranjo.FAIXAS or cas.delineamento is Delineamento.QL
    if cas.arranjo is Arranjo.SUBDIVIDIDA:
        n_itens = max(len({u.principal for u in g}) for _, _, g in grupos)
    else:
        n_itens = max(len(g) for _, _, g in grupos)
    cols = min(cfg.colunas_por_bloco or n_itens, n_itens)

    locais: list[list[_Local]] = []
    for _, _, us in grupos:
        if grade:
            locais.append(_local_grade(us, cfg))
        elif cas.arranjo is Arranjo.SUBDIVIDIDA:
            locais.append(_local_subdividida(us, cfg, cols, cas.niveis_b))
        else:
            locais.append(_local_convencional(us, cfg, cols))
    dims = [(max(c.x0 for c in loc) + w, max(c.y0 for c in loc) + h) for loc in locais]
    larg_g = max(d[0] for d in dims)
    alt_g = max(d[1] for d in dims)
    n_lin_g = max(max(c.linha for c in loc) for loc in locais) + 1
    n_col_g = max(max(c.coluna for c in loc) for loc in locais) + 1

    ng = len(grupos)
    horizontal = cfg.arranjo_blocos == "horizontal"
    margem_banc = (cfg.margem_bancada if (cfg.tipo == "vasos" and cfg.bancadas) else 0.0)
    rot_eixos = grade
    folga_esq = (0.9 * max(w, h) if rot_eixos else 0.0)       # espaço para os rótulos de linha
    folga_topo = (0.6 * h if rot_eixos else 0.0)              # espaço para os rótulos de coluna
    bw = larg_g + 2 * margem_banc + folga_esq                 # caixa de cada grupo (inclui a folga dos rótulos)
    bh = alt_g + 2 * margem_banc + folga_topo
    posicoes = _posicoes_grupos(ng, cfg, bw, bh)
    desloc = [cfg.deslocamento(ig + 1) for ig in range(ng)]
    caixas_brutas = [(px + dx, py + dy - bh, px + dx + bw, py + dy)
                     for (px, py), (dx, dy) in zip(posicoes, desloc)]
    b_esq, b_dir, b_topo, b_base = (cfg.bordadura(lado) for lado in ("esquerda", "direita", "topo", "base"))
    mx0 = min(c[0] for c in caixas_brutas)
    my0 = min(c[1] for c in caixas_brutas)
    mx1 = max(c[2] for c in caixas_brutas)
    my1 = max(c[3] for c in caixas_brutas)
    W = (mx1 - mx0) + b_esq + b_dir
    H = (my1 - my0) + b_base + b_topo
    sx, sy = b_esq - mx0, b_base - my0                        # leva o conteúdo para o sistema do croqui
    espelho_x = cfg.canto_inicial in ("sup_dir", "inf_dir")
    espelho_y = cfg.canto_inicial in ("inf_esq", "inf_dir")
    centro_rot = (W / 2, H / 2)
    ang = math.radians(cfg.rotacao_graus)
    cos_a, sin_a = math.cos(ang), math.sin(ang)

    def plano(p: Ponto) -> Ponto:
        """Bruto -> croqui antes da rotação (translação e espelhamento)."""
        x, y = p[0] + sx, p[1] + sy
        return (W - x if espelho_x else x, H - y if espelho_y else y)

    def rot(p: Ponto) -> Ponto:
        if ang == 0:
            return p
        x, y = p[0] - centro_rot[0], p[1] - centro_rot[1]
        return (centro_rot[0] + x * cos_a - y * sin_a, centro_rot[1] + x * sin_a + y * cos_a)

    def T(p: Ponto) -> Ponto:
        return rot(plano(p))

    def caixa(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
        """Retângulo bruto -> retângulo no plano do croqui (ainda sem rotação)."""
        a, b = plano((x0, y0)), plano((x1, y1))
        return min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])

    def retangulo_plano(x0: float, y0: float, x1: float, y1: float) -> list[Ponto]:
        return [rot(p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]

    def retangulo(x0: float, y0: float, x1: float, y1: float) -> list[Ponto]:
        return retangulo_plano(*caixa(x0, y0, x1, y1))

    celulas: list[Celula] = []
    contornos: list[ContornoBloco] = []
    bancadas: list[ContornoBloco] = []
    principais: list[list[Ponto]] = []
    rotulos: list[Rotulo] = []
    caixas: dict[int, list[Ponto]] = {}
    caixas_planas: dict[int, tuple[float, float, float, float]] = {}
    celulas_planas: dict[int, tuple[float, float, float, float]] = {}
    por_fil = cfg.blocos_por_fileira if 0 < cfg.blocos_por_fileira < ng else ng
    for ig, ((bloco, bancada, us), loc) in enumerate(zip(grupos, locais)):
        gid = ig + 1
        bx0, _, _, by1 = caixas_brutas[ig]
        ox = bx0 + margem_banc + folga_esq
        oy_topo = by1 - margem_banc - folga_topo
        gx0, gx1 = ox, ox + dims[ig][0]
        gy1, gy0 = oy_topo, oy_topo - dims[ig][1]
        f, j = divmod(ig, por_fil)
        caixas_planas[gid] = caixa(gx0 - margem_banc, gy0 - margem_banc, gx1 + margem_banc, gy1 + margem_banc)
        caixas[gid] = retangulo_plano(*caixas_planas[gid])
        caixas_pp: dict[int, list[float]] = {}
        for c in loc:
            x0 = ox + c.x0
            y1 = oy_topo - c.y0
            x1, y0 = x0 + w, y1 - h
            centro = T(((x0 + x1) / 2, (y0 + y1) / 2))
            if cfg.tipo == "vasos":
                r = w / 2
                cx, cy = plano(((x0 + x1) / 2, (y0 + y1) / 2))
                poli = [rot((cx + r * math.cos(a), cy + r * math.sin(a)))
                        for a in (2 * math.pi * i / 48 for i in range(48))]
                util, raio = None, r
            else:
                poli = retangulo(x0, y0, x1, y1)
                dl, dc = cfg.descarte_lateral, cfg.bordadura_cabeceira
                util = retangulo(x0 + dl, y0 + dc, x1 - dl, y1 - dc) if (dl > 0 or dc > 0) else None
                raio = None
            if horizontal:
                lg, cg = f * (n_lin_g + 1) + c.linha, j * (n_col_g + 1) + c.coluna
            else:
                lg, cg = j * (n_lin_g + 1) + c.linha, f * (n_col_g + 1) + c.coluna
            u = c.unidade
            celulas.append(Celula(u.numero, u.bloco, c.linha, c.coluna, lg, cg, centro, poli, util, raio,
                                  c.principal, bancada, grupo=gid))
            celulas_planas[u.numero] = caixa(x0, y0, x1, y1)
            if c.principal is not None:
                cx_ = caixas_pp.setdefault(c.principal, [x0, y0, x1, y1])
                cx_[0], cx_[1], cx_[2], cx_[3] = min(cx_[0], x0), min(cx_[1], y0), max(cx_[2], x1), max(cx_[3], y1)
        for x0, y0, x1, y1 in caixas_pp.values():
            m = 0.04 if cfg.tipo == "parcelas" else 0.01
            principais.append(retangulo(x0 - m, y0 - m, x1 + m, y1 + m))
        if bloco is not None:
            m = max(min(cfg.gap_x, cfg.gap_y, 0.15), 0.05) if cfg.tipo == "parcelas" else cfg.gap_x / 2
            m = max(m, 0.02)
            if bancada is not None:
                m = margem_banc + 0.03
            px0, py0, px1, py1 = caixa(gx0 - m, gy0 - m, gx1 + m, gy1 + m)
            # rótulo sempre acima (lado a lado) ou à esquerda (empilhados) do bloco, mesmo com espelhamento;
            # a folga dos rótulos de eixo fica do lado em que o espelhamento a pôs
            folga_acima = folga_topo if not espelho_y else 0.0
            folga_lado = folga_esq if not espelho_x else 0.0
            em = (((px0 + px1) / 2, py1 + folga_acima) if horizontal else (px0 - folga_lado, (py0 + py1) / 2))
            contornos.append(ContornoBloco(bloco, retangulo_plano(px0, py0, px1, py1), rot(em)))
        if bancada is not None:
            mb = margem_banc
            px0, py0, px1, py1 = caixa(gx0 - mb, gy0 - mb, gx1 + mb, gy1 + mb)
            bancadas.append(ContornoBloco(bancada, retangulo_plano(px0, py0, px1, py1), rot(((px0 + px1) / 2, py0))))
        if rot_eixos:
            linhas_txt, colunas_txt = _rotulos_eixos(cas, us)
            for c in loc:
                if c.coluna == 0:
                    yc = oy_topo - c.y0 - h / 2
                    rotulos.append(Rotulo(linhas_txt.get(c.unidade.linha, ""), T((ox - folga_esq / 2, yc))))
                if c.linha == 0:
                    xc = ox + c.x0 + w / 2
                    rotulos.append(Rotulo(colunas_txt.get(c.unidade.coluna, ""), T((xc, oy_topo + folga_topo / 2))))

    if espelho_x or espelho_y:                                 # grade das planilhas acompanha o espelhamento
        ml = max(c.linha_grade for c in celulas)
        mc = max(c.coluna_grade for c in celulas)
        for c in celulas:
            if espelho_y:
                c.linha_grade = ml - c.linha_grade
            if espelho_x:
                c.coluna_grade = mc - c.coluna_grade

    contorno = retangulo_plano(0, 0, W, H)
    croqui = Croqui(cfg, celulas, contornos, contorno, W, H, principais=principais, bancadas=bancadas,
                    rotulos=rotulos, caixas=caixas)
    for i, c in enumerate(sorted(croqui.celulas, key=lambda c: c.numero), start=1):
        c.vaga = i
    croqui.conflitos = _conflitos(caixas_planas)
    croqui.cotas = _cotas(cfg, celulas, celulas_planas, caixas_planas, W, H, rot)
    croqui.metricas = calcular_metricas(croqui, len(cas.unidades), dims, margem_banc)
    croqui.metricas["n_grupos"] = ng
    croqui.metricas["sobreposicoes"] = len(croqui.conflitos)
    return croqui


def _conflitos(caixas: dict[int, tuple[float, float, float, float]]) -> list[tuple[int, int]]:
    """Pares de grupos (blocos/bancadas) cujas caixas se sobrepõem — possível só com deslocamentos manuais."""
    ids = sorted(caixas)
    out = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            A, B = caixas[a], caixas[b]
            if min(A[2], B[2]) - max(A[0], B[0]) > 1e-6 and min(A[3], B[3]) - max(A[1], B[1]) > 1e-6:
                out.append((a, b))
    return out


def texto_medida(v: float) -> str:
    """3,00 m · 0,50 m · 25 cm (abaixo de 1 m em vasos e espaços pequenos)."""
    if v < 1 and abs(v * 100 - round(v * 100)) < 1e-6:
        return f"{v * 100:.0f} cm"
    txt = f"{v:.2f}".rstrip("0").rstrip(".") if v >= 10 else f"{v:.2f}"
    return txt.replace(".", ",") + " m"


def _cotas(cfg: ConfigLayout, celulas: list[Celula], cel_plano: dict, caixas: dict, W: float, H: float,
           rot) -> list[Cota]:
    """Cotas principais: dimensões externas, da unidade, espaços entre unidades, entre blocos e bordaduras.

    Construídas no plano do croqui (antes da rotação) a partir da geometria final — valem também com
    espelhamento, corredores e deslocamentos.
    """
    ext = max(W, H)
    d_geral, d = 0.045 * ext, 0.022 * ext
    out: list[Cota] = []

    def nova(p1, p2, normal, dist, nivel="detalhe", valor=None):
        nx, ny = normal
        q1 = (p1[0] + nx * dist, p1[1] + ny * dist)
        q2 = (p2[0] + nx * dist, p2[1] + ny * dist)
        v = valor if valor is not None else math.dist(p1, p2)
        if v <= 1e-6:
            return
        out.append(Cota(rot(p1), rot(p2), rot(q1), rot(q2), v, texto_medida(v), nivel))

    nova((0, 0), (W, 0), (0, -1), d_geral, "geral")
    nova((0, 0), (0, H), (-1, 0), d_geral, "geral")

    g1 = [c for c in celulas if c.grupo == 1]
    if not g1:
        return out
    # unidade de referência: canto inferior esquerdo do primeiro grupo — as cotas de detalhe ficam abaixo e à
    # esquerda dela, longe dos rótulos de bloco (sempre acima) e das cotas gerais (mais afastadas)
    ref = min(g1, key=lambda c: (round(cel_plano[c.numero][1], 6), cel_plano[c.numero][0]))
    x0, y0, x1, y1 = cel_plano[ref.numero]
    nova((x0, y0), (x1, y0), (0, -1), d)                                    # largura (ou diâmetro)
    nova((x0, y0), (x0, y1), (-1, 0), d)                                    # comprimento
    linha = sorted((cel_plano[c.numero] for c in g1 if abs(cel_plano[c.numero][1] - y0) < 1e-6),
                   key=lambda b: b[0])
    coluna = sorted((cel_plano[c.numero] for c in g1 if abs(cel_plano[c.numero][0] - x0) < 1e-6),
                    key=lambda b: b[1])                                     # de baixo para cima
    pares_x = list(zip(linha, linha[1:]))
    pares_y = list(zip(coluna, coluna[1:]))
    normais = [(a, b) for a, b in pares_x if abs((b[0] - a[2]) - cfg.gap_x) < 1e-6
               or abs((b[0] - a[2]) - cfg.gap_sub) < 1e-6]
    if normais:                                                             # espaço lateral
        a, b = normais[0]
        nova((a[2], y0), (b[0], y0), (0, -1), d)
    normais = [(a, b) for a, b in pares_y if abs((b[1] - a[3]) - cfg.gap_y) < 1e-6]
    if normais:                                                             # espaço entre linhas
        a, b = normais[0]
        nova((x0, a[3]), (x0, b[1]), (-1, 0), d)
    if cfg.corredor_a_cada_colunas and cfg.largura_corredor_colunas > 0:  # corredores internos
        for a, b in pares_x:
            if b[0] - a[2] > max(cfg.gap_x, cfg.gap_sub) + 1e-6:
                nova((a[2], y0), (b[0], y0), (0, -1), d)
                break
    if cfg.corredor_a_cada_linhas and cfg.largura_corredor_linhas > 0:
        for a, b in pares_y:
            if b[1] - a[3] > cfg.gap_y + 1e-6:
                nova((x0, a[3]), (x0, b[1]), (-1, 0), d)
                break
    # entre grupos vizinhos (blocos/bancadas)
    if len(caixas) > 1:
        A = caixas[1]
        lado = [B for g, B in caixas.items() if g != 1 and min(A[3], B[3]) - max(A[1], B[1]) > 1e-6]
        dir_ = [B for B in lado if B[0] >= A[2] - 1e-6]
        esq = [B for B in lado if B[2] <= A[0] + 1e-6]
        if dir_ or esq:
            if dir_:
                B = min(dir_, key=lambda b: b[0])
                xa, xb = A[2], B[0]
            else:
                B = max(esq, key=lambda b: b[2])
                xa, xb = B[2], A[0]
            ym = min(A[3], B[3]) - 0.3 * (min(A[3], B[3]) - max(A[1], B[1]))   # dentro do carreador
            nova((xa, ym), (xb, ym), (0, 0), 0)
        vert = [B for g, B in caixas.items() if g != 1 and min(A[2], B[2]) - max(A[0], B[0]) > 1e-6]
        baixo = [B for B in vert if B[3] <= A[1] + 1e-6]
        cima = [B for B in vert if B[1] >= A[3] - 1e-6]
        if baixo or cima:
            if baixo:
                B = max(baixo, key=lambda b: b[3])
                ya, yb = B[3], A[1]
            else:
                B = min(cima, key=lambda b: b[1])
                ya, yb = A[3], B[1]
            xm = min(A[2], B[2]) - 0.12 * (min(A[2], B[2]) - max(A[0], B[0]))   # longe do rótulo do bloco
            nova((xm, ya), (xm, yb), (0, 0), 0)
    # bordaduras externas (do contorno à caixa ocupada mais próxima), no meio de cada lado
    mx0 = min(c[0] for c in caixas.values())
    mx1 = max(c[2] for c in caixas.values())
    my0 = min(c[1] for c in caixas.values())
    my1 = max(c[3] for c in caixas.values())
    if mx0 > 1e-6:
        nova((0, H / 2), (mx0, H / 2), (0, 0), 0)
    if W - mx1 > 1e-6 and abs((W - mx1) - mx0) > 1e-6:
        nova((mx1, H / 2), (W, H / 2), (0, 0), 0)
    if my0 > 1e-6:
        nova((W / 2, 0), (W / 2, my0), (0, 0), 0)
    if H - my1 > 1e-6 and abs((H - my1) - my0) > 1e-6:
        nova((W / 2, my1), (W / 2, H), (0, 0), 0)
    return out


def _rotulos_eixos(cas: Casualizacao, us) -> tuple[dict[int, str], dict[int, str]]:
    """Rótulos das linhas e colunas: L1…/C1… no quadrado latino; níveis de A e B nas faixas."""
    if cas.arranjo is Arranjo.FAIXAS:
        b = cas.niveis_b
        lin = {u.linha: f"A{(u.tratamento - 1) // b + 1}" for u in us}
        col = {u.coluna: f"B{(u.tratamento - 1) % b + 1}" for u in us}
        return lin, col
    return ({u.linha: f"L{u.linha}" for u in us}, {u.coluna: f"C{u.coluna}" for u in us})


def calcular_metricas(croqui: Croqui, n: int, dims_grupos=None, margem_banc: float = 0.0) -> dict:
    c = croqui.config
    W, H = croqui.largura_total, croqui.altura_total
    m: dict = {"n_unidades": n, "largura_total_m": W, "comprimento_total_m": H, "area_total_m2": W * H}
    if c.tipo == "parcelas":
        w, h = c.largura_efetiva, c.comprimento_efetivo
        util_w = max(w - 2 * c.descarte_lateral, 0.0)
        util_h = max(h - 2 * c.bordadura_cabeceira, 0.0)
        area_p = w * h
        area_u = util_w * util_h
        m.update({
            "largura_parcela_m": w, "comprimento_parcela_m": h, "area_parcela_m2": area_p,
            "largura_util_m": util_w, "comprimento_util_m": util_h, "area_util_m2": area_u,
            "area_bordadura_parcela_m2": area_p - area_u, "fracao_util": area_u / area_p if area_p else 0.0,
            "area_parcelas_m2": n * area_p, "area_util_total_m2": n * area_u,
            "area_circulacao_m2": W * H - n * area_p,
        })
        if c.usa_linhas:
            m["linhas_plantio"] = c.n_linhas_plantio
            m["linhas_uteis"] = c.n_linhas_plantio - 2 * c.linhas_bordadura
    else:
        r = c.diametro_vaso / 2
        m.update({"diametro_vaso_m": c.diametro_vaso, "distancia_centros_m": c.diametro_vaso + c.espaco_vasos,
                  "area_projetada_vasos_m2": n * math.pi * r * r})
        if croqui.bancadas and dims_grupos:
            lb = max(d[0] for d in dims_grupos) + 2 * margem_banc
            cb = max(d[1] for d in dims_grupos) + 2 * margem_banc
            m.update({"n_bancadas": len(croqui.bancadas), "largura_bancada_m": lb, "comprimento_bancada_m": cb})
    return m


def aplicar_posicoes(croqui: Croqui, vaga_de: dict[int, int]) -> Croqui:
    """Croqui com as unidades nas vagas indicadas ({número da unidade: vaga}).

    As vagas (posições físicas 1..N) são as células do croqui original, na ordem das unidades. A identidade, o
    tratamento e o código de cada unidade não mudam; só o lugar onde ela está.
    """
    por_vaga = {c.vaga: c for c in croqui.celulas}
    if sorted(vaga_de.values()) != sorted(por_vaga):
        raise ValueError("O mapa de posições deve atribuir cada vaga a exatamente uma unidade.")
    novas = []
    for numero, vaga in vaga_de.items():
        base = por_vaga[vaga]
        novas.append(replace(base, numero=numero))
    return replace(croqui, celulas=novas)


def poligono_area(p: list[Ponto]) -> float:
    """Área pela fórmula do laço (shoelace)."""
    s = 0.0
    for (x0, y0), (x1, y1) in zip(p, p[1:] + p[:1]):
        s += x0 * y1 - x1 * y0
    return abs(s) / 2
