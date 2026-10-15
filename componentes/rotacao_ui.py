"""Aba "Posições e rotação": posição vigente dos vasos, novos movimentos, plano de rotações e histórico."""

from __future__ import annotations

import io
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from componentes.croqui_interativo import figura_croqui
from componentes.visual import secao
from motor.exportacao.croqui_estatico import exportar_croqui
from motor.exportacao.estilo import PREDEFINICOES, TRAVA_MPL, OpcoesVisuais
from motor.geometria.layout import Croqui, aplicar_posicoes
from motor.geometria.rotacao import (
    TIPOS,
    ErroRotacao,
    aplicar_tipo,
    posicao_atual,
    tipos_permitidos,
    verificar_mapa,
)
from motor.planejamento import Planejamento


def tabela_posicoes(p: Planejamento, mapa: dict[int, int]) -> pd.DataFrame:
    """Onde está cada unidade: vaga, linha e coluna físicas, bancada."""
    vaga = {c.vaga: c for c in p.croqui.celulas}
    trat = {t.numero: t for t in p.tratamentos}
    linhas = []
    for u in sorted(p.casualizacao.unidades, key=lambda u: mapa[u.numero]):
        c = vaga[mapa[u.numero]]
        linhas.append({"Vaga": c.vaga, "Bancada": c.bancada or "", "Linha": c.linha + 1, "Coluna": c.coluna + 1,
                       "Unidade": u.codigo, "Parcela": u.parcela, "Tratamento": trat[u.tratamento].codigo,
                       "Vaga original": u.numero})
    return pd.DataFrame(linhas)


def _plano_excel(p: Planejamento, mapas: list[tuple[str, dict[int, int]]]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        resumo = pd.DataFrame([{"Rotação": i, "Data": d} for i, (d, _) in enumerate(mapas, start=1)])
        resumo.to_excel(w, sheet_name="Plano", index=False)
        for i, (d, m) in enumerate(mapas, start=1):
            tabela_posicoes(p, m).to_excel(w, sheet_name=f"Rotação {i} ({d[:5].replace('/', '-')})", index=False)
    return buf.getvalue()


def aba_rotacao(p: Planejamento, exp_id: int, repo, autor: str, opcoes: OpcoesVisuais) -> None:
    cas = p.casualizacao
    permitidos = tipos_permitidos(cas)
    if not permitidos:
        st.info("Parcelas em faixas não são remanejadas: as faixas são estruturas fixas de campo.")
        return
    if p.layout.tipo != "vasos":
        st.caption("A rotação é pensada para vasos e bandejas; para parcelas de campo, registre aqui apenas "
                   "remanejamentos excepcionais.")
    movs = repo.movimentos(exp_id)
    atual = posicao_atual(cas, movs)
    croqui_atual: Croqui = aplicar_posicoes(p.croqui, atual)
    rest = {"DBC": "cada vaso permanece nas vagas do seu bloco",
            "DIC": "qualquer vaso pode ir para qualquer vaga",
            "QL": "só linhas ou colunas inteiras se movem, preservando o quadrado latino"}[p.delineamento.value]
    if p.arranjo.value == "subdividida":
        rest += "; a parcela principal se move inteira"
    st.caption(f"A identidade de cada vaso (código, tratamento) nunca muda; muda só a vaga. Restrição: {rest}.")

    secao("Posição atual")
    st.markdown(f"<span class='ae-nota'>{len(movs)} movimento(s) registrado(s)"
                + (f"; o último em {movs[-1]['data'] or 's/ data'} ({TIPOS.get(movs[-1]['tipo'], movs[-1]['tipo'])})"
                   if movs else "; vasos na posição da casualização") + "</span>", unsafe_allow_html=True)
    st.plotly_chart(figura_croqui(cas, p.tratamentos, croqui_atual, opcoes), width="stretch",
                    key=f"rot_atual_{exp_id}", config={"displaylogo": False, "scrollZoom": True})
    c1, c2, c3 = st.columns(3)
    c1.download_button("Croqui atual (PDF A4)", lambda: _croqui_bytes(p, croqui_atual, "pdf"),
                       f"{p.meta.codigo}_posicao_atual.pdf", "application/pdf", width="stretch",
                       key=f"rot_pdf_{exp_id}_{len(movs)}")
    c2.download_button("Croqui atual (PNG)", lambda: _croqui_bytes(p, croqui_atual, "png"),
                       f"{p.meta.codigo}_posicao_atual.png", "image/png", width="stretch",
                       key=f"rot_png_{exp_id}_{len(movs)}")
    c3.download_button("Onde está cada vaso (CSV)", tabela_posicoes(p, atual).to_csv(index=False).encode("utf-8-sig"),
                       f"{p.meta.codigo}_posicoes.csv", "text/csv", width="stretch", key=f"rot_csv_{exp_id}")

    secao("Novo movimento")
    c1, c2, c3 = st.columns([2, 1, 1])
    tipo = c1.selectbox("Tipo", permitidos, format_func=TIPOS.get, key=f"rot_tipo_{exp_id}")
    k = 1
    if tipo in ("deslocamento", "linhas", "colunas"):
        k = int(c2.number_input("Avançar quantas posições (k)", 1, 1000, 1, key=f"rot_k_{exp_id}"))
    data_mov = c3.date_input("Data", value=date.today(), format="DD/MM/YYYY", key=f"rot_data_{exp_id}")
    unidades = None
    if tipo == "troca":
        cods = {u.codigo: u.numero for u in cas.unidades}
        d1, d2 = st.columns(2)
        a = d1.selectbox("Unidade 1", list(cods), key=f"rot_u1_{exp_id}")
        b = d2.selectbox("Unidade 2", list(cods), index=min(1, len(cods) - 1), key=f"rot_u2_{exp_id}")
        unidades = (cods[a], cods[b])
    descricao = st.text_input("Descrição (opcional)", key=f"rot_desc_{exp_id}",
                              placeholder="Ex.: rotação semanal; vaso 12 quebrado e substituído")
    try:
        novo = aplicar_tipo(tipo, atual, cas, p.croqui, k=k, semente=cas.semente, rodada=len(movs) + 1,
                            unidades=unidades)
        problemas = verificar_mapa(novo, cas, p.croqui)
    except ErroRotacao as exc:
        st.error(str(exc))
        novo, problemas = None, ["inválido"]
    if novo is not None and not problemas:
        mudam = sum(1 for n in novo if novo[n] != atual[n])
        with st.expander(f"Prévia — {mudam} vaso(s) mudam de vaga", expanded=False):
            st.plotly_chart(figura_croqui(cas, p.tratamentos, aplicar_posicoes(p.croqui, novo), opcoes),
                            width="stretch", key=f"rot_prev_{exp_id}", config={"displaylogo": False})
        if st.button("Registrar movimento", type="primary", key=f"rot_ok_{exp_id}", disabled=mudam == 0):
            repo.registrar_movimento(exp_id, novo, tipo, descricao.strip(), data_mov.isoformat(), autor)
            st.session_state["_msg"] = "Movimento registrado."
            st.rerun()
    elif problemas and problemas != ["inválido"]:
        st.error("; ".join(problemas))

    with st.expander("Plano de rotações (para imprimir e seguir na casa de vegetação)"):
        c1, c2, c3, c4 = st.columns(4)
        inicio = c1.date_input("Primeira rotação", value=date.today() + timedelta(days=7), format="DD/MM/YYYY",
                               key=f"plan_ini_{exp_id}")
        intervalo = int(c2.number_input("A cada (dias)", 1, 120, 7, key=f"plan_int_{exp_id}"))
        n = int(c3.number_input("Número de rotações", 1, 52, 6, key=f"plan_n_{exp_id}"))
        tipos_plano = [t for t in permitidos if t != "troca"]
        tipo_p = c4.selectbox("Tipo", tipos_plano, format_func=lambda t: TIPOS[t].split(" (")[0],
                              key=f"plan_tipo_{exp_id}")
        mapas = []
        m = atual
        for i in range(n):
            m = aplicar_tipo(tipo_p, m, cas, p.croqui, k=1, semente=cas.semente, rodada=len(movs) + 1 + i)
            mapas.append(((inicio + timedelta(days=intervalo * i)).strftime("%d/%m/%Y"), m))
        st.caption(f"{n} rotações de {inicio:%d/%m/%Y} a {(inicio + timedelta(days=intervalo * (n - 1))):%d/%m/%Y}. "
                   "A planilha traz, para cada data, a vaga de cada vaso. Registre cada rotação aqui ao executá-la.")
        st.download_button("Baixar plano (Excel)", lambda: _plano_excel(p, mapas),
                           f"{p.meta.codigo}_plano_rotacao.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key=f"plan_xlsx_{exp_id}")

    secao("Histórico de movimentos")
    if not movs:
        st.caption("Nenhum movimento registrado.")
        return
    st.dataframe(pd.DataFrame([{"Nº": m["ordem"], "Data": m["data"], "Tipo": TIPOS.get(m["tipo"], m["tipo"]),
                                "Descrição": m["descricao"], "Autor": m["autor"]} for m in reversed(movs)]),
                 hide_index=True, width="stretch")
    if st.button("Desfazer o último movimento", key=f"rot_desf_{exp_id}"):
        repo.desfazer_movimento(exp_id, autor)
        st.session_state["_msg"] = "Último movimento desfeito."
        st.rerun()


def _croqui_bytes(p: Planejamento, croqui: Croqui, fmt: str) -> bytes:
    with TRAVA_MPL:
        return exportar_croqui(p.casualizacao, p.tratamentos, croqui, PREDEFINICOES["operacional"], fmt,
                               "A4" if fmt == "pdf" else "figura", 300)
