"""RF12: metricas operacionais e KPIs em views do PostgreSQL, consumidas pelo Superset (RF13)."""

import json
import logging
from pathlib import Path

from src.config import RAIZ

log = logging.getLogger("metricas")

DDL = RAIZ / "sql" / "criar_banco.sql"

# nome -> consulta; as definicoes estao em sql/criar_banco.sql e documentacao/kpis.md
METRICAS = {
    "M1_volume": "SELECT * FROM vw_metricas_gerais",
    "M2_uso_mensal": "SELECT mes, sum(interacoes) interacoes, sum(visualizacoes) visualizacoes, "
                     "sum(usuarios_ativos) usuarios_ativos FROM vw_uso_mensal GROUP BY mes ORDER BY mes",
    "M3_conteudos_populares": "SELECT conteudo_id, titulo, categoria, visualizacoes, avaliacao_media "
                              "FROM vw_conteudos_populares ORDER BY visualizacoes DESC, usuarios DESC LIMIT 10",
}
KPIS = {
    "KPI1_taxa_conclusao": "SELECT categoria, sum(consumos) consumos, sum(conclusoes) conclusoes, "
                           "round(100.0 * sum(conclusoes) / sum(consumos), 1) taxa_conclusao_pct "
                           "FROM vw_kpi_taxa_conclusao GROUP BY categoria ORDER BY taxa_conclusao_pct DESC",
    "KPI2_qualidade": "SELECT categoria, sum(avaliacoes) avaliacoes, "
                      "round(sum(avaliacao_media * avaliacoes) / sum(avaliacoes), 2) avaliacao_media "
                      "FROM vw_kpi_qualidade GROUP BY categoria ORDER BY avaliacao_media DESC",
    "KPI3_retencao_mensal": "SELECT * FROM vw_kpi_retencao_mensal ORDER BY mes",
    "KPI4_recomendacao": "SELECT classificacao, sum(recomendacoes) recomendacoes, "
                         "round(avg(pontuacao_media), 1) pontuacao_media "
                         "FROM vw_kpi_recomendacao GROUP BY classificacao ORDER BY classificacao",
}


def consultar(pg, sql: str) -> list[dict]:
    cur = pg.execute(sql)
    colunas = [d.name for d in cur.description]
    return [dict(zip(colunas, linha)) for linha in cur.fetchall()]


def registrar_execucao(pg, resumo: dict) -> None:
    ing = resumo.get("ingestao", {})
    with pg.transaction():
        pg.execute(
            """
            INSERT INTO execucao_pipeline (registros_lidos, validos, invalidos, incompletos, duplicados,
                                           corrigidos, comentarios_mongo, embeddings_gerados, recomendacoes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                sum(ing.get("registros_lidos", {}).values()),
                ing.get("validos", 0), ing.get("invalidos", 0), ing.get("incompletos", 0),
                ing.get("duplicados", 0), ing.get("corrigidos", 0),
                resumo.get("mongodb", {}).get("carregados"),
                resumo.get("embeddings", {}).get("gerados"),
                resumo.get("recomendacao", {}).get("recomendacoes"),
            ),
        )


def executar(cfg: dict, pg, resumo: dict) -> dict:
    # garante que as views existem mesmo em bancos criados antes de mudancas no DDL
    with pg.transaction():
        pg.execute(DDL.read_text(encoding="utf-8"))
    registrar_execucao(pg, resumo)

    saida = {"metricas": {}, "kpis": {}}
    for nome, sql in METRICAS.items():
        saida["metricas"][nome] = consultar(pg, sql)
    for nome, sql in KPIS.items():
        saida["kpis"][nome] = consultar(pg, sql)

    caminho = Path(cfg["saida"]["processados"]) / "kpis.json"
    caminho.write_text(json.dumps(saida, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    log.info("[RF12] M1 volume: %s", saida["metricas"]["M1_volume"][0])
    log.info("[RF12] KPI1 taxa de conclusão: %s",
             {r["categoria"]: float(r["taxa_conclusao_pct"]) for r in saida["kpis"]["KPI1_taxa_conclusao"]})
    log.info("[RF12] KPI2 avaliação média: %s",
             {r["categoria"]: float(r["avaliacao_media"]) for r in saida["kpis"]["KPI2_qualidade"]})
    log.info("[RF12] KPI3 retenção mensal: %s",
             {str(r["mes"])[:7]: (float(r["retencao_pct"]) if r["retencao_pct"] is not None else None)
              for r in saida["kpis"]["KPI3_retencao_mensal"]})
    log.info("[RF12] KPI4 recomendação: %s",
             {r["classificacao"]: int(r["recomendacoes"]) for r in saida["kpis"]["KPI4_recomendacao"]})
    return {"metricas": list(METRICAS), "kpis": list(KPIS), "arquivo": str(caminho)}
