"""Etiquetas de vasos e amostras e placas de parcela, em folhas A4, com QR Code e código de barras.

O QR Code leva o identificador da unidade. Se for informado o endereço público do aplicativo, o QR leva um link
que abre o experimento com a unidade destacada (``…/experimento?exp=ID&ue=CODIGO``); sem endereço, leva um texto
legível por qualquer leitor (``EXP=…;UE=…;T=…``), útil também em planilhas de campo.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from urllib.parse import quote

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import code128
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from motor.exportacao.estilo import CHUMBO, OCRE, PETROLEO, PRETO_SUAVE, romano
from motor.planejamento import Planejamento

A4_MM = (210.0, 297.0)


@dataclass(frozen=True)
class ModeloEtiqueta:
    nome: str
    largura: float  # mm
    altura: float
    colunas: int
    linhas: int
    margem_esq: float
    margem_topo: float
    passo_h: float  # distância entre inícios de colunas
    passo_v: float
    paisagem: bool = False
    placa: bool = False  # layout de placa (texto grande)


MODELOS = {
    "a4_21": ModeloEtiqueta("Etiqueta 63,5 × 38,1 mm (3 × 7 por folha)", 63.5, 38.1, 3, 7, 7.25, 15.15, 66.0, 38.1),
    "a4_14": ModeloEtiqueta("Etiqueta 99,1 × 38,1 mm (2 × 7 por folha)", 99.1, 38.1, 2, 7, 4.65, 15.15, 101.6, 38.1),
    "a4_40": ModeloEtiqueta("Etiqueta 48,5 × 25,4 mm (4 × 10 por folha)", 48.5, 25.4, 4, 10, 8.0, 21.5, 48.5, 25.4),
    "placa_2": ModeloEtiqueta("Placa de parcela — meia folha A4 (2 por folha)", 190.0, 133.0, 1, 2, 10.0, 10.0, 190.0,
                              143.0, placa=True),
    "placa_1": ModeloEtiqueta("Placa de parcela — folha A4 inteira (paisagem)", 277.0, 190.0, 1, 1, 10.0, 10.0, 277.0,
                              190.0, paisagem=True, placa=True),
}


@dataclass(frozen=True)
class Etiqueta:
    codigo: str  # conteúdo principal (código da unidade ou da amostra)
    parcela: str
    tratamento: str  # código do tratamento
    rotulo: str  # nome do tratamento
    bloco: str
    repeticao: str
    extra: str = ""  # tipo de amostra
    qr: str = ""


def _fontes() -> tuple[str, str]:
    from motor.exportacao.relatorio_pdf import _fontes as f

    return f()


def etiquetas_unidades(p: Planejamento, url_base: str = "", exp_id: int | None = None,
                       blocos: list[int] | None = None, amostras: list[tuple[str, str]] | None = None,
                       ordem: str = "implantacao") -> list[Etiqueta]:
    """Uma etiqueta por unidade (ou por unidade × tipo de amostra, se `amostras` = [(sufixo, descrição)])."""
    trat = {t.numero: t for t in p.tratamentos}
    us = list(p.casualizacao.unidades)
    if blocos:
        us = [u for u in us if u.bloco in blocos]
    if ordem == "implantacao":
        us.sort(key=lambda u: ((u.bloco or 0), u.posicao))
    else:
        us.sort(key=lambda u: u.numero)
    saida = []
    for u in us:
        t = trat[u.tratamento]
        for sufixo, desc in (amostras or [("", "")]):
            cod = f"{u.codigo}-{sufixo}" if sufixo else u.codigo
            if url_base and exp_id is not None:
                qr = f"{url_base.rstrip('/')}/experimento?exp={exp_id}&ue={quote(u.codigo)}"
            else:
                qr = f"EXP={p.meta.codigo};UE={cod};T={t.codigo}"
            saida.append(Etiqueta(cod, u.parcela, t.codigo, t.rotulo, romano(u.bloco) if u.bloco else "—",
                                  str(u.repeticao), desc, qr))
    return saida


def _qr(c: canvas.Canvas, texto: str, x: float, y: float, lado: float) -> None:
    w = QrCodeWidget(texto, barLevel="M", barBorder=4)   # zona de silêncio de 4 módulos (norma ISO/IEC 18004)
    x0, y0, x1, y1 = w.getBounds()
    d = Drawing(lado, lado, transform=[lado / (x1 - x0), 0, 0, lado / (y1 - y0), 0, 0])
    d.add(w)
    renderPDF.draw(d, c, x, y)


def _caber(texto: str, fonte: str, tam: float, larg: float, minimo: float = 5.0) -> tuple[str, float]:
    while stringWidth(texto, fonte, tam) > larg and tam > minimo:
        tam -= 0.25
    while stringWidth(texto, fonte, tam) > larg and len(texto) > 4:
        texto = texto[:-2] + "…"
    return texto, tam


def _desenhar_etiqueta(c: canvas.Canvas, e: Etiqueta, x: float, y: float, w: float, h: float, exp: str,
                       barras: bool, borda: bool) -> None:
    reg, neg = _fontes()
    pad = 2.2 * mm
    if borda:
        c.setStrokeColor(HexColor("#BBBBBB"))
        c.setLineWidth(0.3)
        c.roundRect(x, y, w, h, 2 * mm)
    lado = h - 2 * pad - (5 * mm if barras and w > 60 * mm else 0)
    lado = min(lado, w * 0.42)
    _qr(c, e.qr, x + pad - 1, y + h - pad - lado, lado)
    tx = x + pad + lado + 1.5 * mm
    larg = x + w - pad - tx
    c.setFillColor(HexColor(CHUMBO))
    t, s = _caber(exp + (f" · {e.extra}" if e.extra else ""), reg, 6.5, larg)
    c.setFont(reg, s)
    c.drawString(tx, y + h - pad - s, t)
    c.setFillColor(HexColor(PETROLEO))
    t, s = _caber(e.codigo, neg, 11 if h > 30 * mm else 8.5, larg)
    c.setFont(neg, s)
    yy = y + h - pad - 6.5 - s - 1.5
    c.drawString(tx, yy, t)
    c.setFillColor(HexColor(PRETO_SUAVE))
    t, s = _caber(f"{e.tratamento} — {e.rotulo}", reg, 8 if h > 30 * mm else 6.5, larg)
    c.setFont(reg, s)
    yy -= s + 2
    c.drawString(tx, yy, t)
    bloco = f" · Bloco {e.bloco}" if e.bloco != "—" else ""
    t, s = _caber(f"Parcela {e.parcela}{bloco} · Rep. {e.repeticao}", reg, 7 if h > 30 * mm else 6, larg)
    c.setFillColor(HexColor(CHUMBO))
    c.setFont(reg, s)
    yy -= s + 2
    c.drawString(tx, yy, t)
    if barras and w > 60 * mm:
        b = code128.Code128(e.codigo, barHeight=4 * mm, barWidth=0.24 * mm, humanReadable=False)
        bw = min(b.width, w - 2 * pad)
        escala = bw / b.width
        c.saveState()
        c.translate(x + pad, y + pad - 0.5 * mm)
        c.scale(escala, 1)
        b.drawOn(c, 0, 0)
        c.restoreState()
    c.setFillColor(HexColor(OCRE))
    c.rect(x + w - 1.6 * mm - 0.5, y + 2 * mm, 1.6 * mm, h - 4 * mm, stroke=0, fill=1)


def _desenhar_placa(c: canvas.Canvas, e: Etiqueta, x: float, y: float, w: float, h: float, exp: str) -> None:
    reg, neg = _fontes()
    c.setStrokeColor(HexColor(PETROLEO))
    c.setLineWidth(2)
    c.roundRect(x, y, w, h, 5 * mm)
    lado = min(h * 0.62, w * 0.36)
    _qr(c, e.qr, x + w - lado - 8 * mm, y + (h - lado) / 2, lado)
    larg = w - lado - 24 * mm
    c.setFillColor(HexColor(CHUMBO))
    c.setFont(reg, 14)
    c.drawString(x + 10 * mm, y + h - 16 * mm, exp)
    c.setFillColor(HexColor(PETROLEO))
    t, s = _caber(e.parcela, neg, min(h * 0.40, 200), larg, 30)
    c.setFont(neg, s)
    c.drawString(x + 10 * mm, y + h * 0.42, t)
    c.setFillColor(HexColor(PRETO_SUAVE))
    t, s2 = _caber(f"{e.tratamento} — {e.rotulo}", reg, 26, larg, 12)
    c.setFont(reg, s2)
    c.drawString(x + 10 * mm, y + h * 0.42 - s2 - 6, t)
    c.setFillColor(HexColor(CHUMBO))
    bloco = f"Bloco {e.bloco} · " if e.bloco != "—" else ""
    t, s3 = _caber(f"{bloco}Repetição {e.repeticao} · {e.codigo}", reg, 15, larg, 9)
    c.setFont(reg, s3)
    c.drawString(x + 10 * mm, y + 10 * mm, t)
    c.setFillColor(HexColor(OCRE))
    c.rect(x, y + 6 * mm, 3 * mm, h - 12 * mm, stroke=0, fill=1)


def gerar_pdf(etiquetas: list[Etiqueta], modelo: str, exp: str, codigo_barras: bool = True,
              bordas: bool = True, pular: int = 0) -> bytes:
    """`pular`: posições já usadas na primeira folha (para reaproveitar folhas de etiquetas)."""
    m = MODELOS[modelo]
    pw, ph = (A4_MM[1], A4_MM[0]) if m.paisagem else A4_MM
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pw * mm, ph * mm))
    c.setTitle(f"Etiquetas — {exp}")
    c.setAuthor("Exp-Ag")
    por_folha = m.colunas * m.linhas
    pos = pular % por_folha
    for e in etiquetas:
        if pos == por_folha:
            c.showPage()
            pos = 0
        lin, col = divmod(pos, m.colunas)
        x = (m.margem_esq + col * m.passo_h) * mm
        y = (ph - m.margem_topo - lin * m.passo_v - m.altura) * mm
        if m.placa:
            _desenhar_placa(c, e, x, y, m.largura * mm, m.altura * mm, exp)
        else:
            _desenhar_etiqueta(c, e, x, y, m.largura * mm, m.altura * mm, exp, codigo_barras, bordas)
        pos += 1
    c.save()
    return buf.getvalue()
