"""DFG interativo: Graphviz em WebAssembly no navegador, com zoom, arrasto, destaque e exportação.

O `st.graphviz_chart` desliga o zoom, e um DFG de centenas de arestas vira um borrão. Aqui o SVG é
gerado no navegador (sem precisar do `dot` no servidor), inclusive para baixar em SVG e PNG.
"""

import streamlit as st
from streamlit.components.v2 import component

from sean.desenho import Dot

GRAPHVIZ_WASM = (
    "https://cdn.jsdelivr.net/npm/@hpcc-js/wasm-graphviz@1.29.2/dist/index.js"
)

_HTML = """
<div class="dfg">
  <div class="topo">
    <span class="dica">Ctrl + roda (ou pinça) para zoom · arraste para mover · duplo clique para ajustar · passe o mouse num vértice para destacar</span>
    <div class="barra">
      <button data-acao="mais" title="Aproximar">+</button>
      <button data-acao="menos" title="Afastar">−</button>
      <button data-acao="ajustar" title="Ajustar à área">⤢</button>
      <button data-acao="tela" title="Tela cheia">⛶</button>
      <span class="sep"></span>
      <button data-acao="svg" title="Baixar SVG (tema claro)">SVG</button>
      <button data-acao="png" title="Baixar PNG em alta resolução (tema claro)">PNG</button>
      <button data-acao="dot" title="Baixar o código DOT">DOT</button>
    </div>
  </div>
  <div class="palco"><div class="aviso">Desenhando o modelo…</div></div>
</div>
"""

_CSS = """
.dfg { display: flex; flex-direction: column; width: 100%; height: 460px; border-radius: 0.6rem; overflow: hidden;
       border: 1px solid var(--st-border-color, rgba(128,128,128,.25)); background: var(--st-background-color); }
.dfg:fullscreen { height: 100vh !important; border-radius: 0; }
.topo { display: flex; align-items: center; justify-content: space-between; gap: .75rem; padding: .3rem .4rem .3rem .75rem;
        border-bottom: 1px solid var(--st-border-color, rgba(128,128,128,.2)); background: var(--st-secondary-background-color); }
.dica { font-size: .72rem; opacity: .6; color: var(--st-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.barra { display: flex; gap: .2rem; align-items: center; flex-shrink: 0; }
.barra button { all: unset; cursor: pointer; min-width: 1.6rem; height: 1.6rem; padding: 0 .35rem; text-align: center;
                border-radius: .35rem; font: 600 .78rem/1.6rem var(--st-font, sans-serif); color: var(--st-text-color); }
.barra button:hover { background: var(--st-primary-color); color: #fff; }
.barra .sep { width: 1px; height: 1.1rem; background: var(--st-border-color, rgba(128,128,128,.35)); margin: 0 .15rem; }
.palco { flex: 1; min-height: 0; cursor: grab; touch-action: none; }
.palco.arrastando { cursor: grabbing; }
.palco svg { width: 100%; height: 100%; display: block; user-select: none; }
.aviso { padding: 1.5rem; opacity: .6; font-size: .9rem; color: var(--st-text-color); }
.foco g.edge, .foco g.node { transition: opacity .12s; }
.foco g.edge:not(.ativo) { opacity: .08; }
.foco g.node:not(.ativo) { opacity: .25; }
"""

_JS = """
const URL_GRAPHVIZ = "__URL__";

function carregarGraphviz() {
  if (!window.__seanGraphviz) {
    window.__seanGraphviz = import(URL_GRAPHVIZ).then((m) => m.Graphviz.load());
  }
  return window.__seanGraphviz;
}

function baixar(nome, blob) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

function pngDeSvg(svgTexto, escala) {
  return new Promise((ok, falha) => {
    const doc = new DOMParser().parseFromString(svgTexto, "image/svg+xml").documentElement;
    const vb = doc.viewBox.baseVal;
    const largura = Math.ceil(vb.width * 96 / 72 * escala), altura = Math.ceil(vb.height * 96 / 72 * escala);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = largura; canvas.height = altura;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, largura, altura);
      ctx.drawImage(img, 0, 0, largura, altura);
      canvas.toBlob(ok, "image/png");
    };
    img.onerror = falha;
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svgTexto);
  });
}

export default function (component) {
  const { data, parentElement, setStateValue } = component;
  const raiz = parentElement.querySelector(".dfg");
  const palco = raiz.querySelector(".palco");
  const limpar = [];
  const ouvir = (alvo, evento, f, opcoes) => { alvo.addEventListener(evento, f, opcoes); limpar.push(() => alvo.removeEventListener(evento, f, opcoes)); };
  let vivo = true;

  carregarGraphviz().then((gv) => {
    if (!vivo) return;
    palco.innerHTML = gv.dot(data.dot);
    const svg = palco.querySelector("svg");
    const vb = svg.viewBox.baseVal;
    const inicial = { x: vb.x, y: vb.y, w: vb.width, h: vb.height };
    let vista = { ...inicial };
    svg.removeAttribute("width"); svg.removeAttribute("height");

    // altura proporcional ao grafo, entre 320 px e 78% da janela
    const proporcional = palco.clientWidth * inicial.h / inicial.w;
    const topo = raiz.querySelector(".topo").offsetHeight;
    raiz.style.height = Math.round(topo + Math.max(320, Math.min(window.innerHeight * 0.75, proporcional + 16))) + "px";

    const aplicar = () => svg.setAttribute("viewBox", `${vista.x} ${vista.y} ${vista.w} ${vista.h}`);
    const pontoSvg = (cx, cy) => {
      const p = svg.createSVGPoint(); p.x = cx; p.y = cy;
      return p.matrixTransform(svg.getScreenCTM().inverse());
    };
    const zoom = (fator, cx, cy) => {
      const r = svg.getBoundingClientRect();
      const alvo = pontoSvg(cx ?? r.left + r.width / 2, cy ?? r.top + r.height / 2);
      const w = Math.min(inicial.w * 4, Math.max(inicial.w / 40, vista.w / fator));
      const k = w / vista.w;
      vista = { x: alvo.x - (alvo.x - vista.x) * k, y: alvo.y - (alvo.y - vista.y) * k, w, h: vista.h * k };
      aplicar();
    };
    const ajustar = () => { vista = { ...inicial }; aplicar(); };

    ouvir(palco, "wheel", (e) => {
      if (!(e.ctrlKey || e.metaKey)) return;   // sem Ctrl, a roda rola a página normalmente
      e.preventDefault();
      zoom(Math.exp(-e.deltaY * 0.0025), e.clientX, e.clientY);
    }, { passive: false });

    let arrasto = null;
    ouvir(palco, "pointerdown", (e) => {
      arrasto = { x: e.clientX, y: e.clientY, vista: { ...vista } };
      palco.setPointerCapture(e.pointerId); palco.classList.add("arrastando");
    });
    ouvir(palco, "pointermove", (e) => {
      if (!arrasto) return;
      const m = svg.getScreenCTM();
      vista = { ...arrasto.vista, x: arrasto.vista.x - (e.clientX - arrasto.x) / m.a, y: arrasto.vista.y - (e.clientY - arrasto.y) / m.d };
      aplicar();
    });
    const soltar = () => { arrasto = null; palco.classList.remove("arrastando"); };
    ouvir(palco, "pointerup", soltar);
    ouvir(palco, "pointercancel", soltar);
    ouvir(palco, "dblclick", ajustar);

    // destaque: vértice sob o mouse, suas arestas e seus vizinhos
    const titulo = (g) => g.querySelector("title")?.textContent ?? "";
    const nos = [...svg.querySelectorAll("g.node")];
    const arestas = [...svg.querySelectorAll("g.edge")].map((g) => {
      const [de, para] = titulo(g).split("->");
      return { g, de, para };
    });
    nos.forEach((g) => {
      const id = titulo(g);
      ouvir(g, "mouseenter", () => {
        const vizinhos = new Set([id]);
        arestas.forEach((a) => {
          const ligada = a.de === id || a.para === id;
          a.g.classList.toggle("ativo", ligada);
          if (ligada) { vizinhos.add(a.de); vizinhos.add(a.para); }
        });
        nos.forEach((n) => n.classList.toggle("ativo", vizinhos.has(titulo(n))));
        svg.classList.add("foco");
      });
      ouvir(g, "mouseleave", () => svg.classList.remove("foco"));
    });

    const acoes = {
      mais: () => zoom(1.4), menos: () => zoom(1 / 1.4), ajustar,
      tela: () => (document.fullscreenElement ? document.exitFullscreen() : raiz.requestFullscreen()),
      dot: () => baixar(`${data.nome}.dot`, new Blob([data.dot_export], { type: "text/vnd.graphviz" })),
      svg: () => baixar(`${data.nome}.svg`, new Blob([gv.dot(data.dot_export)], { type: "image/svg+xml" })),
      png: () => pngDeSvg(gv.dot(data.dot_export), 3).then((blob) => baixar(`${data.nome}.png`, blob)),
    };
    raiz.querySelectorAll(".barra button").forEach((b) => ouvir(b, "click", () => acoes[b.dataset.acao]()));
    ouvir(document, "fullscreenchange", () => setTimeout(ajustar, 50));
  }).catch((erro) => {
    palco.innerHTML = `<div class="aviso">Não consegui carregar o Graphviz (${erro}).</div>`;
    setStateValue("erro", String(erro));
  });

  return () => { vivo = false; limpar.forEach((f) => f()); };
}
""".replace("__URL__", GRAPHVIZ_WASM)

_componente = component("dfg_interativo", html=_HTML, css=_CSS, js=_JS)


def mostrar(grafo: Dot, grafo_exportacao: Dot, nome: str, key: str) -> None:
    """Mostra o DFG. Se o Graphviz em WebAssembly não carregar (sem internet), cai no st.graphviz_chart."""
    resultado = _componente(
        data={"dot": grafo.fonte, "dot_export": grafo_exportacao.fonte, "nome": nome},
        key=key,
        on_erro_change=lambda: None,
    )
    if getattr(resultado, "erro", None):
        st.graphviz_chart(grafo.fonte, width="stretch")
