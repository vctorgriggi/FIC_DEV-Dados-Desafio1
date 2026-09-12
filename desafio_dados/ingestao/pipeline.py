import logging

log = logging.getLogger("ingestao")


def executar(cfg: dict, pg) -> dict:
    """RF02-RF06: le fontes, valida, trata, grava processados e carrega no PostgreSQL.
    Retorna o resumo da ingestao no formato exigido pelo RF05."""
    log.warning("nao implementado")
    return {
        "registros_lidos": {"catalogo": 0, "interacoes": 0, "comentarios": 0},
        "validos": 0,
        "invalidos": 0,
        "incompletos": 0,
        "duplicados": 0,
        "corrigidos": 0,
        "carregados": {"postgresql": 0, "mongodb": 0},
    }
