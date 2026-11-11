"""A página do método: o caminho do alerta ao modelo, a referência principal, o critério e as referências."""

import streamlit as st

from comiset import constantes as K

# (ícone, título, o que acontece, onde se mexe nisso na barra lateral), na ordem da barra lateral
PASSOS = [
    (
        ":material/database:",
        "Alertas",
        (
            "Os eventos Windows da COMISET [2] que têm rótulo ATT&CK: 1,71 M no LAB e 632 k no REAL, com os IDs de "
            "técnica corrigidos (IDs sujos e versões antigas do ATT&CK). Dá para ver um cenário ou os dois lado a lado."
        ),
        "Dados",
    ),
    (
        ":material/folder_open:",
        "Noção de caso",
        (
            "Que colunas agrupam os alertas num mesmo caso (IP, host, usuário, programa, processo…), com ou sem corte "
            "por dia. É o objeto de estudo."
        ),
        "Caso e atividade",
    ),
    (
        ":material/hub:",
        "Atividade",
        "O que vira vértice do modelo: a técnica, a técnica-pai, a técnica + o programa ou o tipo de evento Sysmon.",
        "Caso e atividade",
    ),
    (
        ":material/filter_alt:",
        "Filtros",
        (
            "A direção do tráfego só existe nos alertas de conexão de rede (EventID 3, campo `Initiated`): as opções "
            "**Só conexões** ficam só com eles, e **Todos os alertas** não filtra nada. Depois saem os casos com menos "
            "atividades distintas que o mínimo; dá também para excluir técnicas, tipos de evento ou hosts."
        ),
        "Filtros",
    ),
    (
        ":material/account_tree:",
        "Modelo (DFG)",
        (
            "No dia escolhido, cada par de atividades seguidas num caso vira uma aresta; INÍCIO e FIM marcam o começo e "
            "o fim de cada caso."
        ),
        "Dia",
    ),
    (
        ":material/functions:",
        "Complexidade",
        (
            "Pelo número de vértices e pela razão vértices/arestas, o modelo é classificado como simples ou complexo "
            "(complexo pediria um agrupamento dos casos)."
        ),
        "Critério de complexidade",
    ),
]

# ABNT NBR 6023:2018
REFERENCIAS = [
    (
        "ALVARENGA, S. C. de; BARBON JUNIOR, S.; MIANI, R. S.; CUKIER, M.; ZARPELÃO, B. B. Process mining and "
        "hierarchical clustering to help intrusion alert visualization. **Computers & Security**, v. 73, p. 474-491, "
        "mar. 2018. DOI: [10.1016/j.cose.2017.11.021](https://doi.org/10.1016/j.cose.2017.11.021)."
    ),
    (
        "PÉREZ-SÁNCHEZ, A.; PALACIOS, R.; LÓPEZ LÓPEZ, G. COMISET: dataset for the analysis of malicious events in "
        "Windows systems. **Data in Brief**, v. 61, art. 111723, ago. 2025. DOI: "
        "[10.1016/j.dib.2025.111723](https://doi.org/10.1016/j.dib.2025.111723)."
    ),
]


def pagina() -> None:
    st.markdown("## Método")
    fluxo, lado = st.columns([3, 2], gap="large")

    with fluxo:
        st.markdown("#### Do alerta ao modelo")
        for i, (icone, titulo, texto, onde) in enumerate(PASSOS, start=1):
            if i > 1:
                st.markdown(":gray[:material/arrow_downward:]", text_alignment="center")
            with st.container(border=True):
                st.markdown(f"**{icone} {i}. {titulo}**")
                st.markdown(texto)
                st.caption(f"Na barra lateral: **{onde}**")

    with lado:
        st.markdown("#### Referência principal")
        st.markdown(
            "O ponto de partida é **Alvarenga et al. (2018)** [1], que usam mineração de processos para visualizar "
            "alertas de IDS. Deles vêm: o caso como ⟨IP de origem, dia⟩, o descarte de casos com uma técnica só, "
            "o algoritmo que monta o DFG, os critérios de escolha do dia e o critério de complexidade. Nos controles, "
            "essas escolhas aparecem marcadas com **(Sean)**, o primeiro autor.\n\n"
            "O que muda aqui:\n"
            "- **Os alertas são eventos do Sysmon**, não de um IDS. Neles, o `src_ip` é a máquina monitorada, e a "
            "direção vem do campo `Initiated`.\n"
            "- **Quase não há tráfego de entrada**: 587 alertas no LAB e 234 no REAL. A escolha literal do artigo "
            "gera 3 casos no LAB e 1 no REAL, todos simples.\n"
            "- Por isso o app abre outras **noções de caso** (host, usuário, programa, processo…) e outras "
            "**atividades**, e generaliza o filtro para um mínimo qualquer de atividades distintas."
        )

        st.markdown("#### Critério de complexidade")
        a, b = (str(x).replace(".", "{,}") for x in (K.LIMIAR_A, K.LIMIAR_B))  # vírgula decimal no LaTeX
        st.markdown(
            f"$$\\text{{simplicidade}} = \\frac{{V}}{{E}}$$\n\n"
            f"$$\\text{{limiar}}(V) = {a}\\,V + {b}$$\n\n"
            f"$$\\text{{complexo}} \\iff V > {K.V_MAX} \\;\\lor\\; "
            f"\\left({K.V_MIN} < V \\le {K.V_MAX} \\;\\land\\; \\tfrac{{V}}{{E}} < \\text{{limiar}}(V)\\right)$$"
        )
        st.markdown(
            "V conta as atividades mais INÍCIO e FIM; E, todas as arestas. Quanto mais arestas por vértice, menor "
            "a simplicidade.\n\n"
            "**De onde vêm os números.** Em [1], os autores geraram 219 modelos com um ano de alertas de IDS da "
            "Universidade de Maryland (2012), e um especialista classificou cada um como complexo ou não. Com os "
            "modelos não complexos, uma regressão linear da simplicidade contra o número de vértices deu a reta do "
            "limiar (eq. 5), usada como a menor simplicidade que um modelo pode ter sem ser complexo. Da mesma base "
            f"saíram os limites de {K.V_MIN} e {K.V_MAX} vértices (eq. 6); o limiar só vale entre eles.\n\n"
            "Como essa base é de alertas de rede, e não da COMISET, os quatro números podem ser mudados na barra "
            "lateral, em **Critério de complexidade**."
        )

    with st.expander("Detalhes técnicos", icon=":material/build:"):
        st.markdown(
            "- **Dados.** O app lê um único arquivo, `comiset/dados/alertas.parquet` (~12 MiB, LAB e REAL juntos), "
            "gerado a partir do que o Notebook 4 extrai do dataset completo (16 GB). O identificador `_id` de cada "
            "evento, um hash que não comprime, fica de fora.\n"
            "- **Ordem dos alertas.** O DFG depende da ordem dentro do caso: timestamp e, nos empates de "
            "milissegundo, a ordem do arquivo.\n"
            "- **Dia.** Os dias são cortados em UTC.\n"
            "- **Cálculo.** Tudo é recalculado na hora, em SQL (DuckDB); cada resultado fica em cache por modelagem.\n"
            "- **Desenho.** O DFG é desenhado no navegador (Graphviz em WebAssembly). Acima de 250 arestas, o "
            "desenho mostra só as mais frequentes; as métricas usam sempre o modelo inteiro."
        )

    st.markdown("#### Referências")
    st.markdown("\n\n".join(f"[{i}] {ref}" for i, ref in enumerate(REFERENCIAS, start=1)))
    st.caption("João Pedro Ramires Esteves · mestrado · [código no GitHub](https://github.com/jpramires/mestrado)")
