"""A modelagem na URL, em valores curtos e sem acento: `?cen=real&agr=usuario&min=3`.

O `bind="query-params"` do Streamlit grava o rótulo visível (`?dir=S%C3%B3+conex%C3%B5es...`); aqui vai a chave
da opção. Cada controle recebe como valor inicial `url.ligar(chave, padrão)`: o do link ou, na volta da página
Método, o que estava em uso. No fim da página, `gravar` escreve na URL só o que difere do padrão.
"""

from collections.abc import Iterable, Mapping
from typing import Any

import streamlit as st

MEMORIA = "_url"  # os valores da última execução, que sobrevivem à ida para a página Método
INICIO = "_url_inicio"  # o valor inicial de cada controle, fixo enquanto ele existir (as abas dependem disso)


class Url:
    def __init__(self) -> None:
        self.padroes: dict[str, Any] = {}
        self.textos: dict[str, dict[Any, str]] = {}  # chave -> {valor: texto na URL}
        self.memoria: dict[str, Any] = st.session_state.get(MEMORIA, {})
        self.inicio: dict[str, Any] = st.session_state.setdefault(INICIO, {})

    def ligar[T](self, chave: str, padrao: T, opcoes: Iterable[Any] = (), textos: Mapping[Any, str] | None = None) -> T:
        """Registra o controle `chave` e devolve o valor inicial dele.

        `opcoes`: os valores aceitos, que vão para a URL como `str(valor)` (de um dict, valem as chaves);
        `textos`: {valor: texto na URL}, quando o texto é outro. Números e booleanos não precisam de nenhum dos dois.
        """
        self.padroes[chave] = padrao
        validos = self.textos[chave] = dict(textos) if textos is not None else {v: str(v) for v in opcoes}
        if chave not in st.session_state or chave not in self.inicio:
            self.inicio[chave] = self.memoria[chave] if chave in self.memoria else self._do_link(chave)
        valor: Any = self.inicio[chave]
        if validos and isinstance(valor, list):  # as opções podem ter mudado (outro cenário)
            valor = [v for v in valor if v in validos]
        elif validos and valor not in validos:
            valor = padrao
        return valor

    def indice(self, chave: str, padrao: Any, opcoes: Iterable[Any]) -> int:
        """`ligar` para o `index` de um selectbox."""
        lista = list(opcoes)
        return lista.index(self.ligar(chave, padrao, lista))

    def _do_link(self, chave: str) -> Any:
        padrao = self.padroes[chave]
        if chave not in st.query_params:
            return padrao
        valores = {texto: valor for valor, texto in self.textos[chave].items()}
        if isinstance(padrao, list):
            return [valores[t] for t in st.query_params.get_all(chave) if t in valores]
        texto = st.query_params[chave]
        if valores:
            return valores.get(texto, padrao)
        if isinstance(padrao, bool):
            return texto == "1"
        try:
            return type(padrao)(texto)  # int ou float
        except ValueError:
            return padrao

    def _texto(self, chave: str, valor: Any) -> str:
        if isinstance(valor, bool):
            return "1" if valor else "0"
        return self.textos[chave].get(valor, str(valor))

    def gravar(self) -> None:
        valores = {chave: st.session_state.get(chave, padrao) for chave, padrao in self.padroes.items()}
        st.session_state[MEMORIA] = valores
        st.query_params.from_dict(
            {
                chave: [self._texto(chave, v) for v in valor] if isinstance(valor, list) else self._texto(chave, valor)
                for chave, valor in valores.items()
                if valor != self.padroes[chave]
            }
        )
