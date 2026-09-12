"""RF10-RF11: Pontuacao = ((Ivis + Icur) / 2) * 100 * Iconc, persistida em recomendacao."""

import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("recomendacao")

TIPOS_VISUALIZACAO = ("visualização", "início", "conclusão")

# Ivis: proporcao do tempo consumido pelo usuario na categoria do candidato.
# Icur: proporcao das curtidas/avaliacoes >= nota_minima na categoria do candidato.
# Iconc: 0 se o usuario concluiu o conteudo. Sem historico, o indice vale 0.
# afinidade: cosseno (pgvector) entre o candidato e a media do historico; so desempata.
SQL_INDICES = """
WITH tempo AS (
    SELECT c.categoria_id, sum(coalesce(i.tempo_consumido, 0)) AS t
    FROM interacao i JOIN conteudo c USING (conteudo_id)
    WHERE i.usuario_id = %(usuario)s AND i.tipo_interacao = ANY(%(tipos_vis)s)
    GROUP BY c.categoria_id
), aprov AS (
    SELECT c.categoria_id, count(*) AS n
    FROM interacao i JOIN conteudo c USING (conteudo_id)
    WHERE i.usuario_id = %(usuario)s
      AND (i.tipo_interacao = 'curtida' OR i.avaliacao_atribuida >= %(nota)s)
    GROUP BY c.categoria_id
), perfil AS (
    SELECT avg(e.embedding) AS v
    FROM interacao i JOIN conteudo_embedding e USING (conteudo_id)
    WHERE i.usuario_id = %(usuario)s AND e.modelo = %(modelo)s
), concluidos AS (
    SELECT DISTINCT conteudo_id FROM interacao
    WHERE usuario_id = %(usuario)s
      AND (tipo_interacao = 'conclusão' OR percentual_conclusao >= 100)
)
SELECT c.conteudo_id,
       COALESCE(t.t::float / NULLIF((SELECT sum(t) FROM tempo), 0), 0) AS ivis,
       COALESCE(a.n::float / NULLIF((SELECT sum(n) FROM aprov), 0), 0) AS icur,
       (k.conteudo_id IS NULL)::int AS iconc,
       COALESCE(1 - (e.embedding <=> perfil.v), 0) AS afinidade
FROM conteudo c
LEFT JOIN tempo t ON t.categoria_id = c.categoria_id
LEFT JOIN aprov a ON a.categoria_id = c.categoria_id
LEFT JOIN concluidos k ON k.conteudo_id = c.conteudo_id
LEFT JOIN conteudo_embedding e ON e.conteudo_id = c.conteudo_id AND e.modelo = %(modelo)s
CROSS JOIN perfil
"""


def pontuar(ivis: float, icur: float, iconc: int) -> float:
    return round((ivis + icur) / 2 * 100 * iconc, 2)


def classificar(pontuacao: float, iconc: int) -> str:
    """Enunciado: positivo >= 70; estavel entre 40 e 70; negativo <= 40 ou concluido."""
    if iconc == 0 or pontuacao <= 40:
        return "negativo"
    return "positivo" if pontuacao >= 70 else "estavel"


def recomendar_usuario(cfg: dict, pg, usuario_id: int) -> list[dict]:
    """Candidatos ordenados por pontuacao; negativos sao descartados (RF10)."""
    linhas = pg.execute(SQL_INDICES, {
        "usuario": usuario_id,
        "modelo": cfg["embeddings"]["modelo"],
        "tipos_vis": list(TIPOS_VISUALIZACAO),
        "nota": cfg["recomendacao"]["nota_minima_aprovacao"],
    }).fetchall()

    candidatos = []
    for conteudo_id, ivis, icur, iconc, afinidade in linhas:
        pontuacao = pontuar(ivis, icur, iconc)
        classe = classificar(pontuacao, iconc)
        if classe != "negativo":
            candidatos.append({
                "usuario_id": usuario_id, "conteudo_id": conteudo_id,
                "ivis": round(ivis, 4), "icur": round(icur, 4), "iconc": iconc,
                "pontuacao": pontuacao, "classificacao": classe, "afinidade": round(afinidade, 4),
            })
    candidatos.sort(key=lambda r: (-r["pontuacao"], -r["afinidade"], r["conteudo_id"]))
    melhores = candidatos[:cfg["recomendacao"]["top_k"]]
    for posicao, r in enumerate(melhores, start=1):
        r["posicao"] = posicao
    return melhores


def executar(cfg: dict, pg) -> dict:
    usuarios = [u for (u,) in pg.execute("SELECT usuario_id FROM usuario ORDER BY usuario_id")]
    gerado_em = datetime.now().replace(microsecond=0)
    recomendacoes = []
    for usuario_id in usuarios:
        recomendacoes.extend(recomendar_usuario(cfg, pg, usuario_id))

    # cada execucao substitui o conjunto anterior (snapshot unico para o dashboard)
    with pg.transaction():
        pg.execute("DELETE FROM recomendacao")
        pg.cursor().executemany(
            """
            INSERT INTO recomendacao (usuario_id, conteudo_id, pontuacao, posicao, classificacao, gerado_em)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [(r["usuario_id"], r["conteudo_id"], r["pontuacao"], r["posicao"], r["classificacao"], gerado_em)
             for r in recomendacoes],
        )

    for r in recomendacoes:
        r["gerado_em"] = gerado_em.isoformat()
    caminho = Path(cfg["saida"]["processados"]) / "recomendacoes.json"
    caminho.write_text(json.dumps(recomendacoes, ensure_ascii=False, indent=2), encoding="utf-8")

    por_classe = {c: sum(1 for r in recomendacoes if r["classificacao"] == c) for c in ("positivo", "estavel")}
    usuarios_com = len({r["usuario_id"] for r in recomendacoes})
    log.info("[RF10] usuários=%d com recomendação=%d recomendações=%d %s",
             len(usuarios), usuarios_com, len(recomendacoes), por_classe)
    for r in recomendacoes[:3]:
        log.info("[RF10]   usuário=%d pos=%d conteúdo=%d pontuação=%.2f (%s) gerado=%s",
                 r["usuario_id"], r["posicao"], r["conteudo_id"], r["pontuacao"], r["classificacao"], r["gerado_em"])
    log.info("[RF11] %d recomendações persistidas", len(recomendacoes))
    return {
        "usuarios": len(usuarios), "usuarios_com_recomendacao": usuarios_com,
        "recomendacoes": len(recomendacoes), "por_classificacao": por_classe,
        "gerado_em": gerado_em.isoformat(), "arquivo": str(caminho),
    }
