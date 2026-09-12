import json
import sys
import time
from datetime import datetime
from pathlib import Path

from ingestao import pipeline as ingestao
from mongodb import comentarios
from recomendacao import embeddings, motor as recomendacao
from src import config, db, logger, metricas


def main() -> int:
    cfg = config.carregar()
    log = logger.configurar(cfg["saida"]["log"])
    log.info("Início do processamento")
    inicio = time.perf_counter()
    tempos: dict[str, float] = {}
    resumo: dict = {"inicio": datetime.now().isoformat(timespec="seconds")}

    try:
        with logger.etapa(log, "conexoes", tempos):
            pg = db.conectar_postgres(cfg)
            mongo = db.conectar_mongo(cfg)
    except Exception as e:
        log.error("falha de conexão: %s", e)
        return 1

    try:
        with logger.etapa(log, "ingestao", tempos):
            resumo["ingestao"] = ingestao.executar(cfg, pg)
        with logger.etapa(log, "mongodb", tempos):
            resumo["mongodb"] = comentarios.executar(cfg, mongo)
        with logger.etapa(log, "embeddings", tempos):
            resumo["embeddings"] = embeddings.executar(cfg, pg)
        with logger.etapa(log, "recomendacao", tempos):
            resumo["recomendacao"] = recomendacao.executar(cfg, pg)
        with logger.etapa(log, "metricas", tempos):
            resumo["metricas"] = metricas.executar(cfg, pg)
    except Exception:
        return 1
    finally:
        pg.close()
        resumo["tempos_etapas_s"] = tempos
        resumo["tempo_total_s"] = round(time.perf_counter() - inicio, 3)
        resumo["fim"] = datetime.now().isoformat(timespec="seconds")
        caminho = Path(cfg["saida"]["resumo"])
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("resumo gravado em %s", caminho)
        log.info("Término do processamento em %.3fs", resumo["tempo_total_s"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
