"""Conteúdo da pasta de um experimento no Google Drive (ou de qualquer outro destino de arquivos).

* Relatórios em PDF (planejamento e implantação, com capa) e croqui em PNG;
* "Planilha do experimento" — a planilha completa do Exp-Ag convertida em Planilha Google (atualizada a cada envio);
* "Memorial descritivo" — Documento Google com identificação, tratamentos, quadro de GL e a descrição metodológica
  em português e inglês (atualizado a cada envio);
* "Diário de campo" e "Planilha de coleta" — documentos de trabalho, criados uma única vez e nunca sobrescritos;
* subpasta "Mapas e GIS" — KMZ para o Google Earth, plano de locação, Shapefile, GeoPackage e GeoJSON (se o
  experimento estiver georreferenciado).
"""

from __future__ import annotations

import io
from datetime import datetime
from html import escape

import xlsxwriter

from motor.estatistica.delineamentos import quadro_gl
from motor.integracoes.google_drive import DOC, PLANILHA, XLSX, Arquivo

HTML = "text/html"


def _tabela_html(cab: list[str], linhas: list[list]) -> str:
    th = "".join(f"<th style='text-align:left;border-top:1pt solid #1C1D1F;border-bottom:0.5pt solid #1C1D1F;"
                 f"padding:3px 8px'>{escape(str(h))}</th>" for h in cab)
    trs = []
    for i, ln in enumerate(linhas):
        borda = "border-bottom:1pt solid #1C1D1F;" if i == len(linhas) - 1 else ""
        trs.append("<tr>" + "".join(f"<td style='{borda}padding:2px 8px'>{escape(str(v))}</td>" for v in ln) + "</tr>")
    return (f"<table style='border-collapse:collapse;font-family:Roboto,Arial;font-size:10pt'><tr>{th}</tr>"
            + "".join(trs) + "</table>")


def memorial_html(p, geo_info: dict | None = None) -> bytes:
    from motor.exportacao.relatorio_pdf import _dimensoes, _identificacao
    from motor.exportacao.texto_metodologico import descricao_en, descricao_pt

    m = p.meta
    corpo = [f"<h1 style='font-family:Roboto,Arial;color:#174A51;font-weight:400'>{escape(m.codigo)} — "
             f"{escape(m.titulo)}</h1>",
             f"<p style='color:#5B6166;font-family:Roboto,Arial'>Memorial descritivo · planejamento versão {p.versao} · "
             f"atualizado em {datetime.now():%d/%m/%Y %H:%M} pela plataforma Exp-Ag. Este documento é regenerado a "
             f"cada envio; anotações devem ir para o Diário de campo.</p>",
             "<h2 style='font-family:Roboto,Arial;color:#174A51;font-weight:400'>Identificação</h2>",
             _tabela_html(["Item", "Informação"], _identificacao(p))]
    if m.objetivos or m.hipoteses:
        corpo.append("<h2 style='font-family:Roboto,Arial;color:#174A51;font-weight:400'>Objetivos e hipóteses</h2>")
        if m.objetivos:
            corpo.append(f"<p><i>Objetivos.</i> {escape(m.objetivos)}</p>")
        if m.hipoteses:
            corpo.append(f"<p><i>Hipóteses.</i> {escape(m.hipoteses)}</p>")
    corpo.append("<h2 style='font-family:Roboto,Arial;color:#174A51;font-weight:400'>Tratamentos</h2>")
    corpo.append(_tabela_html(["Código", "Tratamento"], [[t.codigo, t.rotulo] for t in p.tratamentos]))
    corpo.append("<h2 style='font-family:Roboto,Arial;color:#174A51;font-weight:400'>Quadro esperado da análise de "
                 "variância</h2>")
    corpo.append(_tabela_html(["Fonte de variação", "GL", "Estrato"],
                              [[g.fonte.strip(), g.gl, g.estrato] for g in
                               quadro_gl(p.delineamento, p.estrutura, p.repeticoes, p.arranjo)]))
    corpo.append("<h2 style='font-family:Roboto,Arial;color:#174A51;font-weight:400'>Dimensões</h2>")
    corpo.append(_tabela_html(["Item", "Valor"], _dimensoes(p)))
    if geo_info:
        corpo.append("<h2 style='font-family:Roboto,Arial;color:#174A51;font-weight:400'>Posição no terreno</h2>")
        corpo.append(_tabela_html(["Item", "Valor"], [[k, v] for k, v in geo_info.items()]))
    corpo.append("<h2 style='font-family:Roboto,Arial;color:#174A51;font-weight:400'>Descrição metodológica</h2>")
    corpo.append(f"<p style='text-align:justify'>{escape(descricao_pt(p))}</p>")
    corpo.append("<h2 style='font-family:Roboto,Arial;color:#174A51;font-weight:400'>Methods (English)</h2>")
    corpo.append(f"<p style='text-align:justify'>{escape(descricao_en(p))}</p>")
    return ("<html><head><meta charset='utf-8'></head><body style='font-family:Roboto,Arial;font-size:10.5pt'>"
            + "".join(corpo) + "</body></html>").encode("utf-8")


def diario_html(p) -> bytes:
    m = p.meta
    linhas = "".join("<tr><td style='border-bottom:0.5pt solid #C8C8C8;padding:6px 8px;width:90px'></td>"
                     "<td style='border-bottom:0.5pt solid #C8C8C8;padding:6px 8px'></td></tr>" for _ in range(12))
    return (f"<html><head><meta charset='utf-8'></head><body style='font-family:Roboto,Arial;font-size:10.5pt'>"
            f"<h1 style='color:#174A51;font-weight:400'>Diário de campo — {escape(m.codigo)}</h1>"
            f"<p style='color:#5B6166'>{escape(m.titulo)}. Registre aqui operações (semeadura, adubação, aplicações, "
            "irrigação, colheita), ocorrências (chuvas fortes, pragas, danos, falhas de estande) e decisões. "
            "Este documento é seu: a plataforma nunca o sobrescreve.</p>"
            "<table style='border-collapse:collapse;width:100%'><tr>"
            "<th style='text-align:left;border-top:1pt solid #1C1D1F;border-bottom:0.5pt solid #1C1D1F;padding:3px 8px'>"
            "Data</th><th style='text-align:left;border-top:1pt solid #1C1D1F;border-bottom:0.5pt solid #1C1D1F;"
            f"padding:3px 8px'>Registro</th></tr>{linhas}</table></body></html>").encode()


def planilha_coleta(p, variaveis: list[str] | None = None) -> bytes:
    """Planilha de coleta (uma linha por unidade, na ordem de campo) para preencher no Drive ou no celular."""
    from motor.exportacao.excel import estrutura_extra

    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    ws = wb.add_worksheet("Coleta")
    cab_f = wb.add_format({"font_name": "Roboto", "bold": True, "top": 2, "bottom": 1})
    cel = wb.add_format({"font_name": "Roboto"})
    ult = wb.add_format({"font_name": "Roboto", "bottom": 2})
    trat = {t.numero: t for t in p.tratamentos}
    extras = estrutura_extra(p)
    vars_ = [v for v in (variaveis or []) if v.strip()] or ["Variável 1", "Variável 2", "Variável 3"]
    cab = ["Unidade", "Parcela", "Bloco"] + [n for n, _ in extras] + ["Tratamento", "Data"] + vars_ + ["Observações"]
    for j, h in enumerate(cab):
        ws.write(0, j, h, cab_f)
    ordem = sorted(p.casualizacao.unidades, key=lambda u: ((u.bloco or 0), u.posicao))
    for i, u in enumerate(ordem, start=1):
        f = ult if i == len(ordem) else cel
        vals = [u.codigo, u.parcela, u.bloco or ""] + [x(u) for _, x in extras] + [trat[u.tratamento].codigo, ""] \
            + [""] * len(vars_) + [""]
        for j, v in enumerate(vals):
            ws.write(i, j, v, f)
    ws.freeze_panes(1, 0)
    ws.set_column(0, 0, 24)
    ws.set_column(1, len(cab) - 1, 13)
    wb.close()
    return buf.getvalue()


def arquivos_experimento(p, cj=None, variaveis: list[str] | None = None, opcoes=None) -> list[Arquivo]:
    from motor.exportacao.croqui_estatico import exportar_croqui
    from motor.exportacao.estilo import PREDEFINICOES
    from motor.exportacao.excel import exportar_excel
    from motor.exportacao.relatorio_pdf import relatorio_implantacao, relatorio_planejamento

    opcoes = opcoes or PREDEFINICOES["cientifico"]
    arqs = [
        Arquivo("Relatório de planejamento.pdf", relatorio_planejamento(p, opcoes), "application/pdf"),
        Arquivo("Relatório de implantação.pdf", relatorio_implantacao(p), "application/pdf"),
        Arquivo("Croqui.png", exportar_croqui(p.casualizacao, p.tratamentos, p.croqui, opcoes, "png", "figura", 300),
                "image/png"),
        Arquivo("Planilha do experimento", exportar_excel(p, variaveis, opcoes), XLSX, PLANILHA),
    ]
    geo_info = None
    if cj is not None:
        from motor.exportacao.plano_locacao import plano_locacao
        from motor.gis import crs, exportar

        lon, lat = cj.centro_geo
        geo_info = {"Centro (lat, lon)": f"{lat:.7f}, {lon:.7f}", "Azimute do eixo Y": f"{cj.geo.azimute:.2f}°",
                    "Sistema": f"{crs.nome_crs(cj.epsg)} (EPSG:{cj.epsg})",
                    "Google Earth": exportar.link_google_earth(lon, lat)}
        sub = "Mapas e GIS"
        arqs += [
            Arquivo(f"{p.meta.codigo}.kmz", exportar.kmz(cj), "application/vnd.google-earth.kmz", subpasta=sub),
            Arquivo("Plano de locação.pdf", plano_locacao(p, cj), "application/pdf", subpasta=sub),
            Arquivo(f"{p.meta.codigo}_shapefile_utm.zip", exportar.shapefile_zip(cj), "application/zip", subpasta=sub),
            Arquivo(f"{p.meta.codigo}.gpkg", exportar.geopackage(cj), "application/geopackage+sqlite3", subpasta=sub),
            Arquivo(f"{p.meta.codigo}.geojson", exportar.geojson(cj), "application/geo+json", subpasta=sub),
            Arquivo(f"{p.meta.codigo}_piquetes.csv", exportar.csv_camada(cj, "piquetes"), "text/csv", subpasta=sub),
        ]
    arqs += [
        Arquivo("Memorial descritivo", memorial_html(p, geo_info), HTML, DOC),
        Arquivo("Diário de campo", diario_html(p), HTML, DOC, uma_vez=True),
        Arquivo("Planilha de coleta", planilha_coleta(p, variaveis), XLSX, PLANILHA, uma_vez=True),
    ]
    return arqs


def caminho_experimento(p, raiz: str = "Exp-Ag") -> list[str]:
    projeto = (p.meta.projeto or "Sem projeto").strip()[:120]
    return [raiz, projeto, f"{p.meta.codigo} — {p.meta.titulo}"[:150]]
