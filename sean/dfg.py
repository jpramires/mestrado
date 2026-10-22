"""DFG (Algoritmo 1 do Sean) e critério de complexidade (eq. 2, 5 e 6), em SQL."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import TypedDict

import pandas as pd

from .constantes import TS_A, TS_B, V_MAX, V_MIN
from .dados import Conexao, uma_linha
from .modelagem import Modelagem, ordem_no_caso, sql_log

INICIO, FIM = "INÍCIO", "FIM"

# atividade -> [(programa, nº de alertas), ...], do programa que mais dispara a regra pro que menos
Processos = dict[str, list[tuple[str, int]]]


@dataclass(frozen=True)
class Criterio:
    v_min: int = V_MIN
    v_max: int = V_MAX
    a: float = TS_A
    b: float = TS_B

    def limiar(self, n_vertices: float) -> float:
        """Sean, eq. 5: regressão sobre 219 modelos classificados por um especialista."""
        return self.a * n_vertices + self.b

    def eh_complexo(self, n_vertices: int, n_arestas: int) -> bool:
        if n_vertices <= self.v_min:
            return False
        if n_vertices > self.v_max:
            return True
        # eq. 2: simplicidade = V/E
        return n_vertices / n_arestas < self.limiar(n_vertices)


SEAN = Criterio()  # os valores do artigo


class Metricas(TypedDict):
    casos: int
    vertices: int
    arestas: int
    simplicidade: float
    limiar_ts: float
    complexo: bool


@dataclass
class Modelo:
    vertices: pd.DataFrame  # atividade, n
    arestas: pd.DataFrame  # de, para, n
    casos: int

    @property
    def n_vertices(self) -> int:
        return len(self.vertices) + 2  # + INÍCIO e FIM, como no paper

    @property
    def n_arestas(self) -> int:
        return len(self.arestas)

    @property
    def vazio(self) -> bool:
        return self.vertices.empty

    def metricas(self, criterio: Criterio = SEAN) -> Metricas | None:
        if self.vazio:
            return None
        v, e = self.n_vertices, self.n_arestas
        return Metricas(
            casos=self.casos,
            vertices=v,
            arestas=e,
            simplicidade=v / e,
            limiar_ts=criterio.limiar(v),
            complexo=criterio.eh_complexo(v, e),
        )


def descobrir(
    con: Conexao, m: Modelagem, datas: Sequence[date] | None = None
) -> Modelo:
    """Algoritmo 1 do Sean: frequência de cada atividade e de cada par consecutivo (com INÍCIO e FIM)."""
    log = sql_log(m, datas)
    vertices = con.sql(f"""
        SELECT atividade, count(*) AS n FROM ({log}) GROUP BY atividade ORDER BY n DESC, atividade
    """).df()
    arestas = con.sql(f"""
        WITH passos AS (
            SELECT atividade,
                   lag(atividade, 1, '{INICIO}') OVER janela AS anterior,
                   lead(atividade) OVER janela AS proxima
            FROM ({log})
            WINDOW janela AS (PARTITION BY caso ORDER BY {ordem_no_caso(m)})
        )
        SELECT de, para, count(*) AS n FROM (
            SELECT anterior AS de, atividade AS para FROM passos
            UNION ALL
            SELECT atividade, '{FIM}' FROM passos WHERE proxima IS NULL
        )
        GROUP BY de, para ORDER BY n DESC, de, para
    """).df()
    (n_casos,) = uma_linha(con, f"SELECT count(DISTINCT caso) FROM ({log})")
    return Modelo(vertices, arestas, int(n_casos))


def processos_por_atividade(
    con: Conexao, m: Modelagem, datas: Sequence[date] | None = None
) -> Processos:
    """Os programas que disparam a regra de cada atividade, do que mais dispara pro que menos."""
    linhas = con.sql(f"""
        SELECT atividade, proc_name, count(*) AS n
        FROM ({sql_log(m, datas)})
        WHERE proc_name IS NOT NULL
        GROUP BY ALL ORDER BY atividade, n DESC, proc_name
    """).fetchall()
    processos: Processos = {}
    for atividade, programa, n in linhas:
        processos.setdefault(str(atividade), []).append((str(programa), int(n)))
    return processos
