"""Alertas: da extração do Notebook 4 ao parquet enxuto que o app lê.

Uso: `uv run python -m sean.dados` regera `sean/dados/alertas.parquet`.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import duckdb

from .constantes import FIX, PADRAO, SYSMON

Conexao = duckdb.DuckDBPyConnection

RAIZ = Path(__file__).resolve().parents[1]
ORIGEM = {c: RAIZ / "saidas" / "sean" / f"alertas_{c}.parquet" for c in ["lab", "real"]}
ARQUIVO_APP = Path(__file__).resolve().parent / "dados" / "alertas.parquet"

# colunas do arquivo do app (sem `_id`, `rule` e `canal`, que pesam e não são usadas)
COLUNAS = [
    "cenario",
    "ordem",
    "ts",
    "event_id",
    "host",
    "usr",
    "proc_guid",
    "proc_name",
    "proc_path",
    "proc_parent_guid",
    "proc_parent_name",
    "tgt_proc_guid",
    "tgt_proc_name",
    "src_ip",
    "dst_ip",
    "dst_port",
    "initiated",
    "technique_id",
    "technique",
    "technique_parent",
    "technique_name",
    "tecnica_valida",
]


def texto_sql(valor: object) -> str:
    """Literal de texto em SQL, com as aspas simples escapadas."""
    return "'" + str(valor).replace("'", "''") + "'"


def sql_caso_quando(
    coluna: str, mapa: Mapping[int, str] | Mapping[str, str], senao: str
) -> str:
    """CASE coluna WHEN chave THEN valor ... ELSE senao END, a partir de um dict."""
    ramos = " ".join(
        f"WHEN {k if isinstance(k, int) else texto_sql(k)} THEN {texto_sql(v)}"
        for k, v in mapa.items()
    )
    return f"CASE {coluna} {ramos} ELSE {senao} END"


def uma_linha(con: Conexao, sql: str) -> tuple[Any, ...]:
    """A única linha de uma consulta de agregação."""
    linha = con.sql(sql).fetchone()
    if linha is None:
        raise RuntimeError(f"consulta sem resultado: {sql}")
    return linha


def sql_higiene(fontes: Mapping[str, Path], com_id: bool = False) -> str:
    """SELECT com LAB e REAL juntos e a higiene da §2 do Notebook 4 aplicada.

    `ordem` é a posição da linha no arquivo de origem: desempata alertas com o mesmo
    timestamp do mesmo jeito que o `sort_values(..., kind="stable")` da §3.
    """
    tecnica = sql_caso_quando("technique_id", FIX, "technique_id")
    extra = "_id, " if com_id else ""
    partes = [
        f"""SELECT '{cenario}' AS cenario, file_row_number AS ordem, {extra}* EXCLUDE (_id, canal, rule)
            FROM read_parquet('{caminho.as_posix()}', file_row_number = true)"""
        for cenario, caminho in fontes.items()
    ]
    return f"""
    SELECT *,
           nullif(regexp_extract(technique, '^(T\\d{{4}})'), '') AS technique_parent,
           coalesce(regexp_matches(technique, '{PADRAO}'), false) AS tecnica_valida
    FROM (
        SELECT * EXCLUDE (technique_id), technique_id, {tecnica} AS technique
        FROM ({" UNION ALL ".join(partes)})
    )
    """


def preparar(destino: Path = ARQUIVO_APP) -> list[tuple[str, int]]:
    """Gera o parquet do app a partir dos alertas extraídos pelo Notebook 4."""
    faltando = [str(p) for p in ORIGEM.values() if not p.exists()]
    if faltando:
        raise FileNotFoundError(f"Rode a §1 do Notebook 4 antes: faltam {faltando}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"""
        COPY (
            SELECT {", ".join(COLUNAS)}
            FROM ({sql_higiene(ORIGEM)})
            ORDER BY cenario, host, ts, ordem
        ) TO '{destino.as_posix()}' (FORMAT PARQUET, CODEC 'ZSTD', COMPRESSION_LEVEL 9)
    """)
    linhas = con.sql(
        f"SELECT cenario, count(*) AS alertas FROM '{destino.as_posix()}' GROUP BY 1 ORDER BY 1"
    ).fetchall()
    return [(str(cenario), int(n)) for cenario, n in linhas]


def conectar(fonte: Path | str = ARQUIVO_APP) -> Conexao:
    """Conexão DuckDB com a view `alertas`.

    `fonte` é o parquet do app ou um SELECT pronto (a paridade usa os arquivos originais, com `_id`).
    """
    con = duckdb.connect()
    if isinstance(fonte, Path):
        if not fonte.exists():
            raise FileNotFoundError(
                f"{fonte} não existe: rode `uv run python -m sean.dados`"
            )
        fonte = f"SELECT * FROM read_parquet('{fonte.as_posix()}')"
    con.execute(f"CREATE VIEW alertas AS {fonte}")
    return con


def nomes_tecnicas(con: Conexao) -> dict[str, str]:
    """sigla -> nome da técnica, tirado dos próprios alertas (como o NOMES do Notebook 4)."""
    linhas = con.sql("""
        SELECT technique, arg_min(technique_name, (cenario, ordem)) AS nome
        FROM alertas
        WHERE technique_name IS NOT NULL
        GROUP BY technique
    """).fetchall()
    return {str(tecnica): str(nome) for tecnica, nome in linhas}


def nome_evento(event_id: int) -> str:
    return SYSMON.get(event_id, f"EID {event_id}")


if __name__ == "__main__":
    for cenario, n in preparar():
        print(f"{cenario:>4}: {n:,} alertas")
    print(
        f"{ARQUIVO_APP.relative_to(RAIZ)}: {ARQUIVO_APP.stat().st_size / 2**20:.1f} MiB"
    )
