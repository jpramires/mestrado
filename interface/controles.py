"""A barra lateral: os controles viram uma `Modelagem` por cenário, mais as opções de desenho.

Cada controle tem `key` e começa em `url.ligar(key, padrão, ...)`: o valor vai para a URL (`?cen=real&agr=usuario`),
então um link reabre exatamente a mesma modelagem. O valor padrão de cada controle fica nesse `ligar`.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st

from comiset import constantes as K
from comiset.dados import nome_evento
from comiset.dfg import Criterio
from comiset.modelagem import Modelagem

from . import consultas
from .formato import data_br, rotulos
from .url import Url

LIMITE_ARESTAS = 250  # acima disso o Graphviz leva segundos (584 arestas: ~20 s no `dot` nativo)
CENARIOS = ["lab", "real", "ambos"]
AGREGACOES = {**{a: rotulo for a, (rotulo, _, _) in K.AGREGACOES.items()}, "personalizada": "Personalizada…"}
RECORTES = {**K.CRITERIOS, "escolher": "Escolher o dia", "todos": "Todos os dias juntos"}


@dataclass(frozen=True)
class Desenho:
    top: int  # programas listados em cada vértice
    fracao: float  # fração das arestas mais frequentes que aparece
    sem_limite: bool  # ignora o LIMITE_ARESTAS
    titulo: bool


@dataclass(frozen=True)
class Escolhas:
    modelagens: dict[str, Modelagem]  # cenário -> modelagem (dois quando o cenário é "ambos")
    recorte: str  # chave de RECORTES
    escolhidos: dict[str, str]  # cenário -> dia escolhido à mão (AAAA-MM-DD)
    desenho: Desenho
    criterio: Criterio


def barra_lateral(url: Url) -> Escolhas:
    sb = st.sidebar

    sb.markdown("#### :material/dataset: Dados")
    cen = sb.segmented_control(
        "Cenário",
        CENARIOS,
        format_func=lambda c: K.CENARIOS.get(c, "Ambos"),
        required=True,
        default=url.ligar("cen", "lab", CENARIOS),
        key="cen",
        width="stretch",
        help="**Ambos** mostra LAB e REAL lado a lado (os períodos não se sobrepõem).",
    )
    cenarios = ("lab", "real") if cen == "ambos" else (cen or "lab",)

    sb.markdown("#### :material/folder_open: Caso e atividade")
    agr = sb.selectbox(
        "Noção de caso",
        list(AGREGACOES),
        format_func=rotulos(AGREGACOES, K.SEAN),
        index=url.indice("agr", "ip_origem", AGREGACOES),
        key="agr",
        help="Que colunas agrupam os alertas num mesmo caso.",
    )
    if agr in K.AGREGACOES:
        _, caso, por_dia = K.AGREGACOES[agr]
    else:
        colunas = sb.multiselect(
            "Colunas do caso",
            list(K.COLUNAS_CASO),
            format_func=rotulos(K.COLUNAS_CASO),
            default=url.ligar("cols", ["src_ip"], K.COLUNAS_CASO),
            key="cols",
        )
        por_dia = sb.toggle("Separar por dia", url.ligar("pdia", True), key="pdia")
        caso = tuple(colunas) or ("src_ip",)
    atividade = sb.selectbox(
        "Atividade (vértice do DFG)",
        list(K.ATIVIDADES),
        format_func=rotulos(K.ATIVIDADES, K.SEAN),
        index=url.indice("atv", "technique", K.ATIVIDADES),
        key="atv",
    )

    sb.markdown("#### :material/filter_alt: Filtros")
    direcao = sb.selectbox(
        "Direção do tráfego",
        list(K.DIRECOES),
        format_func=rotulos({d: rotulo for d, (rotulo, _) in K.DIRECOES.items()}, K.SEAN),
        index=url.indice("dir", "entrada", K.DIRECOES),
        key="dir",
        help="Só os alertas de conexão de rede (EventID 3) têm direção, no campo `Initiated` do Sysmon: "
        "*entrada* (`false`) é a conexão que veio de fora; *saída* (`true`), a que partiu da máquina. "
        "As opções **Só conexões** ficam só com esses alertas; **Todos os alertas** não filtra nada e "
        "inclui também os que não são de rede.",
    )
    minimo = sb.number_input(
        "Mínimo de atividades distintas por caso",
        min_value=1,
        max_value=10,
        value=url.ligar("min", 2),
        key="min",
        help="Casos com menos atividades distintas saem do event log. 1 desliga o filtro (Sean: 2).",
    )
    with sb.expander("Mais filtros", icon=":material/tune:"):
        nomes = consultas.nomes()
        tecnicas = [str(t) for t in consultas.opcoes("technique", cenarios)]
        excluir = st.multiselect(
            "Excluir técnicas",
            tecnicas,
            default=url.ligar("exc", [], tecnicas),
            key="exc",
            format_func=lambda t: f"{t} · {nomes.get(t, '')}",
            placeholder="Nenhuma (ex.: T1059.001, que domina o LAB)",
        )
        eventos = [int(str(e)) for e in consultas.opcoes("event_id", cenarios)]
        tipos = st.multiselect(
            "Só estes tipos de evento",
            eventos,
            default=url.ligar("eid", [], eventos),
            key="eid",
            format_func=lambda e: f"{e} · {nome_evento(e)}",
            placeholder="Todos",
        )
        todos_hosts = [str(h) for h in consultas.opcoes("host", cenarios)]
        hosts = st.multiselect(
            "Só estes hosts",
            todos_hosts,
            default=url.ligar("hst", [], todos_hosts),
            key="hst",
            placeholder="Todos",
        )

    modelagens = {
        c: Modelagem(
            cenario=c,
            direcao=direcao,
            caso=caso,
            por_dia=por_dia,
            atividade=atividade,
            min_atividades=int(minimo),
            excluir_tecnicas=tuple(excluir),
            event_ids=tuple(tipos),
            hosts=tuple(hosts),
        )
        for c in cenarios
    }

    sb.markdown("#### :material/calendar_today: Dia")
    recorte = sb.selectbox(
        "Dia do modelo",
        list(RECORTES),
        format_func=rotulos(RECORTES, K.SEAN),
        index=url.indice("rec", "tecnicas", RECORTES),
        key="rec",
        help="Os três marcados com (Sean) são os critérios do artigo para escolher o dia analisado.",
    )
    escolhidos: dict[str, str] = {}
    if recorte == "escolher":
        for c, m in modelagens.items():
            dias = [str(pd.Timestamp(d).date()) for d in consultas.por_dia_de(m)["data"]]
            if dias:
                escolhidos[c] = sb.selectbox(
                    f"Dia ({K.CENARIOS[c]})",
                    dias,
                    index=url.indice(f"dia_{c}", dias[0], dias),
                    key=f"dia_{c}",
                    format_func=lambda d: data_br(date.fromisoformat(d)),
                )

    with sb.expander("Desenho", icon=":material/palette:"):
        top = st.slider(
            "Programas por vértice",
            0,
            8,
            value=url.ligar("top", 3),
            key="top",
            help="Os programas (`process_name`) que mais disparam a regra de cada vértice.",
        )
        arestas = st.slider(
            "Arestas visíveis (%)",
            5,
            100,
            step=5,
            value=url.ligar("arest", 100),
            key="arest",
            help="Mostra só as arestas mais frequentes. As métricas usam sempre o modelo inteiro.",
        )
        sem_limite = st.toggle(
            "Sem limite de arestas",
            value=url.ligar("tudo", False),
            key="tudo",
            help=f"Por padrão o desenho para nas {LIMITE_ARESTAS} arestas mais frequentes: "
            "acima disso, o navegador pode levar minutos para desenhar.",
        )
        titulo = st.toggle("Título no grafo", url.ligar("tit", True), key="tit")

    with sb.expander("Critério de complexidade", icon=":material/functions:"):
        c1, c2 = st.columns(2)
        v_min = c1.number_input("V mínimo", 1, 100, url.ligar("vmin", K.V_MIN), key="vmin")
        v_max = c2.number_input("V máximo", 1, 200, url.ligar("vmax", K.V_MAX), key="vmax")
        a = c1.number_input("limiar: a", value=url.ligar("lim_a", K.LIMIAR_A), step=0.001, format="%.4f", key="lim_a")
        b = c2.number_input("limiar: b", value=url.ligar("lim_b", K.LIMIAR_B), step=0.001, format="%.4f", key="lim_b")
        st.caption("Simples se V ≤ V mín., complexo se V > V máx.; no meio, complexo se V/E < limiar(V) = a·V + b.")

    sb.caption(":material/link: A URL guarda a modelagem: é só copiar e mandar.")
    sb.caption(
        ":material/school: **(Sean)** marca as escolhas de Alvarenga et al. (2018), de onde vêm também o "
        "critério de complexidade e a equação do limiar."
    )
    return Escolhas(
        modelagens=modelagens,
        recorte=recorte,
        escolhidos=escolhidos,
        desenho=Desenho(top=top, fracao=arestas / 100, sem_limite=sem_limite, titulo=titulo),
        criterio=Criterio(int(v_min), int(v_max), float(a), float(b)),
    )
