import time
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def cron(nome=""):
    """Cronometra um bloco: with cron("etapa"): ..."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        total = time.perf_counter() - t0
        horas, resto = divmod(total, 3600)
        minutos, segundos = divmod(resto, 60)

        if horas:
            tempo = f"{int(horas)}h {int(minutos)}min {segundos:.1f}s"
        elif minutos:
            tempo = f"{int(minutos)}min {segundos:.1f}s"
        else:
            tempo = f"{segundos:.1f}s"

        print(f"\n[tempo] {nome}: {tempo}\n")


def salvar(df, caminho_sem_extensao):
    """Salva um `df` em parquet e em csv"""
    caminho = Path(caminho_sem_extensao)
    df.to_parquet(caminho.with_suffix(".parquet"))
    # separador ";" e enconding "utf-8-sig" pro Excel em português abrir direto e com acentos certos
    df.to_csv(caminho.with_suffix(".csv"), sep=";", index=False, encoding="utf-8-sig")
