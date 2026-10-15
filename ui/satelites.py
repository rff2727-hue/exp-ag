"""Diagnóstico do talhão por satélite a partir apenas do perímetro (KML/KMZ).

Mesma aba "Satélites" da recomenda-solo (v17): mesmas análises, mesmos parâmetros e mesmas saídas
(PDF, Excel e KML de pontos de visita), com a identidade Exp-Ag no relatório.
"""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from componentes.visual import mostradores, secao
from motor.exportacao.estilo import TRAVA_MPL


def segredo(chave: str):
    """Lê um segredo no nível raiz ou na seção [satelites] dos Secrets."""
    try:
        v = st.secrets.get(chave)
        if v is None:
            v = st.secrets.get("satelites", {}).get(chave)
        return v
    except Exception:  # noqa: BLE001
        return None


def credencial_earthdata() -> dict | None:
    """Login Earthdata (NASA) para ler o NISAR: `earthdata_token`, ou `earthdata_user` e `earthdata_password`."""
    tok, usu, sen = segredo("earthdata_token"), segredo("earthdata_user"), segredo("earthdata_password")
    if tok:
        return {"token": str(tok)}
    if usu and sen:
        return {"usuario": str(usu), "senha": str(sen)}
    return None


def adiado(funcao, *args):
    """Função sem argumentos para o download_button: o arquivo só é montado quando o usuário clica."""
    def gerar():
        with TRAVA_MPL:
            return funcao(*args)
    return gerar


def diagnostico(kml: bytes, nome_arq: str, indices: tuple, modulos: tuple, anos_lav: int, anos_term: int,
                nome: str, progresso=None, par_agua=None):
    from motor.sat.base import area_de_kml
    from motor.sat.diagnostico import executar
    area = area_de_kml(kml, nome_arq, nome, list(indices) or None)
    return executar(area, modulos, anos_lav, anos_term, progresso=progresso, par_agua=par_agua,
                    earthdata=credencial_earthdata())


st.title("Diagnóstico por satélite")
st.markdown("<span class='ae-nota'>Envie só o <b>perímetro</b> da área (KML ou KMZ) ou use uma área já salva. A plataforma consulta bases "
            "públicas e monta a biografia da área, o comportamento da lavoura, o relevo e a água, o perfil "
            "climático, o contexto do solo, a temperatura de superfície e o vento — com relatório em PDF. "
            "Útil para escolher e caracterizar a área de um experimento.</span>", unsafe_allow_html=True)


def pagina() -> None:
    from motor.sat import agua as ag
    from motor.sat import exportar, relatorio
    from motor.sat.diagnostico import MODULOS
    from motor.sat.geo import epsg_utm_sirgas, ler_kml, projetar
    from motor.sat.lavoura import kml_pontos
    from ui.estado import repositorio

    repo = repositorio()
    pre = st.session_state.get("sat_area_pre")
    areas = [a for a in repo.listar_areas() if a["tipo"] == "perimetro"]
    fontes = (["pre"] if pre else []) + ["arquivo"] + (["salva"] if areas else [])
    rot_f = {"pre": f"Área do experimento: {pre['nome']}" if pre else "", "arquivo": "Enviar arquivo KML/KMZ",
             "salva": "Área salva no Exp-Ag"}
    fonte = st.radio("Perímetro", fontes, format_func=rot_f.get, horizontal=True, key="sat_fonte")
    if fonte == "pre":
        kml_bytes, nome_arq = pre["kml"], f"{pre['nome']}.kml"
    elif fonte == "salva":
        aid = st.selectbox("Área", [a["id"] for a in areas], key="sat_area_sel",
                           format_func={a["id"]: f"{a['nome']} · {a['area_ha']:.1f} ha".replace(".", ",")
                                        for a in areas}.get)
        from motor.gis.leitura import para_kml

        a = repo.carregar_area(aid)
        kml_bytes, nome_arq = para_kml(a["geometria"], a["nome"]), f"{a['nome']}.kml"
    else:
        arq = st.file_uploader("Perímetro (KML ou KMZ)", type=["kml", "kmz"], key="sat_kml")
        if not arq:
            return
        if arq.size > 20 * 1024 * 1024:
            st.error("Arquivo muito grande (limite de 20 MB).")
            return
        kml_bytes, nome_arq = arq.getvalue(), arq.name
    try:
        k = ler_kml(kml_bytes, nome_arq)
    except Exception as e:  # noqa: BLE001
        st.error(f"Não foi possível ler o arquivo: {e}")
        return
    if not k.poligonos:
        st.error("O arquivo não tem polígono de perímetro.")
        return
    indices: tuple = ()
    if len(k.poligonos) > 1:
        c = k.poligonos[0].representative_point()
        ep = epsg_utm_sirgas(c.x, c.y)
        rot = [f"Polígono {i + 1} · {projetar(p, ep).area / 1e4:.1f} ha" for i, p in enumerate(k.poligonos)]
        sel = st.multiselect("O arquivo tem vários polígonos: quais formam a área?", rot, default=rot,
                             key="sat_polys")
        if not sel:
            return
        indices = tuple(rot.index(r) for r in sel)
    nome_padrao = re.sub(r"\.(kml|kmz)$", "", nome_arq, flags=re.I).replace("_", " ")
    with st.form("form_sat"):
        c2, c3 = st.columns(2)
        produtor = c2.text_input("Produtor / instituição")
        propriedade = c3.text_input("Propriedade / área experimental")
        c4, c5 = st.columns(2)
        talhao = c4.text_input("Talhão / área", nome_padrao)
        municipio = c5.text_input("Município (UF)")
        mods = st.multiselect("Análises", list(MODULOS), default=list(MODULOS), format_func=MODULOS.get)
        c6, c7 = st.columns(2)
        anos_lav = c6.select_slider("Anos de imagens Sentinel-2 (lavoura)", [2, 3, 4, 5, 6], value=5,
                                    help="Os mapas de NDVI, NDRE, NDMI e MSAVI2 são a média histórica desses anos.")
        anos_term = c7.select_slider("Anos de imagens Landsat (temperatura)", [2, 3, 4, 5], value=3)
        with st.expander("Água no solo — informações opcionais (cultura, solo e irrigação)"):
            st.caption("O perímetro basta para o balanço de chuva e ET₀ dos últimos 90 dias. O **armazenamento na zona "
                       "radicular** só é estimado se você informar cultura, data de semeadura, profundidade radicular e "
                       "CAD. O relatório mostra separadamente o que é dado público e o que foi informado aqui.")
            w1, w2, w3 = st.columns(3)
            cult = w1.selectbox("Cultura", [""] + list(ag.CULTURAS), key="sat_ag_cult",
                                format_func=lambda k: ag.CULTURAS[k][0] if k else "(não informar)")
            semead = w2.date_input("Data de semeadura", value=None, format="DD/MM/YYYY", key="sat_ag_sem")
            ciclo = w3.number_input("Ciclo (dias) — opcional", 0, 400, 0, 5, key="sat_ag_ciclo",
                                    help="0 = usar a duração de referência da FAO-56 para a cultura.")
            w4, w5, w6 = st.columns(3)
            raiz = w4.number_input("Profundidade radicular efetiva (cm)", 0.0, 300.0, 0.0, 5.0, key="sat_ag_raiz",
                                   help="0 = não informar.")
            cad = w5.number_input("CAD (mm de água por cm de solo)", 0.0, 3.0, 0.0, 0.1, format="%.2f",
                                  key="sat_ag_cad",
                                  help="Capacidade de água disponível do solo. 0 = não informar. Referência: "
                                       "arenoso ~0,6–0,9; textura média ~1,0–1,4; argiloso ~1,3–1,8 mm/cm.")
            irrig = w6.selectbox("Irrigação", list(ag.IRRIGACAO), format_func=ag.IRRIGACAO.get, key="sat_ag_irr",
                                 help="“Não informado” não é tratado como “sem irrigação”: o armazenamento sai como "
                                      "cenário sem irrigação, identificado como tal.")
            st.caption("Lâminas de irrigação aplicadas nos últimos 90 dias (só para área irrigada; opcional):")
            lam = st.data_editor(pd.DataFrame({"Data": pd.Series([], dtype="datetime64[ns]"),
                                               "Lâmina (mm)": pd.Series([], dtype=float)}),
                                 num_rows="dynamic", hide_index=True, key="sat_ag_lam",
                                 column_config={"Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                                "Lâmina (mm)": st.column_config.NumberColumn(min_value=0.0,
                                                                                             max_value=200.0)})
            st.caption("NISAR: " + ("credencial Earthdata configurada — a umidade superficial será lida."
                                    if credencial_earthdata() else
                                    "credencial Earthdata **não configurada** nos Secrets — o relatório informa "
                                    "quantas passagens existem, mas não lê os valores (ver README)."))
        gerar = st.form_submit_button("Gerar diagnóstico", type="primary", width="stretch",
                                      icon=":material/satellite_alt:")
    if gerar:
        if not mods:
            st.warning("Escolha ao menos uma análise.")
            return
        barra = st.status("Consultando as bases (pode levar alguns minutos)…", expanded=True)
        try:
            laminas = tuple((pd.Timestamp(d).date(), float(mm)) for d, mm in zip(lam["Data"], lam["Lâmina (mm)"])
                            if pd.notna(d) and pd.notna(mm) and mm > 0)
            par_agua = ag.ParametrosAgua(cultura=cult or "", semeadura=semead, ciclo_dias=int(ciclo) or None,
                                         prof_raiz_cm=float(raiz) or None, cad_mm_cm=float(cad) or None,
                                         irrigacao=irrig, laminas=laminas if irrig == "irrigado" else ())
            diag = diagnostico(kml_bytes, nome_arq, indices, tuple(mods), anos_lav, anos_term, talhao,
                               progresso=barra.write, par_agua=par_agua)
            barra.write("Montando o relatório…")
            chave = segredo("google_maps_key")
            fundo = relatorio.fundo_satelite(diag.area, chave and "Google (Map Tiles API)" or "Esri World Imagery",
                                             chave)
            dados = relatorio.DadosRelatorio(produtor=produtor, propriedade=propriedade, talhao=talhao,
                                             municipio=municipio, data=pd.Timestamp.today().strftime("%d/%m/%Y"))
            with TRAVA_MPL:
                pdf = relatorio.montar(diag, dados, fundo)
            st.session_state["sat_res"] = {"pdf": pdf, "diag": diag, "nome": talhao or nome_padrao}
            barra.update(label="Pronto!", state="complete", expanded=False)
        except Exception as e:  # noqa: BLE001
            barra.update(label="Falhou", state="error")
            st.exception(e)
    r = st.session_state.get("sat_res")
    if not r:
        return
    diag = r["diag"]
    for a in diag.avisos:
        st.caption(f"⚠️ {a}")
    secao("Raio-X")
    ind = relatorio.indicadores(diag)
    for i in range(0, len(ind), 4):
        mostradores([(rot, val, "") for rot, val, _ in ind[i:i + 4]])
    al = relatorio.alertas(diag)
    if al:
        secao("Pontos de atenção")
        for a in al:
            st.markdown(f"- {a}")
    secao("Arquivos")
    b1, b2, b3 = st.columns(3)
    b1.download_button("Relatório (PDF)", r["pdf"], file_name=f"Diagnostico satelite - {r['nome']}.pdf",
                       mime="application/pdf", type="primary", width="stretch", key="sat_pdf",
                       icon=":material/picture_as_pdf:")
    b2.download_button("Tabelas (Excel)", adiado(exportar.excel, diag),
                       file_name=f"Diagnostico satelite - {r['nome']}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch",
                       key="sat_xlsx", icon=":material/table:")
    if diag.lavoura is not None and len(diag.lavoura.pontos):
        b3.download_button("Pontos de visita (KML)", kml_pontos(diag.lavoura.pontos),
                           file_name=f"Pontos prioritarios - {r['nome']}.kml",
                           mime="application/vnd.google-earth.kml+xml", width="stretch", key="sat_kml_pts",
                           icon=":material/location_on:")
    from componentes.drive_ui import botao_drive_arquivos
    from motor.integracoes.google_drive import PLANILHA, XLSX, Arquivo

    data = pd.Timestamp.today().strftime("%Y-%m-%d")
    c1, _ = st.columns([1, 2])
    def arquivos_drive():
        kp = kml_pontos(diag.lavoura.pontos) if (diag.lavoura is not None and len(diag.lavoura.pontos)) else None
        arqs = [Arquivo(f"Diagnóstico por satélite - {r['nome']}.pdf", r["pdf"], "application/pdf"),
                Arquivo(f"Tabelas - {r['nome']}", adiado(exportar.excel, diag)(), XLSX, PLANILHA)]
        if kp is not None:
            arqs.append(Arquivo(f"Pontos de visita - {r['nome']}.kml", kp.encode("utf-8") if isinstance(kp, str) else kp,
                                "application/vnd.google-earth.kml+xml"))
        return arqs

    with c1:
        botao_drive_arquivos(f"sat:{r['nome']}|{data}", ["Exp-Ag", "Diagnósticos por satélite", f"{r['nome']} {data}"],
                             arquivos_drive, repo, "Salvar no Google Drive")
    with st.expander("Tabelas"):
        for nome, df in exportar.tabelas(diag).items():
            st.markdown(f"**{nome}**")
            st.dataframe(df, hide_index=True, width="stretch")


pagina()
