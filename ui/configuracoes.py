"""Configurações: banco de dados, backup, Google Drive e exemplos."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime

import streamlit as st

from aplicacao.exemplos import carregar_exemplos
from componentes.drive_ui import painel_configuracao
from componentes.visual import secao
from motor.casualizacao.casualizador import descrever_algoritmo
from motor.exportacao.projeto_json import para_json_dict
from ui.estado import avisar_depois, em_nuvem, info_banco, repositorio

repo = repositorio()
st.title("Configurações")

secao("Armazenamento")
descricao, persistente = info_banco()
st.markdown(f"Banco em uso: **{descricao}**")
if persistente:
    st.success("Banco externo configurado: os experimentos persistem entre reinicializações.")
elif em_nuvem():
    st.warning("SQLite em servidor na nuvem: os dados podem ser apagados quando o app reiniciar. "
               "Configure `[database] url = \"postgresql://…\"` em *Settings → Secrets*.")
else:
    st.info("SQLite local: adequado para uso individual neste computador. Para uso compartilhado, "
            "configure PostgreSQL (veja o README).")

secao("Backup")
st.caption("Gera um arquivo .zip com um JSON por experimento (versão ativa), importável em "
           "*Meus projetos → Importar*, mais as posições no terreno e as áreas (GeoJSON, abre em qualquer SIG).")
if st.button("Preparar backup de todos os experimentos"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for e in repo.listar(incluir_arquivados=True):
            p = repo.carregar(e.id)
            z.writestr(f"{e.projeto}/{e.codigo}_v{p.versao}.json",
                       json.dumps(para_json_dict(p), ensure_ascii=False, indent=2))
            g = repo.carregar_georreferencia(e.id)
            if g:
                z.writestr(f"{e.projeto}/{e.codigo}_georreferencia.json",
                           json.dumps({"georreferencia": g["geo"].para_dict(), "area_id": g["area_id"],
                                       "evitar_ids": g["evitar_ids"]}, ensure_ascii=False, indent=2))
        areas = repo.listar_areas()
        if areas:
            from shapely.geometry import mapping

            feats = []
            for a in areas:
                d = repo.carregar_area(a["id"])
                feats.append({"type": "Feature", "geometry": mapping(d["geometria"]),
                              "properties": {"id": a["id"], "nome": a["nome"], "tipo": a["tipo"],
                                             "area_ha": a["area_ha"], "origem": a["origem"]}})
            z.writestr("areas.geojson", json.dumps({"type": "FeatureCollection", "features": feats},
                                                   ensure_ascii=False))
    st.session_state["_backup"] = buf.getvalue()
if "_backup" in st.session_state:
    st.download_button("Baixar backup (.zip)", st.session_state["_backup"],
                       f"agro_experimentos_backup_{datetime.now():%Y%m%d_%H%M}.zip", "application/zip",
                       type="primary")

secao("Google Drive e Google Earth")
painel_configuracao()

secao("Experimentos de exemplo")
st.caption("Cria o projeto EXEMPLOS com os cenários de aceitação: DBC a campo (40 parcelas), DIC em vasos "
           "(30 vasos) e fatorial 3 × 2 (24 parcelas).")
if st.button("Carregar exemplos"):
    criados = carregar_exemplos(repo)
    avisar_depois(f"Exemplos criados: {', '.join(criados)}." if criados else "Os exemplos já existiam.")
    st.rerun()

secao("Reprodutibilidade")
st.markdown(descrever_algoritmo())
