"""RF07: comentarios e avaliacoes no MongoDB."""

import csv
import json
import logging
from pathlib import Path

from pymongo import ASCENDING, UpdateOne
from pymongo.database import Database

log = logging.getLogger("mongodb")

# identifica um comentario; usada no upsert para nao duplicar em re-execucoes
CHAVE = ("usuario_id", "conteudo_id", "data", "comentario")


def colecao(cfg: dict, mongo: Database):
    return mongo[cfg["mongodb"]["colecao_comentarios"]]


def executar(cfg: dict, mongo: Database) -> dict:
    processados = Path(cfg["saida"]["processados"])
    comentarios = json.loads((processados / "comentarios_processados.json").read_text(encoding="utf-8"))
    with (processados / "catalogo_processado.csv").open(encoding="utf-8", newline="") as f:
        catalogo = {int(r["conteudo_id"]): r for r in csv.DictReader(f)}

    # categoria/titulo/tipo desnormalizados: permitem agregar por categoria sem join
    docs = []
    for c in comentarios:
        conteudo = catalogo[c["conteudo_id"]]
        docs.append({**c, "categoria": conteudo["categoria"], "titulo": conteudo["titulo"], "tipo": conteudo["tipo"]})

    col = colecao(cfg, mongo)
    col.create_index([("conteudo_id", ASCENDING)])
    col.create_index([("tags", ASCENDING)])
    col.create_index([("avaliacao", ASCENDING)])
    col.create_index([("categoria", ASCENDING)])
    col.create_index([(k, ASCENDING) for k in CHAVE], unique=True)

    resultado = inserir(col, docs)
    log.info("[RF07] MongoDB %s: inseridos=%d atualizados=%d total=%d",
             col.name, resultado["inseridos"], resultado["atualizados"], col.count_documents({}))
    demonstrar(col)
    return {"carregados": col.count_documents({}), **resultado}


def demonstrar(col) -> None:
    """Exercita as consultas exigidas pelo RF07 e registra os resultados."""
    exemplo = col.find_one({}, {"_id": 0, "conteudo_id": 1, "tags": 1}, sort=[("conteudo_id", 1)])
    if not exemplo:
        return
    log.info("[RF07] comentários do conteúdo %d: %d", exemplo["conteudo_id"], len(por_conteudo(col, exemplo["conteudo_id"])))
    if exemplo["tags"]:
        log.info("[RF07] documentos com a tag %r: %d", exemplo["tags"][0], len(por_tag(col, exemplo["tags"][0])))
    log.info("[RF07] avaliações com nota >= 4: %d", len(por_nota(col, 4)))
    log.info("[RF07] por categoria: %s", {r["categoria"]: r["quantidade"] for r in agregar_por_categoria(col)})


def inserir(col, docs: list[dict]) -> dict:
    if not docs:
        return {"inseridos": 0, "atualizados": 0}
    ops = [UpdateOne({k: d[k] for k in CHAVE}, {"$set": d}, upsert=True) for d in docs]
    r = col.bulk_write(ops, ordered=False)
    return {"inseridos": r.upserted_count, "atualizados": r.modified_count}


def por_conteudo(col, conteudo_id: int) -> list[dict]:
    return list(col.find({"conteudo_id": conteudo_id}, {"_id": 0}).sort("data", -1))


def por_tag(col, tag: str) -> list[dict]:
    return list(col.find({"tags": tag.casefold()}, {"_id": 0}))


def por_nota(col, minima: int, maxima: int = 5) -> list[dict]:
    return list(col.find({"avaliacao": {"$gte": minima, "$lte": maxima}}, {"_id": 0}))


def agregar_por_categoria(col) -> list[dict]:
    return list(col.aggregate([
        {"$group": {"_id": "$categoria", "quantidade": {"$sum": 1}, "media": {"$avg": "$avaliacao"}}},
        {"$project": {"_id": 0, "categoria": "$_id", "quantidade": 1, "media": {"$round": ["$media", 2]}}},
        {"$sort": {"quantidade": -1}},
    ]))
