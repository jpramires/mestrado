"""Tema claro/escuro: segue o sistema por padrão, tem seletor próprio e afasta o Dark Reader."""

from typing import cast

import streamlit as st
from streamlit.components.v2 import component

_JS = r"""
export default function (component) {
  const { data, setStateValue } = component;

  // O app já tem tema escuro próprio: com esta trava, o Dark Reader não escurece a página por cima
  for (const [name, content] of [["darkreader-lock", null], ["color-scheme", "light dark"]]) {
    if (!document.head.querySelector(`meta[name="${name}"]`)) {
      const meta = document.createElement("meta");
      meta.name = name;
      if (content) meta.content = content;
      document.head.appendChild(meta);
    }
  }

  // Mesma chave em que o Streamlit guarda a escolha do menu Settings > Theme
  const chave = `stActiveTheme-${window.location.pathname}-v2`;
  const preferencia = () => {
    try {
      const valor = JSON.parse(window.localStorage.getItem(chave));
      return ["System", "Light", "Dark"].includes(valor) ? valor : "System";
    } catch {
      return "System";
    }
  };
  const sistema = window.matchMedia("(prefers-color-scheme: dark)");
  const efetivo = (p) => (p === "Dark" || (p === "System" && sistema.matches) ? "dark" : "light");

  // O seletor do app pediu outro tema: grava onde o Streamlit lê e recarrega (a URL guarda a modelagem)
  const pedido = data && data.pedido;
  if (pedido && pedido !== preferencia()) {
    window.localStorage.setItem(chave, JSON.stringify(pedido));
    window.location.reload();
    return;
  }

  let ultimo = null;
  const informar = () => {
    const p = preferencia();
    const atual = `${p}|${efetivo(p)}`;
    if (atual !== ultimo) {
      ultimo = atual;
      setStateValue("tema", { preferencia: p, efetivo: efetivo(p) });
    }
  };
  informar();
  sistema.addEventListener("change", informar);
  const relogio = window.setInterval(informar, 1000);   // pega trocas feitas pelo menu do próprio Streamlit
  return () => {
    sistema.removeEventListener("change", informar);
    window.clearInterval(relogio);
  };
}
"""

_componente = component("tema_do_app", js=_JS)

OPCOES: dict[str, str] = {
    "System": ":material/contrast: Sistema",
    "Light": ":material/light_mode: Claro",
    "Dark": ":material/dark_mode: Escuro",
}


def montar() -> str:
    """Monta o componente (invisível) e devolve o tema em uso: "light" ou "dark"."""
    resultado = _componente(
        data={"pedido": st.session_state.get("_tema_pedido")},
        key="_tema",
        on_tema_change=lambda: None,
    )
    estado: object = getattr(resultado, "tema", None)
    if isinstance(estado, dict):
        # o JS manda {preferencia, efetivo}, ambos texto
        tema_js = cast("dict[str, str]", estado)
        st.session_state["_tema_preferencia"] = tema_js.get("preferencia", "System")
        return tema_js.get("efetivo", "light")
    return st.context.theme.type or "light"


def seletor() -> None:
    """Seletor Sistema/Claro/Escuro. Começa na escolha salva no navegador."""
    salvo = st.session_state.get("_tema_preferencia", "System")
    if st.session_state.get("tema") != salvo and not st.session_state.get(
        "_tema_pedido"
    ):
        st.session_state["tema"] = salvo
    st.segmented_control(
        "Tema",
        list(OPCOES),
        format_func=lambda opcao: OPCOES[opcao],
        required=True,
        key="tema",
        on_change=lambda: st.session_state.update(
            _tema_pedido=st.session_state["tema"]
        ),
        width="stretch",
    )
