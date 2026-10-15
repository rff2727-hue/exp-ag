"""Assistente: Projeto → Delineamento → Tratamentos → Casualização → Croqui → Revisão."""

from __future__ import annotations

import streamlit as st

from aplicacao.rascunho import planejamento_de, rascunho_vazio
from componentes.formularios import (
    editor_estrutura,
    editor_layout,
    formulario_casualizacao,
    formulario_delineamento,
    formulario_meta,
    itens_por_linha_max,
    resumo_estatistico,
)
from componentes.paineis import metricas_croqui, painel_croqui, tabela_unidades
from componentes.visual import passos, secao, selo_futuro
from dados.repositorios.experimentos import ErroRepositorio
from motor.casualizacao.casualizador import descrever_algoritmo
from motor.exportacao.texto_metodologico import descricao_pt
from motor.planejamento import ErroPlanejamento
from ui.estado import abrir_experimento, autor, avisar_depois, repositorio

PASSOS = ["Projeto", "Delineamento", "Tratamentos", "Casualização", "Croqui", "Revisão"]

repo = repositorio()
ss = st.session_state
if "rascunho" not in ss:
    ss["rascunho"] = rascunho_vazio()
    ss["passo"] = 0
ss.setdefault("rascunho_v", 0)
ss.setdefault("passo", 0)
r = ss["rascunho"]
k = f"nx{ss['rascunho_v']}"

c1, c2 = st.columns([4, 1])
c1.title("Novo experimento")
if c2.button("Recomeçar", width="stretch", help="Descarta o rascunho atual."):
    ss["rascunho"] = rascunho_vazio()
    ss["rascunho_v"] += 1
    ss["passo"] = 0
    st.rerun()
if r.get("modelo"):
    st.caption(f"Partindo do modelo: **{r['modelo']}**")
passos(PASSOS, ss["passo"])
erro: str | None = None
passo = ss["passo"]

if passo == 0:
    secao("Projeto de pesquisa")
    projetos = repo.listar_projetos()
    modos = ["Projeto existente", "Novo projeto"] if projetos else ["Novo projeto"]
    padrao = 0
    if r.get("novo_projeto"):
        padrao = modos.index("Novo projeto")
    modo = st.radio("Vincular a", modos, index=padrao, horizontal=True, key=f"{k}_pmodo")
    if modo == "Projeto existente":
        ids = [p["id"] for p in projetos]
        rot = {p["id"]: f"{p['codigo']} — {p['titulo']}" for p in projetos}
        r["projeto_id"] = st.selectbox("Projeto", ids, format_func=rot.get,
                                       index=ids.index(r["projeto_id"]) if r.get("projeto_id") in ids else 0,
                                       key=f"{k}_pid")
        r.pop("novo_projeto", None)
    else:
        r["projeto_id"] = None
        np_ = r.setdefault("novo_projeto", {"codigo": "", "titulo": "", "instituicao": "", "programa": ""})
        c1, c2 = st.columns([1, 3])
        np_["codigo"] = c1.text_input("Código do projeto *", np_["codigo"], key=f"{k}_npc", max_chars=40)
        np_["titulo"] = c2.text_input("Título do projeto *", np_["titulo"], key=f"{k}_npt")
        c1, c2 = st.columns(2)
        np_["instituicao"] = c1.text_input("Instituição", np_["instituicao"], key=f"{k}_npi")
        np_["programa"] = c2.text_input("Programa / linha de pesquisa", np_["programa"], key=f"{k}_npp")
        if not np_["codigo"].strip() or not np_["titulo"].strip():
            erro = "Informe código e título do novo projeto."
        elif any(p["codigo"].lower() == np_["codigo"].strip().lower() for p in projetos):
            erro = f"Já existe um projeto com o código '{np_['codigo']}'."
    secao("Identificação do experimento")
    erro_meta = formulario_meta(r, f"{k}_meta")
    erro = erro or erro_meta
    if not erro and not repo.codigo_disponivel(r["meta"]["codigo"]):
        erro = f"Já existe um experimento com o código '{r['meta']['codigo']}'."

elif passo == 1:
    secao("Delineamento estatístico")
    formulario_delineamento(r, f"{k}_del")

elif passo == 2:
    secao("Fatores e tratamentos")
    erro = editor_estrutura(r, f"{k}_est")
    if not erro:
        secao("Conferência estatística")
        resumo_estatistico(r)

elif passo == 3:
    secao("Casualização")
    erro = formulario_casualizacao(r, f"{k}_cas")
    if not erro:
        try:
            p = planejamento_de(r)
            st.success(f"Casualização gerada e verificada: {p.casualizacao.n_unidades} unidades, "
                       f"{len(p.tratamentos)} tratamentos × {p.repeticoes} repetições. {descrever_algoritmo()}")
            tabela_unidades(p, altura=380)
        except (ErroPlanejamento, ValueError) as exc:
            erro = str(exc)

elif passo == 4:
    secao("Disposição física e croqui")
    try:
        p0 = planejamento_de(r)
        n_bloco = itens_por_linha_max(p0)
        erro = editor_layout(r, f"{k}_lay", n_bloco, r["repeticoes"] if r["delineamento"] == "DBC" else 1)
        if not erro:
            p = planejamento_de(r)
            metricas_croqui(p)
            painel_croqui(p, f"{k}_cq")
            st.markdown(f"<span class='ae-nota'>Edição por arraste e posicionamento sobre o mapa</span>"
                        f"{selo_futuro('fases 2 e 3')}", unsafe_allow_html=True)
    except (ErroPlanejamento, ValueError) as exc:
        erro = str(exc)

elif passo == 5:
    try:
        p = planejamento_de(r)
    except (ErroPlanejamento, ValueError) as exc:
        erro = str(exc)
    else:
        secao("Resumo")
        metricas_croqui(p)
        st.markdown(f"**{p.meta.codigo} — {p.meta.titulo}**  \n{p.delineamento.nome} · "
                    + (f"fatorial {p.estrutura.esquema}" if p.estrutura.e_fatorial else f"{len(p.tratamentos)} tratamentos")
                    + f" · {p.repeticoes} repetições · semente {p.casualizacao.semente}")
        secao("Descrição metodológica")
        st.write(descricao_pt(p))
        problemas = p.verificar()
        if problemas:
            erro = "; ".join(problemas)
        else:
            st.success("Todas as verificações de integridade foram aprovadas.")
        if not erro and st.button("Salvar experimento", type="primary", icon=":material/save:"):
            try:
                pid = r.get("projeto_id")
                if not pid:
                    np_ = r["novo_projeto"]
                    pid = repo.criar_projeto(np_["codigo"], np_["titulo"], np_.get("instituicao", ""),
                                             np_.get("programa", ""), r["meta"].get("responsavel", ""))
                    r["projeto_id"] = pid
                    r.pop("novo_projeto", None)
                novo = repo.salvar_novo(pid, p, autor(),
                                        "Planejamento inicial" + (f" (modelo: {r['modelo']})" if r.get("modelo") else ""))
            except ErroRepositorio as exc:
                st.error(str(exc))
            else:
                ss.pop("rascunho", None)
                ss["passo"] = 0
                ss["rascunho_v"] += 1
                avisar_depois(f"Experimento {p.meta.codigo} salvo.")
                abrir_experimento(novo)

if erro:
    st.error(erro)

st.divider()
c1, _, c3 = st.columns([1, 3, 1])
if passo > 0 and c1.button("← Voltar", width="stretch"):
    ss["passo"] -= 1
    st.rerun()
if passo < len(PASSOS) - 1 and c3.button("Avançar →", type="primary", width="stretch",
                                          disabled=bool(erro)):
    ss["passo"] += 1
    st.rerun()
