"""Uma modelagem = universo + caso + atividade + filtro. Tudo vira SQL sobre a view `alertas`."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import Self, TypedDict

import pandas as pd

from .constantes import AGREGACOES, DIRECOES, SYSMON
from .dados import Conexao, sql_caso_quando, texto_sql, uma_linha


@dataclass(frozen=True)
class Modelagem:
    cenario: str = "lab"
    direcao: str = "entrada"
    caso: tuple[str, ...] = ("src_ip",)
    por_dia: bool = True
    atividade: str = "technique"
    min_atividades: int = 2  # filtro do Sean: atividades distintas por caso
    excluir_tecnicas: tuple[str, ...] = ()
    event_ids: tuple[int, ...] = ()  # vazio = todos
    hosts: tuple[str, ...] = ()  # vazio = todos
    desempate: tuple[str, ...] = ("ordem",)  # ordem dentro do caso, depois do ts

    def com_agregacao(self, nome: str) -> Self:
        _, colunas, por_dia = AGREGACOES[nome]
        return replace(self, caso=colunas, por_dia=por_dia)


class Funil(TypedDict):
    """Quantos alertas sobram a cada etapa."""

    alertas: int
    universo: int
    casos_antes: int
    casos: int
    eventos: int
    atividades: int


def _lista(valores: Iterable[str | int]) -> str:
    return ", ".join(
        texto_sql(v) if isinstance(v, str) else str(int(v)) for v in valores
    )


def sql_atividade(atividade: str) -> str:
    return {
        "technique": "technique",
        "technique_parent": "technique_parent",
        "technique_proc": "technique || ', ' || coalesce(proc_name, '?')",
        "event_id": sql_caso_quando("event_id", SYSMON, "'EID ' || event_id"),
    }[atividade]


def sql_universo(m: Modelagem) -> str:
    """Alertas que entram na modelagem, já com `caso` e `atividade`."""
    condicoes = [f"cenario = {texto_sql(m.cenario)}", "tecnica_valida"]
    condicoes += [f"{coluna} IS NOT NULL" for coluna in m.caso]
    valores = DIRECOES[m.direcao][1]
    if valores is not None:
        condicoes.append(f"initiated IN ({_lista(valores)})")
    if m.excluir_tecnicas:
        condicoes.append(f"technique NOT IN ({_lista(m.excluir_tecnicas)})")
    if m.event_ids:
        condicoes.append(f"event_id IN ({_lista(m.event_ids)})")
    if m.hosts:
        condicoes.append(f"host IN ({_lista(m.hosts)})")

    partes = list(m.caso) + (["dia"] if m.por_dia else [])
    # mesmo formato do Notebook 4: "10.10.117.130|18/11/2022"
    caso = " || '|' || ".join(partes)
    return f"""
    SELECT {caso} AS caso, data, dia, ts, {", ".join(m.desempate)},
           {sql_atividade(m.atividade)} AS atividade,
           technique, technique_name, event_id, host, usr, proc_name, proc_guid,
           tgt_proc_name, src_ip, dst_ip, dst_port, initiated
    FROM (SELECT *, CAST(ts AS DATE) AS data, strftime(ts, '%d/%m/%Y') AS dia FROM alertas)
    WHERE {" AND ".join(condicoes)}
    """


def sql_base(m: Modelagem) -> str:
    """O universo, com quantas atividades distintas tem o caso de cada alerta (é o que o filtro do Sean olha)."""
    return f"""
    SELECT *, count(DISTINCT atividade) OVER (PARTITION BY caso) AS atividades_no_caso
    FROM ({sql_universo(m)})
    """


def _passa(m: Modelagem) -> str:
    return f"atividades_no_caso >= {int(m.min_atividades)}"


def sql_log(m: Modelagem, datas: Sequence[date] | None = None) -> str:
    """Event log: o universo depois do filtro do Sean, opcionalmente recortado em alguns dias.

    O filtro olha o caso inteiro; o recorte vem depois (como na §5.3 do Notebook 4).
    """
    condicoes = [_passa(m)]
    if datas:
        condicoes.append("data IN (" + ", ".join(f"DATE '{d}'" for d in datas) + ")")
    return f"SELECT * FROM ({sql_base(m)}) WHERE {' AND '.join(condicoes)}"


def ordem_no_caso(m: Modelagem) -> str:
    return "ts, " + ", ".join(m.desempate)


def funil(con: Conexao, m: Modelagem) -> Funil:
    """Quantos alertas sobram a cada etapa."""
    (total,) = uma_linha(
        con, f"SELECT count(*) FROM alertas WHERE cenario = {texto_sql(m.cenario)}"
    )
    universo, casos_antes, eventos, casos, atividades = uma_linha(
        con,
        f"""
        SELECT count(*), count(DISTINCT caso),
               count(*) FILTER ({_passa(m)}), count(DISTINCT caso) FILTER ({_passa(m)}),
               count(DISTINCT atividade) FILTER ({_passa(m)})
        FROM ({sql_base(m)})
        """,
    )
    return Funil(
        alertas=int(total),
        universo=int(universo),
        casos_antes=int(casos_antes),
        casos=int(casos),
        eventos=int(eventos),
        atividades=int(atividades),
    )


def por_dia(con: Conexao, m: Modelagem) -> pd.DataFrame:
    """Por dia: alertas, casos e técnicas no universo (antes do filtro, como na §3.1) e eventos depois dele."""
    return con.sql(f"""
        SELECT data, count(*) AS alertas, count(DISTINCT caso) AS casos, count(DISTINCT technique) AS tecnicas,
               count(*) FILTER ({_passa(m)}) AS eventos,
               count(DISTINCT caso) FILTER ({_passa(m)}) AS casos_filtrados
        FROM ({sql_base(m)})
        GROUP BY data ORDER BY data
    """).df()


def dias_por_criterio(tabela_dias: pd.DataFrame) -> dict[str, date]:
    """critério -> dia escolhido (o primeiro, em caso de empate)."""
    if tabela_dias.empty:
        return {}
    datas = pd.to_datetime(tabela_dias["data"])

    def dia_com_mais(coluna: str) -> date:
        return pd.Timestamp(
            datas.iloc[int(tabela_dias[coluna].to_numpy().argmax())]
        ).date()

    escolhidos = {
        criterio: dia_com_mais(criterio)
        for criterio in ["tecnicas", "alertas", "casos"]
    }
    if tabela_dias["eventos"].to_numpy().max() > 0:
        escolhidos["eventos"] = dia_com_mais("eventos")
    return escolhidos


def casos(
    con: Conexao,
    m: Modelagem,
    datas: Sequence[date] | None = None,
    max_trechos: int = 12,
) -> pd.DataFrame:
    """Um resumo por caso, com a sequência comprimida (repetições seguidas viram ×N), como a §5.4."""
    ordem = ordem_no_caso(m)
    return con.sql(f"""
        WITH log AS ({sql_log(m, datas)}),
        passos AS (
            SELECT caso, atividade || '  ' || coalesce(proc_name, '?') AS passo,
                   row_number() OVER (PARTITION BY caso ORDER BY {ordem}) AS i
            FROM log
        ),
        mudancas AS (
            SELECT *, CASE WHEN passo = lag(passo) OVER (PARTITION BY caso ORDER BY i) THEN 0 ELSE 1 END AS novo
            FROM passos
        ),
        trechos AS (
            SELECT caso, sum(novo) OVER (PARTITION BY caso ORDER BY i) AS trecho, passo
            FROM mudancas
        ),
        comprimidos AS (
            SELECT caso, trecho, any_value(passo) AS passo, count(*) AS vezes
            FROM trechos GROUP BY caso, trecho
        ),
        sequencias AS (
            SELECT caso,
                   string_agg(passo || CASE WHEN vezes > 1 THEN '  ×' || vezes ELSE '' END, '   →   ' ORDER BY trecho)
                       FILTER (WHERE trecho <= {int(max_trechos)}) AS sequencia,
                   count(*) AS trechos
            FROM comprimidos GROUP BY caso
        ),
        resumo AS (
            SELECT caso, min(ts) AS inicio, max(ts) AS fim, count(*) AS eventos,
                   count(DISTINCT atividade) AS atividades, count(DISTINCT proc_name) AS programas,
                   count(DISTINCT dst_ip) AS destinos
            FROM log GROUP BY caso
        )
        SELECT resumo.*, fim - inicio AS duracao, sequencias.trechos,
               sequencias.sequencia || CASE WHEN sequencias.trechos > {int(max_trechos)}
                   THEN '   …(+' || (sequencias.trechos - {int(max_trechos)}) || ' trechos)' ELSE '' END AS sequencia
        FROM resumo JOIN sequencias USING (caso)
        ORDER BY eventos DESC
    """).df()


def eventos(
    con: Conexao,
    m: Modelagem,
    datas: Sequence[date] | None = None,
    caso: str | None = None,
    limite: int = 5000,
) -> pd.DataFrame:
    """Linhas do event log (de um caso, se dado), na ordem usada pelo DFG."""
    filtro = f"WHERE caso = {texto_sql(caso)}" if caso is not None else ""
    return con.sql(f"""
        SELECT caso, ts, atividade, technique, technique_name, event_id, proc_name, host, usr,
               src_ip, dst_ip, dst_port
        FROM ({sql_log(m, datas)}) {filtro}
        ORDER BY caso, {ordem_no_caso(m)}
        LIMIT {int(limite)}
    """).df()


def exportar_log(
    con: Conexao, m: Modelagem, datas: Sequence[date] | None = None
) -> pd.DataFrame:
    """O event log inteiro (do recorte), pronto para baixar."""
    return con.sql(f"""
        SELECT caso AS "case", ts, dia, atividade AS activity, technique, technique_name,
               event_id, proc_name, host, usr, src_ip, dst_ip, dst_port
        FROM ({sql_log(m, datas)})
        ORDER BY caso, {ordem_no_caso(m)}
    """).df()
