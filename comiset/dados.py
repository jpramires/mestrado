"""Os alertas: do que o Notebook 4 extrai ao parquet enxuto que o app lê.

Uso: `uv run python -m comiset.dados` regera `comiset/dados/alertas.parquet`.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import duckdb

from .constantes import FIX, SYSMON, TECNICA_VALIDA

Conexao = duckdb.DuckDBPyConnection

RAIZ = Path(__file__).resolve().parents[1]
ORIGEM = {c: RAIZ / "saidas" / "sean" / f"alertas_{c}.parquet" for c in ["lab", "real"]}
ARQUIVO_APP = Path(__file__).resolve().parent / "dados" / "alertas.parquet"

# colunas do arquivo do app; ficam de fora `_id` (um hash que não comprime), `rule` e `canal`
COLUNAS = [
    "cenario", "ordem", "ts", "event_id", "host", "usr",
    "proc_guid", "proc_name", "proc_path", "proc_parent_guid", "proc_parent_name",
    "tgt_proc_guid", "tgt_proc_name", "src_ip", "dst_ip", "dst_port", "initiated",
    "technique_id", "technique", "technique_parent", "technique_name", "tecnica_valida",
]  # fmt: skip


def texto_sql(valor: object) -> str:
    """Literal de texto em SQL, com as aspas simples escapadas."""
    return "'" + str(valor).replace("'", "''") + "'"


def sql_caso_quando(coluna: str, mapa: Mapping[Any, str], senao: str) -> str:
    """CASE coluna WHEN chave THEN valor ... ELSE senao END, a partir de um dict."""
    ramos = " ".join(f"WHEN {k if isinstance(k, int) else texto_sql(k)} THEN {texto_sql(v)}" for k, v in mapa.items())
    return f"CASE {coluna} {ramos} ELSE {senao} END"


def uma_linha(con: Conexao, sql: str) -> tuple[Any, ...]:
    """A única linha de uma consulta de agregação."""
    linha = con.sql(sql).fetchone()
    if linha is None:
        raise RuntimeError(f"consulta sem resultado: {sql}")
    return linha


def preparar(destino: Path = ARQUIVO_APP) -> list[tuple[str, int]]:
    """Gera o parquet do app: LAB e REAL juntos, com os IDs de técnica corrigidos.

    `ordem` é a posição do alerta no arquivo de origem e desempata alertas com o mesmo
    timestamp, do mesmo jeito que o `sort_values(..., kind="stable")` da §3 do Notebook 4.
    """
    faltando = [str(p) for p in ORIGEM.values() if not p.exists()]
    if faltando:
        raise FileNotFoundError(f"Rode a §1 do Notebook 4 antes: faltam {faltando}")
    partes = " UNION ALL ".join(
        f"""SELECT '{cenario}' AS cenario, file_row_number AS ordem, *
            FROM read_parquet('{caminho.as_posix()}', file_row_number = true)"""
        for cenario, caminho in ORIGEM.items()
    )
    tecnica = sql_caso_quando("technique_id", FIX, "technique_id")
    destino.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"""
        COPY (
            SELECT {", ".join(COLUNAS)} FROM (
                SELECT *,
                       nullif(regexp_extract(technique, '^(T\\d{{4}})'), '') AS technique_parent,
                       coalesce(regexp_matches(technique, '{TECNICA_VALIDA}'), false) AS tecnica_valida
                FROM (SELECT *, {tecnica} AS technique FROM ({partes}))
            )
            ORDER BY cenario, host, ts, ordem
        ) TO '{destino.as_posix()}' (FORMAT PARQUET, CODEC 'ZSTD', COMPRESSION_LEVEL 9)
    """)
    linhas = con.sql(f"SELECT cenario, count(*) FROM '{destino.as_posix()}' GROUP BY 1 ORDER BY 1").fetchall()
    return [(str(cenario), int(n)) for cenario, n in linhas]


def conectar(arquivo: Path = ARQUIVO_APP) -> Conexao:
    """Conexão DuckDB com a view `alertas` sobre o parquet do app."""
    if not arquivo.exists():
        raise FileNotFoundError(f"{arquivo} não existe: rode `uv run python -m comiset.dados`")
    con = duckdb.connect()
    con.execute(f"CREATE VIEW alertas AS SELECT * FROM read_parquet('{arquivo.as_posix()}')")
    return con


def nomes_tecnicas(con: Conexao) -> dict[str, str]:
    """sigla -> nome da técnica, tirado dos próprios alertas."""
    linhas = con.sql("""
        SELECT technique, arg_min(technique_name, (cenario, ordem))
        FROM alertas WHERE technique_name IS NOT NULL
        GROUP BY technique
    """).fetchall()
    return {str(tecnica): str(nome) for tecnica, nome in linhas}


def nome_evento(event_id: int) -> str:
    return SYSMON.get(event_id, f"EID {event_id}")


if __name__ == "__main__":
    for cenario, n in preparar():
        print(f"{cenario:>4}: {n:,} alertas")
    print(f"{ARQUIVO_APP.relative_to(RAIZ)}: {ARQUIVO_APP.stat().st_size / 2**20:.1f} MiB")
