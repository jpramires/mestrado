"""App Streamlit: a modelagem do Sean (Alvarenga et al., 2018) sobre os alertas da COMISET, ao vivo.

uv run streamlit run app.py
"""

import io
from collections.abc import Callable, Mapping, Sequence
from datetime import date, timedelta
from html import escape
from typing import Any, Literal, NamedTuple, TypedDict, cast

import pandas as pd
import streamlit as st

from interface import graficos, tema
from interface import grafo as dfg
from sean import constantes as K
from sean.dados import Conexao, conectar, nome_evento, nomes_tecnicas
from sean.desenho import PALETAS, Dot, arestas_visiveis, desenhar
from sean.dfg import (
    Criterio,
    Metricas,
    Modelo,
    Processos,
    descobrir,
    processos_por_atividade,
)
from sean.modelagem import (
    Funil,
    Modelagem,
    casos,
    dias_por_criterio,
    eventos,
    exportar_log,
    funil,
    por_dia,
)

st.set_page_config(
    page_title="Modelagem do Sean · COMISET", page_icon=":material/hub:", layout="wide"
)

URL = "query-params"
DIRECAO_CURTA = {
    "entrada": "só entrada",
    "saida": "só saída",
    "conexoes": "toda conexão",
    "todos": "todos os alertas",
}
DIRECAO_NOTEBOOK = {
    "entrada": "entrada",
    "saida": "saída",
    "conexoes": "todas",
    "todos": "todos os alertas",
}
RECORTES = {
    **K.CRITERIOS,
    "escolher": "Escolher o dia",
    "todos": "Todos os dias juntos",
}
ABAS = [
    "Modelo",
    "Event log",
    "Por dia",
    "Complexidade",
    "Comparar agregações",
    "Método",
]
# acima disso o Graphviz demora segundos (e no navegador, mais): 584 arestas levam ~20 s no `dot` nativo
LIMITE_ARESTAS = 250

# None = todos os dias; () = nenhum dia atende ao critério
Dias = tuple[date, ...] | None

# A assinatura do `st.dataframe` cita `pa.Array` sem parâmetro de tipo, então o Pyright strict a vê como
# parcialmente desconhecida (é do Streamlit, não daqui). O apelido concentra o único ignore do app.
tabela_st = cast("Callable[..., Any]", st.dataframe)  # pyright: ignore[reportUnknownMemberType]
Cor = Literal["off", "red", "green"]


class Cartao(NamedTuple):
    rotulo: str
    valor: str
    delta: str
    cor: Cor
    ajuda: str | None


class Desenho(TypedDict):
    top: int
    fracao: float
    sem_limite: bool
    titulo: bool


# ---------------------------------------------------------------- formatação pt-BR


def formato(mapa: Mapping[Any, Any]) -> Callable[[Any], str]:
    """`format_func` dos controles a partir de um dicionário valor -> rótulo."""
    return lambda chave: str(mapa[chave])


def num(n: float) -> str:
    return f"{int(n):,}".replace(",", ".")


def dec(x: float, casas: int = 2) -> str:
    return f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def compacto(n: float) -> str:
    """1.713.654 -> "1,71 M"; 684.904 -> "684,9 mil": cabe no cartão."""
    if n >= 1_000_000:
        return f"{dec(n / 1_000_000, 2)} M"
    if n >= 10_000:
        return f"{dec(n / 1_000, 1)} mil"
    return num(n)


def pct(parte: float, todo: float) -> str:
    if not todo:
        return "0%"
    p = 100 * parte / todo
    return f"{dec(p, 1 if p >= 1 or p == 0 else 2)}%"


def data_br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def duracao(td: object) -> str:
    if not isinstance(td, timedelta):  # NaT
        return ""
    segundos = int(td.total_seconds())
    dias, resto = divmod(segundos, 86400)
    horas, resto = divmod(resto, 3600)
    minutos, segundos = divmod(resto, 60)
    if dias:
        return f"{dias}d {horas}h"
    if horas:
        return f"{horas}h {minutos:02d}min"
    if minutos:
        return f"{minutos}min {segundos:02d}s"
    return f"{segundos}s"


# ---------------------------------------------------------------- dados (com cache)


@st.cache_resource
def _conexao() -> Conexao:
    return conectar()


def cursor() -> Conexao:
    # um cursor por consulta: a conexão é compartilhada entre sessões
    return _conexao().cursor()


@st.cache_data(show_spinner=False)
def c_nomes() -> dict[str, str]:
    with cursor() as con:
        return nomes_tecnicas(con)


@st.cache_data(show_spinner=False)
def c_opcoes(coluna: str) -> pd.DataFrame:
    """Valores distintos de uma coluna, por cenário (para os filtros)."""
    with cursor() as con:
        return con.sql(f"""
            SELECT cenario, {coluna} AS valor, count(*) AS n FROM alertas
            WHERE tecnica_valida AND {coluna} IS NOT NULL GROUP BY ALL ORDER BY valor
        """).df()


@st.cache_data(show_spinner=False, max_entries=256)
def c_funil(m: Modelagem) -> Funil:
    with cursor() as con:
        return funil(con, m)


@st.cache_data(show_spinner=False, max_entries=256)
def c_por_dia(m: Modelagem) -> pd.DataFrame:
    with cursor() as con:
        return por_dia(con, m)


@st.cache_data(show_spinner=False, max_entries=256)
def c_modelo(m: Modelagem, datas: Dias) -> Modelo:
    with cursor() as con:
        return descobrir(con, m, datas)


@st.cache_data(show_spinner=False, max_entries=256)
def c_processos(m: Modelagem, datas: Dias) -> Processos:
    with cursor() as con:
        return processos_por_atividade(con, m, datas)


@st.cache_data(show_spinner=False, max_entries=64)
def c_casos(m: Modelagem, datas: Dias) -> pd.DataFrame:
    with cursor() as con:
        return casos(con, m, datas)


@st.cache_data(show_spinner=False, max_entries=64)
def c_eventos(m: Modelagem, datas: Dias, caso: str) -> pd.DataFrame:
    with cursor() as con:
        return eventos(con, m, datas, caso)


@st.cache_data(show_spinner=False, max_entries=8)
def c_exportar(m: Modelagem, datas: Dias, formato_: str) -> bytes:
    with cursor() as con:
        log = exportar_log(con, m, datas)
    buffer = io.BytesIO()
    if (
        formato_ == "csv"
    ):  # mesmo formato do util.salvar: abre direto no Excel em português
        log.to_csv(buffer, sep=";", index=False, encoding="utf-8-sig")
    else:
        log.to_parquet(buffer, index=False)
    return buffer.getvalue()


@st.cache_data(show_spinner=False, max_entries=32)
def c_comparar(
    m: Modelagem, por_mais_eventos: bool, criterio: Criterio
) -> pd.DataFrame:
    """As 8 agregações da §5 com o resto da modelagem igual."""
    linhas: list[dict[str, object]] = []
    for nome, (rotulo, _, _) in K.AGREGACOES.items():
        mm = m.com_agregacao(nome)
        f = c_funil(mm)
        dia = dias_por_criterio(c_por_dia(mm)).get("eventos")
        if dia is None:
            continue
        metricas = c_modelo(mm, (dia,) if por_mais_eventos else None).metricas(criterio)
        if metricas is None:
            continue
        linhas.append(
            {
                "cenario": K.CENARIOS[m.cenario],
                "agregacao": nome,
                "rotulo": rotulo,
                "cobertura": f["universo"] / f["alertas"],
                "casos_antes": f["casos_antes"],
                "casos_depois": f["casos"],
                "eventos": f["eventos"],
                "atividades": f["atividades"],
                "dia": data_br(dia) if por_mais_eventos else "todos",
                **metricas,
            }
        )
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------- textos


def descrever_caso(m: Modelagem) -> str:
    partes = [K.COLUNAS_CASO[c] for c in m.caso] + (["dia"] if m.por_dia else [])
    return "⟨" + ", ".join(partes) + "⟩"


def titulos(m: Modelagem, rotulo_dia: str) -> tuple[str, str]:
    """Como no Notebook 4: (cenário, direção, dia); embaixo, (caso, atividade)."""
    titulo = f"({K.CENARIOS[m.cenario]}, {DIRECAO_NOTEBOOK[m.direcao]}, {rotulo_dia})"
    # a Arial do PNG não tem ⟨⟩
    caso = descrever_caso(m).replace("⟨", "<").replace("⟩", ">")
    return titulo, f"({caso}, {K.ATIVIDADES[m.atividade].lower()})"


def nome_arquivo(m: Modelagem, rotulo_dia: str, sufixo: str) -> str:
    agr = next(
        (
            nome
            for nome, (_, colunas, por_dia_) in K.AGREGACOES.items()
            if colunas == m.caso and por_dia_ == m.por_dia
        ),
        "personalizada",
    )
    return f"{sufixo}_{m.cenario}_{agr}_{m.direcao}_{rotulo_dia.replace('/', '-').replace(' ', '_')}"


# ---------------------------------------------------------------- barra lateral


def voltar_ao_sean() -> None:
    """Recarrega a página sem parâmetros na URL: todos os controles voltam ao padrão (o Sean literal)."""
    st.html(
        "<script>window.location.href = window.location.pathname;</script>",
        unsafe_allow_javascript=True,
    )


def opcoes_de(coluna: str, cenarios: Sequence[str]) -> list[object]:
    """Valores de uma coluna que aparecem nos cenários escolhidos, em ordem."""
    tabela = c_opcoes(coluna)
    valores = tabela.loc[tabela["cenario"].isin(cenarios), "valor"]
    return sorted(set(valores.tolist()), key=str)


class Escolhas(NamedTuple):
    modelagens: dict[str, Modelagem]
    recorte: str
    escolhidos: dict[str, str]
    desenho: Desenho
    criterio: Criterio


def barra_lateral() -> Escolhas:
    """Desenha os controles e devolve a modelagem de cada cenário e os parâmetros do desenho."""
    nomes = c_nomes()
    sb = st.sidebar
    sb.markdown("### :material/tune: Modelagem")

    cen = sb.segmented_control(
        "Cenário",
        ["lab", "real", "ambos"],
        format_func=lambda c: K.CENARIOS.get(c, "Ambos"),
        default="lab",
        required=True,
        key="cen",
        bind=URL,
        width="stretch",
        help="**Ambos** mostra LAB e REAL lado a lado (os períodos não se sobrepõem).",
    )
    cenarios = ["lab", "real"] if cen == "ambos" else [cen or "lab"]

    agr = sb.selectbox(
        "Noção de caso",
        [*K.AGREGACOES, "personalizada"],
        format_func=lambda a: (
            K.AGREGACOES[a][0] if a in K.AGREGACOES else "Personalizada…"
        ),
        key="agr",
        bind=URL,
        help="As 8 agregações da §5.2 do Notebook 4. O Sean usa IP de origem + dia.",
    )
    if agr in K.AGREGACOES:
        _, caso, por_dia_ = K.AGREGACOES[agr]
    else:
        colunas = sb.multiselect(
            "Colunas do caso",
            list(K.COLUNAS_CASO),
            default=["src_ip"],
            format_func=formato(K.COLUNAS_CASO),
            key="cols",
            bind=URL,
        )
        por_dia_ = sb.toggle("Separar por dia", value=True, key="pdia", bind=URL)
        caso = tuple(colunas) or ("src_ip",)

    direcao = sb.selectbox(
        "Direção do tráfego",
        list(K.DIRECOES),
        format_func=lambda d: K.DIRECOES[d][0],
        key="dir",
        bind=URL,
        help="Campo `Initiated` do Sysmon: *false* = conexão veio de fora. Qualquer opção diferente de "
        "**Todos os alertas** restringe o universo aos alertas de rede (EventID 3).",
    )
    atividade = sb.selectbox(
        "Atividade (vértice do DFG)",
        list(K.ATIVIDADES),
        format_func=formato(K.ATIVIDADES),
        key="atv",
        bind=URL,
    )
    minimo = sb.number_input(
        "Mínimo de atividades distintas por caso",
        min_value=1,
        max_value=10,
        value=2,
        key="min",
        bind=URL,
        help="Filtro do Sean: com 2, casos com uma atividade só são descartados. Com 1, o filtro desliga.",
    )

    with sb.expander("Filtros", icon=":material/filter_alt:"):
        excluir = st.multiselect(
            "Excluir técnicas",
            [str(t) for t in opcoes_de("technique", cenarios)],
            default=[],
            key="exc",
            bind=URL,
            format_func=lambda t: f"{t} · {nomes.get(t, '')}",
            placeholder="Nenhuma (ex.: T1059.001, que domina o LAB)",
        )
        eventos_ = st.multiselect(
            "Só estes tipos de evento",
            [int(str(e)) for e in opcoes_de("event_id", cenarios)],
            default=[],
            key="eid",
            bind=URL,
            format_func=lambda e: f"{e} · {nome_evento(e)}",
            placeholder="Todos",
        )
        hosts = st.multiselect(
            "Só estes hosts",
            [str(h) for h in opcoes_de("host", cenarios)],
            default=[],
            key="hst",
            bind=URL,
            placeholder="Todos",
        )

    modelagens = {
        c: Modelagem(
            cenario=c,
            direcao=direcao,
            caso=caso,
            por_dia=por_dia_,
            atividade=atividade,
            min_atividades=int(minimo),
            excluir_tecnicas=tuple(excluir),
            event_ids=tuple(eventos_),
            hosts=tuple(hosts),
        )
        for c in cenarios
    }

    recorte = sb.selectbox(
        "Dia do modelo",
        list(RECORTES),
        format_func=formato(RECORTES),
        key="rec",
        bind=URL,
        help="Os três primeiros são os critérios do Sean (§5.1 do artigo). "
        "**Mais eventos após o filtro** é o da §5.3 do Notebook 4.",
    )
    escolhidos: dict[str, str] = {}
    if recorte == "escolher":
        for c, m in modelagens.items():
            dias = [str(pd.Timestamp(d).date()) for d in c_por_dia(m)["data"]]
            if not dias:  # universo vazio: não há dia para escolher
                continue
            escolhidos[c] = sb.selectbox(
                f"Dia ({K.CENARIOS[c]})",
                dias,
                key=f"dia_{c}",
                bind=URL,
                format_func=lambda d: data_br(date.fromisoformat(d)),
            )

    with sb.expander("Desenho", icon=":material/palette:"):
        top = st.slider(
            "Programas por vértice",
            0,
            8,
            3,
            key="top",
            bind=URL,
            help="Os programas (`process_name`) que mais disparam a regra de cada vértice.",
        )
        arestas = st.slider(
            "Arestas visíveis (%)",
            5,
            100,
            100,
            step=5,
            key="arest",
            bind=URL,
            help="Mostra só as arestas mais frequentes. As métricas usam sempre o modelo inteiro.",
        )
        sem_limite = st.toggle(
            "Sem limite de arestas",
            value=False,
            key="tudo",
            bind=URL,
            help=f"Por padrão o desenho mostra no máximo as {LIMITE_ARESTAS} arestas mais frequentes: "
            "acima disso, o navegador pode levar minutos para desenhar.",
        )
        titulo = st.toggle("Título no grafo", value=True, key="tit", bind=URL)

    with sb.expander("Critério de complexidade", icon=":material/functions:"):
        c1, c2 = st.columns(2)
        v_min = c1.number_input("V mínimo", 1, 100, K.V_MIN, key="vmin", bind=URL)
        v_max = c2.number_input("V máximo", 1, 200, K.V_MAX, key="vmax", bind=URL)
        a = c1.number_input(
            "ts: a", value=K.TS_A, step=0.001, format="%.4f", key="tsa", bind=URL
        )
        b = c2.number_input(
            "ts: b", value=K.TS_B, step=0.001, format="%.4f", key="tsb", bind=URL
        )
        st.caption(
            "Sean, eq. 5 e 6: simples se V ≤ V mín., complexo se V > V máx.; no meio, complexo se V/E < ts(V) = a·V + b."
        )

    if sb.button(
        "Voltar ao Sean literal", icon=":material/restart_alt:", width="stretch"
    ):
        voltar_ao_sean()
    sb.divider()
    with sb:
        tema.seletor()
    sb.caption(":material/link: A URL guarda a modelagem: é só copiar e mandar.")

    return Escolhas(
        modelagens=modelagens,
        recorte=recorte,
        escolhidos=escolhidos,
        desenho=Desenho(
            top=top, fracao=arestas / 100, sem_limite=sem_limite, titulo=titulo
        ),
        criterio=Criterio(int(v_min), int(v_max), float(a), float(b)),
    )


def resolver_recorte(
    m: Modelagem, recorte: str, escolhido: str | None
) -> tuple[Dias, str]:
    """(datas, rótulo) do dia do modelo."""
    if recorte == "todos":
        return None, "todos os dias"
    if recorte == "escolher":
        if escolhido is None:
            return None, "todos os dias"
        dia = date.fromisoformat(escolhido)
        return (dia,), data_br(dia)
    dia = dias_por_criterio(c_por_dia(m)).get(recorte)
    if dia is None:
        return (), "sem dia"
    return (dia,), data_br(dia)


# ---------------------------------------------------------------- blocos da página


def cabecalho(
    modelagens: Mapping[str, Modelagem], recorte: str, rotulos_dia: Mapping[str, str]
) -> None:
    m = next(iter(modelagens.values()))
    st.markdown("## Modelagem do Sean na COMISET")
    st.caption(
        "Alvarenga et al. (2018) sobre os 2,35 M alertas da COMISET: troque a noção de caso, a atividade "
        "ou o filtro e veja o DFG, as métricas e o event log na hora."
    )
    with st.container(horizontal=True, gap="small"):
        st.badge(
            " + ".join(K.CENARIOS[c] for c in modelagens),
            icon=":material/dataset:",
            color="violet",
        )
        st.badge(
            f"caso = {descrever_caso(m)}", icon=":material/folder_open:", color="blue"
        )
        st.badge(
            f"atividade = {K.ATIVIDADES[m.atividade].lower()}",
            icon=":material/hub:",
            color="blue",
        )
        st.badge(DIRECAO_CURTA[m.direcao], icon=":material/swap_horiz:", color="gray")
        st.badge(
            f"≥ {m.min_atividades} atividades por caso"
            if m.min_atividades > 1
            else "sem filtro do Sean",
            icon=":material/filter_alt:",
            color="gray",
        )
        dias = " · ".join(rotulos_dia.values())
        st.badge(
            f"{dias} ({RECORTES[recorte].lower()})",
            icon=":material/calendar_today:",
            color="orange",
        )
        if m.excluir_tecnicas or m.event_ids or m.hosts:
            st.badge("com filtros extras", icon=":material/tune:", color="red")


def _grupo(titulo: str, cartoes_: Sequence[Cartao]) -> None:
    st.caption(titulo)
    for coluna, cartao in zip(st.columns(3, gap="small"), cartoes_, strict=False):
        coluna.metric(
            cartao.rotulo,
            cartao.valor,
            delta=cartao.delta,
            delta_color=cartao.cor,
            delta_arrow="off",
            border=True,
            help=cartao.ajuda,
        )


def cartoes(m: Modelagem, metricas: Metricas | None, rotulo_dia: str) -> None:
    """Dois grupos de três cartões: o event log inteiro e o modelo do recorte."""
    f = c_funil(m)
    log = [
        Cartao(
            "Universo",
            compacto(f["universo"]),
            f"{pct(f['universo'], f['alertas'])} dos alertas",
            "off",
            f"{num(f['universo'])} de {num(f['alertas'])} alertas do cenário",
        ),
        Cartao(
            "Casos",
            compacto(f["casos"]),
            f"{compacto(f['casos_antes'])} antes do filtro",
            "off",
            f"{num(f['casos'])} casos passam no filtro do Sean, de {num(f['casos_antes'])}",
        ),
        Cartao(
            "Eventos",
            compacto(f["eventos"]),
            f"{num(f['atividades'])} atividades",
            "off",
            f"{num(f['eventos'])} eventos no event log",
        ),
    ]
    if metricas is None:
        modelo = [Cartao("Modelo", "vazio", "nenhum caso sobra nesse dia", "off", None)]
    else:
        complexo = metricas["complexo"]
        modelo = [
            Cartao(
                "Vértices · arestas",
                f"{metricas['vertices']} · {metricas['arestas']}",
                f"{num(metricas['casos'])} {'caso' if metricas['casos'] == 1 else 'casos'} no recorte",
                "off",
                "V conta INÍCIO e FIM; E conta todas as arestas",
            ),
            Cartao(
                "Simplicidade V/E",
                dec(metricas["simplicidade"], 3),
                f"ts(V) = {dec(metricas['limiar_ts'], 3)}",
                "off",
                "Sean, eq. 2 e 5: na faixa do meio, o modelo é complexo se V/E < ts(V)",
            ),
            Cartao(
                "Veredito do Sean",
                "Complexo" if complexo else "Simples",
                "pede clustering" if complexo else "dispensa clustering",
                "red" if complexo else "green",
                "No artigo, um modelo complexo segue para o clustering hierárquico dos casos",
            ),
        ]
    _grupo(":material/receipt_long: **Event log** · todos os dias", log)
    _grupo(f":material/hub: **Modelo** · {rotulo_dia}", modelo)


def aba_modelo(
    m: Modelagem,
    datas: Dias,
    rotulo_dia: str,
    desenho: Desenho,
    nomes: Mapping[str, str],
    tema_atual: str,
) -> None:
    modelo = c_modelo(m, datas)
    if modelo.vazio:
        st.info(
            "Nenhum caso sobra nesse dia depois do filtro do Sean. Tente outro dia ou outro critério.",
            icon=":material/info:",
        )
        return
    # com atividade = técnica + programa, a lista de programas do vértice só repetiria o próprio programa
    mostra_programas = desenho["top"] > 0 and m.atividade != "technique_proc"
    processos = c_processos(m, datas) if mostra_programas else None
    titulo, subtitulo = titulos(m, rotulo_dia)
    total = len(modelo.arestas)
    fracao = desenho["fracao"]
    limitado = not desenho["sem_limite"] and fracao * total > LIMITE_ARESTAS
    if limitado:
        fracao = LIMITE_ARESTAS / total

    def grafo_em(tema_: str, com_titulo: bool) -> Dot:
        return desenhar(
            modelo,
            m.atividade,
            nomes,
            processos,
            top=desenho["top"],
            fracao_arestas=fracao,
            titulo=titulo if com_titulo else None,
            subtitulo=subtitulo,
            tema=tema_,
        )

    grafo = grafo_em(tema_atual, desenho["titulo"])
    claro = grafo_em("light", True)  # exportação: sempre clara e com título
    claro.grafo["bgcolor"] = "white"
    dfg.mostrar(
        grafo, claro, nome_arquivo(m, rotulo_dia, "dfg"), key=f"dfg_{m.cenario}"
    )

    visiveis = arestas_visiveis(modelo, fracao)
    legenda = (
        "Cor dos vértices e espessura das arestas seguem a frequência (escala log)."
    )
    if len(visiveis) < total:
        tocados = {str(x) for x in visiveis["de"]} | {str(x) for x in visiveis["para"]}
        ocultos = len({str(x) for x in modelo.vertices["atividade"]} - tocados)
        legenda += (
            f" Mostrando as {len(visiveis)} arestas mais frequentes de {num(total)}"
        )
        legenda += (
            f"; {num(ocultos)} vértices ficaram sem aresta e saíram do desenho."
            if ocultos
            else "."
        )
    if limitado:
        legenda += (
            f" Modelo grande: o desenho para em {LIMITE_ARESTAS} arestas, porque mais que isso pode levar"
            " minutos no navegador. Para ver todas, ligue **Sem limite de arestas** em *Desenho*."
        )
    st.caption(legenda)

    if processos:
        with st.expander("Programas que disparam cada atividade"):
            tabela = pd.DataFrame(
                [
                    {"atividade": atividade, "programa": programa, "alertas": n}
                    for atividade, programas in processos.items()
                    for programa, n in programas
                ]
            )
            tabela_st(
                tabela,
                hide_index=True,
                width="stretch",
                column_config={
                    "alertas": st.column_config.NumberColumn(format="localized")
                },
            )


def _encurtar(casos_: Sequence[str]) -> tuple[list[str], str | None]:
    """Tira dos casos as partes iguais em todos eles (o único host do LAB, o dia do recorte)."""
    partes = [caso.split("|") for caso in casos_]
    n = max(len(p) for p in partes)
    iguais = [
        i for i in range(n) if len({p[i] if i < len(p) else "" for p in partes}) == 1
    ]
    if not iguais or len(iguais) == n:
        return list(casos_), None
    curtos = [" | ".join(x for i, x in enumerate(p) if i not in iguais) for p in partes]
    return curtos, " · ".join(partes[0][i] for i in iguais)


def aba_event_log(m: Modelagem, datas: Dias, rotulo_dia: str, escopo: str) -> None:
    datas_ = datas if escopo == "dia" else None
    tabela = c_casos(m, datas_)
    if tabela.empty:
        st.info("Nenhum caso nesse recorte.", icon=":material/info:")
        return
    nomes_casos = [str(c) for c in tabela["caso"]]
    curtos, omitidas = _encurtar(nomes_casos)
    vista = tabela.assign(
        duracao=[duracao(td) for td in tabela["duracao"]], curto=curtos
    )
    escolha = tabela_st(
        vista,
        hide_index=True,
        width="stretch",
        height=min(420, 38 + 35 * len(vista)),
        on_select="rerun",
        selection_mode="single-row",
        key=f"casos_{m.cenario}",
        column_order=[
            "curto",
            "eventos",
            "atividades",
            "programas",
            "destinos",
            "inicio",
            "fim",
            "duracao",
            "sequencia",
        ],
        column_config={
            "curto": st.column_config.TextColumn("caso", width="medium", pinned=True),
            "eventos": st.column_config.ProgressColumn(
                "eventos",
                format="localized",
                min_value=0,
                max_value=int(tabela["eventos"].to_numpy().max()),
            ),
            "atividades": st.column_config.NumberColumn("ativ.", width="small"),
            "programas": st.column_config.NumberColumn("progr.", width="small"),
            "destinos": st.column_config.NumberColumn("IPs dest.", width="small"),
            "inicio": st.column_config.DatetimeColumn(
                "início", format="DD/MM HH:mm:ss"
            ),
            "fim": st.column_config.DatetimeColumn("fim", format="DD/MM HH:mm:ss"),
            "duracao": st.column_config.TextColumn("duração", width="small"),
            "sequencia": st.column_config.TextColumn(
                "sequência (atividade  programa, ×N = repetições seguidas)",
                width="large",
            ),
        },
    )
    linhas: list[int] = list(escolha.selection.rows)
    st.caption(
        f"{num(len(vista))} {'caso' if len(vista) == 1 else 'casos'}. Clique numa linha para ver os eventos do caso."
        + (
            f" Partes iguais em todos os casos foram omitidas: `{omitidas}`."
            if omitidas
            else ""
        )
    )
    if linhas:
        caso = nomes_casos[linhas[0]]
        detalhe = c_eventos(m, datas_, caso)
        st.markdown(f"##### Eventos de `{caso}`")
        tabela_st(
            detalhe.drop(columns="caso"),
            hide_index=True,
            width="stretch",
            height=360,
            column_config={
                "ts": st.column_config.DatetimeColumn(
                    "ts", format="DD/MM/YYYY HH:mm:ss.SSS"
                )
            },
        )
        total = int(tabela["eventos"].to_numpy()[linhas[0]])
        if total > len(detalhe):
            st.caption(
                f"Mostrando os primeiros {num(len(detalhe))} de {num(total)} eventos."
            )

    base = nome_arquivo(m, rotulo_dia if escopo == "dia" else "todos os dias", "log")
    with st.container(horizontal=True, gap="small"):
        st.download_button(
            "Event log (CSV)",
            lambda: c_exportar(m, datas_, "csv"),
            f"{base}.csv",
            "text/csv",
            icon=":material/download:",
            key=f"csv_{m.cenario}",
        )
        st.download_button(
            "Event log (Parquet)",
            lambda: c_exportar(m, datas_, "parquet"),
            f"{base}.parquet",
            "application/octet-stream",
            icon=":material/download:",
            key=f"pq_{m.cenario}",
        )


def aba_por_dia(m: Modelagem, metrica: str) -> None:
    tabela = c_por_dia(m)
    if tabela.empty:
        st.info("O universo está vazio.", icon=":material/info:")
        return
    escolhas = dias_por_criterio(tabela)
    destaques: dict[date, str] = {}
    for criterio, dia in escolhas.items():
        destaques[dia] = ", ".join(
            filter(None, [destaques.get(dia), K.CRITERIOS[criterio].lower()])
        )
    rotulos = {
        "alertas": "alertas no universo",
        "casos": "casos distintos",
        "tecnicas": "técnicas distintas",
        "eventos": "eventos após o filtro",
    }
    st.altair_chart(
        graficos.por_dia(tabela, metrica, rotulos[metrica], destaques), width="stretch"
    )
    with st.container(horizontal=True, gap="small"):
        for criterio, dia in escolhas.items():
            st.badge(
                f"{K.CRITERIOS[criterio]}: {data_br(dia)}",
                icon=":material/event:",
                color="blue",
            )
    tabela_st(
        tabela.assign(data=pd.to_datetime(tabela["data"])),
        hide_index=True,
        width="stretch",
        column_config={
            "data": st.column_config.DateColumn("dia", format="DD/MM/YYYY"),
            "alertas": "alertas",
            "casos": "casos",
            "tecnicas": "técnicas",
            "eventos": "eventos após filtro",
            "casos_filtrados": "casos após filtro",
        },
    )


def aba_complexidade(
    modelagens: Mapping[str, Modelagem],
    recortes: Mapping[str, tuple[Dias, str]],
    criterio: Criterio,
) -> None:
    pontos: list[dict[str, object]] = []
    for c, m in modelagens.items():
        datas, rotulo = recortes[c]
        metricas = c_modelo(m, datas).metricas(criterio) if datas != () else None
        if metricas:
            pontos.append({**metricas, "rotulo": f"{K.CENARIOS[c]} · {rotulo}"})
    esquerda, direita = st.columns([3, 2], gap="large")
    with esquerda:
        if pontos:
            st.altair_chart(
                graficos.plano_complexidade(
                    pd.DataFrame(pontos), criterio, cor="rotulo"
                ),
                width="stretch",
            )
        else:
            st.info("Sem modelo no recorte atual.", icon=":material/info:")
    with direita:
        st.markdown("##### O critério do Sean")
        a, b = (f"{x:.4f}".replace(".", "{,}") for x in (criterio.a, criterio.b))
        st.markdown(
            r"$$\text{simplicidade} = \frac{V}{E} \qquad \text{(eq. 2)}$$"
            "\n\n"
            rf"$$ts(V) = {a}\,V + {b} \qquad \text{{(eq. 5)}}$$"
            "\n\n"
            rf"$$\text{{complexo}} \iff V > {criterio.v_max} \;\lor\; "
            rf"\left({criterio.v_min} < V \le {criterio.v_max} \;\land\; \tfrac{{V}}{{E}} < ts(V)\right)"
            r"\qquad \text{(eq. 6)}$$"
        )
        st.markdown(
            "V conta as atividades mais **INÍCIO** e **FIM**; E conta todas as arestas, inclusive as que saem "
            "do INÍCIO e chegam ao FIM. A reta `ts` veio de uma regressão sobre 219 modelos classificados por um "
            "especialista. Um modelo complexo, no artigo, segue para o *clustering* hierárquico dos casos."
        )
        st.caption(
            "Os parâmetros podem ser mexidos em **Critério de complexidade**, na barra lateral."
        )


def abrir_agregacao() -> None:
    escolha = st.session_state["tabela_comparar"].selection.rows
    if escolha:
        st.session_state["agr"] = st.session_state["_comparar_agregacoes"][escolha[0]]
        st.session_state["aba"] = "Modelo"


def aba_comparar(modelagens: Mapping[str, Modelagem], criterio: Criterio) -> None:
    c1, c2 = st.columns(2)
    universo = c1.segmented_control(
        "Universo",
        ["sean5", "barra"],
        default="sean5",
        required=True,
        key="cmp_universo",
        format_func=formato(
            {"sean5": "Todos os alertas (§5)", "barra": "O da barra lateral"}
        ),
        help="A §5 do Notebook 4 roda as agregações sobre todos os alertas, sem filtro de direção.",
    )
    modo = c2.segmented_control(
        "Dia de cada modelo",
        ["eventos", "todos"],
        default="eventos",
        required=True,
        key="cmp_modo",
        format_func=formato(
            {"eventos": "O com mais eventos (§5.3)", "todos": "Todos os dias juntos"}
        ),
    )
    tabelas: list[pd.DataFrame] = []
    with st.spinner("Rodando as 8 agregações…"):
        for m in modelagens.values():
            base = (
                m
                if universo == "barra"
                else Modelagem(
                    cenario=m.cenario,
                    direcao="todos",
                    atividade=m.atividade,
                    min_atividades=m.min_atividades,
                )
            )
            tabelas.append(c_comparar(base, modo == "eventos", criterio))
    tabela = pd.concat(tabelas, ignore_index=True)
    if tabela.empty:
        st.info("Nenhuma agregação gerou modelo.", icon=":material/info:")
        return
    st.session_state["_comparar_agregacoes"] = [str(a) for a in tabela["agregacao"]]

    tabela["rotulo_ponto"] = tabela["rotulo"] + (
        " · " + tabela["cenario"] if len(modelagens) > 1 else ""
    )
    st.altair_chart(
        graficos.plano_complexidade(
            tabela,
            criterio,
            rotulo="rotulo_ponto",
            cor="rotulo",
            forma="cenario" if len(modelagens) > 1 else None,
        ),
        width="stretch",
    )
    tabela_st(
        tabela[
            [
                "cenario",
                "rotulo",
                "cobertura",
                "casos_antes",
                "casos_depois",
                "eventos",
                "atividades",
                "dia",
                "casos",
                "vertices",
                "arestas",
                "simplicidade",
                "limiar_ts",
                "complexo",
            ]
        ],
        hide_index=True,
        width="stretch",
        key="tabela_comparar",
        on_select=abrir_agregacao,
        selection_mode="single-row",
        column_config={
            "cenario": "cenário",
            "rotulo": "agregação",
            "cobertura": st.column_config.NumberColumn("cobertura", format="percent"),
            "casos_antes": st.column_config.NumberColumn(
                "casos antes", format="localized"
            ),
            "casos_depois": st.column_config.NumberColumn(
                "casos depois", format="localized"
            ),
            "eventos": st.column_config.NumberColumn("eventos", format="localized"),
            "casos": st.column_config.NumberColumn("casos no dia", format="localized"),
            "vertices": "V",
            "arestas": "E",
            "simplicidade": st.column_config.NumberColumn("V/E", format="%.3f"),
            "limiar_ts": st.column_config.NumberColumn("ts(V)", format="%.3f"),
            "complexo": st.column_config.CheckboxColumn("complexo"),
        },
    )
    st.caption("Clique numa linha para abrir aquela agregação na aba **Modelo**.")


def aba_metodo(tema_atual: str) -> None:
    p = PALETAS[tema_atual]
    etapas = [
        (
            "dados",
            "dados/*.parquet",
            ["252 M eventos Windows", "(Sysmon e log nativo), 16 GB"],
        ),
        (
            "alertas",
            "Alertas",
            ["eventos com rótulo ATT&CK:", "1,71 M (LAB) + 632 k (REAL)"],
        ),
        (
            "higiene",
            "Higiene",
            ["IDs sujos e versões antigas", "do ATT&CK normalizados"],
        ),
        (
            "universo",
            "Universo",
            ["direção do tráfego, técnica válida,", "filtros, chave do caso presente"],
        ),
        ("caso", "Caso", ["colunas que agrupam", "os alertas (+ dia)"]),
        (
            "filtro",
            "Filtro do Sean",
            ["descarta casos com menos", "de N atividades distintas"],
        ),
        ("recorte", "Recorte", ["o dia do modelo", "(critérios do Sean ou à mão)"]),
        ("dfg", "DFG", ["Algoritmo 1: vértices, arestas,", "INÍCIO e FIM"]),
        ("complexidade", "Complexidade", ["eq. 2, 5 e 6:", "simples ou complexo"]),
    ]
    g = Dot(
        grafo={
            "rankdir": "TB",
            "bgcolor": "transparent",
            "nodesep": "0.25",
            "ranksep": "0.22",
        },
        vertices={
            "shape": "box",
            "style": "rounded,filled",
            "fontname": "Arial",
            "fontsize": "11",
            "fillcolor": p["vertice_min"],
            "color": p["vertice_max"],
            "fontcolor": p["texto"],
            "margin": "0.15,0.08",
            "width": "3.2",
        },
        arestas={"color": p["aresta"], "arrowsize": "0.7"},
    )
    for i, (chave, nome, desc) in enumerate(etapas):
        linhas = "<BR/>".join(escape(linha) for linha in desc)
        g.vertice(
            chave,
            label=f'<<B>{escape(nome)}</B><BR/><FONT POINT-SIZE="9" COLOR="{p["suave"]}">{linhas}</FONT>>',
        )
        if i:
            g.aresta(etapas[i - 1][0], chave)
    esquerda, direita = st.columns([2, 3], gap="large")
    esquerda.graphviz_chart(g.fonte, width="content")
    direita.markdown("""
O app refaz, ao vivo, o pipeline do **Notebook 4** (`4_replicacao_sean.ipynb`). Cada controle da barra lateral mexe
numa etapa:

| Etapa | Controle | No Sean |
|---|---|---|
| Universo | cenário, direção do tráfego, filtros | alertas de IDS com tráfego de entrada |
| Caso | noção de caso | ⟨IP de origem, dia⟩ |
| Atividade | atividade | a técnica do alerta |
| Filtro | mínimo de atividades distintas | 2 (casos de uma técnica só saem) |
| Recorte | dia do modelo | dias com mais alertas, IPs e técnicas |

**Diferenças em relação ao artigo.** No Sysmon, `src_ip` é a máquina monitorada e não o atacante, então a direção
vem do campo `Initiated` (*false* = entrada). Há pouquíssimo tráfego de entrada (587 alertas no LAB e 234 no REAL),
por isso a replicação literal gera 3 casos no LAB e 1 no REAL; as outras noções de caso estão aqui para comparar.

**Ordem dos alertas.** O DFG depende da ordem dentro do caso. Alertas com o mesmo timestamp seguem a ordem do
arquivo de alertas, como o `sort_values(..., kind="stable")` da §3 do notebook. O dia é cortado em UTC.

**Reprodutibilidade.** `uv run python -m sean.paridade` confere que o núcleo reproduz as tabelas salvas pelo
notebook (`tabela_modelos`, `tabela_dias`, `tabela_agregacoes` e `tabela_complexidade`).

**Referências.** Alvarenga, S. C. et al. *Process mining and hierarchical clustering to help intrusion alert
visualization*. Computers & Security 73, 2018. Pérez-Sánchez, A. et al. *COMISET: Dataset for the analysis of
malicious events in Windows systems*. Data in Brief 61, 2025.
""")


# ---------------------------------------------------------------- página


def colunas_por_cenario(modelagens: Mapping[str, Modelagem]) -> list[Any]:
    """Uma coluna por cenário quando são dois; senão, a página inteira."""
    if len(modelagens) > 1:
        return list(st.columns(len(modelagens), gap="large"))
    return [st.container()]


def pagina() -> None:
    tema_atual = tema.montar()
    escolhas = barra_lateral()
    modelagens, criterio = escolhas.modelagens, escolhas.criterio
    recortes = {
        c: resolver_recorte(m, escolhas.recorte, escolhas.escolhidos.get(c))
        for c, m in modelagens.items()
    }
    cabecalho(modelagens, escolhas.recorte, {c: r[1] for c, r in recortes.items()})

    with st.spinner("Calculando…"):
        for coluna, (c, m) in zip(
            colunas_por_cenario(modelagens), modelagens.items(), strict=True
        ):
            with coluna:
                if len(modelagens) > 1:
                    st.markdown(f"#### {K.CENARIOS[c]}")
                datas, rotulo = recortes[c]
                cartoes(
                    m,
                    c_modelo(m, datas).metricas(criterio) if datas != () else None,
                    rotulo,
                )

    abas = st.tabs(ABAS, key="aba", bind=URL)
    nomes = c_nomes()

    with abas[0]:
        if abas[0].open:
            for coluna, (c, m) in zip(
                colunas_por_cenario(modelagens), modelagens.items(), strict=True
            ):
                with coluna, st.spinner("Desenhando o modelo…"):
                    datas, rotulo = recortes[c]
                    if datas == ():
                        st.info(
                            "Nenhum dia atende ao critério.", icon=":material/info:"
                        )
                    else:
                        aba_modelo(
                            m, datas, rotulo, escolhas.desenho, nomes, tema_atual
                        )

    with abas[1]:
        if abas[1].open:
            rotulos = " · ".join(r[1] for r in recortes.values())
            escopo = st.segmented_control(
                "Casos de",
                ["dia", "todos"],
                default="dia",
                required=True,
                key="escopo",
                format_func=formato(
                    {"dia": f"Recorte do modelo ({rotulos})", "todos": "Todos os dias"}
                ),
            )
            for c, m in modelagens.items():
                if len(modelagens) > 1:
                    st.markdown(f"#### {K.CENARIOS[c]}")
                with st.spinner("Montando os casos…"):
                    datas, rotulo = recortes[c]
                    aba_event_log(m, datas or None, rotulo, escopo or "dia")

    with abas[2]:
        if abas[2].open:
            metrica = st.segmented_control(
                "Métrica",
                ["alertas", "casos", "tecnicas", "eventos"],
                default="alertas",
                required=True,
                key="metrica_dia",
                format_func=formato(
                    {
                        "alertas": "Alertas",
                        "casos": "Casos distintos",
                        "tecnicas": "Técnicas distintas",
                        "eventos": "Eventos após o filtro",
                    }
                ),
            )
            for coluna, (c, m) in zip(
                colunas_por_cenario(modelagens), modelagens.items(), strict=True
            ):
                with coluna:
                    if len(modelagens) > 1:
                        st.markdown(f"#### {K.CENARIOS[c]}")
                    aba_por_dia(m, metrica or "alertas")

    with abas[3]:
        if abas[3].open:
            aba_complexidade(modelagens, recortes, criterio)

    with abas[4]:
        if abas[4].open:
            aba_comparar(modelagens, criterio)

    with abas[5]:
        if abas[5].open:
            aba_metodo(tema_atual)


pagina()
