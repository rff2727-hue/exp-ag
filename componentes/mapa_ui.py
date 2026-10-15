"""Aba "Mapa e locação": área, posicionamento no terreno, conferência, medidas, locação e exportação GIS."""

from __future__ import annotations

import math
from dataclasses import replace

import pandas as pd
import streamlit as st
from shapely.geometry import Polygon
from shapely.ops import unary_union

from componentes.mapa import dados_mapa, mapa_experimento
from componentes.visual import mostradores, secao
from motor.exportacao.estilo import NOMES_ROTULOS, fmt_num
from motor.geometria.layout import ConfigLayout, texto_medida
from motor.gis import crs, exportar, feicoes, leitura
from motor.gis.controle import PontoControle, ajustar, avaliar_ajuste
from motor.gis.encaixe import conferir, encaixar
from motor.gis.georref import (
    REFERENCIAS,
    Georreferencia,
    Transformacao,
    com_referencia,
    croqui_local,
    reancorar,
)
from motor.gis.locacao import diagonais, piquetes, pontos_notaveis, roteiro_trena

ss = st.session_state

COMO = {
    "arraste": "Arrastar e girar no mapa",
    "perimetro": "Encaixar no perímetro",
    "manual": "Coordenadas",
    "pontos": "Pontos de controle (GPS)",
}


# ------------------------------------------------------------------------------------------------- estado
class _Rascunho:
    """Rascunho da posição (e da disposição dos blocos) até o usuário salvar."""

    def __init__(self, exp_id: int, p, repo) -> None:
        self.k = f"gm{exp_id}_{p.versao}"
        self.exp_id, self.p, self.repo = exp_id, p, repo
        if f"{self.k}_ini" in ss and ss.get(f"{self.k}_base") != p.layout.para_dict():
            self.descartar()                      # a disposição foi salva em outra aba: recomeça do banco
        if f"{self.k}_ini" not in ss:
            ss[f"{self.k}_base"] = p.layout.para_dict()
            salvo = repo.carregar_georreferencia(exp_id)
            ss[f"{self.k}_geo"] = salvo["geo"].para_dict() if salvo else None
            ss[f"{self.k}_area"] = salvo["area_id"] if salvo else None
            ss[f"{self.k}_evitar"] = salvo["evitar_ids"] if salvo else []
            ss[f"{self.k}_lay"] = p.layout.para_dict()
            ss[f"{self.k}_v"] = 0
            ss[f"{self.k}_fit"] = 0
            ss[f"{self.k}_ini"] = True
            ss[f"{self.k}_salvo"] = (ss[f"{self.k}_geo"], ss[f"{self.k}_area"], list(ss[f"{self.k}_evitar"]),
                                     ss[f"{self.k}_lay"])

    # leitura
    @property
    def geo(self) -> Georreferencia | None:
        d = ss[f"{self.k}_geo"]
        return Georreferencia.de_dict(d) if d else None

    @property
    def layout(self) -> ConfigLayout:
        return ConfigLayout.de_dict(ss[f"{self.k}_lay"])

    @property
    def area_id(self) -> int | None:
        return ss[f"{self.k}_area"]

    @property
    def evitar_ids(self) -> list[int]:
        return list(ss[f"{self.k}_evitar"])

    @property
    def versao(self) -> int:
        return ss[f"{self.k}_v"]

    @property
    def ajuste(self) -> int:
        return ss[f"{self.k}_fit"]

    def alterado(self) -> bool:
        return (ss[f"{self.k}_geo"], ss[f"{self.k}_area"], list(ss[f"{self.k}_evitar"]),
                ss[f"{self.k}_lay"]) != ss[f"{self.k}_salvo"]

    # escrita
    def definir_geo(self, geo: Georreferencia | None, enquadrar: bool = False) -> None:
        ss[f"{self.k}_geo"] = geo.para_dict() if geo else None
        ss[f"{self.k}_v"] += 1
        if enquadrar:
            ss[f"{self.k}_fit"] += 1

    def definir_layout(self, lay: ConfigLayout) -> None:
        ss[f"{self.k}_lay"] = lay.para_dict()
        ss[f"{self.k}_v"] += 1

    def definir_area(self, area_id: int | None, evitar: list[int]) -> None:
        mudou = area_id != ss[f"{self.k}_area"]
        ss[f"{self.k}_area"] = area_id
        ss[f"{self.k}_evitar"] = list(evitar)
        if mudou:
            ss[f"{self.k}_fit"] += 1

    def salvar(self, autor: str) -> None:
        lay = self.layout
        if lay.para_dict() != self.p.layout.para_dict():
            self.repo.atualizar_layout(self.exp_id, lay, autor)
        if self.geo is not None:
            self.repo.salvar_georreferencia(self.exp_id, self.geo, self.area_id, self.evitar_ids, autor)
        else:
            self.repo.remover_georreferencia(self.exp_id, autor)
        self.descartar()

    def descartar(self) -> None:
        for suf in ("_ini", "_geo", "_area", "_evitar", "_lay", "_salvo", "_base"):
            ss.pop(f"{self.k}{suf}", None)


@st.cache_data(show_spinner=False, max_entries=64)
def _area(_repo, area_id: int, _marca: str):
    return _repo.carregar_area(area_id)


def _carregar_area(repo, area_id: int | None):
    if area_id is None:
        return None
    try:
        return repo.carregar_area(area_id)
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------------------------------------- aba
def aba_mapa(p, exp_id: int, repo, autor: str, projeto_id: int, status: str) -> None:
    r = _Rascunho(exp_id, p, repo)
    k = r.k
    lay = r.layout
    cr = croqui_local(p.casualizacao, lay)
    geo = r.geo

    if p.layout.tipo == "vasos":
        st.info("O georreferenciamento é pensado para experimentos de campo. Para vasos, ele pode registrar a posição "
                "da casa de vegetação, mas a locação usa o croqui das bancadas.", icon=":material/info:")

    # ---------------------------------------------------------------- área
    areas = repo.listar_areas(projeto_id)
    perims = [a for a in areas if a["tipo"] == "perimetro"]
    evitaveis = [a for a in areas if a["tipo"] == "evitar"]
    nomes = {a["id"]: f"{a['nome']} · {fmt_num(a['area_ha'])} ha" for a in areas}
    secao("1 · Área de implantação")
    _aplicar_pendente(k)
    c1, c2, c3 = st.columns([2, 2, 1.2])
    opcoes_area = [0] + [a["id"] for a in perims]             # 0 = sem perímetro
    atual = r.area_id if r.area_id in opcoes_area else 0
    if ss.get(f"{k}_sel_area", "x") not in opcoes_area:
        ss[f"{k}_sel_area"] = atual
    ids_evitar = [a["id"] for a in evitaveis]
    if f"{k}_sel_evitar" not in ss or any(i not in ids_evitar for i in ss[f"{k}_sel_evitar"]):
        ss[f"{k}_sel_evitar"] = [i for i in (ss.get(f"{k}_sel_evitar") or r.evitar_ids) if i in ids_evitar]
    area_id = c1.selectbox("Perímetro", opcoes_area, key=f"{k}_sel_area",
                           format_func=lambda i: "— sem perímetro —" if not i else nomes[i],
                           help="Talhão ou área onde o experimento será implantado. Envie um arquivo ou desenhe no mapa.")
    evitar = c2.multiselect("Áreas a evitar", ids_evitar, format_func=nomes.get,
                            key=f"{k}_sel_evitar", help="Cupinzeiros, árvores, terraços, manchas de solo, "
                                                        "canais — o encaixe automático passa longe delas.")
    area_id = area_id or None
    if area_id != r.area_id or evitar != r.evitar_ids:
        r.definir_area(area_id, evitar)
    with c3.popover("Adicionar área", width="stretch", icon=":material/add_location_alt:"):
        _adicionar_area(repo, projeto_id, autor, k)
    area = _carregar_area(repo, area_id)
    evitar_geo = [g for g in (_carregar_area(repo, i) for i in evitar) if g]
    if st.session_state.get(f"{k}_desenhando"):
        _formulario_desenho(repo, projeto_id, autor, k)

    # ---------------------------------------------------------------- posicionamento
    secao("2 · Posição no terreno")
    padrao = "perimetro" if (geo is None and area) else (geo.modo if geo and geo.modo in COMO else "arraste")
    como = st.segmented_control("Como posicionar", list(COMO), format_func=COMO.get, default=padrao,
                                key=f"{k}_como", label_visibility="collapsed") or "arraste"
    editar = "nenhum"
    if st.session_state.get(f"{k}_desenhando"):
        editar = "desenhar"
    elif como == "arraste":
        editar = _painel_arraste(r, cr, area, k, status)
    elif como == "perimetro":
        _painel_encaixe(r, cr, area, evitar_geo, k)
    elif como == "manual":
        _painel_coordenadas(r, cr, k)
    else:
        _painel_controle(r, cr, p, k)

    # ---------------------------------------------------------------- mapa
    c1, c2, c3, c4, c5, c6 = st.columns([1.3, 1.3, 1, 1, 1, 1])
    cor = c1.selectbox("Colorir por", ["tratamento", "bloco", "nenhum"], key=f"{k}_cor",
                       format_func={"tratamento": "Tratamento", "bloco": "Bloco", "nenhum": "Sem cor"}.get)
    rot = c2.selectbox("Rótulo", list(NOMES_ROTULOS), format_func=NOMES_ROTULOS.get, key=f"{k}_rot")
    cam = {"cotas": c3.toggle("Cotas", True, key=f"{k}_cam_cot"),
           "util": c4.toggle("Área útil", lay.tipo == "parcelas", key=f"{k}_cam_util"),
           "piquetes": c5.toggle("Piquetes", False, key=f"{k}_cam_piq"),
           "rotulos": c6.toggle("Rótulos", True, key=f"{k}_cam_rot")}
    t = Transformacao(geo, cr.largura_total, cr.altura_total) if geo else None
    centro = t.ponto_geo((cr.largura_total / 2, cr.altura_total / 2)) if t else None
    pqs = [[q.x, q.y, q.id] for q in piquetes(cr, p.casualizacao)] if cam["piquetes"] else []
    lista_areas = ([{"tipo": "perimetro", "geometria": area["geometria"]}] if area else []) + \
        [{"tipo": "evitar", "geometria": a["geometria"]} for a in evitar_geo]
    vista = None
    if centro is None and area is None:
        vista = (-15.5, -54.0, 4)
    dados = dados_mapa(p, cr, modo="geo", ref=(centro[1], centro[0]) if centro else None,
                       azimute=geo.azimute if geo else 0.0, editar=editar if (geo or editar != "mover") else "clique",
                       rotulo=rot, colorir_por=cor, camadas=cam, areas=lista_areas, piquetes=pqs,
                       versao=r.versao, ajustar=r.ajuste, altura=600, vista=vista)
    if geo is None and editar in ("mover", "blocos"):
        dados["editar"] = "clique"
    res = mapa_experimento(dados, key=f"{k}_mapa")
    if _processar_mapa(res, r, cr, p, k):
        st.rerun()

    if r.alterado():
        c1, c2, c3 = st.columns([1.4, 1, 3])
        if c1.button("Salvar posição", type="primary", key=f"{k}_salvar", icon=":material/save:",
                     disabled=bool(cr.conflitos), width="stretch"):
            r.salvar(autor)
            st.toast("Posição no terreno salva.")
            st.rerun()
        if c2.button("Descartar", key=f"{k}_desc", width="stretch"):
            r.descartar()
            st.rerun()
        c3.caption("Há alterações ainda não salvas" + (" (inclui o deslocamento de blocos)."
                                                        if lay.para_dict() != p.layout.para_dict() else "."))
    if cr.conflitos:
        st.error("Blocos sobrepostos: " + ", ".join(f"{a} e {b}" for a, b in cr.conflitos)
                 + ". Afaste-os antes de salvar.")
    if geo is None:
        st.info("Posicione o experimento: encaixe-o num perímetro, clique no mapa onde fica o centro, informe "
                "coordenadas ou use pontos medidos com GPS.", icon=":material/near_me:")
        return

    # ---------------------------------------------------------------- conferência e medidas
    secao("3 · Conferência e medidas")
    conf = conferir(cr, geo, area["geometria"] if area else None, [a["geometria"] for a in evitar_geo])
    lon_c, lat_c = centro
    zona = crs.nome_crs(t.epsg).replace("SIRGAS 2000 / ", "").replace("UTM zone ", "UTM ")
    itens = [("Latitude do centro", f"{lat_c:.6f}".replace(".", ","), ""),
             ("Longitude do centro", f"{lon_c:.6f}".replace(".", ","), ""),
             ("Azimute do eixo Y", f"{geo.azimute:.1f}".replace(".", ","), "°"),
             ("Sistema", zona, ""),
             ("Área", fmt_num(conf["area_experimento_m2"]), "m²")]
    if conf["dentro"] is not None:
        itens.append(("Na área", "sim" if conf["dentro"] else "não",
                      f"folga {conf['folga_m']:.1f} m".replace(".", ",") if conf["dentro"] else
                      f"{len(conf['parcelas_fora'])} unidades fora"))
    mostradores(itens)
    if conf["parcelas_fora"] or conf["parcelas_em_obstaculo"]:
        cod = {u.numero: u.codigo or u.parcela for u in p.casualizacao.unidades}
        if conf["parcelas_fora"]:
            st.warning("Unidades fora do perímetro: " + ", ".join(cod[n] for n in conf["parcelas_fora"][:40])
                       + (" …" if len(conf["parcelas_fora"]) > 40 else ""))
        if conf["parcelas_em_obstaculo"]:
            st.warning("Unidades sobre áreas a evitar: " + ", ".join(cod[n] for n in conf["parcelas_em_obstaculo"]))
    if geo.modo == "pontos" and geo.pontos_controle:
        for a in avaliar_ajuste(geo):
            st.warning(a)
    c1, c2 = st.columns([1.1, 1])
    with c1:
        st.markdown("**Medidas do experimento**")
        st.dataframe(_tabela_medidas(cr, t), hide_index=True, width="stretch")
    with c2:
        st.markdown("**Diagonais para conferir o esquadro**")
        st.dataframe(pd.DataFrame(diagonais(cr)), hide_index=True, width="stretch",
                     column_config={"Diagonal (m)": st.column_config.NumberColumn(format="%.2f")})
        st.caption(f"Fator de escala UTM no local: {t.k:.6f} · convergência meridiana: "
                   f"{t.convergencia:+.3f}°. Distâncias do croqui são medidas no terreno; a conversão para a grade "
                   "UTM já está aplicada nos arquivos.".replace(".", ",", 2))

    # ---------------------------------------------------------------- locação e arquivos
    secao("4 · Locação, Google Earth e arquivos")
    _painel_saidas(p, r, cr, geo, t, area, evitar_geo, k, exp_id, repo)


# ------------------------------------------------------------------------------------------------- áreas
def _adicionar_area(repo, projeto_id: int, autor: str, k: str) -> None:
    tipo = st.radio("Tipo", ["perimetro", "evitar"], horizontal=True, key=f"{k}_nova_tipo",
                    format_func={"perimetro": "Perímetro", "evitar": "Área a evitar"}.get)
    arq = st.file_uploader("Arquivo", type=leitura.EXTENSOES, key=f"{k}_upl{ss.get(f'{k}_upl_v', 0)}",
                           help="KML/KMZ (Google Earth), GeoJSON, Shapefile em ZIP, GeoPackage, GPX (trilha do GPS) "
                                "ou CSV com latitude e longitude.")
    if arq is not None:
        try:
            lidas = leitura.ler(arq.getvalue(), arq.name)
        except leitura.ErroLeitura as e:
            st.error(str(e))
            lidas = []
        if lidas:
            opc = list(range(len(lidas)))
            escolha = st.multiselect("Polígonos do arquivo", opc, default=opc[:1], key=f"{k}_upl_sel",
                                     format_func=lambda i: f"{lidas[i].nome} · {fmt_num(lidas[i].area_ha)} ha "
                                                           f"({lidas[i].origem})")
            nome = st.text_input("Nome", lidas[escolha[0]].nome if escolha else "", key=f"{k}_upl_nome")
            if st.button("Salvar área", type="primary", key=f"{k}_upl_ok", disabled=not escolha or not nome.strip()):
                g = unary_union([lidas[i].geometria for i in escolha])
                aid = repo.salvar_area(nome, g, tipo, projeto_id, origem=arq.name, autor=autor)
                _selecionar_area_nova(k, aid, tipo)
                ss[f"{k}_upl_v"] = ss.get(f"{k}_upl_v", 0) + 1
                st.toast(f"Área “{nome}” salva.")
                st.rerun()
    st.divider()
    if st.button("Desenhar no mapa", key=f"{k}_des_ini", icon=":material/draw:", width="stretch"):
        ss[f"{k}_desenhando"] = tipo
        st.rerun()


def _selecionar_area_nova(k: str, aid: int, tipo: str) -> None:
    """Agenda a seleção da área recém-salva (os seletores já foram criados nesta execução)."""
    ss[f"{k}_pendente"] = (aid, tipo)


def _aplicar_pendente(k: str) -> None:
    pend = ss.pop(f"{k}_pendente", None)
    if not pend:
        return
    aid, tipo = pend
    if tipo == "perimetro":
        ss[f"{k}_sel_area"] = aid
    else:
        ss[f"{k}_sel_evitar"] = list(ss.get(f"{k}_sel_evitar", [])) + [aid]


def _formulario_desenho(repo, projeto_id: int, autor: str, k: str) -> None:
    tipo = ss[f"{k}_desenhando"]
    anel = ss.get(f"{k}_anel")
    with st.container(border=True):
        rotulo = "perímetro" if tipo == "perimetro" else "área a evitar"
        if not anel:
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**Desenhando {rotulo}.** Clique no mapa para marcar os vértices; duplo clique (ou *Concluir "
                        "área*) fecha o polígono. *Esc* cancela.")
            if c2.button("Cancelar", key=f"{k}_des_canc", width="stretch"):
                ss.pop(f"{k}_desenhando", None)
                st.rerun()
            return
        pol = Polygon([(lon, lat) for lat, lon in anel])
        if not pol.is_valid:
            pol = pol.buffer(0)
        ha = leitura.AreaLida("", pol, "").area_ha
        c1, c2, c3 = st.columns([2.5, 1, 1])
        nome = c1.text_input(f"Nome do {rotulo} desenhado ({fmt_num(ha)} ha)", key=f"{k}_des_nome",
                             value="Perímetro desenhado" if tipo == "perimetro" else "Área a evitar")
        if c2.button("Salvar", type="primary", key=f"{k}_des_ok", width="stretch", disabled=not nome.strip()):
            aid = repo.salvar_area(nome, pol, tipo, projeto_id, origem="desenhado no mapa", autor=autor)
            _selecionar_area_nova(k, aid, tipo)
            ss.pop(f"{k}_desenhando", None)
            ss.pop(f"{k}_anel", None)
            st.rerun()
        if c3.button("Descartar", key=f"{k}_des_x", width="stretch"):
            ss.pop(f"{k}_anel", None)
            st.rerun()


# ------------------------------------------------------------------------------------------------- posicionamento
def _painel_arraste(r: _Rascunho, cr, area, k: str, status: str) -> str:
    geo = r.geo
    c1, c2, c3 = st.columns([1.3, 1.3, 2])
    travado = status in ("implantado", "em condução", "concluído")
    if geo is None:
        txt = c1.text_input("Ir para (lat, lon)", key=f"{k}_ir", placeholder="-22.2745, -54.8180",
                            help="Cole a coordenada do Google Maps (clique com o botão direito no mapa e copie).")
        if c2.button("Colocar o centro aqui", key=f"{k}_ir_ok", disabled=not txt.strip()):
            try:
                lat, lon = crs.ler_coordenada(txt)
            except ValueError as e:
                st.error(str(e))
            else:
                r.definir_geo(Georreferencia(lat=lat, lon=lon, azimute=0.0, modo="arraste"), enquadrar=True)
                st.rerun()
        if area is not None:
            if c3.button("Começar no centro do perímetro", key=f"{k}_centro_area"):
                c = area["geometria"].representative_point()
                r.definir_geo(Georreferencia(lat=c.y, lon=c.x, azimute=0.0, modo="arraste"), enquadrar=True)
                st.rerun()
        st.caption("Ou clique no mapa onde deve ficar o centro do experimento.")
        return "clique"
    modo = c1.segmented_control("Arrastar", ["mover", "blocos", "ver"], key=f"{k}_arr_modo",
                                default="ver" if travado else "mover",
                                format_func={"mover": "Experimento", "blocos": "Blocos", "ver": "Só ver"}.get)
    modo = modo or "ver"
    az = c2.number_input("Azimute (°)", 0.0, 359.9, float(round(geo.azimute, 1)), 0.5, format="%.1f",
                         key=f"{k}_az_{r.versao}", help="Azimute verdadeiro do eixo Y do croqui ('para cima' do "
                                                        "desenho), medido do Norte no sentido horário.")
    if abs(az - round(geo.azimute, 1)) > 1e-9:
        r.definir_geo(replace(geo, azimute=az, modo="arraste"))
        st.rerun()
    if travado:
        c3.caption("Experimento já implantado: a edição começa em *Só ver* para evitar arrastes acidentais.")
    else:
        c3.caption("Arraste para mover; gire pela alça ocre (Shift = passos de 5°). Em *Blocos*, arraste cada bloco "
                   "para contornar obstáculos ou acompanhar o terreno.")
    return {"mover": "mover", "blocos": "blocos", "ver": "nenhum"}[modo]


def _painel_encaixe(r: _Rascunho, cr, area, evitar_geo, k: str) -> None:
    if area is None:
        st.info("Escolha ou adicione um perímetro para encaixar o experimento automaticamente.")
        return
    c1, c2, c3, c4 = st.columns([1.6, 1, 1, 1.2])
    orient = c1.radio("Orientação", ["melhor", "lado", "fixo"], key=f"{k}_enc_or", horizontal=False,
                      format_func={"melhor": "A de maior folga", "lado": "Alinhada ao lado mais longo da área",
                                   "fixo": "Azimute informado"}.get)
    az = c2.number_input("Azimute (°)", 0.0, 359.9, 0.0, 1.0, key=f"{k}_enc_az", disabled=orient != "fixo",
                         help="Ex.: o sentido das linhas de plantio ou do terraceamento.")
    folga = c3.number_input("Folga mínima (m)", 0.0, 200.0, 0.0, 0.5, key=f"{k}_enc_folga",
                            help="Distância mínima desejada até a divisa e as áreas a evitar.")
    if c4.button("Encaixar", type="primary", key=f"{k}_enc_ok", width="stretch", icon=":material/fit_screen:"):
        with st.spinner("Procurando a melhor posição…"):
            res = encaixar(cr, area["geometria"], [a["geometria"] for a in evitar_geo],
                           azimute_fixo=az if orient == "fixo" else None, alinhar_lado_longo=orient == "lado",
                           folga_desejada=folga)
        r.definir_geo(res.geo, enquadrar=True)
        ss[f"{k}_enc_msg"] = (res.cabe, res.mensagem)
        st.rerun()
    msg = ss.get(f"{k}_enc_msg")
    if msg:
        (st.success if msg[0] else st.warning)(msg[1])


def _painel_coordenadas(r: _Rascunho, cr, k: str) -> None:
    geo = r.geo
    c1, c2, c3, c4 = st.columns([1.6, 1.5, 0.9, 1])
    ref = c2.selectbox("Ponto do croqui", list(REFERENCIAS), format_func=REFERENCIAS.get, key=f"{k}_man_ref")
    padrao = ""
    if geo:
        g2 = com_referencia(geo, ref, cr.largura_total, cr.altura_total)
        padrao = f"{g2.lat:.7f}, {g2.lon:.7f}"
    txt = c1.text_input("Coordenada (lat, lon)", padrao, key=f"{k}_man_txt_{ref}_{r.versao}",
                        help="Graus decimais (como o Google Maps copia) ou graus, minutos e segundos.")
    az = c3.number_input("Azimute (°)", 0.0, 359.9, float(round(geo.azimute, 2)) if geo else 0.0, 0.5,
                         format="%.2f", key=f"{k}_man_az_{r.versao}")
    if c4.button("Aplicar", type="primary", key=f"{k}_man_ok", width="stretch"):
        try:
            lat, lon = crs.ler_coordenada(txt)
        except ValueError as e:
            st.error(str(e))
            return
        g = Georreferencia(lat=lat, lon=lon, azimute=az, referencia=ref, modo="manual")
        r.definir_geo(com_referencia(g, "centro", cr.largura_total, cr.altura_total), enquadrar=True)
        st.rerun()
    st.caption("O azimute é o do eixo Y do croqui (o \"para cima\" do desenho), em graus a partir do Norte verdadeiro, "
               "no sentido horário — o mesmo da régua do Google Earth.")


def _painel_controle(r: _Rascunho, cr, p, k: str) -> None:
    nomes = pontos_notaveis(cr, p.casualizacao)
    st.caption("Marque no campo dois ou mais pontos do croqui (cantos do experimento ou de blocos) e meça-os com GPS. "
               "Com três ou mais, a plataforma calcula o erro de cada ponto. GPS de navegação erra de 3 a 5 m; "
               "com RTK, centímetros.")
    chave = f"{k}_pc_df"
    if chave not in ss:
        ss[chave] = pd.DataFrame([{"Ponto do croqui": n, "Coordenada (lat, lon)": ""} for n in list(nomes)[:3]])
    ed = st.data_editor(ss[chave], num_rows="dynamic", hide_index=True, width="stretch", key=f"{k}_pc_ed",
                        column_config={
                            "Ponto do croqui": st.column_config.SelectboxColumn(options=list(nomes), required=True,
                                                                                width="large"),
                            "Coordenada (lat, lon)": st.column_config.TextColumn(
                                help="Ex.: -22.2741532, -54.8172210", width="medium")})
    if st.button("Ajustar aos pontos", type="primary", key=f"{k}_pc_ok"):
        pts = []
        try:
            for _, row in ed.iterrows():
                if not str(row["Coordenada (lat, lon)"] or "").strip():
                    continue
                lat, lon = crs.ler_coordenada(str(row["Coordenada (lat, lon)"]))
                x, y = nomes[row["Ponto do croqui"]]
                pts.append(PontoControle(row["Ponto do croqui"], x, y, lat, lon))
            g = ajustar(pts, cr.largura_total, cr.altura_total)
        except (ValueError, KeyError) as e:
            st.error(str(e))
            return
        ss[chave] = ed
        r.definir_geo(g, enquadrar=True)
        st.rerun()
    geo = r.geo
    if geo and geo.modo == "pontos" and geo.pontos_controle:
        st.dataframe(pd.DataFrame([{"Ponto": q["nome"], "Resíduo (m)": q["residuo_m"]} for q in geo.pontos_controle]),
                     hide_index=True, width="content")
        st.caption(f"Erro médio quadrático: {geo.residuo_rms:.3f} m".replace(".", ","))


# ------------------------------------------------------------------------------------------------- retorno do mapa
def _processar_mapa(res, r: _Rascunho, cr, p, k: str) -> bool:
    if res is None:
        return False
    mudou = False
    pos = getattr(res, "posicao", None)
    if pos and pos.get("versao") == r.versao and pos.get("n") != ss.get(f"{k}_np"):
        ss[f"{k}_np"] = pos.get("n")
        geo = r.geo
        if geo is not None:
            nova = Georreferencia(lat=float(pos["lat"]), lon=float(pos["lon"]), azimute=float(pos["azimute"]),
                                  referencia="centro", modo="arraste", epsg=geo.epsg)
            desloc = {str(a): [float(b[0]), float(b[1])] for a, b in (pos.get("deslocamentos") or {}).items()}
            lay = r.layout
            if pos.get("tipo") == "bloco" and desloc != (lay.deslocamentos_blocos or {}):
                novo_lay = replace(lay, deslocamentos_blocos=desloc)
                novo_cr = croqui_local(p.casualizacao, novo_lay)
                movido = pos.get("grupo_movido")
                fixo = next((g for g in sorted(cr.caixas) if g != movido), movido or 1)
                nova = reancorar(com_referencia(nova, "centro", cr.largura_total, cr.altura_total), cr, novo_cr, fixo)
                r.definir_layout(ConfigLayout.de_dict(novo_lay.para_dict()))
            r.definir_geo(nova)
            mudou = True
    cl = getattr(res, "clique", None)
    if cl and cl.get("n") != ss.get(f"{k}_nc"):
        ss[f"{k}_nc"] = cl.get("n")
        geo = r.geo
        r.definir_geo(Georreferencia(lat=float(cl["lat"]), lon=float(cl["lon"]),
                                     azimute=geo.azimute if geo else 0.0, modo="arraste"))
        mudou = True
    de = getattr(res, "desenho", None)
    if de and de.get("n") != ss.get(f"{k}_nd") and ss.get(f"{k}_desenhando"):
        ss[f"{k}_nd"] = de.get("n")
        ss[f"{k}_anel"] = de["anel"]
        mudou = True
    return mudou


# ------------------------------------------------------------------------------------------------- tabelas e saídas
def _tabela_medidas(cr, t: Transformacao) -> pd.DataFrame:
    cfg = cr.config
    m = cr.metricas
    lin = [("Largura total (eixo X)", texto_medida(cr.largura_total)),
           ("Comprimento total (eixo Y)", texto_medida(cr.altura_total)),
           ("Área total", f"{fmt_num(m['area_total_m2'])} m²")]
    if cfg.tipo == "parcelas":
        lin += [("Parcela", f"{texto_medida(m['largura_parcela_m'])} × {texto_medida(m['comprimento_parcela_m'])}"),
                ("Área útil da parcela", f"{texto_medida(m['largura_util_m'])} × {texto_medida(m['comprimento_util_m'])}"),
                ("Entre parcelas (lateral)", texto_medida(cfg.espaco_x)),
                ("Entre linhas de parcelas", texto_medida(cfg.espaco_y))]
    else:
        lin += [("Diâmetro do vaso", texto_medida(cfg.diametro_vaso)),
                ("Entre vasos (livre)", texto_medida(cfg.espaco_vasos))]
    if cr.blocos:
        lin.append(("Carreador entre blocos", texto_medida(cfg.espaco_blocos)))
        if 0 < cfg.blocos_por_fileira < len(cr.blocos):
            lin.append(("Entre fileiras de blocos", texto_medida(cfg.espaco_fileiras)))
    if cfg.corredor_a_cada_colunas and cfg.largura_corredor_colunas:
        lin.append((f"Corredor a cada {cfg.corredor_a_cada_colunas} unidades", texto_medida(cfg.largura_corredor_colunas)))
    if cfg.corredor_a_cada_linhas and cfg.largura_corredor_linhas:
        lin.append((f"Corredor a cada {cfg.corredor_a_cada_linhas} linhas", texto_medida(cfg.largura_corredor_linhas)))
    bs = {lado: cfg.bordadura(lado) for lado in ("esquerda", "direita", "topo", "base")}
    if len(set(bs.values())) == 1:
        lin.append(("Bordadura externa", texto_medida(bs["esquerda"]) if bs["esquerda"] else "—"))
    else:
        lin.append(("Bordadura externa (E · D · topo · base)", " · ".join(texto_medida(v) for v in bs.values())))
    lin.append(("Azimute do eixo X (largura)", f"{t.azimute_eixo_x:.1f}°".replace(".", ",")))
    lin.append(("Azimute do eixo Y (comprimento)", f"{t.geo.azimute:.1f}°".replace(".", ",")))
    return pd.DataFrame(lin, columns=["Medida", "Valor"])


def _painel_saidas(p, r: _Rascunho, cr, geo, t, area, evitar_geo, k: str, exp_id: int, repo) -> None:
    from motor.exportacao.plano_locacao import plano_locacao

    nome = f"{p.meta.codigo}_v{p.versao}"
    p_lay = p
    if r.layout.para_dict() != p.layout.para_dict():
        import copy

        p_lay = copy.copy(p)
        p_lay.trocar_layout(r.layout)
        st.caption("Os arquivos usam a disposição em edição (ainda não salva).")
    c1, c2 = st.columns([1, 1])
    com_parcelas = c1.toggle("Piquetes também nos cantos de cada parcela", True, key=f"{k}_pq_parc")
    wgs = c2.toggle("Shapefile e GeoPackage em WGS 84 (em vez de UTM)", False, key=f"{k}_wgs")
    cj = feicoes.montar(p_lay, geo, area["geometria"] if area else None, [a["geometria"] for a in evitar_geo],
                        piquetes_de_parcela=com_parcelas)
    cache = ss.setdefault("_exportacoes_gis", {})
    assinatura = f"{exp_id}|{p.versao}|{geo.para_dict()}|{r.layout.para_dict()}|{com_parcelas}|{wgs}|" \
                 f"{area['id'] if area else None}|{[a['id'] for a in evitar_geo]}|{p.meta.titulo}"

    def gerar(chave, f):
        ck = (assinatura, chave)
        if ck not in cache:
            cache[ck] = f()
            while len(cache) > 16:
                cache.pop(next(iter(cache)))
        return cache[ck]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Locação no campo**")
        st.download_button("Plano de locação (PDF)", lambda: gerar("plano", lambda: plano_locacao(p_lay, cj)),
                           f"{nome}_plano_locacao.pdf", "application/pdf", type="primary", width="stretch",
                           key=f"{k}_dl_plano", icon=":material/straighten:",
                           help="Mapa com coordenadas, medidas, piquetes (local, UTM e lat/lon), diagonais e roteiro "
                                "de locação com trena.")
        st.download_button("Piquetes (CSV)", lambda: gerar("pqcsv", lambda: exportar.csv_camada(cj, "piquetes")),
                           f"{nome}_piquetes.csv", "text/csv", width="stretch", key=f"{k}_dl_pq")
        st.download_button("GPS — pontos (GPX)", lambda: gerar("gpx", lambda: exportar.gpx(cj).encode("utf-8")),
                           f"{nome}.gpx", "application/gpx+xml", width="stretch", key=f"{k}_dl_gpx",
                           help="Piquetes e centros das parcelas como pontos de passagem (Garmin, apps de campo).")
    with c2:
        st.markdown("**Google Earth**")
        lon_c, lat_c = cj.centro_geo
        st.link_button("Abrir o local no Google Earth", exportar.link_google_earth(
            lon_c, lat_c, max(cr.largura_total, cr.altura_total) * 3 + 80, geo.azimute), width="stretch",
            icon=":material/public:")
        st.download_button("Experimento para o Google Earth (KMZ)", lambda: gerar("kmz", lambda: exportar.kmz(cj)),
                           f"{nome}.kmz", "application/vnd.google-earth.kmz", type="primary", width="stretch",
                           key=f"{k}_dl_kmz")
        st.caption("No Google Earth na Web: *Projetos → Novo projeto → Importar arquivo KML do computador*. No Google "
                   "Earth Pro, basta abrir o KMZ. Com o Google Drive ligado, o KMZ vai para a pasta do experimento e "
                   "abre direto no Earth.")
        st.link_button("Ver no Google Maps", exportar.link_google_maps(lon_c, lat_c), width="stretch")
    with c3:
        st.markdown("**SIG e CAD**")
        sufixo = "wgs84" if wgs else f"utm{cj.epsg}"
        st.download_button("Shapefile (ZIP)", lambda: gerar("shp", lambda: exportar.shapefile_zip(cj, wgs)),
                           f"{nome}_{sufixo}_shp.zip", "application/zip", width="stretch", key=f"{k}_dl_shp")
        st.download_button("GeoPackage", lambda: gerar("gpkg", lambda: exportar.geopackage(cj, wgs)),
                           f"{nome}_{sufixo}.gpkg", "application/geopackage+sqlite3", width="stretch",
                           key=f"{k}_dl_gpkg")
        st.download_button("GeoJSON", lambda: gerar("geojson", lambda: exportar.geojson(cj)),
                           f"{nome}.geojson", "application/geo+json", width="stretch", key=f"{k}_dl_gj")
        st.download_button("DXF (CAD, UTM)", lambda: gerar("dxf", lambda: exportar.dxf(cj)),
                           f"{nome}_utm.dxf", "application/dxf", width="stretch", key=f"{k}_dl_dxf")
        st.download_button("Centros das parcelas (CSV)",
                           lambda: gerar("ctcsv", lambda: exportar.csv_camada(cj, "centroides")),
                           f"{nome}_centros.csv", "text/csv", width="stretch", key=f"{k}_dl_ct")
    with st.expander("Roteiro de locação com trena"):
        for i, passo in enumerate(roteiro_trena(cj.transformacao), start=1):
            st.markdown(f"{i}. {passo}")
    c1, c2 = st.columns(2)
    if area is not None and c1.button("Diagnóstico por satélite desta área", key=f"{k}_sat", width="stretch",
                                      icon=":material/satellite_alt:"):
        from ui.estado import PAGINAS

        ss["sat_area_pre"] = {"nome": area["nome"], "kml": leitura.para_kml(area["geometria"], area["nome"])}
        st.switch_page(PAGINAS["satelites"])
    with c2:
        from componentes.drive_ui import botao_drive_experimento

        botao_drive_experimento(p_lay, exp_id, repo, cj=cj, chave=k)


def _num(v: float) -> str:
    return f"{v:.2f}".replace(".", ",") if math.isfinite(v) else "—"
