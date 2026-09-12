"""RF08: embeddings dos conteudos em pgvector. RF09: busca semantica."""

import json
import logging
from pathlib import Path

log = logging.getLogger("embeddings")

_modelos = {}


def carregar_modelo(nome: str):
    if nome not in _modelos:
        from sentence_transformers import SentenceTransformer  # import tardio: pesado
        _modelos[nome] = SentenceTransformer(nome)
    return _modelos[nome]


def texto_conteudo(titulo: str, descricao: str | None) -> str:
    """Representacao textual: titulo e descricao em uma unica string."""
    return f"{titulo}. {descricao}" if descricao else titulo


def codificar(modelo, textos: list[str], lote: int):
    # vetores normalizados: distancia de cosseno no pgvector = 1 - produto interno
    return modelo.encode(textos, batch_size=lote, normalize_embeddings=True, show_progress_bar=False)


def executar(cfg: dict, pg) -> dict:
    nome = cfg["embeddings"]["modelo"]
    lote = cfg["embeddings"]["lote"]

    # apenas conteudos sem embedding do modelo atual (evita geracao duplicada)
    pendentes = pg.execute(
        """
        SELECT c.conteudo_id, c.titulo, c.descricao
        FROM conteudo c
        LEFT JOIN conteudo_embedding e ON e.conteudo_id = c.conteudo_id AND e.modelo = %s
        WHERE e.conteudo_id IS NULL
        ORDER BY c.conteudo_id
        """,
        (nome,),
    ).fetchall()
    existentes = pg.execute("SELECT count(*) FROM conteudo_embedding WHERE modelo = %s", (nome,)).fetchone()[0]
    log.info("[RF08] modelo=%s existentes=%d pendentes=%d", nome, existentes, len(pendentes))

    gerados = falhas = 0
    if pendentes:
        modelo = carregar_modelo(nome)
        dimensao = modelo.get_sentence_embedding_dimension()
        if dimensao != cfg["embeddings"]["dimensao"]:
            raise ValueError(f"modelo gera {dimensao} dimensoes; config e DDL esperam {cfg['embeddings']['dimensao']}")

        with pg.transaction():
            for i in range(0, len(pendentes), lote):
                bloco = pendentes[i:i + lote]
                try:
                    vetores = codificar(modelo, [texto_conteudo(t, d) for _, t, d in bloco], lote)
                except Exception:
                    falhas += len(bloco)
                    log.exception("[RF08] falha ao gerar embeddings do bloco %d-%d", bloco[0][0], bloco[-1][0])
                    continue
                pg.cursor().executemany(
                    """
                    INSERT INTO conteudo_embedding (conteudo_id, modelo, embedding)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (conteudo_id) DO UPDATE
                        SET modelo = EXCLUDED.modelo, embedding = EXCLUDED.embedding, gerado_em = now()
                    """,
                    [(cid, nome, vec) for (cid, _, _), vec in zip(bloco, vetores)],
                )
                gerados += len(bloco)

    log.info("[RF08] gerados=%d falhas=%d", gerados, falhas)
    return {"modelo": nome, "existentes": existentes, "gerados": gerados, "falhas": falhas}


def buscar(cfg: dict, pg, consulta: str, top_k: int | None = None) -> list[dict]:
    """Conteudos semanticamente mais proximos da consulta (similaridade de cosseno)."""
    nome = cfg["embeddings"]["modelo"]
    top_k = top_k or cfg["busca"]["top_k"]
    vetor = codificar(carregar_modelo(nome), [consulta], 1)[0]
    linhas = pg.execute(
        """
        SELECT c.conteudo_id, c.titulo, cat.nome, c.tipo, 1 - (e.embedding <=> %s) AS similaridade
        FROM conteudo_embedding e
        JOIN conteudo c ON c.conteudo_id = e.conteudo_id
        JOIN categoria cat ON cat.categoria_id = c.categoria_id
        WHERE e.modelo = %s
        ORDER BY e.embedding <=> %s
        LIMIT %s
        """,
        (vetor, nome, vetor, top_k),
    ).fetchall()
    return [
        {"posicao": i, "conteudo_id": cid, "titulo": t, "categoria": cat, "tipo": tipo, "similaridade": round(sim, 4)}
        for i, (cid, t, cat, tipo, sim) in enumerate(linhas, start=1)
    ]


def demonstrar(cfg: dict, pg) -> dict:
    """RF09: executa as consultas de demonstracao do config; log + busca_semantica.json."""
    saida = []
    for consulta in cfg["busca"]["demonstracao"]:
        resultados = buscar(cfg, pg, consulta)
        log.info("[RF09] %r", consulta)
        for r in resultados:
            log.info("[RF09]   %d. (%d) %s | %s | %s | sim=%.4f",
                     r["posicao"], r["conteudo_id"], r["titulo"], r["categoria"], r["tipo"], r["similaridade"])
        saida.append({"consulta": consulta, "resultados": resultados})
    caminho = Path(cfg["saida"]["processados"]) / "busca_semantica.json"
    caminho.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"consultas": len(saida), "top_k": cfg["busca"]["top_k"], "arquivo": str(caminho)}
