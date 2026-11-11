"""O modelo de processo (DFG) e o critério de complexidade de Alvarenga et al. (2018), em SQL."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import TypedDict

import pandas as pd

from .constantes import LIMIAR_A, LIMIAR_B, V_MAX, V_MIN
from .dados import Conexao, uma_linha
from .modelagem import ORDEM, Modelagem, sql_log

INICIO, FIM = "INÍCIO", "FIM"

# atividade -> [(programa, nº de alertas), ...], do programa que mais dispara a regra pro que menos
Processos = dict[str, list[tuple[str, int]]]


@dataclass(frozen=True)
class Criterio:
    """Critério de complexidade (eq. 2, 5 e 6 do artigo); os valores padrão são os do artigo."""

    v_min: int = V_MIN
    v_max: int = V_MAX
    a: float = LIMIAR_A
    b: float = LIMIAR_B

    def limiar(self, n_vertices: float) -> float:
        """eq. 5: regressão linear da simplicidade sobre os modelos não complexos de uma base de 219."""
        return self.a * n_vertices + self.b

    def eh_complexo(self, n_vertices: int, n_arestas: int) -> bool:
        if n_vertices <= self.v_min:
            return False
        if n_vertices > self.v_max:
            return True
        return n_vertices / n_arestas < self.limiar(n_vertices)  # eq. 2: simplicidade = V/E


CRITERIO_DO_ARTIGO = Criterio()


class Metricas(TypedDict):
    casos: int
    vertices: int
    arestas: int
    simplicidade: float
    limiar: float
    complexo: bool


@dataclass
class Modelo:
    vertices: pd.DataFrame  # atividade, n
    arestas: pd.DataFrame  # de, para, n
    casos: int

    @property
    def vazio(self) -> bool:
        return self.vertices.empty

    def metricas(self, criterio: Criterio = CRITERIO_DO_ARTIGO) -> Metricas | None:
        if self.vazio:
            return None
        v = len(self.vertices) + 2  # + INÍCIO e FIM, como no artigo
        e = len(self.arestas)
        return Metricas(
            casos=self.casos,
            vertices=v,
            arestas=e,
            simplicidade=v / e,
            limiar=criterio.limiar(v),
            complexo=criterio.eh_complexo(v, e),
        )


def descobrir(con: Conexao, m: Modelagem, datas: Sequence[date] | None = None) -> Modelo:
    """DFG: a frequência de cada atividade e de cada par de atividades seguidas (Algoritmo 1 do artigo)."""
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
            WINDOW janela AS (PARTITION BY caso ORDER BY {ORDEM})
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


def processos_por_atividade(con: Conexao, m: Modelagem, datas: Sequence[date] | None = None) -> Processos:
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
