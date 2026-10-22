"""Gráficos em Altair: o plano de complexidade do Sean e as séries por dia."""

from collections.abc import Mapping
from datetime import date
from itertools import pairwise

import altair as alt
import numpy as np
import pandas as pd

from sean.dfg import Criterio

VERDE, VERMELHO, ACENTO, CINZA = "#1F9D6B", "#D9485F", "#5B6CE0", "#9AA1B5"


def plano_complexidade(
    pontos: pd.DataFrame,
    criterio: Criterio,
    rotulo: str = "rotulo",
    cor: str = "grupo",
    forma: str | None = None,
) -> alt.LayerChart:
    """V × V/E com as regiões do Sean: V ≤ V_MIN simples, V > V_MAX complexo e, no meio, a reta ts(V).

    `pontos` tem as colunas vertices, arestas, simplicidade, limiar_ts, complexo e as de rótulo/cor/forma.
    """
    vertices = [float(v) for v in pontos["vertices"]]
    simplicidades = [float(s) for s in pontos["simplicidade"]]
    x_max = max(50, int(max(vertices, default=0) * 1.1) + 2)
    y_max = max(1.0, max(simplicidades, default=0) * 1.15)

    escala_x = alt.Scale(domain=[0, x_max], nice=False)
    escala_y = alt.Scale(domain=[0, y_max], nice=False)

    def x(campo: str) -> alt.X:
        return alt.X(
            f"{campo}:Q", scale=escala_x, title="V (vértices, com INÍCIO e FIM)"
        )

    def y(campo: str) -> alt.Y:
        return alt.Y(f"{campo}:Q", scale=escala_y, title="V/E (simplicidade)")

    v = [float(x) for x in np.linspace(criterio.v_min, criterio.v_max, 61)]
    faixa = pd.DataFrame({"v": v, "ts": [criterio.limiar(x) for x in v]})
    # a faixa do meio em fatias finas: abaixo da reta ts é complexo, acima é simples
    fatias = pd.DataFrame(
        {
            "v0": v[:-1],
            "v1": v[1:],
            "ts": [criterio.limiar((a + b) / 2) for a, b in pairwise(v)],
            "base": 0.0,
            "topo": y_max,
        }
    )

    def regiao(v0: float, v1: float, cor_: str) -> alt.Chart:
        dados = pd.DataFrame([{"v0": v0, "v1": v1, "s0": 0.0, "s1": y_max}])
        return (
            alt.Chart(dados)
            .mark_rect(opacity=0.13, color=cor_)
            .encode(x=x("v0"), x2="v1:Q", y=y("s0"), y2="s1:Q")
        )

    simples = regiao(0, criterio.v_min, VERDE)
    complexo = regiao(criterio.v_max, x_max, VERMELHO)
    abaixo = (
        alt.Chart(fatias)
        .mark_rect(opacity=0.13, color=VERMELHO)
        .encode(x=x("v0"), x2="v1:Q", y=y("base"), y2="ts:Q")
    )
    acima = (
        alt.Chart(fatias)
        .mark_rect(opacity=0.13, color=VERDE)
        .encode(x=x("v0"), x2="v1:Q", y=y("ts"), y2="topo:Q")
    )
    reta = (
        alt.Chart(faixa)
        .mark_line(color=VERMELHO, strokeDash=[5, 4], opacity=0.8)
        .encode(x=x("v"), y=y("ts"))
    )
    limites = (
        alt.Chart(pd.DataFrame({"v": [criterio.v_min, criterio.v_max]}))
        .mark_rule(color=CINZA, strokeDash=[2, 3])
        .encode(x=x("v"))
    )

    dica = [
        alt.Tooltip(f"{rotulo}:N", title="modelo"),
        alt.Tooltip("vertices:Q", title="V"),
        alt.Tooltip("arestas:Q", title="E"),
        alt.Tooltip("simplicidade:Q", title="V/E", format=".3f"),
        alt.Tooltip("limiar_ts:Q", title="ts(V)", format=".3f"),
        alt.Tooltip("veredito:N", title="veredito"),
    ]
    dados = pontos.assign(
        veredito=["complexo" if c else "simples" for c in pontos["complexo"]]
    )
    legenda_cor = alt.Color(
        f"{cor}:N", title=None, sort=None, legend=alt.Legend(orient="bottom", columns=4)
    )
    base = alt.Chart(dados).mark_point(
        filled=True, size=150, opacity=0.95, stroke="white", strokeWidth=0.6
    )
    if forma:
        marcas = base.encode(
            x=x("vertices"),
            y=y("simplicidade"),
            tooltip=dica,
            color=legenda_cor,
            shape=alt.Shape(
                f"{forma}:N", title=None, legend=alt.Legend(orient="bottom")
            ),
        )
    else:
        marcas = base.encode(
            x=x("vertices"), y=y("simplicidade"), tooltip=dica, color=legenda_cor
        )
    # cores e formas independentes: as regiões têm cor fixa e não podem entrar na legenda dos pontos
    resolucao = alt.Resolve(
        scale=alt.ScaleResolveMap(color="independent", shape="independent")
    )
    return alt.LayerChart(
        layer=[simples, complexo, abaixo, acima, reta, limites, marcas],
        resolve=resolucao,
        height=440,
    )


def por_dia(
    tabela: pd.DataFrame, metrica: str, titulo: str, destaques: Mapping[date, str]
) -> alt.Chart:
    """Barras por dia, com os dias escolhidos por algum critério em destaque.

    `destaques`: dia -> texto dos critérios que escolheram aquele dia.
    """
    dias = [pd.Timestamp(d).date() for d in tabela["data"]]
    escolhidos = [destaques.get(d, "") for d in dias]
    # datas como texto: o Altair não serializa `date`
    dados = tabela.drop(columns="data").assign(
        dia=[d.strftime("%d/%m") for d in dias],
        escolhido=escolhidos,
        grupo=["escolhido" if e else "outro" for e in escolhidos],
    )
    return (
        alt.Chart(dados)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("dia:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y(f"{metrica}:Q", title=titulo),
            color=alt.Color(
                "grupo:N",
                scale=alt.Scale(domain=["escolhido", "outro"], range=[ACENTO, CINZA]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("dia:N"),
                alt.Tooltip(f"{metrica}:Q", title=titulo, format=",d"),
                alt.Tooltip("escolhido:N", title="escolhido por"),
            ],
        )
        .properties(height=260)
    )
