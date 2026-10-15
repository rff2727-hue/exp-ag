/* Exp-Ag — mapa do experimento (Leaflet embutido).
 *
 * Recebe do Python a geometria do croqui no plano local (metros) e a posição no terreno (centro + azimute
 * verdadeiro). Desenha sobre a imagem de satélite e permite:
 *   - "mover": arrastar o experimento inteiro e girá-lo pela alça;
 *   - "blocos": arrastar blocos/bancadas individualmente (deslocamentos no plano do croqui);
 *   - "desenhar": desenhar um polígono (perímetro ou área a evitar);
 *   - "clique": clicar para indicar o centro do experimento.
 * Ao soltar, devolve a nova posição (setStateValue "posicao"); desenhos e cliques vão como gatilhos.
 * No modo "local" (sem georreferência) usa um plano cartesiano em metros — é o editor de croqui por arraste.
 */

const A = 6378137.0, F = 1 / 298.257223563, E2 = F * (2 - F);
const RAD = Math.PI / 180;

function raios(latGraus) {
  const s = Math.sin(latGraus * RAD);
  const w = Math.sqrt(1 - E2 * s * s);
  return { M: A * (1 - E2) / (w * w * w), N: A / w };
}

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}

function fmt(v, casas) {
  return v.toFixed(casas).replace(".", ",");
}

class MapaExpAg {
  constructor(raiz, comp) {
    this.comp = comp;
    this.raiz = raiz;
    this.caixa = el("div", "ea-caixa");
    this.divMapa = el("div", "ea-mapa");
    this.caixa.appendChild(this.divMapa);
    raiz.appendChild(this.caixa);
    this.temp = {};        // deslocamentos temporários por grupo durante o arraste (m, plano do croqui)
    this.n = 0;            // contador de envios
    this.versao = null;
    this.ajuste = null;
    this.desenho = [];
    this.fundoAtual = null;
  }

  // ------------------------------------------------------------------ transformação local -> mapa
  centro() { return this.pos; }

  paraMapa(x, y, g) {
    const d = this.d;
    let ox = 0, oy = 0;
    if (g !== undefined && this.temp[g]) { ox = this.temp[g][0]; oy = this.temp[g][1]; }
    const dx = x + ox - d.W / 2, dy = y + oy - d.H / 2;
    if (d.modo === "local") return L.latLng(d.H / 2 + dy, d.W / 2 + dx);
    const a = this.pos.azimute * RAD, c = Math.cos(a), s = Math.sin(a);
    const dE = dx * c + dy * s, dN = -dx * s + dy * c;
    const r = raios(this.pos.lat);
    return L.latLng(this.pos.lat + dN / r.M / RAD, this.pos.lon + dE / (r.N * Math.cos(this.pos.lat * RAD)) / RAD);
  }

  metrosEntre(ll1, ll2) {           // (dE, dN) de ll1 a ll2
    if (this.d.modo === "local") return [ll2.lng - ll1.lng, ll2.lat - ll1.lat];
    const r = raios(ll1.lat);
    return [(ll2.lng - ll1.lng) * RAD * r.N * Math.cos(ll1.lat * RAD), (ll2.lat - ll1.lat) * RAD * r.M];
  }

  paraLocal(dE, dN) {               // vetor no terreno -> vetor no plano do croqui
    if (this.d.modo === "local") return [dE, dN];
    const a = this.pos.azimute * RAD, c = Math.cos(a), s = Math.sin(a);
    return [dE * c - dN * s, dE * s + dN * c];
  }

  anel(pts, g) { return pts.map(p => this.paraMapa(p[0], p[1], g)); }

  // ------------------------------------------------------------------ mapa e fundo
  iniciarMapa() {
    const d = this.d;
    const opc = { zoomControl: true, attributionControl: true, preferCanvas: true, zoomSnap: 0.25,
                  zoomDelta: 0.5, wheelPxPerZoomLevel: 90, doubleClickZoom: false, boxZoom: false };
    if (d.modo === "local") { opc.crs = L.CRS.Simple; opc.minZoom = -6; opc.maxZoom = 8; }
    else { opc.maxZoom = 23; }
    this.mapa = L.map(this.divMapa, opc);
    this.mapa.attributionControl.setPrefix(false);
    this.renderer = L.canvas({ padding: 0.3, tolerance: 3 });
    this.gExp = L.layerGroup().addTo(this.mapa);
    this.gAreas = L.layerGroup().addTo(this.mapa);
    this.gRot = L.layerGroup().addTo(this.mapa);
    this.gDes = L.layerGroup().addTo(this.mapa);
    this.criarControles();
    this.mapa.on("zoomend", () => this.atualizarRotulos());
    // a aba pode estar oculta quando o mapa nasce (tamanho zero): ao aparecer, recalcula o tamanho e enquadra
    this.ro = new ResizeObserver(() => {
      const w = this.divMapa.clientWidth, h = this.divMapa.clientHeight;
      if (!w || !h) return;
      const tam = `${w}x${h}`;
      if (tam === this._tam) return;
      this._tam = tam;
      this.mapa.invalidateSize();
      if (this._enquadrarDepois) { this._enquadrarDepois = false; this.enquadrar(); }
      this.atualizarRotulos();
    });
    this.ro.observe(this.divMapa);
    this.mapa.on("click", (e) => this.aoClicar(e));
    this.mapa.on("dblclick", () => { if (this.d.editar === "desenhar") this.concluirDesenho(); });
    this.mapa.on("mousemove", (e) => this.aoMover(e));
    this.mapa.on("mouseup", (e) => this.aoSoltar(e));
    document.addEventListener("mouseup", this._soltarDoc = (e) => { if (this.arrasto) this.aoSoltar(e); });
    document.addEventListener("keydown", this._tecla = (e) => {
      if (this.d && this.d.editar === "desenhar") {
        if (e.key === "Escape") this.cancelarDesenho();
        if (e.key === "Enter") this.concluirDesenho();
      }
    });
  }

  definirFundo(nome) {
    if (this.d.modo === "local") return;
    if (this.fundoAtual === nome) return;
    if (this.camadaFundo) this.mapa.removeLayer(this.camadaFundo);
    if (this.camadaNomes) { this.mapa.removeLayer(this.camadaNomes); this.camadaNomes = null; }
    this.camadaFundo = null;
    if (nome === "satelite") {
      this.camadaFundo = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        { maxNativeZoom: 19, maxZoom: 23, attribution: "Imagem © Esri, Maxar, Earthstar Geographics" });
      this.camadaNomes = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        { maxNativeZoom: 19, maxZoom: 23, opacity: 0.85 });
    } else if (nome === "mapa") {
      this.camadaFundo = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        { maxNativeZoom: 19, maxZoom: 23, attribution: "© colaboradores do OpenStreetMap" });
    }
    if (this.camadaFundo) this.camadaFundo.addTo(this.mapa).bringToBack();
    if (this.camadaNomes) this.camadaNomes.addTo(this.mapa);
    const mudou = this.fundoAtual !== null && this.fundoAtual !== undefined;
    this.fundoAtual = nome;
    this.caixa.querySelectorAll(".ea-fundo button").forEach(b => b.classList.toggle("ativo", b.dataset.f === nome));
    if (mudou && this.gExp && !this.arrasto) this.redesenhar();
  }

  criarControles() {
    const d = this.d;
    const Ctl = L.Control.extend({
      onAdd: () => {
        const div = el("div", "ea-ctl leaflet-bar");
        L.DomEvent.disableClickPropagation(div);
        L.DomEvent.disableScrollPropagation(div);
        if (d.modo !== "local") {
          const f = el("div", "ea-fundo");
          [["satelite", "Satélite"], ["mapa", "Mapa"], ["nenhum", "Sem fundo"]].forEach(([k, t]) => {
            const b = el("button", "", t); b.dataset.f = k; b.type = "button";
            b.onclick = () => this.definirFundo(k);
            f.appendChild(b);
          });
          div.appendChild(f);
        }
        const linha = el("div", "ea-fundo");
        const e = el("button", "ea-enq", "Experimento");
        e.type = "button"; e.title = "Enquadrar o experimento";
        e.onclick = () => this.enquadrar("exp");
        linha.appendChild(e);
        if (d.modo !== "local") {
          const a = el("button", "ea-enq", "Área");
          a.type = "button"; a.title = "Enquadrar a área de implantação";
          a.onclick = () => this.enquadrar("area");
          linha.appendChild(a);
        }
        div.appendChild(linha);
        return div;
      }
    });
    this.ctl = new Ctl({ position: "topright" }).addTo(this.mapa);
    this.painel = el("div", "ea-painel");
    this.caixa.appendChild(this.painel);
    this.barraDesenho = el("div", "ea-barra-des");
    const bOk = el("button", "primario", "Concluir área"); bOk.type = "button";
    const bDesf = el("button", "", "Desfazer ponto"); bDesf.type = "button";
    const bCanc = el("button", "", "Limpar"); bCanc.type = "button";
    bOk.onclick = () => this.concluirDesenho();
    bDesf.onclick = () => { this.desenho.pop(); this.desenharRascunho(); };
    bCanc.onclick = () => this.cancelarDesenho();
    [bOk, bDesf, bCanc].forEach(b => { L.DomEvent.disableClickPropagation(b); this.barraDesenho.appendChild(b); });
    this.caixa.appendChild(this.barraDesenho);
  }

  enquadrar(alvo) {
    const pts = [];
    const temExp = this.d.contorno && !this.d.ocultar;
    if (!alvo) alvo = temExp ? "exp" : "area";
    if (temExp && alvo === "exp") this.anel(this.d.contorno).forEach(p => pts.push(p));
    if (alvo === "area" || !pts.length)
      (this.d.areas || []).forEach(a => a.aneis.forEach(r => r.forEach(p => pts.push(L.latLng(p[0], p[1])))));
    if (!pts.length && temExp) this.anel(this.d.contorno).forEach(p => pts.push(p));
    if (!pts.length) {
      if (this.d.modo !== "local") this.mapa.setView(this.d.vista ? [this.d.vista[0], this.d.vista[1]] : [-15.5, -54.0],
                                                    this.d.vista ? this.d.vista[2] : 4);
      return;
    }
    const b = L.latLngBounds(pts);
    this.mapa.fitBounds(b, { padding: alvo === "exp" ? [60, 60] : [28, 28], maxZoom: this.d.modo === "local" ? 6 : 21 });
  }

  // ------------------------------------------------------------------ desenho do experimento
  claro() { return this.d.modo !== "local" && this.fundoAtual === "satelite"; }

  redesenhar() {
    const d = this.d;
    const linha = this.claro() ? "#FFFFFF" : "#3A3D40";
    this.gExp.clearLayers();
    this.gRot.clearLayers();
    this.camPorGrupo = {};
    this.camContorno = null;
    if (d.ocultar) { this.atualizarPainel(); return; }
    const r = this.renderer;
    const editar = d.editar;
    const exp = L.polygon(this.anel(d.contorno), { renderer: r, color: "#174A51", weight: 2.5, fill: true,
      fillOpacity: editar === "mover" ? 0.06 : 0.0, fillColor: "#174A51", interactive: editar === "mover" });
    exp.on("mousedown", (e) => this.iniciarArrasto(e, "mover"));
    exp.addTo(this.gExp);
    this.camContorno = exp;
    (d.grupos || []).forEach(g => {
      const cams = [];
      if (g.contorno && d.camadas.blocos) {
        const p = L.polygon(this.anel(g.contorno, g.id), { renderer: r, color: linha, weight: 1.6,
          dashArray: "6 4", fill: editar === "blocos", fillOpacity: 0.05, interactive: editar === "blocos" });
        p._anel = g.contorno; p._g = g.id;
        p.on("mousedown", (e) => this.iniciarArrasto(e, "bloco", g.id));
        p.addTo(this.gExp); cams.push(p);
      } else if (editar === "blocos") {
        const p = L.polygon(this.anel(g.caixa, g.id), { renderer: r, color: "#AE7E2F", weight: 1.2, dashArray: "4 4",
          fill: true, fillOpacity: 0.04 });
        p._anel = g.caixa; p._g = g.id;
        p.on("mousedown", (e) => this.iniciarArrasto(e, "bloco", g.id));
        p.addTo(this.gExp); cams.push(p);
      }
      this.camPorGrupo[g.id] = cams;
    });
    d.unidades.forEach(u => {
      const p = L.polygon(this.anel(u.p, u.g), { renderer: r, color: "#1C1D1F", weight: 0.8, fillColor: u.cor,
        fillOpacity: 0.78 });
      p._anel = u.p; p._g = u.g;
      p.bindTooltip(u.dica, { sticky: true, direction: "top", className: "ea-dica" });
      if (editar === "mover") p.on("mousedown", (e) => this.iniciarArrasto(e, "mover"));
      if (editar === "blocos") p.on("mousedown", (e) => this.iniciarArrasto(e, "bloco", u.g));
      p.addTo(this.gExp);
      (this.camPorGrupo[u.g] = this.camPorGrupo[u.g] || []).push(p);
      if (u.u && d.camadas.util) {
        const q = L.polyline(this.anel(u.u.concat([u.u[0]]), u.g), { renderer: r, color: linha, weight: 0.7,
          dashArray: "2 3", opacity: 0.9, interactive: false });
        q._anel = u.u.concat([u.u[0]]); q._g = u.g; q.addTo(this.gExp);
        this.camPorGrupo[u.g].push(q);
      }
    });
    if (d.camadas.cotas) {
      (d.cotas || []).forEach(c => {
        c.segs.forEach(sg => {
          const l = L.polyline([this.paraMapa(sg[0][0], sg[0][1]), this.paraMapa(sg[1][0], sg[1][1])],
            { renderer: r, color: linha, weight: 1.1, opacity: 0.95, interactive: false });
          l._seg = sg; l.addTo(this.gExp);
        });
      });
    }
    if (d.camadas.piquetes) {
      (d.piquetes || []).forEach(q => {
        const m = L.circleMarker(this.paraMapa(q[0], q[1]), { renderer: r, radius: 3, color: "#AE7E2F", weight: 1,
          fillColor: "#F4F0E8", fillOpacity: 1 });
        m.bindTooltip(q[2], { direction: "top", className: "ea-dica" });
        m._pt = q; m.addTo(this.gExp);
      });
    }
    if (editar === "mover" && d.modo !== "local") this.criarAlca();
    this.atualizarRotulos();
    this.atualizarPainel();
  }

  criarAlca() {
    const d = this.d;
    const R = d.H / 2 + Math.max(d.W, d.H) * 0.12 + 2;
    this._raioAlca = R;
    const ll = this.paraMapa(d.W / 2, d.H / 2 + R);
    const haste = L.polyline([this.paraMapa(d.W / 2, d.H), ll], { renderer: this.renderer, color: "#AE7E2F",
      weight: 2, interactive: false });
    haste._seg = [[d.W / 2, d.H], [d.W / 2, d.H / 2 + R]];
    haste.addTo(this.gExp);
    const alca = L.circleMarker(ll, { renderer: this.renderer, radius: 9, color: "#FFFFFF", weight: 2,
      fillColor: "#AE7E2F", fillOpacity: 1, className: "ea-alca" });
    alca._pt = [d.W / 2, d.H / 2 + R];
    alca.bindTooltip("Arraste para girar", { direction: "right", className: "ea-dica" });
    alca.on("mousedown", (e) => this.iniciarArrasto(e, "girar"));
    alca.addTo(this.gExp);
  }

  // rótulos (DOM) — tamanho conforme o zoom; giram com o experimento
  atualizarRotulos() {
    const d = this.d;
    if (!this.mapa || !d) return;
    this.gRot.clearLayers();
    if (d.ocultar) return;
    const z = this.mapa.getZoom();
    let mpp;
    if (d.modo === "local") mpp = 1 / Math.pow(2, z);
    else mpp = 156543.03392 * Math.cos(this.pos.lat * RAD) / Math.pow(2, z);
    const pxm = 1 / mpp;
    const ang = d.modo === "local" ? 0 : this.pos.azimute;
    const vertical = (a) => { let r = ((a % 360) + 360) % 360; if (r > 90 && r <= 270) r -= 180; return r; };
    if (d.camadas.rotulos) {
      const w = d.dim[0] * pxm, h = d.dim[1] * pxm;
      const linhas = d.maxLinhas, chars = d.maxChars;
      let fs = Math.min(15, w * 0.8 / (0.62 * chars), h * 0.62 / (1.25 * linhas));
      if (fs >= 6) {
        d.unidades.forEach(u => {
          const ll = this.paraMapa(u.c[0], u.c[1], u.g);
          const ic = L.divIcon({ className: "ea-rot", iconSize: null,
            html: `<div style="font-size:${fs.toFixed(1)}px;color:${u.tc};transform:translate(-50%,-50%) rotate(${vertical(ang)}deg)">${u.rot}</div>` });
          L.marker(ll, { icon: ic, interactive: false, keyboard: false }).addTo(this.gRot);
        });
      }
    }
    const larguraBloco = (d.grupos && d.grupos.length) ? Math.max(...d.grupos[0].caixa.map(p => p[0])) -
      Math.min(...d.grupos[0].caixa.map(p => p[0])) : d.W;
    const expPx = Math.max(d.W, d.H) * pxm;
    if (d.camadas.blocos && larguraBloco * pxm >= 70) {
      (d.grupos || []).forEach(g => {
        if (!g.rotulo_em) return;
        const ll = this.paraMapa(g.rotulo_em[0], g.rotulo_em[1], g.id);
        const ic = L.divIcon({ className: "ea-rot", iconSize: null,
          html: `<div class="ea-bloco" style="transform:translate(-50%,-50%) rotate(${vertical(ang)}deg)">${g.rotulo}</div>` });
        L.marker(ll, { icon: ic, interactive: false, keyboard: false }).addTo(this.gRot);
      });
    }
    if (d.camadas.cotas && expPx >= 260) {
      (d.cotas || []).forEach(c => {
        const L_m = c.v * pxm;
        if (L_m < 18 && !c.geral) return;
        const ll = this.paraMapa(c.pos[0], c.pos[1]);
        const rot = vertical(ang - c.ang);
        const ic = L.divIcon({ className: "ea-rot", iconSize: null,
          html: `<div class="ea-cota${c.geral ? " geral" : ""}" style="transform:translate(-50%,-50%) rotate(${rot}deg)">${c.txt}</div>` });
        L.marker(ll, { icon: ic, interactive: false, keyboard: false }).addTo(this.gRot);
      });
    }
    if (d.camadas.piquetes && z >= (d.modo === "local" ? 3 : 20)) {
      (d.piquetes || []).forEach(q => {
        const ic = L.divIcon({ className: "ea-rot", iconSize: null,
          html: `<div class="ea-piq">${q[2]}</div>` });
        L.marker(this.paraMapa(q[0], q[1]), { icon: ic, interactive: false, keyboard: false }).addTo(this.gRot);
      });
    }
  }

  atualizarGeometria(grupoSo) {
    // reposiciona as camadas existentes (arraste) sem recriá-las
    this.gExp.eachLayer(l => {
      if (grupoSo !== undefined && l._g !== grupoSo) return;
      if (l._anel) l.setLatLngs(this.anel(l._anel, l._g));
      else if (l._seg && grupoSo === undefined) l.setLatLngs([this.paraMapa(l._seg[0][0], l._seg[0][1]),
                                                              this.paraMapa(l._seg[1][0], l._seg[1][1])]);
      else if (l._pt && grupoSo === undefined) l.setLatLng(this.paraMapa(l._pt[0], l._pt[1]));
    });
    if (grupoSo === undefined && this.camContorno) this.camContorno.setLatLngs(this.anel(this.d.contorno));
  }

  atualizarPainel() {
    const d = this.d;
    let t = "";
    if (d.modo === "local") {
      t = d.editar === "blocos" ? "<b>Arraste os blocos</b> para reposicioná-los. Medidas em metros." : "Croqui em metros.";
    } else if (d.ocultar) {
      t = "Experimento ainda sem posição no terreno.";
    } else {
      t = `<b>Centro</b> ${fmt(this.pos.lat, 6)}, ${fmt(this.pos.lon, 6)} · <b>Azimute</b> ${fmt(this.pos.azimute, 1)}°`;
      const extra = {
        mover: "Arraste o experimento para movê-lo; gire pela alça ocre.",
        blocos: "Arraste cada bloco para reposicioná-lo no terreno.",
        desenhar: "Clique para marcar os vértices; duplo clique ou <i>Concluir área</i> fecha o polígono.",
        clique: "Clique no mapa onde deve ficar o centro do experimento.",
      }[d.editar];
      if (extra) t += `<br>${extra}`;
    }
    if (this.arrasto && this.arrasto.tipo === "bloco") {
      const o = this.temp[this.arrasto.g] || [0, 0];
      t += `<br>Bloco ${this.arrasto.rot}: ${fmt(o[0], 2)} m → , ${fmt(o[1], 2)} m ↑`;
    }
    this.painel.innerHTML = t;
    this.barraDesenho.style.display = d.editar === "desenhar" ? "flex" : "none";
    this.divMapa.style.cursor = (d.editar === "desenhar" || d.editar === "clique") ? "crosshair" : "";
  }

  // ------------------------------------------------------------------ arraste
  iniciarArrasto(e, tipo, g) {
    if (this.d.editar === "desenhar" || this.d.editar === "clique") return;
    L.DomEvent.stop(e);
    if (e.originalEvent) e.originalEvent.preventDefault();
    this.mapa.dragging.disable();
    const grupo = (this.d.grupos || []).find(x => x.id === g);
    this.arrasto = { tipo, g, ini: e.latlng, pos0: Object.assign({}, this.pos),
                     temp0: this.temp[g] ? this.temp[g].slice() : [0, 0], rot: grupo ? grupo.rotulo : "" };
    this.caixa.classList.add("arrastando");
  }

  aoMover(e) {
    if (this.d.editar === "desenhar" && this.desenho.length) { this.desenharRascunho(e.latlng); return; }
    const a = this.arrasto;
    if (!a) return;
    if (a.tipo === "mover") {
      const [dE, dN] = this.metrosEntre(a.ini, e.latlng);
      const r = raios(a.pos0.lat);
      this.pos.lat = a.pos0.lat + dN / r.M / RAD;
      this.pos.lon = a.pos0.lon + dE / (r.N * Math.cos(a.pos0.lat * RAD)) / RAD;
      this.atualizarGeometria();
    } else if (a.tipo === "girar") {
      const c = L.latLng(this.pos.lat, this.pos.lon);
      const [dE, dN] = this.metrosEntre(c, e.latlng);
      let az = Math.atan2(dE, dN) / RAD;
      const passo = e.originalEvent && e.originalEvent.shiftKey ? 5 : 0.1;
      az = Math.round(az / passo) * passo;
      this.pos.azimute = ((az % 360) + 360) % 360;
      this.atualizarGeometria();
    } else if (a.tipo === "bloco") {
      const [dE, dN] = this.metrosEntre(a.ini, e.latlng);
      const [lx, ly] = this.paraLocal(dE, dN);
      const passo = 0.1;
      this.temp[a.g] = [Math.round((a.temp0[0] + lx) / passo) * passo, Math.round((a.temp0[1] + ly) / passo) * passo];
      this.atualizarGeometria(a.g);
    }
    this.atualizarPainel();
  }

  aoSoltar() {
    const a = this.arrasto;
    if (!a) return;
    this.arrasto = null;
    this.mapa.dragging.enable();
    this.caixa.classList.remove("arrastando");
    this.atualizarRotulos();
    const mudou = a.tipo === "bloco" ? (this.temp[a.g] && (this.temp[a.g][0] !== a.temp0[0] || this.temp[a.g][1] !== a.temp0[1]))
      : (this.pos.lat !== a.pos0.lat || this.pos.lon !== a.pos0.lon || this.pos.azimute !== a.pos0.azimute);
    if (!mudou) return;
    this.n += 1;
    const desloc = {};
    const base = this.d.desloc || {};
    const ids = new Set([...Object.keys(base), ...Object.keys(this.temp)]);
    ids.forEach(k => {
      const b = base[k] || [0, 0], t = this.temp[k] || [0, 0];
      desloc[k] = [Math.round((b[0] + t[0]) * 1000) / 1000, Math.round((b[1] + t[1]) * 1000) / 1000];
    });
    this.comp.setStateValue("posicao", {
      lat: this.pos.lat, lon: this.pos.lon, azimute: this.pos.azimute, deslocamentos: desloc,
      grupo_movido: a.tipo === "bloco" ? a.g : null, tipo: a.tipo, n: this.n, versao: this.d.versao });
  }

  // ------------------------------------------------------------------ clique e desenho
  aoClicar(e) {
    const d = this.d;
    if (d.editar === "clique") {
      this.n += 1;
      this.comp.setTriggerValue("clique", { lat: e.latlng.lat, lon: e.latlng.lng, n: this.n });
    } else if (d.editar === "desenhar") {
      this.desenho.push(e.latlng);
      this.desenharRascunho();
    }
  }

  desenharRascunho(cursor) {
    this.gDes.clearLayers();
    const pts = this.desenho.slice();
    if (cursor) pts.push(cursor);
    if (pts.length >= 2) {
      L.polyline(pts.concat(pts.length >= 3 ? [pts[0]] : []), { color: "#AE7E2F", weight: 2.5, dashArray: "6 4",
        interactive: false }).addTo(this.gDes);
    }
    this.desenho.forEach((p, i) => {
      L.circleMarker(p, { radius: i === 0 ? 6 : 4, color: "#FFFFFF", weight: 1.5, fillColor: "#AE7E2F",
        fillOpacity: 1, interactive: false }).addTo(this.gDes);
    });
  }

  concluirDesenho() {
    // o duplo clique também gera um clique: remove o vértice repetido
    const pts = [];
    this.desenho.forEach(p => { if (!pts.length || pts[pts.length - 1].distanceTo(p) > 0.05) pts.push(p); });
    if (pts.length < 3) return;
    this.n += 1;
    this.comp.setTriggerValue("desenho", { anel: pts.map(p => [p.lat, p.lng]), n: this.n });
    this.desenho = [];
    this.gDes.clearLayers();
  }

  cancelarDesenho() { this.desenho = []; this.gDes.clearLayers(); }

  // ------------------------------------------------------------------ áreas
  desenharAreas() {
    this.gAreas.clearLayers();
    (this.d.areas || []).forEach(a => {
      const est = a.tipo === "evitar"
        ? { color: "#B23A2E", weight: 2, fillColor: "#B23A2E", fillOpacity: 0.28, dashArray: "5 4" }
        : { color: "#AE7E2F", weight: 3, fill: false };
      L.polygon(a.aneis.map(r => r.map(p => L.latLng(p[0], p[1]))),
        Object.assign({ renderer: this.renderer, interactive: false }, est)).addTo(this.gAreas);
    });
  }

  // ------------------------------------------------------------------ atualização vinda do Python
  atualizar(d) {
    const primeira = !this.mapa;
    const novaVersao = this.versao !== d.versao;
    this.d = d;
    this.divMapa.style.height = (d.altura || 560) + "px";
    if (primeira) this.iniciarMapa();
    if (novaVersao) {
      this.temp = {};
      this.pos = { lat: d.ref.lat, lon: d.ref.lon, azimute: d.azimute };
      this.versao = d.versao;
    }
    if (d.editar !== "desenhar") this.cancelarDesenho();
    this.definirFundo(this.fundoAtual && !primeira ? this.fundoAtual : (d.fundo || "satelite"));
    this.desenharAreas();
    this.redesenhar();
    if (primeira || this.ajuste !== d.ajustar) {
      this.ajuste = d.ajustar;
      if (!this.divMapa.clientWidth) this._enquadrarDepois = true;
      else setTimeout(() => { this.mapa.invalidateSize(); this.enquadrar(); }, 30);
    }
  }

  destruir() {
    if (this.ro) this.ro.disconnect();
    document.removeEventListener("mouseup", this._soltarDoc);
    document.removeEventListener("keydown", this._tecla);
    if (this.mapa) this.mapa.remove();
  }
}

export default function (component) {
  const { data, parentElement } = component;
  if (!data) return;
  let inst = parentElement.__expag;
  if (!inst || (inst.d && inst.d.modo !== data.modo)) {
    if (inst) { inst.destruir(); inst.caixa.remove(); }
    inst = new MapaExpAg(parentElement, component);
    parentElement.__expag = inst;
  }
  inst.comp = component;
  inst.atualizar(data);
}
