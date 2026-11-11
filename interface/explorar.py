"""A página principal: escolha a modelagem na barra lateral e veja o modelo, as métricas e o event log."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import pandas as pd
import streamlit as st

from comiset import constantes as K
from comiset.desenho import Dot, arestas_visiveis, desenhar
from comiset.dfg import Criterio, Metricas
from comiset.modelagem import Modelagem, dias_por_criterio

from . import consultas, dfg_interativo, graficos, tema
from .consultas import Dias
from .controles import LIMITE_ARESTAS, RECORTES, Desenho, barra_lateral
from .formato import compacto, data_br, dec, duracao, num, pct, plural, rotulos
from .url import Url

# rótulo da aba -> nome curto na URL (?aba=log)
ABAS = {"Modelo": "modelo", "Event log": "log", "Por dia": "dias", "Complexidade": "complexidade", "Comparar noções de caso": "comparar"}  # fmt: skip
DIRECAO_CURTA = {"entrada": "entrada", "saida": "saída", "conexoes": "entrada e saída", "todos": "sem filtro (todos os alertas)"}  # fmt: skip
DIRECAO_NO_TITULO = {"entrada": "entrada", "saida": "saída", "conexoes": "entrada e saída", "todos": "todos os alertas"}  # fmt: skip


@dataclass(frozen=True)
class Cartao:
    rotulo: str
    valor: str
    delta: str
    ajuda: str | None = None
    cor: Literal["off", "red", "green"] = "off"


def pagina() -> None:
    url = Url()
    escolhas = barra_lateral(url)
    modelagens = escolhas.modelagens
    recortes = {c: _recorte(m, escolhas.recorte, escolhas.escolhidos.get(c)) for c, m in modelagens.items()}
    _cabecalho(next(iter(modelagens.values())), escolhas.recorte, [rotulo for _, rotulo in recortes.values()])

    for coluna, (c, m) in zip(_colunas(modelagens), modelagens.items(), strict=True):
        with coluna:
            if len(modelagens) > 1:
                st.markdown(f"#### {K.CENARIOS[c]}")
            datas, rotulo = recortes[c]
            metricas = consultas.modelo_de(m, datas).metricas(escolhas.criterio) if datas != () else None
            _cartoes(m, metricas, rotulo)

    abas = st.tabs(list(ABAS), default=url.ligar("aba", "Modelo", textos=ABAS), key="aba", on_change="rerun")
    url.gravar()
    with abas[0]:
        if abas[0].open:
            for coluna, (c, m) in zip(_colunas(modelagens), modelagens.items(), strict=True):
                with coluna, st.spinner("Desenhando o modelo…"):
                    _aba_modelo(m, *recortes[c], escolhas.desenho)
    with abas[1]:
        if abas[1].open:
            _aba_event_log(modelagens, recortes)
    with abas[2]:
        if abas[2].open:
            _aba_por_dia(modelagens)
    with abas[3]:
        if abas[3].open:
            _aba_complexidade(modelagens, recortes, escolhas.criterio)
    with abas[4]:
        if abas[4].open:
            _aba_comparar(modelagens, escolhas.criterio)


# ---------------------------------------------------------------- cabeçalho e cartões


def _recorte(m: Modelagem, recorte: str, escolhido: str | None) -> tuple[Dias, str]:
    """(datas, rótulo) do dia do modelo; datas `()` quando nenhum dia atende ao critério."""
    if recorte == "todos" or (recorte == "escolher" and escolhido is None):
        return None, "todos os dias"
    if recorte == "escolher" and escolhido is not None:
        dia = date.fromisoformat(escolhido)
    else:
        dia = dias_por_criterio(consultas.por_dia_de(m)).get(recorte)
        if dia is None:
            return (), "sem dia"
    return (dia,), data_br(dia)


def _descrever_caso(m: Modelagem) -> str:
    partes = [K.COLUNAS_CASO[c] for c in m.caso] + (["dia"] if m.por_dia else [])
    return "⟨" + ", ".join(partes) + "⟩"


def _cabecalho(m: Modelagem, recorte: str, rotulos_dia: Sequence[str]) -> None:
    st.markdown("## Noções de caso na COMISET")
    st.caption(
        "Escolha como agrupar os 2,35 M alertas da COMISET em casos e veja o modelo de processo, "
        "as métricas e o event log que saem daí. O passo a passo está na página **Método**."
    )
    with st.container(horizontal=True, gap="small"):
        cenarios = "LAB + REAL" if len(rotulos_dia) > 1 else K.CENARIOS[m.cenario]
        st.badge(cenarios, icon=":material/dataset:", color="violet")
        st.badge(f"caso = {_descrever_caso(m)}", icon=":material/folder_open:", color="blue")
        st.badge(f"atividade = {K.ATIVIDADES[m.atividade].lower()}", icon=":material/hub:", color="blue")
        st.badge(f"tráfego = {DIRECAO_CURTA[m.direcao]}", icon=":material/swap_horiz:", color="gray")
        filtro = f"≥ {m.min_atividades} atividades por caso" if m.min_atividades > 1 else "sem filtro de atividades"
        st.badge(filtro, icon=":material/filter_alt:", color="gray")
        if m.excluir_tecnicas or m.event_ids or m.hosts:
            st.badge("com mais filtros", icon=":material/tune:", color="red")
        dias = " · ".join(rotulos_dia)
        st.badge(f"{dias} ({RECORTES[recorte].lower()})", icon=":material/calendar_today:", color="orange")


def _cartoes(m: Modelagem, metricas: Metricas | None, rotulo_dia: str) -> None:
    """Duas faixas de três cartões: o event log inteiro e o modelo do dia."""
    f = consultas.funil_de(m)
    log = [
        Cartao(
            "Universo",
            compacto(f["universo"]),
            f"{pct(f['universo'], f['alertas'])} dos alertas",
            f"{num(f['universo'])} de {num(f['alertas'])} alertas do cenário",
        ),
        Cartao(
            "Casos",
            compacto(f["casos"]),
            f"{compacto(f['casos_antes'])} antes do filtro",
            f"{num(f['casos'])} casos com atividades suficientes, de {num(f['casos_antes'])}",
        ),
        Cartao("Eventos", compacto(f["eventos"]), plural(f["atividades"], "atividade", "atividades")),
    ]
    if metricas is None:
        modelo = [Cartao("Modelo", "vazio", "nenhum caso sobra nesse dia")]
    else:
        complexo = metricas["complexo"]
        modelo = [
            Cartao(
                "Vértices · arestas",
                f"{metricas['vertices']} · {metricas['arestas']}",
                f"{plural(metricas['casos'], 'caso', 'casos')} no dia",
                "V conta INÍCIO e FIM; E conta todas as arestas",
            ),
            Cartao(
                "Simplicidade V/E",
                dec(metricas["simplicidade"], 3),
                f"limiar(V) = {dec(metricas['limiar'], 3)}",
                "Na faixa do meio, o modelo é complexo se V/E < limiar(V)",
            ),
            Cartao(
                "Complexidade",
                "Complexo" if complexo else "Simples",
                "pediria clustering" if complexo else "dispensa clustering",
                "Critério de Alvarenga et al. (2018); detalhes na página Método",
                "red" if complexo else "green",
            ),
        ]
    for titulo, cartoes in [
        (":material/receipt_long: **Event log** · todos os dias", log),
        (f":material/hub: **Modelo** · {rotulo_dia}", modelo),
    ]:
        st.caption(titulo)
        for coluna, c in zip(st.columns(3, gap="small"), cartoes, strict=False):
            coluna.metric(
                c.rotulo, c.valor, delta=c.delta, delta_color=c.cor, delta_arrow="off", border=True, help=c.ajuda
            )


def _colunas(modelagens: Mapping[str, Modelagem]) -> list[Any]:
    """Uma coluna por cenário quando são dois; senão, a largura toda."""
    return list(st.columns(len(modelagens), gap="large")) if len(modelagens) > 1 else [st.container()]


# ---------------------------------------------------------------- abas


def _aba_modelo(m: Modelagem, datas: Dias, rotulo_dia: str, desenho: Desenho) -> None:
    if datas == ():
        st.info("Nenhum dia atende ao critério.", icon=":material/info:")
        return
    modelo = consultas.modelo_de(m, datas)
    if modelo.vazio:
        st.info("Nenhum caso sobra nesse dia depois do filtro de atividades.", icon=":material/info:")
        return
    # com atividade = técnica + programa, a lista de programas só repetiria o próprio programa
    processos = consultas.processos_de(m, datas) if desenho.top and m.atividade != "technique_proc" else None
    total = len(modelo.arestas)
    fracao = desenho.fracao
    limitado = not desenho.sem_limite and fracao * total > LIMITE_ARESTAS
    if limitado:
        fracao = LIMITE_ARESTAS / total

    # título como no Notebook 4: (cenário, direção, dia); embaixo, (caso, atividade)
    titulo = f"({K.CENARIOS[m.cenario]}, {DIRECAO_NO_TITULO[m.direcao]}, {rotulo_dia})"
    caso = _descrever_caso(m).replace("⟨", "<").replace("⟩", ">")  # a Arial do PNG não tem ⟨⟩
    subtitulo = f"({caso}, {K.ATIVIDADES[m.atividade].lower()})"

    def dot(tema_: str, com_titulo: bool) -> Dot:
        return desenhar(
            modelo,
            tipo_atividade=m.atividade,
            nomes=consultas.nomes(),
            processos=processos,
            top=desenho.top,
            fracao_arestas=fracao,
            titulo=titulo if com_titulo else None,
            subtitulo=subtitulo,
            tema=tema_,
        )

    exportacao = dot("light", True)  # exportação: sempre clara, com título e fundo branco
    exportacao.grafo["bgcolor"] = "white"
    nome = f"dfg_{m.cenario}_{m.direcao}_{rotulo_dia.replace('/', '-').replace(' ', '_')}"
    dfg_interativo.mostrar(dot(tema.em_uso(), desenho.titulo), exportacao, nome, key=f"dfg_{m.cenario}")

    visiveis = arestas_visiveis(modelo, fracao)
    legenda = "Cor dos vértices e espessura das arestas seguem a frequência (escala log)."
    if len(visiveis) < total:
        tocados = {str(x) for x in visiveis["de"]} | {str(x) for x in visiveis["para"]}
        ocultos = len({str(x) for x in modelo.vertices["atividade"]} - tocados)
        legenda += f" Mostrando as {num(len(visiveis))} arestas mais frequentes de {num(total)}"
        legenda += f"; {num(ocultos)} vértices ficaram sem aresta e saíram do desenho." if ocultos else "."
    if limitado:
        legenda += (
            f" O desenho para em {LIMITE_ARESTAS} arestas (mais que isso pode levar minutos no navegador):"
            " ligue **Sem limite de arestas** em *Desenho* para ver todas."
        )
    st.caption(legenda)

    if processos:
        with st.expander("Programas que disparam cada atividade"):
            linhas = [(a, p, n) for a, programas in processos.items() for p, n in programas]
            st.dataframe(
                pd.DataFrame(linhas, columns=["atividade", "programa", "alertas"]),
                hide_index=True,
                column_config={"alertas": st.column_config.NumberColumn(format="localized")},
            )


def _aba_event_log(modelagens: Mapping[str, Modelagem], recortes: Mapping[str, tuple[Dias, str]]) -> None:
    rotulo_dias = " · ".join(rotulo for _, rotulo in recortes.values())
    escopo = st.segmented_control(
        "Casos de",
        ["dia", "todos"],
        default="dia",
        required=True,
        key="escopo",
        format_func=rotulos({"dia": f"O dia do modelo ({rotulo_dias})", "todos": "Todos os dias"}),
    )
    for c, m in modelagens.items():
        if len(modelagens) > 1:
            st.markdown(f"#### {K.CENARIOS[c]}")
        datas, rotulo = recortes[c]
        datas = (datas or None) if escopo == "dia" else None
        with st.spinner("Montando os casos…"):
            _casos(m, datas, rotulo if escopo == "dia" else "todos os dias")


def _encurtar(casos: Sequence[str]) -> tuple[list[str], str | None]:
    """Tira dos casos as partes iguais em todos eles (o único host do LAB, o dia do recorte)."""
    partes = [caso.split("|") for caso in casos]
    n = max(len(p) for p in partes)
    iguais = [i for i in range(n) if len({p[i] if i < len(p) else "" for p in partes}) == 1]
    if not iguais or len(iguais) == n:
        return list(casos), None
    curtos = [" | ".join(x for i, x in enumerate(p) if i not in iguais) for p in partes]
    return curtos, " · ".join(partes[0][i] for i in iguais)


def _casos(m: Modelagem, datas: Dias, rotulo: str) -> None:
    tabela = consultas.casos_de(m, datas)
    if tabela.empty:
        st.info("Nenhum caso nesse recorte.", icon=":material/info:")
        return
    nomes_casos = [str(c) for c in tabela["caso"]]
    curtos, omitidas = _encurtar(nomes_casos)
    vista = tabela.assign(duracao=[duracao(td) for td in tabela["duracao"]], curto=curtos)
    colunas = ["curto", "eventos", "atividades", "programas", "destinos", "inicio", "fim", "duracao", "sequencia"]
    escolha = st.dataframe(
        vista,
        hide_index=True,
        height=min(420, 38 + 35 * len(vista)),
        on_select="rerun",
        selection_mode="single-row",
        key=f"casos_{m.cenario}",
        column_order=colunas,
        column_config={
            "curto": st.column_config.TextColumn("caso", width="medium", pinned=True),
            "eventos": st.column_config.ProgressColumn(
                "eventos", format="localized", min_value=0, max_value=int(tabela["eventos"].max())
            ),
            "atividades": st.column_config.NumberColumn("ativ.", width="small"),
            "programas": st.column_config.NumberColumn("progr.", width="small"),
            "destinos": st.column_config.NumberColumn("IPs dest.", width="small"),
            "inicio": st.column_config.DatetimeColumn("início", format="DD/MM HH:mm:ss"),
            "fim": st.column_config.DatetimeColumn("fim", format="DD/MM HH:mm:ss"),
            "duracao": st.column_config.TextColumn("duração", width="small"),
            "sequencia": st.column_config.TextColumn("sequência (atividade  programa, ×N = repetições)", width="large"),
        },
    )
    omitido = f" Partes iguais em todos os casos foram omitidas: `{omitidas}`." if omitidas else ""
    st.caption(f"{plural(len(vista), 'caso', 'casos')}. Clique numa linha para ver os eventos do caso.{omitido}")

    linhas: list[int] = list(escolha.selection.rows)
    if linhas:
        caso = nomes_casos[linhas[0]]
        detalhe = consultas.eventos_de(m, datas, caso)
        st.markdown(f"##### Eventos de `{caso}`")
        st.dataframe(
            detalhe.drop(columns="caso"),
            hide_index=True,
            height=360,
            column_config={"ts": st.column_config.DatetimeColumn("ts", format="DD/MM/YYYY HH:mm:ss.SSS")},
        )
        total = int(tabela["eventos"].iloc[linhas[0]])
        if total > len(detalhe):
            st.caption(f"Mostrando os primeiros {num(len(detalhe))} de {num(total)} eventos.")

    base = f"log_{m.cenario}_{m.direcao}_{rotulo.replace('/', '-').replace(' ', '_')}"
    with st.container(horizontal=True, gap="small"):
        for formato, rotulo_botao, mime in [
            ("csv", "CSV", "text/csv"),
            ("parquet", "Parquet", "application/octet-stream"),
        ]:
            st.download_button(
                f"Event log ({rotulo_botao})",
                lambda formato=formato: consultas.arquivo_do_log(m, datas, formato),
                f"{base}.{formato}",
                mime,
                icon=":material/download:",
                key=f"{formato}_{m.cenario}",
            )


def _aba_por_dia(modelagens: Mapping[str, Modelagem]) -> None:
    metricas = {
        "alertas": "alertas no universo",
        "casos": "casos distintos",
        "tecnicas": "técnicas distintas",
        "eventos": "eventos após o filtro",
    }
    metrica = st.segmented_control(
        "Métrica", list(metricas), default="alertas", required=True, key="metrica_dia", format_func=rotulos(metricas)
    )
    metrica = metrica or "alertas"
    for coluna, (c, m) in zip(_colunas(modelagens), modelagens.items(), strict=True):
        with coluna:
            if len(modelagens) > 1:
                st.markdown(f"#### {K.CENARIOS[c]}")
            tabela = consultas.por_dia_de(m)
            if tabela.empty:
                st.info("O universo está vazio.", icon=":material/info:")
                continue
            escolhidos = dias_por_criterio(tabela)
            destaques: dict[date, str] = {}
            for criterio, dia in escolhidos.items():
                destaques[dia] = ", ".join(filter(None, [destaques.get(dia), K.CRITERIOS[criterio].lower()]))
            st.altair_chart(graficos.por_dia(tabela, metrica, metricas[metrica], destaques), width="stretch")
            with st.container(horizontal=True, gap="small"):
                for criterio, dia in escolhidos.items():
                    st.badge(f"{K.CRITERIOS[criterio]}: {data_br(dia)}", icon=":material/event:", color="blue")


def _aba_complexidade(
    modelagens: Mapping[str, Modelagem], recortes: Mapping[str, tuple[Dias, str]], criterio: Criterio
) -> None:
    pontos: list[dict[str, object]] = []
    for c, m in modelagens.items():
        datas, rotulo = recortes[c]
        metricas = consultas.modelo_de(m, datas).metricas(criterio) if datas != () else None
        if metricas:
            pontos.append({**metricas, "rotulo": f"{K.CENARIOS[c]} · {rotulo}"})
    if not pontos:
        st.info("Sem modelo no recorte atual.", icon=":material/info:")
        return
    st.altair_chart(graficos.plano_complexidade(pd.DataFrame(pontos), criterio, cor="rotulo"), width="stretch")
    st.caption(
        "Cada ponto é um modelo: V (vértices) contra V/E (simplicidade). À esquerda de V mín. o modelo é simples; "
        "à direita de V máx., complexo; no meio, complexo se ficar abaixo da reta do limiar. "
        "As equações estão na página **Método**; os parâmetros, em *Critério de complexidade*, na barra lateral."
    )


def _abrir_nocao_de_caso() -> None:
    linhas = st.session_state["tabela_comparar"].selection.rows
    if linhas:
        st.session_state["agr"] = st.session_state["_comparar"][linhas[0]]
        st.session_state["aba"] = "Modelo"


def _aba_comparar(modelagens: Mapping[str, Modelagem], criterio: Criterio) -> None:
    c1, c2 = st.columns(2)
    universo = c1.segmented_control(
        "Universo",
        ["todos", "barra"],
        default="todos",
        required=True,
        key="cmp_universo",
        format_func=rotulos({"todos": "Todos os alertas", "barra": "O da barra lateral"}),
        help="*Todos os alertas* ignora a direção do tráfego e os outros filtros da barra lateral; valem só a "
        "atividade e o mínimo de atividades.",
    )
    modo = c2.segmented_control(
        "Dia de cada modelo",
        ["eventos", "todos"],
        default="eventos",
        required=True,
        key="cmp_modo",
        format_func=rotulos({"eventos": "O dia com mais eventos", "todos": "Todos os dias juntos"}),
    )
    tabelas: list[pd.DataFrame] = []
    with st.spinner("Calculando as noções de caso…"):
        for m in modelagens.values():
            if universo == "todos":  # sem direção nem filtros, só a atividade e o mínimo de atividades
                m = Modelagem(
                    cenario=m.cenario, direcao="todos", atividade=m.atividade, min_atividades=m.min_atividades
                )
            tabelas.append(consultas.comparacao(m, modo == "eventos", criterio))
    tabela = pd.concat(tabelas, ignore_index=True)
    if tabela.empty:
        st.info("Nenhuma noção de caso gerou modelo.", icon=":material/info:")
        return
    st.session_state["_comparar"] = [str(a) for a in tabela["agregacao"]]

    forma = "cenario" if len(modelagens) > 1 else None
    st.altair_chart(graficos.plano_complexidade(tabela, criterio, cor="rotulo", forma=forma), width="stretch")
    colunas = [
        "cenario",
        "rotulo",
        "cobertura",
        "casos_depois",
        "eventos",
        "dia",
        "casos",
        "vertices",
        "arestas",
        "simplicidade",
        "limiar",
        "complexo",
    ]
    st.dataframe(
        tabela[colunas],
        hide_index=True,
        key="tabela_comparar",
        on_select=_abrir_nocao_de_caso,
        selection_mode="single-row",
        column_config={
            "cenario": "cenário",
            "rotulo": "noção de caso",
            "cobertura": st.column_config.NumberColumn("cobertura", format="percent"),
            "casos_depois": st.column_config.NumberColumn("casos", format="localized"),
            "eventos": st.column_config.NumberColumn("eventos", format="localized"),
            "casos": st.column_config.NumberColumn("casos no dia", format="localized"),
            "vertices": "V",
            "arestas": "E",
            "simplicidade": st.column_config.NumberColumn("V/E", format="%.3f"),
            "limiar": st.column_config.NumberColumn("limiar(V)", format="%.3f"),
            "complexo": st.column_config.CheckboxColumn("complexo"),
        },
    )
    st.caption("Clique numa linha para abrir aquela noção de caso na aba **Modelo**.")
