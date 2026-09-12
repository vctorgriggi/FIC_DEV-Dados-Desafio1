import logging

log = logging.getLogger("embeddings")


def executar(cfg: dict, pg) -> dict:
    """RF08: gera embeddings (titulo + descricao) e grava em conteudo_embedding."""
    log.warning("nao implementado")
    return {}


def buscar(cfg: dict, pg, consulta: str, top_k: int | None = None) -> list[dict]:
    """RF09: busca semantica por consulta em linguagem natural."""
    raise NotImplementedError
