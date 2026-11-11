"""Números, datas e rótulos no formato brasileiro."""

from collections.abc import Callable, Collection, Mapping
from datetime import date, timedelta
from typing import Any


def rotulos(mapa: Mapping[Any, Any], marcar: Collection[Any] = ()) -> Callable[[Any], str]:
    """`format_func` dos controles a partir de um dicionário valor -> rótulo; as chaves em `marcar` ganham "(Sean)"."""
    return lambda chave: f"{mapa[chave]} (Sean)" if chave in marcar else str(mapa[chave])


def num(n: float) -> str:
    """1713654 -> "1.713.654"."""
    return f"{int(n):,}".replace(",", ".")


def dec(x: float, casas: int = 2) -> str:
    """0.5556 -> "0,56"."""
    return f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def compacto(n: float) -> str:
    """1.713.654 -> "1,71 M"; 684.904 -> "684,9 mil": cabe num cartão."""
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


def plural(n: int, singular: str, plural_: str) -> str:
    return f"{num(n)} {singular if n == 1 else plural_}"


def duracao(td: object) -> str:
    """timedelta -> "2d 3h", "13h 24min", "5min 02s" ou "40s"; NaT -> ""."""
    if not isinstance(td, timedelta):
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
