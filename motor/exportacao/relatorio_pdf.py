"""Relatórios em PDF (ReportLab) com croqui vetorial (Matplotlib) intercalado.

* Relatório de planejamento — documento técnico completo.
* Relatório de implantação — voltado à equipe de campo/casa de vegetação.
"""

from __future__ import annotations

import io
from dataclasses import replace
from datetime import datetime

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from motor.estatistica.delineamentos import avisos_planejamento, quadro_gl
from motor.estatistica.tratamentos import descrever_tipo
from motor.exportacao.croqui_estatico import desenhar_croqui, figura_para_bytes, rodape_padrao
from motor.exportacao.estilo import (
    CHUMBO,
    OCRE,
    PASTA_FONTES,
    PETROLEO,
    PREDEFINICOES,
    PRETO_SUAVE,
    OpcoesVisuais,
    fmt_m,
    fmt_num,
    romano,
)
from motor.exportacao.excel import estrutura_extra
from motor.exportacao.texto_metodologico import descricao_pt
from motor.planejamento import Planejamento

_FONTES_OK: tuple[str, str] | None = None


def _fontes() -> tuple[str, str]:
    global _FONTES_OK
    if _FONTES_OK is None:
        try:
            pdfmetrics.registerFont(TTFont("Roboto", str(PASTA_FONTES / "Roboto-Regular.ttf")))
            pdfmetrics.registerFont(TTFont("Roboto-Bold", str(PASTA_FONTES / "Roboto-Bold.ttf")))
            pdfmetrics.registerFont(TTFont("Roboto-Light", str(PASTA_FONTES / "Roboto-Light.ttf")))
            _FONTES_OK = ("Roboto", "Roboto-Bold")
        except Exception:  # pragma: no cover - ambiente sem as fontes
            _FONTES_OK = ("Helvetica", "Helvetica-Bold")
    return _FONTES_OK


def _estilos():
    reg, neg = _fontes()
    return {
        "titulo": ParagraphStyle("titulo", fontName=reg, fontSize=17, leading=21, textColor=HexColor(PRETO_SUAVE)),
        "sub": ParagraphStyle("sub", fontName=reg, fontSize=9, leading=12, textColor=HexColor(CHUMBO)),
        "h": ParagraphStyle("h", fontName=reg, fontSize=11.5, leading=15, spaceBefore=12, spaceAfter=5,
                            textColor=HexColor(PETROLEO)),
        "p": ParagraphStyle("p", fontName=reg, fontSize=9.5, leading=13.5, alignment=TA_JUSTIFY,
                            textColor=HexColor(PRETO_SUAVE)),
        "cel": ParagraphStyle("cel", fontName=reg, fontSize=8.5, leading=10.5, textColor=HexColor(PRETO_SUAVE)),
        "cab": ParagraphStyle("cab", fontName=neg, fontSize=8.5, leading=10.5, textColor=HexColor(PRETO_SUAVE)),
        "nota": ParagraphStyle("nota", fontName=reg, fontSize=7.5, leading=10, textColor=HexColor(CHUMBO)),
    }


def _esc(s) -> str:
    t = (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    recuo = len(t) - len(t.lstrip(" "))
    return "&nbsp;" * (2 * recuo) + t.lstrip(" ")


def _tabela(cab: list[str], linhas: list[list], larguras: list[float], est, direita: set[int] | None = None,
            repetir: bool = True) -> Table:
    direita = direita or set()
    dados = [[Paragraph(_esc(h), est["cab"]) for h in cab]]
    for ln in linhas:
        dados.append([Paragraph(_esc(v), est["cel"]) for v in ln])
    t = Table(dados, colWidths=larguras, repeatRows=1 if repetir else 0, hAlign="LEFT")
    estilo = [
        ("LINEABOVE", (0, 0), (-1, 0), 1.0, HexColor(PRETO_SUAVE)),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, HexColor(PRETO_SUAVE)),
        ("LINEBELOW", (0, -1), (-1, -1), 1.0, HexColor(PRETO_SUAVE)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for j in direita:
        estilo.append(("ALIGN", (j, 0), (j, -1), "RIGHT"))
    t.setStyle(TableStyle(estilo))
    return t


def _doc_para_bytes(historia) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                            bottomMargin=1.8 * cm, title="Exp-Ag", author="Exp-Ag")
    doc.build(historia)
    return buf.getvalue()


def _cabecalho(p: Planejamento, tipo: str, est) -> list:
    from reportlab.platypus import Image as RLImage

    m = p.meta
    larg = A4[0] - 4 * cm
    logo = RLImage(str(PASTA_FONTES.parent / "logo_expag.png"), width=3.4 * cm, height=3.4 * cm * 422 / 1771)
    textos = [Paragraph(f"{_esc(m.codigo)} — {_esc(m.titulo)}", est["titulo"]), Spacer(1, 3),
              Paragraph(f"{tipo} · planejamento versão {p.versao} · emitido em {datetime.now():%d/%m/%Y %H:%M}",
                        est["sub"])]
    t = Table([[textos, logo]], colWidths=[larg - 3.8 * cm, 3.8 * cm], hAlign="LEFT")
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("LINEBELOW", (0, 0), (-1, 0), 0.8, HexColor(OCRE)), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return [t, Spacer(1, 8)]


def _identificacao(p: Planejamento) -> list[list[str]]:
    m = p.meta
    itens = [
        ("Projeto", m.projeto), ("Instituição", m.instituicao), ("Responsável", m.responsavel),
        ("Colaboradores", m.colaboradores), ("Cultura", m.cultura), ("Cultivar", m.cultivar),
        ("Ambiente", m.ambiente), ("Local", m.local),
        ("Município/UF", " – ".join(x for x in (m.municipio, m.uf) if x)), ("Safra", m.safra),
        ("Data prevista", _data(m.data_prevista)), ("Data de implantação", _data(m.data_implantacao)),
    ]
    return [[a, b] for a, b in itens if b]


def _data(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return iso or ""


def _dimensoes(p: Planejamento) -> list[list[str]]:
    mt = p.croqui.metricas
    lay = p.layout
    if lay.tipo == "vasos":
        return [
            ["Número de vasos", str(mt["n_unidades"])],
            ["Diâmetro do vaso", f"{fmt_m(mt['diametro_vaso_m'] * 100)} cm"],
            ["Distância entre centros", f"{fmt_m(mt['distancia_centros_m'] * 100)} cm"],
            ["Área ocupada", f"{fmt_m(mt['largura_total_m'])} × {fmt_m(mt['comprimento_total_m'])} m "
                             f"({fmt_num(mt['area_total_m2'])} m²)"],
        ]
    lin = [
        ["Número de parcelas", str(mt["n_unidades"])],
        ["Parcela (largura × comprimento)", f"{fmt_m(mt['largura_parcela_m'])} × {fmt_m(mt['comprimento_parcela_m'])} m"
                                            f" = {fmt_num(mt['area_parcela_m2'])} m²"],
        ["Área útil da parcela", f"{fmt_m(mt['largura_util_m'])} × {fmt_m(mt['comprimento_util_m'])} m"
                                 f" = {fmt_num(mt['area_util_m2'])} m² ({fmt_num(100 * mt['fracao_util'], 1)}%)"],
        ["Bordadura por parcela", f"{fmt_num(mt['area_bordadura_parcela_m2'])} m²"],
    ]
    if lay.usa_linhas:
        lin.append(["Linhas de plantio", f"{lay.n_linhas_plantio} linhas a {fmt_m(lay.espacamento_linhas)} m "
                                         f"({lay.n_linhas_plantio - 2 * lay.linhas_bordadura} úteis)"])
    lin += [
        ["Espaçamento entre parcelas", f"{fmt_m(lay.espaco_x)} m (lateral) · {fmt_m(lay.espaco_y)} m (entre linhas de parcelas)"],
        ["Carreador entre blocos", f"{fmt_m(lay.espaco_blocos)} m"],
        ["Bordadura externa", f"{fmt_m(lay.bordadura_externa)} m"],
        ["Dimensões externas", f"{fmt_m(mt['largura_total_m'])} × {fmt_m(mt['comprimento_total_m'])} m"],
        ["Área total", f"{fmt_num(mt['area_total_m2'])} m² ({fmt_num(mt['area_total_m2'] / 10000, 4)} ha)"],
        ["Área em parcelas / útil total", f"{fmt_num(mt['area_parcelas_m2'])} m² / {fmt_num(mt['area_util_total_m2'])} m²"],
        ["Área de circulação", f"{fmt_num(mt['area_circulacao_m2'])} m²"],
    ]
    return lin


def _pagina_croqui(p: Planejamento, opcoes: OpcoesVisuais, pagina: str) -> bytes:
    op = replace(opcoes, titulo=f"Croqui — {p.meta.codigo}")
    fig = desenhar_croqui(p.casualizacao, p.tratamentos, p.croqui, op, pagina, rodape_padrao(p.croqui))
    return figura_para_bytes(fig, "pdf")


def _numerar(pdf: bytes, rotulo: str, capa: bool = False) -> bytes:
    """Rodapé com o rótulo e a numeração; com capa, a primeira página fica limpa e a contagem começa depois dela."""
    leitor = PdfReader(io.BytesIO(pdf))
    escritor = PdfWriter()
    total = len(leitor.pages) - (1 if capa else 0)
    reg, _ = _fontes()
    for i, pg in enumerate(leitor.pages, start=0 if capa else 1):
        if capa and i == 0:
            escritor.add_page(pg)
            continue
        w, h = float(pg.mediabox.width), float(pg.mediabox.height)
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(w, h))
        c.setFont(reg, 7)
        c.setFillColor(HexColor(CHUMBO))
        c.drawString(2 * cm, 1.0 * cm, rotulo)
        c.drawRightString(w - 2 * cm, 1.0 * cm, f"{i} / {total}")
        c.save()
        pg.merge_page(PdfReader(io.BytesIO(buf.getvalue())).pages[0])
        escritor.add_page(pg)
    escritor.add_metadata({"/Title": rotulo, "/Creator": "Exp-Ag"})
    out = io.BytesIO()
    escritor.write(out)
    return out.getvalue()


def _juntar(partes: list[bytes]) -> bytes:
    w = PdfWriter()
    for parte in partes:
        for pg in PdfReader(io.BytesIO(parte)).pages:
            w.add_page(pg)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def _pagina_auto(p: Planejamento) -> str:
    return "A3" if p.casualizacao.n_unidades > 80 else "A4"


def relatorio_planejamento(p: Planejamento, opcoes: OpcoesVisuais | None = None, pagina: str | None = None,
                           capa: bool = True) -> bytes:
    est = _estilos()
    opcoes = opcoes or PREDEFINICOES["cientifico"]
    m = p.meta
    cas = p.casualizacao
    trat = {t.numero: t for t in p.tratamentos}
    larg = A4[0] - 4 * cm

    secoes = iter(range(1, 20))

    def titulo(txt: str) -> Paragraph:
        return Paragraph(f"{next(secoes)}. {txt}", est["h"])

    h1: list = _cabecalho(p, "Relatório de planejamento", est)
    h1.append(titulo("Identificação"))
    h1.append(_tabela(["Item", "Informação"], _identificacao(p), [5 * cm, larg - 5 * cm], est))
    if m.objetivos or m.hipoteses:
        h1.append(titulo("Objetivos e hipóteses"))
        if m.objetivos:
            h1.append(Paragraph(f"<i>Objetivos.</i> {_esc(m.objetivos)}", est["p"]))
        if m.hipoteses:
            h1.append(Spacer(1, 4))
            h1.append(Paragraph(f"<i>Hipóteses.</i> {_esc(m.hipoteses)}", est["p"]))
    h1.append(titulo("Delineamento e tratamentos"))
    esquema = f"fatorial {p.estrutura.esquema}" if p.estrutura.e_fatorial else f"{len(p.tratamentos)} tratamentos"
    arr_txt = f" em {p.arranjo.nome}" if p.arranjo.value != "convencional" else ""
    h1.append(Paragraph(
        f"{p.delineamento.nome} ({p.delineamento.value}){arr_txt}; {esquema}; {p.repeticoes} repetições"
        f"{' (blocos)' if p.delineamento.value == 'DBC' else ''}; {cas.n_unidades} unidades experimentais.",
        est["p"]))
    h1.append(Spacer(1, 6))
    fatores = [f.nome for f in p.estrutura.fatores] if p.estrutura.e_fatorial else []
    cab = ["Código", "Tratamento"] + fatores + ["Tipo"]
    w_f = 3.2 * cm
    w_tipo = 3.4 * cm
    w_rot = larg - 1.6 * cm - w_tipo - w_f * len(fatores)
    h1.append(_tabela(cab, [[t.codigo, t.rotulo] + [t.niveis.get(f, "—") for f in fatores]
                            + [descrever_tipo(t, p.estrutura.e_fatorial) + (f" ({t.papel.value})" if t.papel.value else "")]
                            for t in p.tratamentos],
                      [1.6 * cm, w_rot] + [w_f] * len(fatores) + [w_tipo], est))
    h1.append(Spacer(1, 8))
    gl = quadro_gl(p.delineamento, p.estrutura, p.repeticoes, p.arranjo)
    h1.append(KeepTogether([
        Paragraph("Quadro esperado da análise de variância", est["sub"]), Spacer(1, 3),
        _tabela(["Fonte de variação", "GL", "Estrato de erro"], [[g.fonte, g.gl, g.estrato] for g in gl],
                [7 * cm, 1.5 * cm, 3.6 * cm], est, direita={1}),
    ]))
    avisos = avisos_planejamento(p.delineamento, p.estrutura, p.repeticoes, p.arranjo)
    for a in avisos:
        if a.nivel != "info":
            h1.append(Spacer(1, 3))
            h1.append(Paragraph(f"Atenção: {_esc(a.mensagem)}", est["nota"]))
    h1.append(titulo("Dimensões e áreas"))
    h1.append(_tabela(["Item", "Valor"], _dimensoes(p), [6 * cm, larg - 6 * cm], est))

    h2: list = [titulo("Tabela de casualização")]
    extras = estrutura_extra(p)
    cab = ["Parcela", "Unidade", "Bloco"] + [n.replace("Parcela principal", "P. princ.") for n, _ in extras] \
        + ["Rep.", "Trat.", "Tratamento"]
    w = [1.4 * cm, 4.6 * cm, 1.2 * cm] + [1.5 * cm] * len(extras) + [1.0 * cm, 1.2 * cm]
    w.append(larg - sum(w))
    h2.append(_tabela(cab, [[u.parcela, u.codigo, romano(u.bloco) if u.bloco else "—"] + [f(u) for _, f in extras]
                            + [u.repeticao, trat[u.tratamento].codigo, trat[u.tratamento].rotulo]
                            for u in cas.unidades], w, est))
    h2.append(titulo("Descrição metodológica"))
    h2.append(Paragraph(_esc(descricao_pt(p)), est["p"]))
    h2.append(titulo("Reprodutibilidade e integridade"))
    problemas = p.verificar()
    h2.append(_tabela(["Item", "Valor"], [
        ["Semente", str(cas.semente)], ["Algoritmo", cas.algoritmo],
        ["Padrão de identificação", p.padrao_codigo],
        ["Verificações de integridade", "aprovadas" if not problemas else "; ".join(problemas)],
    ], [5 * cm, larg - 5 * cm], est))

    partes = [_doc_para_bytes(h1), _pagina_croqui(p, opcoes, pagina or _pagina_auto(p)), _doc_para_bytes(h2)]
    if capa:
        from motor.exportacao.capa import capa_do_plano

        partes.insert(0, capa_do_plano(p, "Relatório de planejamento"))
    return _numerar(_juntar(partes), f"Exp-Ag · {m.codigo} · relatório de planejamento", capa)


def relatorio_implantacao(p: Planejamento, pagina: str | None = None, capa: bool = True) -> bytes:
    est = _estilos()
    m = p.meta
    cas = p.casualizacao
    trat = {t.numero: t for t in p.tratamentos}
    larg = A4[0] - 4 * cm
    h1: list = _cabecalho(p, "Relatório de implantação", est)
    h1.append(Paragraph(
        "Documento para a equipe de campo. O croqui operacional (página seguinte) mostra o número de cada "
        "parcela e o código do tratamento; a tabela abaixo segue a ordem de implantação (bloco a bloco, na "
        "ordem das posições).", est["p"]))
    h1.append(Paragraph("Dimensões", est["h"]))
    h1.append(_tabela(["Item", "Valor"], _dimensoes(p), [6 * cm, larg - 6 * cm], est))
    h1.append(Paragraph("Tratamentos", est["h"]))
    h1.append(_tabela(["Código", "Tratamento"], [[t.codigo, t.rotulo] for t in p.tratamentos],
                      [2 * cm, larg - 2 * cm], est))
    h2: list = [Paragraph("Sequência de implantação", est["h"])]
    pos = {c.numero: c for c in p.croqui.celulas}
    ordem = sorted(cas.unidades, key=lambda u: ((u.bloco or 0), u.posicao))
    cab = ["Ordem", "Parcela", "Bloco", "Linha", "Coluna", "Trat.", "Tratamento", "Feito"]
    w = [1.2 * cm, 1.5 * cm, 1.2 * cm, 1.2 * cm, 1.4 * cm, 1.3 * cm]
    w += [larg - sum(w) - 1.2 * cm, 1.2 * cm]
    h2.append(_tabela(cab, [[i, u.parcela, romano(u.bloco) if u.bloco else "—", pos[u.numero].linha + 1,
                             pos[u.numero].coluna + 1, trat[u.tratamento].codigo, trat[u.tratamento].rotulo, ""]
                            for i, u in enumerate(ordem, start=1)], w, est))
    h2.append(Spacer(1, 6))
    h2.append(Paragraph("Linha e coluna referem-se à posição dentro do bloco no croqui (linha 1 = topo).",
                        est["nota"]))
    op = replace(PREDEFINICOES["operacional"], rotulo="parcela_tratamento")
    partes = [_doc_para_bytes(h1), _pagina_croqui(p, op, pagina or _pagina_auto(p)), _doc_para_bytes(h2)]
    if capa:
        from motor.exportacao.capa import capa_do_plano

        partes.insert(0, capa_do_plano(p, "Relatório de implantação"))
    return _numerar(_juntar(partes), f"Exp-Ag · {m.codigo} · relatório de implantação", capa)
