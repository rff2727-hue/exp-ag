"""Exportação do planejamento para Excel (.xlsx), com tabelas no padrão de
publicação: filete mais espesso acima e abaixo da tabela, filete fino sob o
cabeçalho, apenas o texto do cabeçalho em negrito, sem grade.
"""

from __future__ import annotations

import io
from datetime import datetime

import xlsxwriter

from motor.estatistica.delineamentos import quadro_gl
from motor.estatistica.tratamentos import descrever_tipo
from motor.exportacao.estilo import (
    OpcoesVisuais,
    atribuir_cores,
    cor_texto,
    romano,
)
from motor.exportacao.texto_metodologico import descricao_en, descricao_pt
from motor.planejamento import Planejamento

FONTE = "Roboto"


class _Estilos:
    def __init__(self, wb: xlsxwriter.Workbook) -> None:
        base = {"font_name": FONTE, "font_size": 10, "valign": "vcenter"}
        self.base = base
        self.wb = wb
        self.titulo = wb.add_format({**base, "font_size": 13})
        self.sub = wb.add_format({**base, "font_color": "#5B6166", "italic": True})
        self.texto = wb.add_format({**base, "text_wrap": True, "valign": "top"})
        self._cache: dict = {}

    def cel(self, cab: bool = False, topo: bool = False, base_: bool = False, num: str | None = None,
            alinhar: str = "left") -> xlsxwriter.format.Format:
        chave = (cab, topo, base_, num, alinhar)
        if chave not in self._cache:
            f = {**self.base, "align": alinhar}
            if cab:
                f.update({"bold": True, "top": 2, "bottom": 1})
            if base_:
                f["bottom"] = 2
            if num:
                f["num_format"] = num
            self._cache[chave] = self.wb.add_format(f)
        return self._cache[chave]


def _tabela(ws, est: _Estilos, linha0: int, col0: int, cabecalho: list[str], linhas: list[list],
            formatos: list[str | None] | None = None, larguras: list[int] | None = None) -> int:
    """Escreve uma tabela no padrão definido. Retorna a próxima linha livre."""
    formatos = formatos or [None] * len(cabecalho)
    for j, h in enumerate(cabecalho):
        alin = "right" if formatos[j] else "left"
        ws.write(linha0, col0 + j, h, est.cel(cab=True, alinhar=alin))
    for i, ln in enumerate(linhas):
        ultima = i == len(linhas) - 1
        for j, v in enumerate(ln):
            alin = "right" if formatos[j] else "left"
            ws.write(linha0 + 1 + i, col0 + j, "" if v is None else v,
                     est.cel(base_=ultima, num=formatos[j], alinhar=alin))
    if not linhas:  # tabela vazia: fecha com o filete inferior
        for j in range(len(cabecalho)):
            ws.write_blank(linha0 + 1, col0 + j, None, est.cel(base_=True))
    if larguras:
        for j, w in enumerate(larguras):
            ws.set_column(col0 + j, col0 + j, w)
    return linha0 + 1 + max(len(linhas), 1) + 1


def estrutura_extra(p: Planejamento) -> list[tuple[str, object]]:
    """Colunas próprias da estrutura: parcela principal/subparcela ou linha/coluna."""
    from motor.dominio import Arranjo, Delineamento

    if p.arranjo is Arranjo.SUBDIVIDIDA:
        return [("Parcela principal", lambda u: u.principal), ("Subparcela", lambda u: u.sub)]
    if p.arranjo is Arranjo.FAIXAS or p.delineamento is Delineamento.QL:
        return [("Linha", lambda u: u.linha), ("Coluna", lambda u: u.coluna)]
    return []


def exportar_excel(p: Planejamento, variaveis: list[str] | None = None,
                   opcoes: OpcoesVisuais | None = None) -> bytes:
    opcoes = opcoes or OpcoesVisuais()
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    wb.set_properties({"title": f"{p.meta.codigo} — {p.meta.titulo}", "author": p.meta.responsavel,
                       "comments": "Gerado por Exp-Ag"})
    est = _Estilos(wb)
    m = p.meta
    cas = p.casualizacao
    cr = p.croqui
    trat = {t.numero: t for t in p.tratamentos}
    fatores = [f.nome for f in p.estrutura.fatores] if len(p.estrutura.fatores) > 1 else []

    # 1. Resumo -------------------------------------------------------------
    ws = wb.add_worksheet("Resumo")
    ws.hide_gridlines(2)
    ws.write(0, 0, f"{m.codigo} — {m.titulo}", est.titulo)
    ws.write(1, 0, f"Planejamento versão {p.versao} · gerado em {datetime.now():%d/%m/%Y %H:%M}", est.sub)
    mt = cr.metricas
    itens = [
        ("Projeto", m.projeto), ("Instituição", m.instituicao), ("Responsável", m.responsavel),
        ("Colaboradores", m.colaboradores), ("Cultura", m.cultura), ("Cultivar", m.cultivar),
        ("Ambiente", m.ambiente), ("Local", m.local), ("Município/UF", f"{m.municipio} {m.uf}".strip()),
        ("Safra", m.safra), ("Data prevista", m.data_prevista), ("Data de implantação", m.data_implantacao),
        ("Delineamento", f"{p.delineamento.nome} ({p.delineamento.value})"
                         + (f" em {p.arranjo.nome}" if p.arranjo.value != "convencional" else "")),
        ("Estrutura de tratamentos", (f"Fatorial {p.estrutura.esquema}" if p.estrutura.e_fatorial
                                      else f"{len(p.tratamentos)} tratamentos")),
        ("Tratamentos", len(p.tratamentos)), ("Repetições", p.repeticoes),
        ("Unidades experimentais", cas.n_unidades),
        ("Semente", cas.semente), ("Algoritmo de casualização", cas.algoritmo),
        ("Padrão de identificação", p.padrao_codigo),
    ]
    if p.layout.tipo == "parcelas":
        itens += [
            ("Parcela (largura × comprimento, m)", f"{mt['largura_parcela_m']:g} × {mt['comprimento_parcela_m']:g}"),
            ("Área da parcela (m²)", round(mt["area_parcela_m2"], 4)),
            ("Área útil (m²)", round(mt["area_util_m2"], 4)),
            ("Área total do experimento (m²)", round(mt["area_total_m2"], 2)),
            ("Dimensões externas (m)", f"{mt['largura_total_m']:g} × {mt['comprimento_total_m']:g}"),
        ]
    else:
        itens += [
            ("Diâmetro do vaso (m)", mt["diametro_vaso_m"]),
            ("Distância entre centros (m)", round(mt["distancia_centros_m"], 4)),
            ("Área ocupada (m)", f"{mt['largura_total_m']:g} × {mt['comprimento_total_m']:g}"),
        ]
    itens += [("Objetivos", m.objetivos), ("Hipóteses", m.hipoteses), ("Observações", m.observacoes)]
    _tabela(ws, est, 3, 0, ["Item", "Valor"], [[a, b] for a, b in itens if b not in ("", None)], larguras=[34, 70])

    # 2. Tratamentos ----------------------------------------------------------
    ws = wb.add_worksheet("Tratamentos")
    ws.hide_gridlines(2)
    cab = ["Nº", "Código", "Tratamento"] + fatores + ["Tipo", "Papel"]
    linhas = [[t.numero, t.codigo, t.rotulo] + [t.niveis.get(f, "—") for f in fatores]
              + [descrever_tipo(t, p.estrutura.e_fatorial), t.papel.value] for t in p.tratamentos]
    _tabela(ws, est, 0, 0, cab, linhas, ["0"] + [None] * (len(cab) - 1),
            [6, 9, 40] + [18] * len(fatores) + [11, 18])

    # 3. Casualização (formato longo, uma linha por unidade experimental) ------
    ws = wb.add_worksheet("Casualização")
    ws.hide_gridlines(2)
    ws.freeze_panes(1, 0)
    pos = {c.numero: c for c in cr.celulas}
    extras = estrutura_extra(p)
    cab = (["Projeto", "Experimento", "Ambiente", "Local", "Unidade", "Parcela", "Bloco"] + [n for n, _ in extras]
           + ["Repetição", "Tratamento nº", "Tratamento código", "Tratamento"] + fatores
           + ["Linha no croqui", "Coluna no croqui", "X centro (m)", "Y centro (m)"])
    linhas = []
    for u in cas.unidades:
        t = trat[u.tratamento]
        c = pos[u.numero]
        linhas.append([m.projeto, m.codigo, m.ambiente, m.local, u.codigo, u.parcela, u.bloco or ""]
                      + [f(u) for _, f in extras]
                      + [u.repeticao, t.numero, t.codigo, t.rotulo] + [t.niveis.get(f, "—") for f in fatores]
                      + [c.linha_grade + 1, c.coluna_grade + 1, round(c.centro[0], 3), round(c.centro[1], 3)])
    fmts = ([None] * 6 + ["0"] + ["0"] * len(extras) + ["0", "0", None, None] + [None] * len(fatores)
            + ["0", "0", "0.000", "0.000"])
    _tabela(ws, est, 0, 0, cab, linhas, fmts,
            [14, 13, 14, 14, 24, 8, 7] + [13] * len(extras) + [10, 12, 16, 32] + [16] * len(fatores)
            + [14, 15, 12, 12])
    ws.autofilter(0, 0, len(linhas), len(cab) - 1)

    # 4. Croqui em grade --------------------------------------------------------
    _aba_croqui(wb, est, p, opcoes)

    # 5. Planilha de campo (formato largo) --------------------------------------
    ws = wb.add_worksheet("Planilha de campo")
    ws.hide_gridlines(2)
    ws.freeze_panes(1, 0)
    vars_ = [v.strip() for v in (variaveis or []) if v.strip()] or ["Variável 1", "Variável 2", "Variável 3"]
    cab = ["Unidade", "Parcela", "Bloco"] + [n for n, _ in extras] + ["Tratamento", "Data"] + vars_ + ["Observações"]
    ordem = sorted(cas.unidades, key=lambda u: ((u.bloco or 0), u.posicao))
    linhas = [[u.codigo, u.parcela, u.bloco or ""] + [f(u) for _, f in extras]
              + [trat[u.tratamento].codigo, ""] + [""] * len(vars_) + [""] for u in ordem]
    _tabela(ws, est, 0, 0, cab, linhas,
            larguras=[24, 8, 7] + [12] * len(extras) + [11, 11] + [14] * len(vars_) + [30])
    ws.set_landscape()
    ws.repeat_rows(0)
    ws.fit_to_pages(1, 0)

    # 6. Modelo de coleta em formato longo (para análise) ----------------------
    ws = wb.add_worksheet("Coleta (formato longo)")
    ws.hide_gridlines(2)
    cab = ["Unidade", "Data", "Variável", "Subamostra", "Valor", "Unidade de medida", "Responsável", "Observação"]
    linhas = [[u.codigo, "", "", 1, "", "", "", ""] for u in ordem]
    _tabela(ws, est, 0, 0, cab, linhas, larguras=[24, 11, 18, 11, 10, 16, 16, 30])
    ws.write(len(linhas) + 3, 0, "Subamostras são medidas dentro da mesma unidade experimental e não constituem "
             "repetições independentes.", est.sub)

    # 7. Quadro de graus de liberdade ------------------------------------------
    ws = wb.add_worksheet("Quadro de GL")
    ws.hide_gridlines(2)
    gl = quadro_gl(p.delineamento, p.estrutura, p.repeticoes, p.arranjo)
    _tabela(ws, est, 0, 0, ["Fonte de variação", "GL", "Estrato de erro"], [[g.fonte, g.gl, g.estrato] for g in gl],
            [None, "0", None], [36, 8, 20])
    ws.write(len(gl) + 3, 0, "Quadro esperado para a análise de variância, antes da coleta dos dados.", est.sub)

    # 8. Metodologia -------------------------------------------------------------
    ws = wb.add_worksheet("Metodologia")
    ws.hide_gridlines(2)
    ws.set_column(0, 0, 110)
    ws.write(0, 0, "Descrição metodológica (português)", est.cel(cab=True))
    ws.write(1, 0, descricao_pt(p), est.texto)
    ws.set_row(1, 150)
    ws.write(3, 0, "Methods description (English)", est.cel(cab=True))
    ws.write(4, 0, descricao_en(p), est.texto)
    ws.set_row(4, 130)

    wb.close()
    return buf.getvalue()


def _aba_croqui(wb, est: _Estilos, p: Planejamento, opcoes: OpcoesVisuais) -> None:
    ws = wb.add_worksheet("Croqui")
    ws.hide_gridlines(2)
    cas, cr = p.casualizacao, p.croqui
    cores, _, legenda = atribuir_cores(cas, p.tratamentos, opcoes.colorir_por if opcoes.colorir_por != "nenhum"
                                       else "tratamento")
    por_u = {u.numero: u for u in cas.unidades}
    trat = {t.numero: t for t in p.tratamentos}
    ws.write(0, 0, f"Croqui — {p.meta.codigo} (vista em grade, sem rotação; topo = primeira linha)", est.titulo)
    L0, C0 = 3, 1
    max_c = max(c.coluna_grade for c in cr.celulas)
    max_l = max(c.linha_grade for c in cr.celulas)
    ws.set_column(0, 0, 9)
    ws.set_column(C0, C0 + max_c, 9.5)
    for r in range(L0, L0 + max_l + 1):
        ws.set_row(r, 34)
    cache: dict[str, object] = {}
    for c in cr.celulas:
        u = por_u[c.numero]
        cor = cores[c.numero]
        if cor not in cache:
            cache[cor] = wb.add_format({"font_name": FONTE, "font_size": 9, "align": "center", "valign": "vcenter",
                                        "text_wrap": True, "bg_color": cor, "font_color": cor_texto(cor),
                                        "border": 1, "border_color": "#3A3D40"})
        ws.write(L0 + c.linha_grade, C0 + c.coluna_grade, f"{u.parcela}\n{trat[u.tratamento].codigo}", cache[cor])
    # rótulos de bloco
    rot = wb.add_format({"font_name": FONTE, "font_size": 10, "align": "center", "font_color": "#5B6166"})
    blocos: dict[int, list] = {}
    for c in cr.celulas:
        if c.bloco is not None:
            blocos.setdefault(c.bloco, []).append(c)
    for b, cels in blocos.items():
        if p.layout.arranjo_blocos == "horizontal":
            c_min = min(x.coluna_grade for x in cels)
            c_max = max(x.coluna_grade for x in cels)
            r_lab = L0 + min(x.linha_grade for x in cels) - 1
            if c_max > c_min:
                ws.merge_range(r_lab, C0 + c_min, r_lab, C0 + c_max, f"Bloco {romano(b)}", rot)
            else:
                ws.write(r_lab, C0 + c_min, f"Bloco {romano(b)}", rot)
        else:
            r_min = min(x.linha_grade for x in cels)
            c_min = min(x.coluna_grade for x in cels)
            ws.write(L0 + r_min, C0 + c_min - 1, f"Bloco {romano(b)}", rot)
    # legenda
    lin = L0 + max_l + 2
    ws.write(lin, C0, "Legenda", est.cel(cab=True))
    for i, (txt, cor) in enumerate(legenda):
        f = wb.add_format({"bg_color": cor, "border": 1, "border_color": "#3A3D40"})
        ws.write_blank(lin + 1 + i, C0, None, f)
        ws.write(lin + 1 + i, C0 + 1, txt, wb.add_format({"font_name": FONTE, "font_size": 9}))
    ws.set_landscape()
    ws.fit_to_pages(1, 1)
