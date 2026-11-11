"""Noções de caso na COMISET: o app do mestrado, em Streamlit.

uv run streamlit run app.py

O núcleo (SQL, DFG, complexidade, desenho) fica em `comiset/`; as telas, em `interface/`.
"""

import streamlit as st

from interface import explorar, metodo, tema

st.set_page_config(page_title="Noções de caso · COMISET", page_icon=":material/hub:", layout="wide")
tema.montar()
st.navigation(
    [
        st.Page(explorar.pagina, title="Explorar", icon=":material/hub:", default=True),
        st.Page(metodo.pagina, title="Método", icon=":material/menu_book:", url_path="metodo"),
    ],
    position="top",
).run()
