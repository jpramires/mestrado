"""Qual tema (claro ou escuro) está em uso, para o DFG usar as cores certas; e a trava do Dark Reader.

O seletor de tema é o do próprio Streamlit (menu ⋮ > Settings). Este componente só observa a cor de fundo
que o Streamlit aplicou, então acompanha qualquer troca na hora, em qualquer página.
"""

import streamlit as st
from streamlit.components.v2 import component

_JS = r"""
export default function (component) {
  const { setStateValue } = component;

  // O app já tem tema escuro próprio: com estas metas, o Dark Reader não escurece a página por cima
  for (const [name, content] of [["darkreader-lock", null], ["color-scheme", "light dark"]]) {
    if (!document.head.querySelector(`meta[name="${name}"]`)) {
      const meta = document.createElement("meta");
      meta.name = name;
      if (content) meta.content = content;
      document.head.appendChild(meta);
    }
  }

  const tema = () => {
    const fundo = getComputedStyle(document.querySelector(".stApp") || document.body).backgroundColor;
    const [r, g, b] = (fundo.match(/\d+/g) || [255, 255, 255]).map(Number);
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 < 0.5 ? "dark" : "light";
  };
  let ultimo = null;
  const informar = () => {
    const atual = tema();
    if (atual !== ultimo) {
      ultimo = atual;
      setStateValue("tema", atual);
    }
  };
  informar();
  const relogio = window.setInterval(informar, 500);
  return () => window.clearInterval(relogio);
}
"""

_componente = component("tema_do_app", js=_JS)


def montar() -> None:
    """Monta o componente (invisível). O `app.py` chama uma vez por execução, antes da página."""
    resultado = _componente(key="_tema", on_tema_change=lambda: None)
    tema = getattr(resultado, "tema", None)
    st.session_state["_tema_em_uso"] = tema if tema in ("light", "dark") else st.context.theme.type or "light"


def em_uso() -> str:
    """O tema em uso: "light" ou "dark"."""
    return str(st.session_state.get("_tema_em_uso", "light"))
