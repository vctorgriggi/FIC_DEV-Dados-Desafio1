import logging
import time
from contextlib import contextmanager
from pathlib import Path

FORMATO = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def configurar(caminho_log: str) -> logging.Logger:
    Path(caminho_log).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format=FORMATO,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(caminho_log, encoding="utf-8"),
        ],
    )
    return logging.getLogger("pipeline")


@contextmanager
def etapa(log: logging.Logger, nome: str, tempos: dict):
    """Mede e registra a duracao de uma etapa (RF14)."""
    log.info("[%s] inicio", nome)
    t0 = time.perf_counter()
    try:
        yield
    except Exception:
        log.exception("[%s] falhou", nome)
        raise
    finally:
        tempos[nome] = round(time.perf_counter() - t0, 3)
        log.info("[%s] fim em %.3fs", nome, tempos[nome])
