"""Formulários reutilizados pelo assistente e pela edição de experimentos.

Todos operam sobre o dicionário de rascunho (``aplicacao.rascunho``) e usam
chaves de widget com um número de versão (``k``), que é incrementado quando o
rascunho é substituído (modelo aplicado, edição reiniciada).
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd
import streamlit as st

from motor.casualizacao.gerador import SEMENTE_MAX, semente_aleatoria
from motor.dominio import Ambiente
from motor.estatistica.delineamentos import avisos_planejamento, quadro_gl
from motor.estatistica.tratamentos import ErroEstrutura, descrever_tipo, gerar_tratamentos
from motor.geometria.layout import ConfigLayout
from motor.identificadores.codigos import (
    MARCADORES,
    ErroIdentificador,
    padrao_sugerido,
    validar_codigo_experimento,
    validar_padrao,
)

UFS = ["", "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR",
       "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]
PAPEIS = ["", "testemunha", "controle positivo", "controle negativo"]


# --------------------------------------------------------------- metadados
def formulario_meta(r: dict, k: str, codigo_editavel: bool = True) -> str | None:
    m = r["meta"]
    c1, c2 = st.columns([1, 3])
    m["codigo"] = c1.text_input("Código do experimento *", m["codigo"], key=f"{k}_cod", max_chars=24,
                                disabled=not codigo_editavel,
                                help="Curto e sem espaços (ex.: SOJA-P26). Compõe os identificadores das unidades.")
    m["titulo"] = c2.text_input("Título *", m["titulo"], key=f"{k}_tit")
    c1, c2, c3 = st.columns(3)
    ambientes = [a.value for a in Ambiente]
    m["ambiente"] = c1.selectbox("Ambiente experimental", ambientes,
                                 index=ambientes.index(m.get("ambiente") or "campo"), key=f"{k}_amb")
    m["cultura"] = c2.text_input("Cultura", m["cultura"], key=f"{k}_cult")
    m["cultivar"] = c3.text_input("Cultivar", m["cultivar"], key=f"{k}_cv")
    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
    m["local"] = c1.text_input("Local (área, fazenda, estação)", m["local"], key=f"{k}_loc")
    m["municipio"] = c2.text_input("Município", m["municipio"], key=f"{k}_mun")
    m["uf"] = c3.selectbox("UF", UFS, index=UFS.index(m["uf"]) if m["uf"] in UFS else 0, key=f"{k}_uf",
                           format_func=lambda x: x or "—")
    m["safra"] = c4.text_input("Safra/ciclo", m["safra"], key=f"{k}_safra", placeholder="2026/27")
    c1, c2, c3 = st.columns(3)
    m["instituicao"] = c1.text_input("Instituição", m["instituicao"], key=f"{k}_inst")
    m["responsavel"] = c2.text_input("Pesquisador responsável", m["responsavel"], key=f"{k}_resp")
    m["colaboradores"] = c3.text_input("Colaboradores", m["colaboradores"], key=f"{k}_colab")
    c1, c2 = st.columns(2)
    m["data_prevista"] = _data(c1, "Data prevista de implantação", m["data_prevista"], f"{k}_dprev")
    m["data_implantacao"] = _data(c2, "Data efetiva de implantação", m["data_implantacao"], f"{k}_dimp")
    m["objetivos"] = st.text_area("Objetivos", m["objetivos"], key=f"{k}_obj", height=80)
    m["hipoteses"] = st.text_area("Hipóteses", m["hipoteses"], key=f"{k}_hip", height=70)
    m["observacoes"] = st.text_area("Observações", m["observacoes"], key=f"{k}_obs", height=70)
    if not m["codigo"].strip():
        return "Informe o código do experimento."
    try:
        validar_codigo_experimento(m["codigo"])
    except ErroIdentificador as e:
        return str(e)
    if not m["titulo"].strip():
        return "Informe o título do experimento."
    return None


def _data(col, rotulo: str, iso: str, key: str) -> str:
    try:
        valor = date.fromisoformat(iso) if iso else None
    except ValueError:
        valor = None
    d = col.date_input(rotulo, value=valor, key=key, format="DD/MM/YYYY")
    return d.isoformat() if d else ""


# ------------------------------------------------------------ delineamento
ARRANJOS = {"convencional": "Convencional", "subdividida": "Parcelas subdivididas", "faixas": "Faixas"}
ARRANJOS_POR_DEL = {"DBC": ["convencional", "subdividida", "faixas"], "DIC": ["convencional", "subdividida"],
                    "QL": ["convencional"]}


def formulario_delineamento(r: dict, k: str) -> None:
    c1, c2 = st.columns([2, 1])
    opcoes = {"DBC": "DBC — blocos casualizados", "DIC": "DIC — inteiramente casualizado",
              "QL": "QL — quadrado latino"}
    antigo = r["delineamento"]
    r["delineamento"] = c1.radio("Delineamento", list(opcoes), format_func=opcoes.get,
                                 index=list(opcoes).index(r["delineamento"]), key=f"{k}_del", horizontal=True)
    if r["delineamento"] != antigo:  # ajusta numeração e padrão de identificação
        r["numeracao"] = "bloco" if r["delineamento"] == "DBC" else "sequencial"
        r["padrao_codigo"] = padrao_sugerido(r["delineamento"])
    if r["delineamento"] == "QL":
        c2.markdown("**Repetições:** iguais ao número de tratamentos")
    else:
        rot = "Número de blocos (repetições)" if r["delineamento"] == "DBC" else "Número de repetições"
        r["repeticoes"] = int(c2.number_input(rot, 2, 50, max(2, int(r["repeticoes"])), key=f"{k}_rep"))
    permitidos = ARRANJOS_POR_DEL[r["delineamento"]]
    if r.get("arranjo", "convencional") not in permitidos:
        r["arranjo"] = "convencional"
    r["arranjo"] = st.radio("Arranjo dos tratamentos", permitidos, format_func=ARRANJOS.get,
                            index=permitidos.index(r.get("arranjo", "convencional")), key=f"{k}_arr_{r['delineamento']}",
                            horizontal=True)
    textos = {
        "DBC": "Cada bloco recebe todos os tratamentos uma vez; os tratamentos são casualizados independentemente "
               "dentro de cada bloco. Use quando houver uma fonte de variação conhecida (declive, fertilidade, "
               "posição na bancada).",
        "DIC": "Os tratamentos são casualizados sobre todas as unidades, sem restrição. Indicado para condições "
               "homogêneas (casa de vegetação, laboratório).",
        "QL": "Controla duas fontes de variação ao mesmo tempo (linhas e colunas — por exemplo, gradiente de luz e "
              "de temperatura numa bancada). Cada tratamento aparece uma vez em cada linha e em cada coluna; de 3 a "
              "12 tratamentos.",
    }
    st.caption(textos[r["delineamento"]])
    if r["arranjo"] == "subdividida":
        st.info("**Parcelas subdivididas:** o **primeiro fator** (A) vai para as parcelas principais e o **segundo** "
                "(B) para as subparcelas, sorteadas dentro de cada parcela principal. Use quando A exige áreas "
                "maiores (preparo do solo, irrigação, época de semeadura). A é testado com menos precisão que B e "
                "A×B.", icon=":material/call_split:")
    elif r["arranjo"] == "faixas":
        st.info("**Faixas:** em cada bloco, o **primeiro fator** (A) ocupa faixas horizontais e o **segundo** (B) "
                "faixas verticais. Útil quando os dois fatores exigem máquinas em sentidos diferentes. A interação "
                "A×B é estimada com mais precisão que os efeitos principais.", icon=":material/view_column:")
    st.markdown("<span class='ae-nota'>Parcelas subsubdivididas, blocos incompletos e látices "
                "</span><span class='ae-futuro'>fases futuras</span>", unsafe_allow_html=True)


# --------------------------------------------------------------- estrutura
def _base_df(key: str, df: pd.DataFrame) -> pd.DataFrame:
    """Mantém o DataFrame inicial do data_editor estável entre execuções."""
    bk = f"{key}__base"
    # renova a base quando o widget não existia na execução anterior (ex.: voltou ao passo)
    if bk not in st.session_state or key not in st.session_state:
        st.session_state[bk] = df
    return st.session_state[bk]


def _numero(texto: str) -> float | None:
    t = str(texto).strip().replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", t):
        t = t.replace(".", "")
    t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def editor_estrutura(r: dict, k: str) -> str | None:
    est = r["estrutura"]
    v = st.session_state.setdefault(f"{k}_v", 0)
    kk = f"{k}_{v}"
    dois_fatores = r.get("arranjo", "convencional") != "convencional"
    if dois_fatores:
        st.caption("O arranjo escolhido exige **dois fatores** e nenhum tratamento adicional. Fator A: "
                   + ("parcelas principais" if r["arranjo"] == "subdividida" else "faixas horizontais")
                   + "; fator B: " + ("subparcelas." if r["arranjo"] == "subdividida" else "faixas verticais."))
        fatorial, n_fat = True, 2
    else:
        fatorial = st.radio(
            "Estrutura dos tratamentos", ["Unifatorial (lista de tratamentos ou doses)", "Fatorial (2 a 4 fatores)"],
            index=1 if len(est["fatores"]) >= 2 else 0, horizontal=True, key=f"{kk}_modo",
        ).startswith("Fatorial")
        n_fat = int(st.number_input("Número de fatores", 2, 4, max(2, len(est["fatores"])), key=f"{kk}_nf")) \
            if fatorial else 1
    fatores = list(est["fatores"])
    letras = "ABCD"
    while len(fatores) < n_fat:
        i = len(fatores)
        fatores.append({"nome": f"Fator {letras[i]}", "tipo": "qualitativo", "unidade": "",
                        "niveis": [{"rotulo": f"{letras[i]}{j}", "valor": None} for j in (1, 2)]})
    fatores = fatores[:n_fat]
    colunas = st.columns(n_fat) if n_fat > 1 else [st.container()]
    novos = []
    for i, (col, f) in enumerate(zip(colunas, fatores)):
        with col:
            if dois_fatores:
                st.markdown(f"**Fator {'AB'[i]}** — " + (("parcelas principais", "subparcelas") if r["arranjo"] ==
                                                         "subdividida" else ("faixas horizontais",
                                                                             "faixas verticais"))[i])
            novos.append(_editor_fator(f, f"{kk}_f{i}", n_fat == 1))

    if dois_fatores:
        r["estrutura"] = {"fatores": novos, "adicionais": []}
        return _matriz(r)
    st.markdown("**Tratamentos adicionais** (testemunhas e controles fora do fatorial)")
    df_ad = pd.DataFrame(est["adicionais"] or [], columns=["rotulo", "papel", "descricao"])
    ed = st.data_editor(
        _base_df(f"{kk}_ad", df_ad), num_rows="dynamic", hide_index=True, width="stretch",
        key=f"{kk}_ad",
        column_config={
            "rotulo": st.column_config.TextColumn("Tratamento adicional", width="medium"),
            "papel": st.column_config.SelectboxColumn("Papel", options=PAPEIS, width="small"),
            "descricao": st.column_config.TextColumn("Descrição", width="large"),
        },
    )
    adicionais = [
        {"rotulo": str(x.rotulo).strip(), "papel": x.papel if isinstance(x.papel, str) else "",
         "descricao": x.descricao if isinstance(x.descricao, str) else ""}
        for x in ed.itertuples() if isinstance(x.rotulo, str) and x.rotulo.strip()
    ]
    r["estrutura"] = {"fatores": novos, "adicionais": adicionais}
    return _matriz(r)


def _matriz(r: dict) -> str | None:
    """Gera e mostra a matriz de tratamentos; devolve a mensagem de erro, se houver."""
    from aplicacao.rascunho import estrutura_de

    try:
        e = estrutura_de(r)
        trats = gerar_tratamentos(e)
    except (ErroEstrutura, ValueError, TypeError) as exc:
        return str(exc)
    st.markdown(f"**Matriz de tratamentos** — {len(trats)} tratamento(s)"
                + (f", esquema fatorial {e.esquema}" if e.e_fatorial else ""))
    fat_nomes = [f.nome for f in e.fatores] if e.e_fatorial else []
    st.dataframe(
        pd.DataFrame([{"Código": t.codigo, "Tratamento": t.rotulo, **{f: t.niveis.get(f, "—") for f in fat_nomes},
                       "Tipo": descrever_tipo(t, e.e_fatorial) + (f" · {t.papel.value}" if t.papel.value else "")} for t in trats]),
        hide_index=True, width="stretch", height=min(38 + 35 * len(trats), 360),
    )
    return None


def _editor_fator(f: dict, key: str, unico: bool) -> dict:
    nome = st.text_input("Nome do fator" if not unico else "Nome do fator (ex.: Tratamento, Dose de P)",
                         f["nome"], key=f"{key}_nome")
    c1, c2 = st.columns(2)
    tipo = c1.selectbox("Tipo", ["qualitativo", "quantitativo"],
                        index=0 if f["tipo"] == "qualitativo" else 1, key=f"{key}_tipo",
                        help="Quantitativo: níveis numéricos (doses, épocas), analisáveis por regressão.")
    unidade = c2.text_input("Unidade", f.get("unidade", ""), key=f"{key}_un", disabled=tipo != "quantitativo",
                            placeholder="kg ha⁻¹")
    vk = f"{key}_nv"
    st.session_state.setdefault(vk, 0)
    with st.expander("Preencher níveis rapidamente"):
        txt = st.text_area("Um nível por linha ou separados por ponto e vírgula", key=f"{key}_rapido",
                           height=90, placeholder="0; 50; 100; 150; 200")
        if st.button("Substituir níveis", key=f"{key}_aplicar"):
            itens = [x.strip() for x in re.split(r"[;\n]", txt) if x.strip()]
            if itens:
                f = {**f, "niveis": [{"rotulo": x, "valor": _numero(x)} for x in itens]}
                st.session_state[vk] += 1
    ek = f"{key}_niv_{st.session_state[vk]}"
    df = pd.DataFrame(f["niveis"], columns=["rotulo", "valor"])
    cfg = {"rotulo": st.column_config.TextColumn("Nível", width="medium")}
    if tipo == "quantitativo":
        cfg["valor"] = st.column_config.NumberColumn("Valor", help="Valor numérico do nível", format="%g")
    else:
        cfg["valor"] = None  # oculta a coluna
    ed = st.data_editor(_base_df(ek, df), num_rows="dynamic", hide_index=True, width="stretch",
                        key=ek, column_config=cfg)
    niveis = []
    for x in ed.itertuples():
        if not isinstance(x.rotulo, str) or not x.rotulo.strip():
            continue
        valor = None if pd.isna(x.valor) else float(x.valor)
        if tipo == "quantitativo" and valor is None:
            valor = _numero(x.rotulo)
        niveis.append({"rotulo": x.rotulo.strip(), "valor": valor if tipo == "quantitativo" else None})
    return {"nome": nome.strip(), "tipo": tipo, "unidade": unidade.strip() if tipo == "quantitativo" else "",
            "niveis": niveis}


def resumo_estatistico(r: dict) -> None:
    """Quadro de GL esperado e avisos de planejamento."""
    from aplicacao.rascunho import estrutura_de

    try:
        e = estrutura_de(r)
        gerar_tratamentos(e)
    except Exception:
        return
    c1, c2 = st.columns([1, 2])
    with c1:
        gl = quadro_gl(r["delineamento"], e, int(r["repeticoes"]), r.get("arranjo", "convencional"))
        st.markdown("**Quadro de GL esperado**")
        st.dataframe(pd.DataFrame([{"Fonte de variação": g.fonte.replace("  ", "  ↳ "), "GL": g.gl} for g in gl]),
                     hide_index=True, width="stretch")
    with c2:
        avisos = avisos_planejamento(r["delineamento"], e, int(r["repeticoes"]), r.get("arranjo", "convencional"))
        if not avisos:
            st.success("Estrutura adequada: graus de liberdade do resíduo e número de unidades suficientes.")
        for a in avisos:
            {"erro": st.error, "alerta": st.warning, "info": st.info}[a.nivel](a.mensagem)


# ------------------------------------------------------------ casualização
def formulario_casualizacao(r: dict, k: str) -> str | None:
    c1, c2 = st.columns([2, 1])
    v = st.session_state.setdefault(f"{k}_sv", 0)
    sem = c1.number_input("Semente aleatória", 0, SEMENTE_MAX, int(r["semente"]), step=1, key=f"{k}_sem_{v}",
                          help="A mesma semente, com as mesmas configurações, reproduz exatamente a mesma "
                               "casualização. Registre-a no caderno de campo.")
    r["semente"] = int(sem)
    c2.write("")
    c2.write("")
    if c2.button("Sortear nova semente", key=f"{k}_sortear", width="stretch"):
        r["semente"] = semente_aleatoria()
        st.session_state[f"{k}_sv"] = v + 1
        st.rerun()
    c1, c2 = st.columns([1, 2])
    if r["delineamento"] == "DBC":
        ops = {"bloco": "Por bloco (101, 102…, 201…)", "sequencial": "Sequencial (1, 2, 3…)"}
        r["numeracao"] = c1.radio("Numeração das parcelas", list(ops), format_func=ops.get,
                                  index=list(ops).index(r["numeracao"]) if r["numeracao"] in ops else 0,
                                  key=f"{k}_num")
    else:
        r["numeracao"] = "sequencial"
        c1.markdown("**Numeração:** sequencial (1, 2, 3…)")
    r["padrao_codigo"] = c2.text_input(
        "Padrão de identificação das unidades", r["padrao_codigo"], key=f"{k}_pad",
        help="Marcadores: " + ", ".join("{" + m + "}" for m in MARCADORES)
             + ". Zeros à esquerda são acrescentados automaticamente.",
    )
    try:
        validar_padrao(r["padrao_codigo"])
    except ErroIdentificador as e:
        return str(e)
    return None


# ------------------------------------------------------------------ layout
def itens_por_linha_max(plano) -> int | None:
    """Máximo de 'unidades por linha': None quando a grade é fixa (faixas e quadrado latino)."""
    from motor.dominio import Arranjo, Delineamento

    if plano.arranjo is Arranjo.FAIXAS or plano.delineamento is Delineamento.QL:
        return None
    if plano.arranjo is Arranjo.SUBDIVIDIDA:
        a = plano.casualizacao.niveis_a
        return a if plano.delineamento is Delineamento.DBC else a * plano.repeticoes
    if plano.delineamento is Delineamento.DBC:
        return len(plano.tratamentos)
    return plano.casualizacao.n_unidades


def editor_layout(r: dict, k: str, n_por_bloco: int | None, n_blocos: int) -> str | None:
    lay = dict(r["layout"])
    dbc = r["delineamento"] == "DBC"
    sub_ = r.get("arranjo") == "subdividida"
    vasos_padrao = r["meta"].get("ambiente") in ("casa de vegetação", "laboratório")
    tipos = {"parcelas": "Parcelas (campo)", "vasos": "Vasos (casa de vegetação)"}
    if f"{k}_tipo" not in st.session_state and lay.get("tipo") not in tipos:
        lay["tipo"] = "vasos" if vasos_padrao else "parcelas"
    lay["tipo"] = st.radio("Unidade experimental", list(tipos), format_func=tipos.get,
                           index=list(tipos).index(lay["tipo"]), key=f"{k}_tipo", horizontal=True)
    c1, c2, c3 = st.columns(3)
    if n_por_bloco is None:
        c1.markdown("**Disposição:** grade fixa pelo sorteio de linhas e colunas")
    else:
        max_cols = max(n_por_bloco, 1)
        atual = lay.get("colunas_por_bloco") or max_cols
        rot = "Parcelas principais por linha" if sub_ else "Unidades por linha"
        lay["colunas_por_bloco"] = int(c1.number_input(
            rot + (" (em cada bloco)" if dbc else ""), 1, max_cols, min(int(atual), max_cols), key=f"{k}_cols",
            help="Quantas unidades (ou parcelas principais) lado a lado em cada linha do bloco "
                 "(ou do experimento, no DIC)."))
    if dbc:
        arr = {"horizontal": "Lado a lado", "vertical": "Empilhados"}
        lay["arranjo_blocos"] = c2.radio("Blocos", list(arr), format_func=arr.get,
                                         index=list(arr).index(lay["arranjo_blocos"]), key=f"{k}_arr",
                                         horizontal=True)
    ordens = {"linear": "Linear", "serpentina": "Serpentina (zigue-zague)"}
    lay["ordem"] = c3.radio("Ordem física das unidades", list(ordens), format_func=ordens.get,
                            index=list(ordens).index(lay["ordem"]), key=f"{k}_ordem",
                            help="Serpentina inverte o sentido nas linhas pares, facilitando o caminhamento.")

    if lay["tipo"] == "parcelas":
        st.markdown("**Dimensões da parcela (m)**")
        por_linhas = st.toggle("Definir a largura pelas linhas de plantio", value=lay.get("n_linhas_plantio", 0) > 0,
                               key=f"{k}_porlinhas")
        c1, c2, c3, c4 = st.columns(4)
        if por_linhas:
            lay["n_linhas_plantio"] = int(c1.number_input("Linhas por parcela", 1, 100,
                                                          max(int(lay.get("n_linhas_plantio") or 4), 1), key=f"{k}_nl"))
            lay["espacamento_linhas"] = c2.number_input("Espaçamento entre linhas", 0.05, 5.0,
                                                        float(lay.get("espacamento_linhas") or 0.5), 0.05,
                                                        format="%.2f", key=f"{k}_el")
            lay["linhas_bordadura"] = int(c3.number_input("Linhas de bordadura (cada lado)", 0, 20,
                                                          int(lay.get("linhas_bordadura", 1)), key=f"{k}_lb"))
            col_comp = c4
        else:
            lay["n_linhas_plantio"] = 0
            lay["largura"] = c1.number_input("Largura", 0.1, 500.0, float(lay["largura"]), 0.1, format="%.2f",
                                             key=f"{k}_larg")
            lay["bordadura_lateral"] = c2.number_input("Bordadura lateral (cada lado)", 0.0, 100.0,
                                                       float(lay["bordadura_lateral"]), 0.05, format="%.2f",
                                                       key=f"{k}_bl")
            col_comp = c3
        lay["comprimento"] = col_comp.number_input("Comprimento (sentido das linhas)", 0.1, 1000.0,
                                                   float(lay["comprimento"]), 0.1, format="%.2f", key=f"{k}_comp")
        if por_linhas:
            st.caption(f"Largura resultante: {lay['n_linhas_plantio'] * lay['espacamento_linhas']:.2f} m "
                       f"({lay['n_linhas_plantio'] - 2 * lay['linhas_bordadura']} linhas úteis).")
        c1, c2, c3, c4 = st.columns(4)
        lay["bordadura_cabeceira"] = c1.number_input("Bordadura de cabeceira (cada extremidade)", 0.0, 100.0,
                                                     float(lay["bordadura_cabeceira"]), 0.05, format="%.2f",
                                                     key=f"{k}_bc")
        lay["espaco_x"] = c2.number_input("Espaço entre parcelas (lateral)", 0.0, 100.0, float(lay["espaco_x"]),
                                          0.1, format="%.2f", key=f"{k}_ex")
        lay["espaco_y"] = c3.number_input("Espaço entre linhas de parcelas", 0.0, 100.0, float(lay["espaco_y"]),
                                          0.1, format="%.2f", key=f"{k}_ey")
        lay["bordadura_externa"] = c4.number_input("Bordadura externa do experimento", 0.0, 500.0,
                                                   float(lay["bordadura_externa"]), 0.5, format="%.2f",
                                                   key=f"{k}_bext")
        c1, c2 = st.columns(2)
        if dbc:
            lay["espaco_blocos"] = c1.number_input("Carreador entre blocos (m)", 0.0, 100.0,
                                                   float(lay["espaco_blocos"]), 0.5, format="%.2f", key=f"{k}_eb")
        if sub_:
            lay["espaco_sub"] = c2.number_input("Espaço entre subparcelas (m)", 0.0, 20.0,
                                                float(lay.get("espaco_sub", 0.0)), 0.1, format="%.2f",
                                                key=f"{k}_esub")
    else:
        c1, c2, c3 = st.columns(3)
        lay["diametro_vaso"] = c1.number_input("Diâmetro do vaso (cm)", 2.0, 200.0,
                                               float(lay["diametro_vaso"]) * 100, 1.0, format="%.1f",
                                               key=f"{k}_dv") / 100
        lay["espaco_vasos"] = c2.number_input("Espaço livre entre vasos (cm)", 0.0, 200.0,
                                              float(lay["espaco_vasos"]) * 100, 1.0, format="%.1f",
                                              key=f"{k}_esv") / 100
        if dbc:
            lay["espaco_blocos"] = c3.number_input("Distância entre blocos (m)", 0.0, 50.0,
                                                   float(lay["espaco_blocos"]), 0.05, format="%.2f", key=f"{k}_ebv")
        c1, c2, c3 = st.columns(3)
        lay["bancadas"] = c1.toggle("Desenhar bancadas", bool(lay.get("bancadas", False)), key=f"{k}_banc",
                                    help="No DBC, uma bancada por bloco. No DIC, divide os vasos em bancadas.")
        if lay["bancadas"]:
            if not dbc and r["delineamento"] != "QL":
                lay["vasos_por_bancada"] = int(c2.number_input(
                    "Vasos por bancada (0 = uma só)", 0, 1000, int(lay.get("vasos_por_bancada", 0)),
                    key=f"{k}_vpb"))
            lay["margem_bancada"] = c3.number_input("Margem da bancada (cm)", 0.0, 100.0,
                                                    float(lay.get("margem_bancada", 0.05)) * 100, 1.0,
                                                    format="%.0f", key=f"{k}_mb") / 100

    _disposicao_avancada(lay, k, r, n_blocos)

    c1, c2 = st.columns(2)
    lay["rotacao_graus"] = c1.slider("Rotação do croqui (°)", -180, 180, int(lay.get("rotacao_graus", 0)), 5,
                                     key=f"{k}_rot")
    lay["azimute_norte"] = c2.slider("Direção do Norte (° a partir do topo, sentido horário)", 0, 359,
                                     int(lay.get("azimute_norte", 0)), 5, key=f"{k}_az")
    try:
        r["layout"] = ConfigLayout.de_dict(lay).para_dict()
    except ValueError as e:
        r["layout"] = lay
        return str(e)
    return None


CANTOS = {"sup_esq": "Superior esquerdo", "sup_dir": "Superior direito", "inf_esq": "Inferior esquerdo",
          "inf_dir": "Inferior direito"}


def _avancado_em_uso(lay: dict) -> bool:
    base = ConfigLayout()
    return any(lay.get(c, getattr(base, c)) != getattr(base, c) for c in (
        "blocos_por_fileira", "espaco_fileiras_blocos", "ordem_blocos", "corredor_a_cada_colunas",
        "corredor_a_cada_linhas", "bordadura_esquerda", "bordadura_direita", "bordadura_topo", "bordadura_base",
        "canto_inicial")) or bool(lay.get("deslocamentos_blocos"))


def _disposicao_avancada(lay: dict, k: str, r: dict, n_blocos: int) -> None:
    """Blocos em grade, corredores internos, bordaduras por lado, canto inicial e deslocamentos manuais."""
    base = ConfigLayout().para_dict()
    for chave, v in base.items():
        lay.setdefault(chave, v)
    dbc = r["delineamento"] == "DBC"
    vasos = lay["tipo"] == "vasos"
    if not st.toggle("Disposição avançada: blocos em fileiras, corredores, bordaduras por lado e ponto de partida",
                     key=f"{k}_avanc", value=_avancado_em_uso(lay)):
        return
    with st.container(border=True):
        if dbc and n_blocos > 1:
            st.markdown("**Blocos**")
            c1, c2, c3 = st.columns(3)
            lay["blocos_por_fileira"] = int(c1.number_input(
                "Blocos por fileira (0 = todos numa fileira)", 0, n_blocos, min(int(lay["blocos_por_fileira"]), n_blocos),
                key=f"{k}_bpf", help="Ex.: 8 blocos com 4 por fileira formam duas fileiras de quatro blocos."))
            esp_f = float(lay["espaco_fileiras_blocos"])
            mesmo = c2.toggle("Mesmo espaço entre fileiras e entre blocos", esp_f < 0, key=f"{k}_efm",
                              disabled=not (0 < lay["blocos_por_fileira"] < n_blocos))
            lay["espaco_fileiras_blocos"] = -1.0 if mesmo else c2.number_input(
                "Espaço entre fileiras de blocos (m)", 0.0, 500.0,
                float(lay["espaco_blocos"]) if esp_f < 0 else esp_f, 0.5, format="%.2f", key=f"{k}_ef")
            ordens = {"linear": "Linear", "serpentina": "Serpentina"}
            lay["ordem_blocos"] = c3.radio("Numeração dos blocos nas fileiras", list(ordens), format_func=ordens.get,
                                           index=list(ordens).index(lay["ordem_blocos"]), key=f"{k}_ob",
                                           horizontal=True)
        st.markdown("**Corredores internos** (acesso, passagem de máquinas, irrigação)")
        c1, c2, c3, c4 = st.columns(4)
        unid = "vasos" if vasos else ("parcelas principais" if r.get("arranjo") == "subdividida" else "parcelas")
        lay["corredor_a_cada_colunas"] = int(c1.number_input(
            f"Corredor a cada n {unid} na linha", 0, 500, int(lay["corredor_a_cada_colunas"]), key=f"{k}_cac",
            help="0 = sem corredor. Ex.: 3 abre um corredor depois de cada 3 unidades lado a lado."))
        lay["largura_corredor_colunas"] = c2.number_input("Largura desse corredor (m)", 0.0, 100.0,
                                                         float(lay["largura_corredor_colunas"]), 0.1, format="%.2f",
                                                         key=f"{k}_lcc")
        lay["corredor_a_cada_linhas"] = int(c3.number_input(
            "Corredor a cada n linhas de unidades", 0, 500, int(lay["corredor_a_cada_linhas"]), key=f"{k}_cal"))
        lay["largura_corredor_linhas"] = c4.number_input("Largura desse corredor (m) ", 0.0, 100.0,
                                                        float(lay["largura_corredor_linhas"]), 0.1, format="%.2f",
                                                        key=f"{k}_lcl")
        st.caption("O corredor soma-se ao espaço normal entre unidades.")

        st.markdown("**Bordadura externa por lado**")
        lados = ("esquerda", "direita", "topo", "base")
        diferente = st.toggle("Bordadura diferente em cada lado", any(lay[f"bordadura_{x}"] >= 0 for x in lados),
                              key=f"{k}_bdif")
        if diferente:
            cols = st.columns(4)
            for col, lado in zip(cols, lados):
                v = lay[f"bordadura_{lado}"]
                lay[f"bordadura_{lado}"] = col.number_input(
                    f"{lado.capitalize()} (m)", 0.0, 500.0, float(lay["bordadura_externa"] if v < 0 else v), 0.5,
                    format="%.2f", key=f"{k}_b_{lado}")
        else:
            for lado in lados:
                lay[f"bordadura_{lado}"] = -1.0

        st.markdown("**Ponto de partida**")
        lay["canto_inicial"] = st.radio(
            "Canto onde ficam a unidade 1" + (" e o bloco I" if dbc else ""), list(CANTOS), format_func=CANTOS.get,
            index=list(CANTOS).index(lay["canto_inicial"]), key=f"{k}_canto", horizontal=True,
            help="Espelha a numeração para começar pelo canto mais cômodo no campo (ex.: o mais próximo da entrada).")

        grupos = n_blocos if dbc else 0
        if grupos > 1 or lay.get("deslocamentos_blocos"):
            st.markdown("**Deslocamento manual dos blocos** (m; também pelo arraste no editor ou no mapa)")
            rotulo = "Bancada" if (vasos and lay.get("bancadas")) else "Bloco"
            atual = lay.get("deslocamentos_blocos") or {}
            df = pd.DataFrame([{rotulo: g, "Deslocar para a direita (m)": float(atual.get(str(g), [0, 0])[0]),
                                "Deslocar para cima (m)": float(atual.get(str(g), [0, 0])[1])}
                               for g in range(1, max(grupos, 1) + 1)])
            ed = st.data_editor(df, hide_index=True, width="stretch", key=f"{k}_desl", disabled=[rotulo],
                                column_config={c: st.column_config.NumberColumn(format="%.2f", step=0.1)
                                               for c in df.columns[1:]})
            lay["deslocamentos_blocos"] = {str(int(row[rotulo])): [float(row.iloc[1] or 0), float(row.iloc[2] or 0)]
                                           for _, row in ed.iterrows()
                                           if abs(row.iloc[1] or 0) > 1e-9 or abs(row.iloc[2] or 0) > 1e-9}
            st.caption("Use para contornar obstáculos ou seguir o terreno. Valores positivos movem o bloco para a "
                       "direita e para cima no croqui (antes da rotação).")
