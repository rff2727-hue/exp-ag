"""Painéis compostos: croqui interativo, tabela de casualização e exportações."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pandas as pd
import streamlit as st

from componentes.croqui_interativo import figura_croqui
from componentes.visual import mostradores, secao
from motor.exportacao.croqui_estatico import aviso_paleta, exportar_croqui
from motor.exportacao.estilo import NOMES_MODOS, NOMES_ROTULOS, PREDEFINICOES, fmt_m, fmt_num, romano
from motor.exportacao.excel import estrutura_extra, exportar_excel
from motor.exportacao.projeto_json import exportar_json
from motor.exportacao.relatorio_pdf import relatorio_implantacao, relatorio_planejamento
from motor.exportacao.texto_metodologico import descricao_en, descricao_pt
from motor.planejamento import Planejamento


def metricas_croqui(p: Planejamento) -> None:
    m = p.croqui.metricas
    if p.layout.tipo == "parcelas":
        mostradores([
            ("Unidades", str(m["n_unidades"]), "parcelas"),
            ("Parcela", f"{fmt_m(m['largura_parcela_m'])}×{fmt_m(m['comprimento_parcela_m'])}", "m"),
            ("Área da parcela", fmt_num(m["area_parcela_m2"]), "m²"),
            ("Área útil", fmt_num(m["area_util_m2"]), "m²"),
            ("Dimensões externas", f"{fmt_m(m['largura_total_m'])}×{fmt_m(m['comprimento_total_m'])}", "m"),
            ("Área total", fmt_num(m["area_total_m2"]), "m²"),
        ])
    else:
        mostradores([
            ("Unidades", str(m["n_unidades"]), "vasos"),
            ("Diâmetro", fmt_m(m["diametro_vaso_m"] * 100), "cm"),
            ("Entre centros", fmt_m(m["distancia_centros_m"] * 100), "cm"),
            ("Área ocupada", f"{fmt_m(m['largura_total_m'])}×{fmt_m(m['comprimento_total_m'])}", "m"),
        ])


def opcoes_visuais(p: Planejamento, k: str):
    c1, c2, c3 = st.columns(3)
    modo = c1.selectbox("Modo de visualização", list(NOMES_MODOS), format_func=NOMES_MODOS.get, key=f"{k}_modo",
                        help="Estatístico: cores por tratamento. Operacional: numeração para implantação. "
                             "Científico: croqui limpo para publicação. Sobre o mapa: aba Mapa e locação.")
    base = PREDEFINICOES[modo]
    cores = {"tratamento": "Tratamento", "bloco": "Bloco", "nenhum": "Sem cor"}
    if p.estrutura.e_fatorial:
        for f in p.estrutura.fatores:
            cores[f"fator:{f.nome}"] = f"Fator: {f.nome}"
    if p.delineamento.value != "DBC":
        cores.pop("bloco")
    padrao_cor = base.colorir_por if base.colorir_por in cores else "tratamento"
    colorir = c2.selectbox("Colorir por", list(cores), format_func=cores.get,
                           index=list(cores).index(padrao_cor), key=f"{k}_cor_{modo}")
    rotulo = c3.selectbox("Rótulo das unidades", list(NOMES_ROTULOS), format_func=NOMES_ROTULOS.get,
                          index=list(NOMES_ROTULOS).index(base.rotulo), key=f"{k}_rot_{modo}")
    c1, c2, c3, c4, c5 = st.columns(5)
    util = c1.toggle("Área útil", base.mostrar_area_util, key=f"{k}_util_{modo}",
                     disabled=p.layout.tipo == "vasos")
    blocos = c2.toggle("Contorno dos blocos", base.mostrar_blocos, key=f"{k}_bl_{modo}",
                       disabled=p.delineamento.value != "DBC")
    escala = c3.toggle("Escala e Norte", base.mostrar_escala, key=f"{k}_esc_{modo}")
    plantio = c4.toggle("Sentido de plantio", base.mostrar_plantio, key=f"{k}_pl_{modo}",
                        disabled=p.layout.tipo == "vasos")
    cotas = c5.toggle("Cotas (medidas)", base.mostrar_dimensoes, key=f"{k}_cot_{modo}",
                      help="Dimensões externas, da unidade, espaços entre unidades, entre blocos e bordaduras.")
    return replace(base, colorir_por=colorir, rotulo=rotulo, mostrar_area_util=util, mostrar_blocos=blocos,
                   mostrar_escala=escala, mostrar_norte=escala, mostrar_plantio=plantio, mostrar_dimensoes=cotas)


def painel_croqui(p: Planejamento, k: str, altura: int = 720):
    opcoes = opcoes_visuais(p, k)
    por_codigo = {u.codigo: u.numero for u in p.casualizacao.unidades}
    c1, c2 = st.columns([2, 1])
    busca = c1.multiselect("Localizar unidades", list(por_codigo), key=f"{k}_busca",
                           placeholder="Digite parte do código, parcela ou tratamento")
    destacar = {por_codigo[b] for b in busca}
    fig = figura_croqui(p.casualizacao, p.tratamentos, p.croqui, opcoes, destacar, altura)
    ev = st.plotly_chart(
        fig, width="stretch", key=f"{k}_graf", on_select="rerun", selection_mode=("points", "box", "lasso"),
        config={"displaylogo": False, "scrollZoom": True,
                "modeBarButtonsToRemove": ["toImage", "autoScale2d", "select2d", "lasso2d"]},
    )
    c2.caption("Role para ampliar, arraste para mover. Clique ou use a seleção retangular/laço para "
               "consultar unidades. Duplo clique restaura a vista.")
    aviso = aviso_paleta(len(p.tratamentos)) if opcoes.colorir_por == "tratamento" else None
    if aviso:
        st.caption(aviso)
    selec = set()
    try:
        for pt in ev.selection.points:
            cd = pt.get("customdata")
            if cd is not None:
                selec.add(int(cd[0] if isinstance(cd, (list, tuple)) else cd))
    except AttributeError:
        pass
    selec |= destacar
    if selec:
        tabela_unidades(p, selec)
    return opcoes


def tabela_unidades(p: Planejamento, numeros: set[int] | None = None, altura: int | None = None) -> pd.DataFrame:
    trat = {t.numero: t for t in p.tratamentos}
    pos = {c.numero: c for c in p.croqui.celulas}
    fatores = [f.nome for f in p.estrutura.fatores] if p.estrutura.e_fatorial else []
    extras = estrutura_extra(p)
    linhas = []
    for u in p.casualizacao.unidades:
        if numeros is not None and u.numero not in numeros:
            continue
        t = trat[u.tratamento]
        c = pos[u.numero]
        linhas.append({
            "Unidade": u.codigo, "Parcela": u.parcela,
            **({"Bloco": romano(u.bloco)} if u.bloco else {}),
            **{n: f(u) for n, f in extras},
            "Repetição": u.repeticao, "Trat.": t.codigo, "Tratamento": t.rotulo,
            **{f: t.niveis.get(f, "—") for f in fatores},
            "Linha no croqui": c.linha + 1, "Coluna no croqui": c.coluna + 1,
        })
    df = pd.DataFrame(linhas)
    st.dataframe(df, hide_index=True, width="stretch",
                 height=altura or min(38 + 35 * len(linhas), 420))
    return df


def _chave(p: Planejamento, *extras) -> str:
    base = f"{p.meta.codigo}|{p.versao}|{p.casualizacao.semente}|{sorted(p.layout.para_dict().items())}|{extras}"
    base += str(sorted(vars(p.meta).items()))
    return hashlib.sha1(base.encode()).hexdigest()[:16]


def painel_exportacoes(p: Planejamento, k: str, opcoes=None) -> None:
    opcoes = opcoes or PREDEFINICOES["cientifico"]
    cache = st.session_state.setdefault("_exportacoes", {})
    nome = f"{p.meta.codigo}_v{p.versao}"

    def botao(rotulo: str, chave: str, gerar, arquivo: str, mime: str, primario: bool = False, ajuda: str = ""):
        if chave in cache:
            st.download_button(f"Baixar {rotulo}", cache[chave], arquivo, mime, key=f"{k}_dl_{chave}",
                               type="primary" if primario else "secondary", width="stretch", help=ajuda)
        elif st.button(f"Gerar {rotulo}", key=f"{k}_g_{chave}", width="stretch", help=ajuda):
            with st.spinner(f"Gerando {rotulo}…"):
                cache[chave] = gerar()
            while len(cache) > 12:  # limita a memória da sessão
                cache.pop(next(iter(cache)))
            st.rerun()

    secao("Relatórios")
    c1, c2, c3 = st.columns(3)
    with c1:
        botao("relatório de planejamento (PDF)", "plan_" + _chave(p, opcoes),
              lambda: relatorio_planejamento(p, opcoes), f"{nome}_planejamento.pdf", "application/pdf", True,
              "Identificação, tratamentos, quadro de GL, dimensões, croqui, casualização e metodologia.")
    with c2:
        botao("relatório de implantação (PDF)", "impl_" + _chave(p),
              lambda: relatorio_implantacao(p), f"{nome}_implantacao.pdf", "application/pdf",
              ajuda="Croqui operacional e sequência de implantação para a equipe de campo.")
    with c3:
        vars_txt = st.text_input("Variáveis da planilha de campo (separe por vírgula)", key=f"{k}_vars",
                                 placeholder="Altura (cm), Massa seca (g)")
        variaveis = [v.strip() for v in vars_txt.split(",") if v.strip()]
        botao("planilha Excel", "xlsx_" + _chave(p, variaveis, opcoes.colorir_por),
              lambda: exportar_excel(p, variaveis, opcoes), f"{nome}.xlsx",
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              ajuda="Resumo, tratamentos, casualização (formato longo), croqui em grade, planilha de campo, "
                    "modelo de coleta, quadro de GL e metodologia.")

    secao("Croqui")
    c1, c2, c3 = st.columns(3)
    pagina = c1.selectbox("Formato", ["figura", "A4", "A3"], key=f"{k}_pag",
                          format_func={"figura": "Figura (17,4 cm, para artigos)", "A4": "Página A4",
                                       "A3": "Página A3"}.get)
    dpi = c2.selectbox("Resolução do PNG", [300, 600], key=f"{k}_dpi", format_func=lambda d: f"{d} dpi")
    rodape = c3.toggle("Incluir dimensões no rodapé", True, key=f"{k}_rod")
    st.caption(f"Exporta o croqui com as opções do modo selecionado ({NOMES_MODOS[opcoes.modo].lower()}).")
    c1, c2, c3 = st.columns(3)
    for col, fmt, mime in ((c1, "png", "image/png"), (c2, "svg", "image/svg+xml"), (c3, "pdf", "application/pdf")):
        with col:
            botao(f"croqui {fmt.upper()}", f"cq_{fmt}_" + _chave(p, opcoes, pagina, dpi, rodape),
                  lambda fmt=fmt: exportar_croqui(p.casualizacao, p.tratamentos, p.croqui, opcoes, fmt,
                                                  pagina, dpi, rodape),
                  f"{nome}_croqui.{fmt}", mime)

    secao("Dados")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("Baixar projeto completo (JSON)", exportar_json(p), f"{nome}.json", "application/json",
                           key=f"{k}_json", width="stretch",
                           help="Backup integral: pode ser importado em outra instalação do aplicativo.")
    with c2:
        csv = tabela_csv(p)
        st.download_button("Baixar casualização (CSV)", csv, f"{nome}_casualizacao.csv", "text/csv",
                           key=f"{k}_csv", width="stretch")

    secao("Descrição metodológica")
    lingua = st.radio("Idioma", ["Português", "English"], horizontal=True, key=f"{k}_ling",
                      label_visibility="collapsed")
    texto = descricao_pt(p) if lingua == "Português" else descricao_en(p)
    st.text_area("Texto editável, derivado apenas das configurações do experimento", texto, height=190,
                 key=f"{k}_met_{lingua}_{_chave(p)}")


def tabela_csv(p: Planejamento) -> bytes:
    trat = {t.numero: t for t in p.tratamentos}
    fatores = [f.nome for f in p.estrutura.fatores] if p.estrutura.e_fatorial else []
    linhas = []
    for u in p.casualizacao.unidades:
        t = trat[u.tratamento]
        linhas.append({"experimento": p.meta.codigo, "unidade": u.codigo, "parcela": u.parcela,
                       "bloco": u.bloco or "", "repeticao": u.repeticao, "tratamento_n": t.numero,
                       "tratamento_codigo": t.codigo, "tratamento": t.rotulo,
                       **{f: t.niveis.get(f, "") for f in fatores}})
    return pd.DataFrame(linhas).to_csv(index=False).encode("utf-8-sig")
