"""Desenho do DFG em DOT (a linguagem do Graphviz): título, rótulos ricos e cor/espessura pela frequência.

O app só precisa do texto DOT, porque quem desenha é o Graphviz em WebAssembly, no navegador.
"""

import math
import textwrap
from collections.abc import Mapping
from dataclasses import dataclass, field
from html import escape

import pandas as pd

from .dfg import FIM, INICIO, Modelo, Processos

PALETAS: dict[str, dict[str, str]] = {
    "light": {
        "fundo": "transparent",
        "texto": "#1C1F2A",
        "suave": "#5A6175",
        "vertice_min": "#EEF0FB",
        "vertice_max": "#4C5FD5",
        "aresta": "#8A91A8",
        "rotulo_aresta": "#5A6175",
        "inicio": "#1F9D6B",
        "fim": "#D9485F",
    },
    "dark": {
        "fundo": "transparent",
        "texto": "#E7E9F0",
        "suave": "#A5ACBF",
        "vertice_min": "#1F2333",
        "vertice_max": "#6E7FF3",
        "aresta": "#7C849A",
        "rotulo_aresta": "#A5ACBF",
        "inicio": "#2FB383",
        "fim": "#E5687C",
    },
}
FONTE = "Arial"  # o Graphviz conhece as métricas da Arial, então os rótulos cabem nas caixas


def _id(texto: str) -> str:
    """Identificador DOT entre aspas (em DOT, só a aspa dupla precisa de escape)."""
    return '"' + texto.replace('"', '\\"') + '"'


def _valor(texto: str) -> str:
    """Valor de atributo: rótulos HTML (<...>) vão crus, o resto entre aspas."""
    return texto if texto.startswith("<") and texto.endswith(">") else _id(texto)


def _atributos(atributos: Mapping[str, str]) -> str:
    if not atributos:
        return ""
    return (
        " ["
        + " ".join(f"{chave}={_valor(valor)}" for chave, valor in atributos.items())
        + "]"
    )


@dataclass
class Dot:
    """Um grafo direcionado em DOT, com os atributos padrão do grafo, dos vértices e das arestas."""

    grafo: dict[str, str] = field(default_factory=dict[str, str])
    vertices: dict[str, str] = field(default_factory=dict[str, str])
    arestas: dict[str, str] = field(default_factory=dict[str, str])
    corpo: list[str] = field(default_factory=list[str])

    def vertice(self, nome: str, **atributos: str) -> None:
        self.corpo.append(f"\t{_id(nome)}{_atributos(atributos)}")

    def aresta(self, de: str, para: str, **atributos: str) -> None:
        self.corpo.append(f"\t{_id(de)} -> {_id(para)}{_atributos(atributos)}")

    @property
    def fonte(self) -> str:
        padroes = [
            f"\t{tipo}{_atributos(atributos)}"
            for tipo, atributos in [
                ("graph", self.grafo),
                ("node", self.vertices),
                ("edge", self.arestas),
            ]
            if atributos
        ]
        return "digraph {\n" + "\n".join(padroes + self.corpo) + "\n}\n"


def fmt(n: float) -> str:
    return f"{n:,}".replace(",", ".")


def _rgb(cor: str) -> tuple[int, int, int]:
    return int(cor[1:3], 16), int(cor[3:5], 16), int(cor[5:7], 16)


def _misturar(c1: str, c2: str, t: float) -> str:
    return "#" + "".join(
        f"{round(a + (b - a) * t):02X}" for a, b in zip(_rgb(c1), _rgb(c2), strict=True)
    )


def _luminancia(cor: str) -> float:
    r, g, b = (c / 255 for c in _rgb(cor))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _intensidade(n: float, maximo: float) -> float:
    """0 a 1 em escala log, pra frequências de 1 a centenas de milhares caberem na mesma régua."""
    return math.log1p(n) / math.log1p(maximo) if maximo > 0 else 0


def rotulo_atividade(
    atividade: str, tipo: str, nomes: Mapping[str, str]
) -> tuple[str, str]:
    """(título, detalhe) de um vértice, conforme o que a atividade representa."""
    if tipo in ("technique", "technique_parent"):
        return nomes.get(atividade, atividade), atividade
    if tipo == "technique_proc":
        tecnica, _, programa = atividade.partition(", ")
        return nomes.get(tecnica, tecnica), f"{tecnica}, {programa}"
    return atividade, ""


def _linhas(texto: str, largura: int = 30) -> list[str]:
    return textwrap.wrap(texto, largura) or [texto]


def _celula(texto: str, cor: str, tamanho: str) -> str:
    return f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="{tamanho}" COLOR="{cor}">{texto}</FONT></TD></TR>'


def _rotulo_vertice(
    atividade: str,
    n: int,
    tipo: str,
    nomes: Mapping[str, str],
    programas: list[tuple[str, int]],
    top: int,
    cor_suave: str,
) -> str:
    titulo, detalhe = rotulo_atividade(atividade, tipo, nomes)
    linhas = [
        f'<TR><TD ALIGN="LEFT"><B>{escape(parte)}</B></TD></TR>'
        for parte in _linhas(titulo)
    ]
    detalhe = f"{detalhe} ({fmt(n)})" if detalhe else fmt(n)  # como no Notebook 4
    linhas.append(_celula(escape(detalhe), cor_suave, "10"))
    if programas and top:
        linhas.append("<HR/>")
        linhas += [
            _celula(f"{escape(programa)}: {fmt(k)}", cor_suave, "9.5")
            for programa, k in programas[:top]
        ]
        resto = len(programas) - top
        if resto > 0:
            texto = (
                "+ 1 outro programa" if resto == 1 else f"+ {resto} outros programas"
            )
            linhas.append(_celula(texto, cor_suave, "9.5"))
    tabela = f'<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="1" COLOR="{cor_suave}">'
    return f"<{tabela}{''.join(linhas)}</TABLE>>"


def arestas_visiveis(modelo: Modelo, fracao: float) -> pd.DataFrame:
    """As arestas mais frequentes, `fracao` do total (pelo menos uma)."""
    if fracao >= 1 or modelo.arestas.empty:
        return modelo.arestas
    return modelo.arestas.nlargest(
        max(1, math.ceil(fracao * len(modelo.arestas))), "n", keep="first"
    )


def desenhar(
    modelo: Modelo,
    tipo_atividade: str,
    nomes: Mapping[str, str],
    processos: Processos | None = None,
    top: int = 3,
    fracao_arestas: float = 1.0,
    titulo: str | None = None,
    subtitulo: str | None = None,
    tema: str = "light",
) -> Dot:
    """O DFG do modelo em DOT. `fracao_arestas` < 1 mostra só as arestas mais frequentes."""
    p = PALETAS[tema]
    grafo = Dot(
        grafo={
            "rankdir": "LR",
            "bgcolor": p["fundo"],
            "fontname": FONTE,
            "fontcolor": p["texto"],
            "nodesep": "0.3",
            "ranksep": "0.5",
            "pad": "0.25",
        },
        vertices={"fontname": FONTE, "fontsize": "12", "fontcolor": p["texto"]},
        arestas={
            "fontname": FONTE,
            "fontsize": "10",
            "fontcolor": p["rotulo_aresta"],
            "color": p["aresta"],
            "arrowsize": "0.7",
        },
    )
    if titulo:
        sub = (
            f'<BR/><FONT POINT-SIZE="12" COLOR="{p["suave"]}">{escape(subtitulo)}</FONT>'
            if subtitulo
            else ""
        )
        grafo.grafo.update(
            label=f"<<B>{escape(titulo)}</B>{sub}>",
            labelloc="t",
            labeljust="l",
            fontsize="18",
        )

    arestas = arestas_visiveis(modelo, fracao_arestas)
    de = [str(x) for x in arestas["de"]]
    para = [str(x) for x in arestas["para"]]
    frequencias = [int(x) for x in arestas["n"]]
    tocados = set(de) | set(para)

    for nome, cor, forma in [
        (INICIO, p["inicio"], "circle"),
        (FIM, p["fim"], "doublecircle"),
    ]:
        if nome in tocados:
            grafo.vertice(
                nome,
                label=nome,
                shape=forma,
                style="filled",
                fillcolor=cor,
                color=cor,
                fontcolor="#FFFFFF",
                fontsize="9",
                width="0.6",
                fixedsize="true",
            )

    contagens = [int(x) for x in modelo.vertices["n"]]
    maximo = max(contagens, default=0)
    for atividade, n in zip(
        (str(x) for x in modelo.vertices["atividade"]), contagens, strict=True
    ):
        if atividade not in tocados:  # sem nenhuma aresta visível: some do desenho
            continue
        fundo = _misturar(p["vertice_min"], p["vertice_max"], _intensidade(n, maximo))
        claro = _luminancia(fundo) > 0.5
        programas = processos.get(atividade, []) if processos else []
        grafo.vertice(
            atividade,
            label=_rotulo_vertice(
                atividade,
                n,
                tipo_atividade,
                nomes,
                programas,
                top,
                "#4A5064" if claro else "#D5D9E6",
            ),
            shape="box",
            style="rounded,filled",
            fillcolor=fundo,
            fontcolor="#1C1F2A" if claro else "#F4F5FA",
            color=_misturar(fundo, p["vertice_max"], 0.6),
            margin="0.14,0.07",
        )

    maximo = max(frequencias, default=0)
    for origem, destino, n in zip(de, para, frequencias, strict=True):
        grafo.aresta(
            origem,
            destino,
            label=fmt(n),
            penwidth=f"{0.6 + 3.4 * _intensidade(n, maximo):.2f}",
        )
    return grafo
