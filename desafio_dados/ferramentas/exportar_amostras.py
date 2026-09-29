"""Amostras das camadas e registros de execucao para as evidencias (RF34).

    docker compose run --rm beam ferramentas/exportar_amostras.py

Le o banco com o papel dono e grava CSVs pequenos e versionaveis:
  dados/bronze/, dados/silver/amostras/, dados/gold/, dados/quarentena/  amostras da execucao mais recente
  qualidade/resultados/                                                 resultados de todas as execucoes
  hop/evidencias/                                                       execucoes e etapas do workflow
Dados pessoais (ficticios) nao entram nas amostras: da bronze.usuarios saem so colunas nao pessoais. As amostras da
Silver nao trazem usuario_pseudo: junto do usuario_id, ele formaria uma tabela de correspondencia, que nao pode ir
para o repositorio (RF33). O pseudonimo aparece so na Gold, onde nao ha usuario_id.
"""
import csv
import os
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parent.parent
LINHAS = 20

AMOSTRAS = {
    "dados/bronze": {
        "catalogo": "SELECT conteudo_id, titulo, tipo, categoria, nivel, carga_horaria_min, data_publicacao, _execucao_id, _origem, _linha, _ingerido_em FROM bronze.catalogo WHERE _execucao_id = %(ex)s ORDER BY _origem DESC, _linha",
        "usuarios_sem_dados_pessoais": "SELECT usuario_id, uf, data_cadastro, atualizado_em, _execucao_id, _origem, _linha, _ingerido_em FROM bronze.usuarios WHERE _execucao_id = %(ex)s ORDER BY _origem DESC, _linha",
        "interacoes": "SELECT * FROM bronze.interacoes WHERE _execucao_id = %(ex)s ORDER BY _origem DESC, _linha",
        "comentarios": "SELECT usuario_id, conteudo_id, avaliacao, tags, data, _execucao_id, _origem, _linha, _ingerido_em FROM bronze.comentarios WHERE _execucao_id = %(ex)s ORDER BY _origem DESC, _linha",
        "recomendacoes": "SELECT * FROM bronze.recomendacoes WHERE _execucao_id = %(ex)s ORDER BY _linha",
    },
    "dados/silver/amostras": {
        "conteudo": "SELECT * FROM silver.conteudo ORDER BY conteudo_id DESC",
        "usuario": "SELECT usuario_id, nome_mascarado, email_mascarado, email_hash, cpf_hash, faixa_etaria, cidade, uf, "
                   "data_cadastro, atualizado_em, _execucao_id, _origem, _ingerido_em "
                   "FROM silver.usuario ORDER BY usuario_id DESC",
        "usuario_mestre": "SELECT usuario_mestre_id, nome_mascarado, email_mascarado, faixa_etaria, cidade, uf, data_cadastro, "
                          "atualizado_em, registros_origem, _execucao_id "
                          "FROM silver.usuario_mestre ORDER BY registros_origem DESC, usuario_mestre_id",
        "usuario_correspondencia": "SELECT * FROM silver.usuario_correspondencia ORDER BY (regra = 'proprio'), usuario_id",
        "interacao": "SELECT * FROM silver.interacao ORDER BY data_hora DESC",
        "comentario": "SELECT * FROM silver.comentario ORDER BY (comentario ~ '\\[(email|telefone)\\]') DESC, data DESC",
        "recomendacao": "SELECT * FROM silver.recomendacao ORDER BY usuario_id, posicao",
    },
    "dados/gold": {
        "dim_conteudo": "SELECT * FROM gold.dim_conteudo ORDER BY conteudo_id",
        "dim_usuario": "SELECT * FROM gold.dim_usuario ORDER BY registros_origem DESC, usuario_pseudo",
        "fato_interacao": "SELECT * FROM gold.fato_interacao ORDER BY data_hora DESC",
        "fato_recomendacao": "SELECT * FROM gold.fato_recomendacao ORDER BY convertida DESC, usuario_pseudo",
        "kpi_engajamento_mensal": "SELECT * FROM gold.kpi_engajamento_mensal ORDER BY mes, categoria",
        "kpi_usuarios_ativos_mensal": "SELECT * FROM gold.kpi_usuarios_ativos_mensal ORDER BY mes_referencia",
        "kpi_taxa_conclusao": "SELECT * FROM gold.kpi_taxa_conclusao ORDER BY categoria, tipo, nivel",
        "kpi_conversao_recomendacao": "SELECT * FROM gold.kpi_conversao_recomendacao ORDER BY classificacao, categoria",
        "kpi_avaliacao": "SELECT * FROM gold.kpi_avaliacao ORDER BY categoria, tipo",
    },
}
COMPLETOS = {  # sem limite de linhas
    "dados/quarentena/registros": "SELECT quarentena_id, fonte, origem, linha, chave_registro, regra, severidade, mensagem, status, criado_em, corrigido_em, reprocessado_em, execucao_id, ultima_execucao_id, reprocessado_execucao_id FROM quarentena.registro ORDER BY fonte, origem, linha",
    # o que a triagem fez: campo alterado, valor original e valor corrigido; valores de usuarios nao saem (dado pessoal)
    "dados/quarentena/correcoes": """SELECT q.quarentena_id, q.fonte, q.origem, q.linha, q.chave_registro, q.regra, q.status, k.key AS campo_corrigido,
               CASE WHEN q.fonte = 'usuarios' THEN '(dado pessoal omitido)' ELSE q.registro_original ->> k.key END AS valor_original,
               CASE WHEN q.fonte = 'usuarios' THEN '(dado pessoal omitido)' ELSE q.registro ->> k.key END AS valor_corrigido,
               q.criado_em, q.corrigido_em, q.reprocessado_em, q.reprocessado_execucao_id
          FROM quarentena.registro q
          LEFT JOIN LATERAL (SELECT e.key FROM jsonb_each(q.registro) e
                              WHERE q.registro -> e.key IS DISTINCT FROM q.registro_original -> e.key) k ON TRUE
         WHERE q.status <> 'pendente'
         ORDER BY q.status, q.fonte, q.linha""",
    "qualidade/resultados/resultados": "SELECT * FROM qualidade.vw_resultado ORDER BY executado_em, teste_id, fonte",
    "hop/evidencias/execucoes": "SELECT * FROM controle.execucao ORDER BY inicio",
    "hop/evidencias/etapas": "SELECT * FROM controle.etapa ORDER BY inicio",
}
KPIS_COMPLETOS = {"kpi_engajamento_mensal", "kpi_usuarios_ativos_mensal", "kpi_taxa_conclusao",
                  "kpi_conversao_recomendacao", "kpi_avaliacao"}


def gravar(cur, sql, destino: Path, params: dict, limite: int | None) -> int:
    cur.execute(sql + (f" LIMIT {limite}" if limite else ""), params)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([c.name for c in cur.description])
        linhas = cur.fetchall()
        w.writerows(linhas)
    return len(linhas)


def main() -> None:
    with psycopg.connect(host=os.environ.get("POSTGRES_HOST", "postgres"), dbname=os.environ["POSTGRES_DB"],
                         user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"]) as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT _execucao_id FROM silver.conteudo")
        execucao = cur.fetchone()[0]
        for pasta, consultas in AMOSTRAS.items():
            for nome, sql in consultas.items():
                limite = None if nome in KPIS_COMPLETOS else LINHAS
                n = gravar(cur, sql, RAIZ / pasta / f"{nome}.csv", {"ex": execucao}, limite)
                print(f"{pasta}/{nome}.csv: {n} linhas")
        for caminho, sql in COMPLETOS.items():
            n = gravar(cur, sql, RAIZ / f"{caminho}.csv", {}, None)
            print(f"{caminho}.csv: {n} linhas")
    print(f"amostras da execucao {execucao}")


if __name__ == "__main__":
    main()
