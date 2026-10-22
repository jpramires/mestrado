"""Confere se o núcleo reproduz as tabelas salvas pelo Notebook 4.

Uso: `uv run python -m sean.paridade`. Lê os alertas originais (com `_id`), porque a §5 desempata por ele.
"""

import sys
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

import pandas as pd

from .dados import ORIGEM, RAIZ, Conexao, conectar, sql_higiene, uma_linha
from .dfg import Metricas, descobrir
from .modelagem import Modelagem, dias_por_criterio, funil, por_dia, sql_log

TABELAS = RAIZ / "saidas" / "sean"
DIRECAO_NB = {
    "entrada": "entrada",
    "todas": "conexoes",
}  # nome no notebook -> nome no núcleo
CRITERIO_NB = {
    "alertas": "alertas",
    "ips_distintos": "casos",
    "tecnicas_distintas": "tecnicas",
}


def data(texto: str) -> date:
    return datetime.strptime(texto, "%d/%m/%Y").date()


def linhas(tabela: str) -> list[dict[str, Any]]:
    """As linhas de uma tabela salva pelo notebook, como dicionários."""
    registros = pd.read_parquet(TABELAS / f"{tabela}.parquet").to_dict("records")
    return [
        {str(chave): valor for chave, valor in registro.items()}
        for registro in registros
    ]


def metricas_do_dia(con: Conexao, m: Modelagem, dia: date) -> Metricas:
    metricas = descobrir(con, m, [dia]).metricas()
    if metricas is None:
        raise AssertionError(f"modelo vazio em {dia} para {m}")
    return metricas


def comparar(
    rotulo: str, esperado: Mapping[str, object], obtido: Mapping[str, object]
) -> bool:
    divergentes = {
        k: (esperado[k], obtido[k]) for k in esperado if esperado[k] != obtido[k]
    }
    status = "ok " if not divergentes else "DIF"
    print(f"  {status} {rotulo}" + (f"  {divergentes}" if divergentes else ""))
    return not divergentes


def secao_3(con: Conexao) -> bool:
    print("§3 (caso = <IP de origem, dia>, desempate pela ordem do arquivo)")
    ok = True
    for linha in linhas("tabela_dias"):
        m = Modelagem(cenario=linha["cenario"], direcao=DIRECAO_NB[linha["direcao"]])
        dia = dias_por_criterio(por_dia(con, m))[CRITERIO_NB[linha["criterio"]]]
        modelo = descobrir(con, m, [dia])
        obtido = {
            "dia": dia,
            "eventos": int(modelo.vertices["n"].to_numpy().sum())
            if not modelo.vazio
            else 0,
            "casos": modelo.casos,
            "atividades": len(modelo.vertices),
        }
        esperado = {
            "dia": data(linha["dia"]),
            "eventos": linha["eventos"],
            "casos": linha["casos"],
            "atividades": linha["atividades"],
        }
        ok &= comparar(
            f"dias   {linha['cenario']} {linha['direcao']} {linha['criterio']}",
            esperado,
            obtido,
        )
    for linha in linhas("tabela_modelos"):
        m = Modelagem(cenario=linha["cenario"], direcao=DIRECAO_NB[linha["direcao"]])
        metricas = metricas_do_dia(con, m, data(linha["dia"]))
        esperado = {
            "vertices": linha["vertices"],
            "arestas": linha["arestas"],
            "complexo": linha["complexo"],
        }
        obtido = {
            "vertices": metricas["vertices"],
            "arestas": metricas["arestas"],
            "complexo": metricas["complexo"],
        }
        ok &= comparar(
            f"modelo {linha['cenario']} {linha['direcao']} {linha['dia']}",
            esperado,
            obtido,
        )
    return ok


def secao_5(con: Conexao) -> bool:
    print("§5 (8 agregações sobre todos os alertas, desempate pelo _id)")
    ok = True
    complexidade = {
        (linha["cenario"], linha["agregacao"]): linha
        for linha in linhas("tabela_complexidade")
    }
    for linha in linhas("tabela_agregacoes"):
        cenario, nome = linha["cenario"], linha["agregacao"]
        m = Modelagem(
            cenario=cenario, direcao="todos", desempate=("_id",)
        ).com_agregacao(nome)
        f = funil(con, m)
        (mediana,) = uma_linha(
            con,
            f"SELECT coalesce(median(n), 0) FROM (SELECT count(*) n FROM ({sql_log(m)}) GROUP BY caso)",
        )
        esperado = {
            "cobertura_%": linha["cobertura_%"],
            "casos_antes": linha["casos_antes"],
            "casos_depois": linha["casos_depois"],
            "eventos_depois": linha["eventos_depois"],
            "atividades": linha["atividades"],
            "mediana": linha["mediana_eventos_por_caso"],
        }
        obtido = {
            "cobertura_%": round(100 * f["universo"] / f["alertas"], 1),
            "casos_antes": f["casos_antes"],
            "casos_depois": f["casos"],
            "eventos_depois": f["eventos"],
            "atividades": f["atividades"],
            "mediana": float(mediana),
        }
        ok &= comparar(f"log    {cenario} {nome}", esperado, obtido)

        alvo = complexidade[(cenario, nome)]
        dia = dias_por_criterio(por_dia(con, m))["eventos"]
        metricas = metricas_do_dia(con, m, dia)
        esperado = {
            "dia": data(alvo["dia"]),
            "casos": alvo["casos"],
            "vertices": alvo["vertices"],
            "arestas": alvo["arestas"],
            "complexo": alvo["complexo"],
        }
        obtido = {
            "dia": dia,
            "casos": metricas["casos"],
            "vertices": metricas["vertices"],
            "arestas": metricas["arestas"],
            "complexo": metricas["complexo"],
        }
        ok &= comparar(f"modelo {cenario} {nome}", esperado, obtido)
    return ok


if __name__ == "__main__":
    con = conectar(sql_higiene(ORIGEM, com_id=True))
    ok = secao_3(con) & secao_5(con)
    print("\nTudo bate com o Notebook 4." if ok else "\nHá divergências (acima).")
    sys.exit(0 if ok else 1)
