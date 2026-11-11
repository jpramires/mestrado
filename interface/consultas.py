"""As consultas do núcleo (`comiset/`), com cache: cada resultado é calculado uma vez por modelagem.

Todas recebem `datas`: `None` = todos os dias; uma tupla = só esses dias.
"""

import io
from datetime import date

import pandas as pd
import streamlit as st

from comiset import constantes as K
from comiset.dados import Conexao, conectar, nomes_tecnicas
from comiset.dfg import Criterio, Modelo, Processos, descobrir, processos_por_atividade
from comiset.modelagem import Funil, Modelagem, casos, dias_por_criterio, eventos, exportar_log, funil, por_dia

from .formato import data_br

Dias = tuple[date, ...] | None


@st.cache_resource
def _conexao() -> Conexao:
    return conectar()


def _cursor() -> Conexao:
    return _conexao().cursor()  # um cursor por consulta: a conexão é compartilhada entre as sessões


@st.cache_data(show_spinner=False)
def nomes() -> dict[str, str]:
    with _cursor() as con:
        return nomes_tecnicas(con)


@st.cache_data(show_spinner=False)
def opcoes(coluna: str, cenarios: tuple[str, ...]) -> list[object]:
    """Valores distintos de uma coluna nos cenários escolhidos (para os filtros)."""
    with _cursor() as con:
        lista = ", ".join(f"'{c}'" for c in cenarios)
        linhas = con.sql(f"""
            SELECT DISTINCT {coluna} FROM alertas
            WHERE tecnica_valida AND {coluna} IS NOT NULL AND cenario IN ({lista})
            ORDER BY 1
        """).fetchall()
        return [valor for (valor,) in linhas]


@st.cache_data(show_spinner=False, max_entries=256)
def funil_de(m: Modelagem) -> Funil:
    with _cursor() as con:
        return funil(con, m)


@st.cache_data(show_spinner=False, max_entries=256)
def por_dia_de(m: Modelagem) -> pd.DataFrame:
    with _cursor() as con:
        return por_dia(con, m)


@st.cache_data(show_spinner=False, max_entries=256)
def modelo_de(m: Modelagem, datas: Dias) -> Modelo:
    with _cursor() as con:
        return descobrir(con, m, datas)


@st.cache_data(show_spinner=False, max_entries=256)
def processos_de(m: Modelagem, datas: Dias) -> Processos:
    with _cursor() as con:
        return processos_por_atividade(con, m, datas)


@st.cache_data(show_spinner=False, max_entries=64)
def casos_de(m: Modelagem, datas: Dias) -> pd.DataFrame:
    with _cursor() as con:
        return casos(con, m, datas)


@st.cache_data(show_spinner=False, max_entries=64)
def eventos_de(m: Modelagem, datas: Dias, caso: str) -> pd.DataFrame:
    with _cursor() as con:
        return eventos(con, m, datas, caso)


@st.cache_data(show_spinner=False, max_entries=8)
def arquivo_do_log(m: Modelagem, datas: Dias, formato: str) -> bytes:
    """O event log em CSV (no formato do `util.salvar`, que abre direto no Excel) ou em Parquet."""
    with _cursor() as con:
        log = exportar_log(con, m, datas)
    buffer = io.BytesIO()
    if formato == "csv":
        log.to_csv(buffer, sep=";", index=False, encoding="utf-8-sig")
    else:
        log.to_parquet(buffer, index=False)
    return buffer.getvalue()


@st.cache_data(show_spinner=False, max_entries=32)
def comparacao(m: Modelagem, so_dia_com_mais_eventos: bool, criterio: Criterio) -> pd.DataFrame:
    """As noções de caso prontas lado a lado, com o resto da modelagem igual."""
    linhas: list[dict[str, object]] = []
    for nome, (rotulo, _, _) in K.AGREGACOES.items():
        mm = m.com_agregacao(nome)
        dia = dias_por_criterio(por_dia_de(mm)).get("eventos")
        if dia is None:
            continue
        metricas = modelo_de(mm, (dia,) if so_dia_com_mais_eventos else None).metricas(criterio)
        if metricas is None:
            continue
        f = funil_de(mm)
        linhas.append(
            {
                "cenario": K.CENARIOS[m.cenario],
                "agregacao": nome,
                "rotulo": rotulo,
                "cobertura": f["universo"] / f["alertas"],
                "casos_depois": f["casos"],
                "eventos": f["eventos"],
                "dia": data_br(dia) if so_dia_com_mais_eventos else "todos",
                **metricas,
            }
        )
    return pd.DataFrame(linhas)
