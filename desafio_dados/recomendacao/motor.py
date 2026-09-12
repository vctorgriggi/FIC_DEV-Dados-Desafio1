import logging

log = logging.getLogger("recomendacao")


def executar(cfg: dict, pg) -> dict:
    """RF10-RF11: Pontuacao = ((Ivis + Icur) / 2) * 100 * Iconc; persiste em recomendacao."""
    log.warning("nao implementado")
    return {}
