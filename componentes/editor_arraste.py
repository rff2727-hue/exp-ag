"""Editor de disposição por arraste: os blocos (ou bancadas) do croqui, num plano em metros, movidos com o mouse."""

from __future__ import annotations

import streamlit as st

from componentes.mapa import dados_mapa, mapa_experimento
from motor.exportacao.estilo import romano
from motor.geometria.layout import ConfigLayout
from motor.gis.georref import croqui_local

ss = st.session_state


def editor_arraste(p, rl: dict, chave: str) -> str | None:
    """Mostra o editor quando há mais de um bloco/bancada. Atualiza ``rl["layout"]["deslocamentos_blocos"]``.

    Devolve uma mensagem de erro se houver blocos sobrepostos."""
    try:
        lay = ConfigLayout.de_dict(rl["layout"])
    except ValueError as e:
        return str(e)
    cr = croqui_local(p.casualizacao, lay)
    if len(cr.caixas) < 2:
        return None
    if st.toggle("Arrastar blocos com o mouse", key=f"{chave}_arr_tg",
                 help="Reposicione blocos ou bancadas livremente (ex.: contornar um obstáculo). Os tratamentos e a "
                      "casualização não mudam; a posição vale também para o mapa."):
        vk = f"{chave}_arr_v"
        ss.setdefault(vk, 0)
        dados = dados_mapa(p, cr, modo="local", editar="blocos", camadas={"cotas": True}, versao=ss[vk],
                           ajustar=0, altura=430)
        res = mapa_experimento(dados, key=f"{chave}_arr_mapa")
        pos = getattr(res, "posicao", None) if res is not None else None
        if pos and pos.get("versao") == ss[vk] and pos.get("n") != ss.get(f"{chave}_arr_n"):
            ss[f"{chave}_arr_n"] = pos.get("n")
            rl["layout"]["deslocamentos_blocos"] = {str(k): [round(float(v[0]), 3), round(float(v[1]), 3)]
                                                    for k, v in (pos.get("deslocamentos") or {}).items()}
            ss[vk] += 1
            ss[chave + "_v"] = ss.get(chave + "_v", 0) + 1     # recria o formulário com os novos valores
            st.rerun()
        c1, c2 = st.columns([3, 1])
        c1.caption("Arraste um bloco para movê-lo (passos de 10 cm). As cotas acompanham.")
        if lay.deslocamentos_blocos and c2.button("Zerar deslocamentos", key=f"{chave}_arr_zero", width="stretch"):
            rl["layout"]["deslocamentos_blocos"] = {}
            ss[vk] += 1
            ss[chave + "_v"] = ss.get(chave + "_v", 0) + 1
            st.rerun()
    if cr.conflitos:
        nomes = {}
        for cel in cr.celulas:
            nomes[cel.grupo] = f"bloco {romano(cel.bloco)}" if cel.bloco else f"bancada {cel.bancada or cel.grupo}"
        return "Blocos sobrepostos: " + "; ".join(f"{nomes[a]} e {nomes[b]}" for a, b in cr.conflitos) + \
            ". Afaste-os para salvar."
    return None
