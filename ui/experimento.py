"""Área de trabalho do experimento aberto."""

from __future__ import annotations

import copy

import pandas as pd
import streamlit as st

from aplicacao.rascunho import planejamento_de, rascunho_de_planejamento
from componentes.drive_ui import botao_drive_experimento
from componentes.editor_arraste import editor_arraste
from componentes.etiquetas_ui import aba_etiquetas
from componentes.formularios import (
    editor_estrutura,
    editor_layout,
    formulario_casualizacao,
    formulario_delineamento,
    formulario_meta,
    itens_por_linha_max,
    resumo_estatistico,
)
from componentes.mapa_ui import aba_mapa
from componentes.paineis import metricas_croqui, painel_croqui, painel_exportacoes, tabela_unidades
from componentes.rotacao_ui import aba_rotacao
from componentes.visual import mostradores, secao
from dados.repositorios.experimentos import ErroRepositorio
from motor.casualizacao.casualizador import descrever_algoritmo
from motor.casualizacao.gerador import SEMENTE_MAX, semente_aleatoria
from motor.estatistica.delineamentos import quadro_gl
from motor.estatistica.tratamentos import descrever_tipo
from motor.geometria.layout import ConfigLayout
from motor.planejamento import ErroPlanejamento, Metadados
from ui.estado import PAGINAS, autor, avisar_depois, definir_exp_ativo, exp_ativo, repositorio

repo = repositorio()
ss = st.session_state
exp_id = exp_ativo()

lista = repo.listar(incluir_arquivados=True)
if not lista:
    st.title("Experimento aberto")
    st.info("Ainda não há experimentos. Crie o primeiro em **Novo experimento**.")
    if st.button("Novo experimento", type="primary"):
        st.switch_page(PAGINAS["novo"])
    st.stop()

ids = [e.id for e in lista]
rotulos = {e.id: f"{e.codigo} — {e.titulo}" + (" (arquivado)" if e.arquivado else "") for e in lista}
if exp_id not in ids:
    exp_id = ids[0]
escolhido = st.selectbox("Experimento", ids, index=ids.index(exp_id), format_func=rotulos.get,
                         label_visibility="collapsed")
if escolhido != exp_ativo():
    definir_exp_ativo(escolhido)
    st.rerun()

try:
    p = repo.carregar(escolhido)
except ErroRepositorio as exc:
    st.error(f"Não foi possível carregar o experimento: {exc}")
    st.stop()
resumo = next(e for e in lista if e.id == escolhido)

st.title(f"{p.meta.codigo} — {p.meta.titulo}")
st.markdown(
    f"<span class='ae-nota'>Projeto {resumo.projeto} · {p.delineamento.nome}"
    + (f" em {p.arranjo.nome}" if p.arranjo.value != "convencional" else "") + " · "
    + (f"fatorial {p.estrutura.esquema}" if p.estrutura.e_fatorial else f"{len(p.tratamentos)} tratamentos")
    + f" · {p.repeticoes} repetições · versão {p.versao} · semente {p.casualizacao.semente} · "
      f"status: {resumo.status}</span>",
    unsafe_allow_html=True,
)

# QR Code de etiqueta: ?exp=ID&ue=CÓDIGO destaca a unidade
ue = st.query_params.get("ue")
if ue:
    alvo = next((u for u in p.casualizacao.unidades if u.codigo == ue), None)
    if alvo is None:
        st.warning(f"A unidade {ue} não pertence à versão ativa deste experimento.")
    else:
        t_alvo = next(t for t in p.tratamentos if t.numero == alvo.tratamento)
        st.success(f"**{alvo.codigo}** — parcela {alvo.parcela}"
                   + (f" · bloco {alvo.bloco}" if alvo.bloco else "") + f" · repetição {alvo.repeticao} · "
                   f"**{t_alvo.codigo} — {t_alvo.rotulo}**", icon=":material/qr_code_scanner:")
        st.session_state.setdefault(f"ex{escolhido}_cq_busca", [alvo.codigo])

abas = st.tabs(["Croqui", "Mapa e locação", "Casualização", "Tratamentos e delineamento", "Posições e rotação",
                "Etiquetas", "Exportações", "Informações gerais", "Versões e histórico"])
aba_croqui, aba_mapa_, aba_cas, aba_trat, aba_pos, aba_etq, aba_exp, aba_info, aba_hist = abas

# ------------------------------------------------------------------ croqui
with aba_croqui:
    metricas_croqui(p)
    opcoes = painel_croqui(p, f"ex{escolhido}_cq")
    with st.expander("Ajustar disposição física (não altera a casualização)"):
        st.caption("Dimensões, espaçamentos, colunas, arranjo dos blocos, serpentina e rotação mudam apenas a "
                   "posição física das unidades. Tratamentos, blocos e identificadores são preservados.")
        chave = f"lay_{escolhido}_{p.versao}"
        if chave in ss and ss.get(chave + "_base") != p.layout.para_dict():
            ss.pop(chave, None)                                  # disposição salva em outro lugar (ex.: mapa)
            ss[chave + "_v"] = ss.get(chave + "_v", 0) + 1
        if chave not in ss:
            ss[chave] = rascunho_de_planejamento(p)
            ss[chave + "_base"] = p.layout.para_dict()
        rl = ss[chave]
        n_bloco = itens_por_linha_max(p)
        erro = editor_layout(rl, f"{chave}_ed{ss.get(chave + '_v', 0)}", n_bloco, p.repeticoes)
        if not erro:
            erro = editor_arraste(p, rl, chave)
        if erro:
            st.error(erro)
        c1, c2 = st.columns(2)
        if c1.button("Salvar disposição", type="primary", disabled=bool(erro), key=f"{chave}_salvar"):
            repo.atualizar_layout(escolhido, ConfigLayout.de_dict(rl["layout"]), autor())
            ss.pop(chave, None)
            avisar_depois("Disposição física atualizada; casualização preservada.")
            st.rerun()
        if c2.button("Descartar ajustes", key=f"{chave}_desc"):
            ss.pop(chave, None)
            ss[chave + "_v"] = ss.get(chave + "_v", 0) + 1
            st.rerun()
        if not erro and rl["layout"] != p.layout.para_dict():
            st.info("Pré-visualização dos ajustes ainda não salvos:")
            p_prev = copy.copy(p)
            p_prev.trocar_layout(ConfigLayout.de_dict(rl["layout"]))
            metricas_croqui(p_prev)
            painel_croqui(p_prev, f"{chave}_prev", altura=420)

# ------------------------------------------------------------ mapa e locação
with aba_mapa_:
    aba_mapa(p, escolhido, repo, autor(), repo.projeto_de(escolhido), resumo.status)

# ------------------------------------------------------------ casualização
with aba_cas:
    problemas = p.verificar()
    if problemas:
        st.error("Falhas de integridade: " + "; ".join(problemas))
    else:
        st.success(f"Casualização íntegra: {p.casualizacao.n_unidades} unidades; cada tratamento com "
                   f"{p.repeticoes} repetições" + ("; cada bloco com todos os tratamentos uma única vez."
                                                   if p.delineamento.value == "DBC" else "."))
    mostradores([("Semente", str(p.casualizacao.semente), ""), ("Algoritmo", p.casualizacao.algoritmo, ""),
                 ("Versão", str(p.versao), ""), ("Padrão de código", p.padrao_codigo, "")])
    st.caption(descrever_algoritmo())
    tabela_unidades(p, altura=460)
    with st.expander("Gerar nova casualização (cria nova versão)"):
        st.warning("A versão atual será preservada no histórico, mas deixará de ser a ativa. Não refaça a "
                   "casualização depois que o experimento estiver implantado.")
        c1, c2 = st.columns([1, 2])
        ns_k = f"ns_{escolhido}"
        ss.setdefault(ns_k, semente_aleatoria())
        nova = c1.number_input("Nova semente", 0, SEMENTE_MAX, int(ss[ns_k]), key=f"{ns_k}_in")
        motivo = c2.text_input("Motivo (obrigatório)", key=f"{ns_k}_mot")
        if st.button("Gerar nova casualização", disabled=not motivo.strip() or int(nova) == p.casualizacao.semente,
                     key=f"{ns_k}_btn"):
            r2 = rascunho_de_planejamento(p)
            r2["semente"] = int(nova)
            v = repo.nova_versao(escolhido, planejamento_de(r2), motivo.strip(), autor())
            ss.pop(ns_k, None)
            avisar_depois(f"Versão {v} criada com a semente {int(nova)}.")
            st.rerun()

# ---------------------------------------------- tratamentos e delineamento
with aba_trat:
    c1, c2 = st.columns([2, 1])
    with c1:
        secao("Tratamentos")
        fat = [f.nome for f in p.estrutura.fatores] if p.estrutura.e_fatorial else []
        st.dataframe(pd.DataFrame([{"Código": t.codigo, "Tratamento": t.rotulo,
                                    **{f: t.niveis.get(f, "—") for f in fat},
                                    "Tipo": descrever_tipo(t, p.estrutura.e_fatorial) + (f" · {t.papel.value}" if t.papel.value else "")}
                                   for t in p.tratamentos]), hide_index=True, width="stretch")
    with c2:
        secao("Quadro de GL esperado")
        st.dataframe(pd.DataFrame([{"Fonte de variação": g.fonte.replace("  ", "  ↳ "), "GL": g.gl}
                                   for g in quadro_gl(p.delineamento, p.estrutura, p.repeticoes, p.arranjo)]),
                     hide_index=True, width="stretch")
    with st.expander("Alterar estrutura experimental (cria nova versão)"):
        st.warning("Alterar delineamento, repetições ou tratamentos invalida a casualização atual. "
                   "Uma nova versão será criada; a anterior fica disponível em *Versões e histórico*.")
        ek = f"est_{escolhido}_{p.versao}"
        if ek not in ss:
            ss[ek] = rascunho_de_planejamento(p)
        re_ = ss[ek]
        formulario_delineamento(re_, f"{ek}_d")
        erro = editor_estrutura(re_, f"{ek}_e")
        if not erro:
            resumo_estatistico(re_)
            erro = formulario_casualizacao(re_, f"{ek}_c")
        motivo = st.text_input("Motivo da alteração (obrigatório)", key=f"{ek}_mot")
        if erro:
            st.error(erro)
        if st.button("Salvar nova versão", type="primary", disabled=bool(erro) or not motivo.strip(), key=f"{ek}_ok"):
            try:
                novo = planejamento_de(re_)
                v = repo.nova_versao(escolhido, novo, motivo.strip(), autor())
            except (ErroPlanejamento, ErroRepositorio, ValueError) as exc:
                st.error(str(exc))
            else:
                ss.pop(ek, None)
                avisar_depois(f"Versão {v} criada.")
                st.rerun()

# ---------------------------------------------------------- posições e rotação
with aba_pos:
    aba_rotacao(p, escolhido, repo, autor(), opcoes)

# ------------------------------------------------------------------ etiquetas
with aba_etq:
    aba_etiquetas(p, escolhido)

# ------------------------------------------------------------- exportações
with aba_exp:
    painel_exportacoes(p, f"ex{escolhido}_exp", opcoes)
    secao("Google Drive")
    c1, c2 = st.columns([1, 2])
    with c1:
        cj_drive = None
        geo_salvo = repo.carregar_georreferencia(escolhido)
        if geo_salvo:
            from motor.gis import feicoes

            try:
                area_d = repo.carregar_area(geo_salvo["area_id"]) if geo_salvo["area_id"] else None
            except ErroRepositorio:
                area_d = None
            cj_drive = feicoes.montar(p, geo_salvo["geo"], area_d["geometria"] if area_d else None)
        botao_drive_experimento(p, escolhido, repo, cj=cj_drive, chave="exp")
    c2.caption("Uma pasta por experimento (Exp-Ag › projeto › experimento) com os relatórios, a planilha como "
               "Planilha Google, o memorial como Documento Google, um diário de campo e uma planilha de coleta "
               "(estes dois nunca são sobrescritos) e, se o experimento estiver georreferenciado, a subpasta "
               "*Mapas e GIS* com o KMZ que abre no Google Earth.")

# -------------------------------------------------------- informações gerais
with aba_info:
    mk = f"meta_{escolhido}"
    if mk not in ss:
        ss[mk] = rascunho_de_planejamento(p)
    rm = ss[mk]
    erro = formulario_meta(rm, f"{mk}_f", codigo_editavel=False)
    c1, c2 = st.columns([1, 2])
    status_ops = ["planejado", "implantado", "em condução", "concluído"]
    novo_status = c1.selectbox("Status", status_ops, index=status_ops.index(resumo.status)
                               if resumo.status in status_ops else 0, key=f"{mk}_st")
    if erro:
        st.error(erro)
    if st.button("Salvar informações", type="primary", disabled=bool(erro), key=f"{mk}_ok"):
        meta = Metadados(**{k_: v for k_, v in rm["meta"].items() if k_ in Metadados.__dataclass_fields__})
        repo.atualizar_metadados(escolhido, meta, autor())
        if novo_status != resumo.status:
            repo.definir_status(escolhido, novo_status, autor())
        ss.pop(mk, None)
        avisar_depois("Informações atualizadas.")
        st.rerun()

    secao("Ações")
    c1, c2, c3 = st.columns(3)
    with c1.popover("Duplicar experimento", width="stretch"):
        st.caption("Copia tratamentos, delineamento e disposição para um novo experimento.")
        nc = st.text_input("Novo código", key=f"dup_{escolhido}_c")
        nt = st.text_input("Novo título", p.meta.titulo, key=f"dup_{escolhido}_t")
        mesma = st.toggle("Manter a mesma casualização (mesma semente)", False, key=f"dup_{escolhido}_m",
                          help="Desligado: uma nova semente é sorteada — o usual para outro local ou safra.")
        if st.button("Duplicar", type="primary", key=f"dup_{escolhido}_ok", disabled=not nc.strip()):
            try:
                novo = repo.duplicar(escolhido, nc.strip(), nt.strip(), None if mesma else semente_aleatoria(),
                                     autor())
            except (ErroRepositorio, ErroPlanejamento, ValueError) as exc:
                st.error(str(exc))
            else:
                definir_exp_ativo(novo)
                avisar_depois(f"Experimento {nc.strip()} criado.")
                st.rerun()
    if c2.button("Desarquivar" if resumo.arquivado else "Arquivar", width="stretch", key=f"arq_{escolhido}"):
        repo.arquivar(escolhido, not resumo.arquivado, autor())
        avisar_depois("Experimento " + ("desarquivado." if resumo.arquivado else "arquivado."))
        st.rerun()
    with c3.popover("Excluir definitivamente", width="stretch"):
        st.error("A exclusão remove o experimento, todas as versões e o histórico. Exporte o JSON antes.")
        conf = st.text_input(f"Digite {p.meta.codigo} para confirmar", key=f"exc_{escolhido}")
        if st.button("Excluir", disabled=conf.strip() != p.meta.codigo, key=f"exc_{escolhido}_ok"):
            repo.excluir(escolhido)
            definir_exp_ativo(None)
            avisar_depois(f"Experimento {p.meta.codigo} excluído.")
            st.rerun()

# ------------------------------------------------------ versões e histórico
with aba_hist:
    secao("Versões do planejamento")
    for v in reversed(repo.versoes(escolhido)):
        c1, c2, c3 = st.columns([1, 5, 1.3])
        c1.markdown(f"**v{v.versao}**" + (" · ativa" if v.ativa else ""))
        c2.markdown(f"<span class='ae-nota'>{v.criada_em:%d/%m/%Y %H:%M} UTC · semente {v.semente} · "
                    f"{v.n_unidades} unidades · {v.motivo}{' · ' + v.criada_por if v.criada_por else ''}</span>",
                    unsafe_allow_html=True)
        if not v.ativa and c3.button("Restaurar", key=f"rest_{escolhido}_{v.versao}", width="stretch"):
            repo.restaurar_versao(escolhido, v.versao, autor())
            avisar_depois(f"Versão {v.versao} reativada.")
            st.rerun()
    secao("Histórico de alterações")
    hist = repo.historico(escolhido)
    st.dataframe(pd.DataFrame([{"Quando (UTC)": h["momento"].strftime("%d/%m/%Y %H:%M"), "Ação": h["acao"],
                                "Detalhe": h["detalhe"], "Autor": h["autor"]} for h in hist]),
                 hide_index=True, width="stretch")
