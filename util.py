import time
from contextlib import contextmanager

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
