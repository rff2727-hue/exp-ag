"""Capas dos documentos do Exp-Ag (arte do autor em assets/capas).

A arte já traz a marca e o título; a capa acrescenta, na faixa clara entre o título e a paisagem, o tipo de documento
e a identificação do experimento. As posições abaixo são frações da página medidas sobre a arte (A4 retrato).
"""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas

from motor.exportacao.estilo import CHUMBO, OCRE, PETROLEO, RAIZ

CAPAS = RAIZ / "assets" / "capas"
CAPA_EXPERIMENTOS = CAPAS / "capa_experimentos.jpg"
CAPA_SATELITES = CAPAS / "capa_satelites.jpg"

# faixa livre da arte "Experimentos" (frações a partir do topo da página): entre o título e a paisagem
FAIXA_EXP = (0.232, 0.388)
MARGEM_X = 0.10


def _quebrar(texto: str, fonte: str, tam: float, largura: float, max_linhas: int) -> list[str]:
    palavras = texto.split()
    linhas, atual = [], ""
    for p in palavras:
        cand = f"{atual} {p}".strip()
        if stringWidth(cand, fonte, tam) <= largura or not atual:
            atual = cand
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]
        while stringWidth(linhas[-1] + " …", fonte, tam) > largura and " " in linhas[-1]:
            linhas[-1] = linhas[-1].rsplit(" ", 1)[0]
        linhas[-1] += " …"
    return linhas


def capa_experimento(tipo_documento: str, codigo: str, titulo: str, linhas_info: list[str],
                     emitido: datetime | None = None) -> bytes:
    """Página de capa (PDF de uma página) com a arte "Experimentos"."""
    from motor.exportacao.relatorio_pdf import _fontes

    reg, neg = _fontes()
    W, H = A4
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"{tipo_documento} — {codigo}")
    if CAPA_EXPERIMENTOS.exists():
        c.drawImage(str(CAPA_EXPERIMENTOS), 0, 0, W, H)
    x = MARGEM_X * W
    larg = W * (1 - 2 * MARGEM_X)
    y = H * (1 - FAIXA_EXP[0])
    c.setFillColor(HexColor(OCRE))
    c.setFont(reg, 9.5)
    c.drawString(x, y, tipo_documento.upper())
    c.setStrokeColor(HexColor(OCRE))
    c.setLineWidth(1.4)
    c.line(x, y - 6, x + 2.2 * 28.35, y - 6)
    y -= 30
    tam = 21.0
    linhas = _quebrar(f"{codigo} — {titulo}", reg, tam, larg, 2)
    while len(linhas) == 2 and tam > 15 and any(stringWidth(t, reg, tam) > larg for t in linhas):
        tam -= 1
        linhas = _quebrar(f"{codigo} — {titulo}", reg, tam, larg, 2)
    c.setFillColor(HexColor(PETROLEO))
    c.setFont(reg, tam)
    for t in linhas:
        c.drawString(x, y, t)
        y -= tam * 1.22
    y -= 6
    c.setFont(reg, 10)
    c.setFillColor(HexColor("#2E3134"))
    limite = H * (1 - FAIXA_EXP[1])
    for t in linhas_info:
        if not t or y < limite + 14:
            continue
        for sub in _quebrar(t, reg, 10, larg, 1):
            c.drawString(x, y, sub)
            y -= 14.5
    c.setFont(reg, 8.5)
    c.setFillColor(HexColor(CHUMBO))
    c.drawString(x, max(y - 4, limite), f"Emitido em {(emitido or datetime.now()):%d/%m/%Y %H:%M} · plataforma Exp-Ag")
    c.showPage()
    c.save()
    return buf.getvalue()


def capa_do_plano(p, tipo_documento: str) -> bytes:
    m = p.meta
    local = " · ".join(x for x in (m.local, " – ".join(y for y in (m.municipio, m.uf) if y)) if x)
    esquema = f"fatorial {p.estrutura.esquema}" if p.estrutura.e_fatorial else f"{len(p.tratamentos)} tratamentos"
    arr = f" em {p.arranjo.nome}" if p.arranjo.value != "convencional" else ""
    info = [
        m.projeto and f"Projeto: {m.projeto}",
        f"{p.delineamento.nome}{arr} · {esquema} · {p.repeticoes} repetições · {p.casualizacao.n_unidades} unidades",
        " · ".join(x for x in (m.cultura and f"Cultura: {m.cultura}", m.safra and f"Safra {m.safra}") if x),
        local,
        " · ".join(x for x in (m.responsavel and f"Responsável: {m.responsavel}", m.instituicao) if x),
        f"Planejamento versão {p.versao} · semente {p.casualizacao.semente}",
    ]
    return capa_experimento(tipo_documento, m.codigo, m.titulo, [t for t in info if t])
