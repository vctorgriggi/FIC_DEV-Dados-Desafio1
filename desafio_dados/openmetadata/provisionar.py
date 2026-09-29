"""Governanca no OpenMetadata (RF27, RF28, RF29, RF32): servicos, ingestao, responsaveis, classificacoes,
glossario e linhagem.

    docker compose --profile governanca up -d          # e esperar o OpenMetadata ficar saudavel
    docker compose run --rm beam openmetadata/provisionar.py

Idempotente (createOrUpdate). Pre-requisitos: Gold publicada (workflow principal) e Superset provisionado
(superset/provisionar.py), para a linhagem ir ate o dashboard. Grava o token do ingestion-bot em
OM_BOT_TOKEN no .env: o workflow hop/workflows/metadados.hwf o usa para disparar as ingestoes.

As descricoes das tabelas e colunas vem do proprio banco (sql/catalogo.sql, COMMENT ON).
"""
import base64
import os
import re
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
API = "http://openmetadata:8585/api/v1"
BANCO = "postgres_desafio"
DB = f"{BANCO}.desafio"
PAINEIS = "superset_desafio"
ARQUIVOS = "arquivos_desafio"
HOP = "apache_hop"
GLOSSARIO = "plataforma_conteudos"
SCHEMAS = ["bronze", "silver", "gold", "quarentena", "qualidade", "controle", "restrito"]

TIMES = {
    "estudante1_ingestao": ("Estudante 1 - Ingestão (Kevin)", "Apache Hop, Bronze, Silver, workflow e quarentena."),
    "estudante2_analitico": ("Estudante 2 - Analítico (Vinycius)", "Parquet, Beam, Gold e testes de qualidade."),
    "estudante3_governanca": ("Estudante 3 - Governança e consumo (Victor)",
                              "OpenMetadata, LGPD, SQL Lab, dashboards e storytelling."),
}
DONOS = {"bronze": "estudante1_ingestao", "silver": "estudante1_ingestao", "quarentena": "estudante1_ingestao",
         "controle": "estudante1_ingestao", "gold": "estudante2_analitico", "qualidade": "estudante2_analitico",
         "restrito": "estudante3_governanca"}

CLASSIFICACOES = {
    "LGPD": ("Tratamento de dados pessoais segundo a LGPD (RF32, RF33).", {
        "DadoPessoal": "Identifica ou torna identificável uma pessoa natural (art. 5, I): nome, e-mail, CPF, telefone, nascimento.",
        "IdentificadorIndireto": "Sozinho não identifica, mas combinado com outros dados pode identificar (ex.: cidade, UF, faixa etária, usuario_id).",
        "DadoDeCriancaOuAdolescente": "Permite identificar crianças e adolescentes, que exigem tratamento no melhor interesse (art. 14).",
        "Pseudonimizado": "Substituído por pseudônimo (HMAC com chave secreta); reidentificável só com a tabela de correspondência (art. 13, par. 4).",
        "HashComSalt": "SHA-256 com salt secreto: permite comparar valores sem revelá-los; irreversível.",
        "Mascarado": "Exibição parcial para consumo (ex.: a***@email.example).",
        "Anonimizado": "Texto livre com e-mails e telefones substituidos por marcadores.",
        "TabelaDeCorrespondencia": "Permite reverter a pseudonimizacao; acesso restrito ao controlador.",
    }),
    # "Medalhao", e nao "Camada": a interface em portugues ja chama de "Camada" o Tier nativo do OpenMetadata
    "Medalhao": ("Camada da arquitetura medalhão (Bronze, Silver, Gold) a que o ativo pertence.", {
        "Bronze": "Cópia auditável das fontes, sem transformação.",
        "Silver": "Dados padronizados, validados e deduplicados.",
        "Gold": "Tabelas de consumo orientadas aos KPIs.",
        "Operacional": "Controle de execução, quarentena e qualidade.",
        "Restrita": "Acesso restrito por conter chave de reidentificação.",
    }),
}
# Tier nativo do OpenMetadata (criticidade para o negocio): Tier1 = consumo, Tier2 = base do consumo e chave de
# reidentificacao, Tier3 = operacional e copia bruta
TIER_DO_SCHEMA = {"gold": "Tier.Tier1", "silver": "Tier.Tier2", "restrito": "Tier.Tier2", "bronze": "Tier.Tier3",
                  "quarentena": "Tier.Tier3", "qualidade": "Tier.Tier3", "controle": "Tier.Tier3"}
CAMADA_DO_SCHEMA = {"bronze": "Bronze", "silver": "Silver", "gold": "Gold", "quarentena": "Operacional",
                    "qualidade": "Operacional", "controle": "Operacional", "restrito": "Restrita"}

# tags de coluna (RF28, RF32): tabela -> coluna -> tags
TAGS_COLUNA = {
    "bronze.usuarios": {
        "nome": ["LGPD.DadoPessoal", "PII.Sensitive"], "email": ["LGPD.DadoPessoal", "PII.Sensitive"],
        "cpf": ["LGPD.DadoPessoal", "PII.Sensitive"], "telefone": ["LGPD.DadoPessoal", "PII.Sensitive"],
        "data_nascimento": ["LGPD.DadoPessoal", "LGPD.DadoDeCriancaOuAdolescente", "PII.Sensitive"],
        "cidade": ["LGPD.IdentificadorIndireto", "PII.NonSensitive"], "uf": ["LGPD.IdentificadorIndireto", "PII.NonSensitive"],
        "usuario_id": ["LGPD.IdentificadorIndireto", "PII.NonSensitive"],
        "data_cadastro": ["LGPD.IdentificadorIndireto"], "atualizado_em": ["LGPD.IdentificadorIndireto"],
    },
    "bronze.comentarios": {"comentario": ["LGPD.DadoPessoal", "PII.Sensitive"]},
    "silver.usuario": {
        "usuario_pseudo": ["LGPD.Pseudonimizado"], "nome_mascarado": ["LGPD.Mascarado"],
        "email_mascarado": ["LGPD.Mascarado"], "email_hash": ["LGPD.HashComSalt"], "cpf_hash": ["LGPD.HashComSalt"],
        "faixa_etaria": ["LGPD.IdentificadorIndireto", "LGPD.DadoDeCriancaOuAdolescente"],
        "cidade": ["LGPD.IdentificadorIndireto"], "uf": ["LGPD.IdentificadorIndireto"],
        "usuario_id": ["LGPD.IdentificadorIndireto"],
        "data_cadastro": ["LGPD.IdentificadorIndireto"], "atualizado_em": ["LGPD.IdentificadorIndireto"],
    },
    "silver.usuario_mestre": {"usuario_pseudo": ["LGPD.Pseudonimizado"], "nome_mascarado": ["LGPD.Mascarado"],
                              "email_mascarado": ["LGPD.Mascarado"], "data_cadastro": ["LGPD.IdentificadorIndireto"],
                              "atualizado_em": ["LGPD.IdentificadorIndireto"]},
    "silver.comentario": {"comentario": ["LGPD.Anonimizado"]},
    "quarentena.registro": {"registro": ["LGPD.DadoPessoal"], "registro_original": ["LGPD.DadoPessoal"]},
    "restrito.usuario_pseudonimo": {"usuario_id": ["LGPD.TabelaDeCorrespondencia"],
                                    "usuario_pseudo": ["LGPD.TabelaDeCorrespondencia"]},
    "gold.dim_usuario": {"usuario_pseudo": ["LGPD.Pseudonimizado"], "nome_mascarado": ["LGPD.Mascarado"],
                         "faixa_etaria": ["LGPD.IdentificadorIndireto"],
                         "uf": ["LGPD.IdentificadorIndireto"], "data_cadastro": ["LGPD.IdentificadorIndireto"]},
    "gold.fato_interacao": {"usuario_pseudo": ["LGPD.Pseudonimizado"]},
    "gold.fato_recomendacao": {"usuario_pseudo": ["LGPD.Pseudonimizado"]},
}

# glossario (RF28): termo -> (nome exibido, definicao e regra, dono, colunas associadas)
TERMOS = {
    "usuario_ativo": ("Usuário ativo",
                      "**Definição.** Pessoa (usuário mestre) com pelo menos uma interação válida no período.\n\n"
                      "**Regra de cálculo.** `count(DISTINCT usuario_pseudo)` de `gold.fato_interacao` no mês; ids diferentes "
                      "da mesma pessoa contam uma vez (RF30).\n\n**Onde está.** `gold.kpi_usuarios_ativos_mensal.pessoas_ativas`.",
                      "estudante2_analitico",
                      ["gold.kpi_usuarios_ativos_mensal.pessoas_ativas", "gold.kpi_engajamento_mensal.pessoas_ativas"]),
    "taxa_de_conclusao": ("Taxa de conclusão",
                          "**Definição.** Proporção dos conteúdos iniciados que são terminados.\n\n**Regra de cálculo.** "
                          "100 × pares (pessoa, conteúdo) concluídos ÷ pares com consumo (visualização, início ou conclusão). "
                          "Um par é concluído quando há interação `conclusão` ou `percentual_conclusao` = 100.\n\n"
                          "**Onde está.** `gold.kpi_taxa_conclusao.taxa_conclusao_pct` e o dataset virtual `vd_conclusao_coorte`.",
                          "estudante2_analitico", ["gold.kpi_taxa_conclusao.taxa_conclusao_pct"]),
    "conversao_de_recomendacao": ("Conversão de recomendação",
                                  "**Definição.** Proporção das recomendações seguidas de consumo do conteúdo recomendado.\n\n"
                                  "**Regra de cálculo.** 100 × recomendações em que a pessoa teve visualização, início ou conclusão "
                                  "do conteúdo depois de `gerado_em` ÷ recomendações.\n\n**Onde está.** "
                                  "`gold.kpi_conversao_recomendacao.conversao_pct` e `gold.fato_recomendacao.convertida`.",
                                  "estudante2_analitico",
                                  ["gold.kpi_conversao_recomendacao.conversao_pct", "gold.fato_recomendacao.convertida"]),
    "avaliacao_media": ("Avaliação média",
                        "**Definição.** Nota média atribuída aos conteúdos, na escala de 1 a 5.\n\n**Regra de cálculo.** Média de "
                        "`avaliacao_atribuida` não nula; ao agregar categorias, média ponderada pelo número de avaliações.\n\n"
                        "**Onde está.** `gold.kpi_avaliacao.avaliacao_media`.",
                        "estudante2_analitico", ["gold.kpi_avaliacao.avaliacao_media"]),
    "pessoa": ("Pessoa (usuário mestre)",
               "**Definição.** Indivíduo único por trás de um ou mais cadastros (`usuario_id`).\n\n**Regra de cálculo.** Cadastros com "
               "o mesmo `cpf_hash` ou `email_hash` são a mesma pessoa, inclusive por transitividade; o mestre é o menor id e os "
               "atributos vêm do cadastro atualizado mais recentemente (RF30).\n\n**Onde está.** `silver.usuario_mestre` e "
               "`gold.dim_usuario.usuario_pseudo`.",
               "estudante1_ingestao", ["gold.dim_usuario.usuario_pseudo", "silver.usuario_mestre.usuario_pseudo"]),
}

DESCRICAO_PAINEL = {  # inicio do titulo no Superset -> descricao no catalogo
    "Desafio 2 - Por que": "Storytelling executivo (RF16): em qual categoria agir primeiro para aumentar a conclusão "
                           "de conteúdos. Lê só a Gold, com o papel `consumo`.",
    "Desafio 2 - Exploração": "Exploração (RF18): filtros de período e categoria, filtro cruzado, evolução da qualidade "
                              "(RF31) e pessoas mais engajadas só com nome mascarado e pseudônimo (RF33).",
}

FONTES = {  # arquivo de origem -> tabela bronze
    "dados/brutos/catalogo.csv": "catalogo", "dados/brutos/lote_2/catalogo.csv": "catalogo",
    "dados/brutos/usuarios.csv": "usuarios", "dados/brutos/lote_2/usuarios.csv": "usuarios",
    "dados/brutos/interacoes.json": "interacoes", "dados/brutos/lote_2/interacoes.json": "interacoes",
    "dados/brutos/comentarios.json": "comentarios", "dados/brutos/lote_2/comentarios.json": "comentarios",
    "dados/brutos/recomendacoes_desafio1.json": "recomendacoes",
}
PIPELINES = {  # pipelines do Hop (e etapas SQL orquestradas por ele) -> descricao
    **{f"bronze_{f}": f"hop/pipelines/bronze_{f}.hpl: lê os arquivos de {f}, acrescenta _execucao_id, _origem e _linha e grava em bronze.{f}."
       for f in ("catalogo", "usuarios", "interacoes", "comentarios", "recomendacoes")},
    **{f"silver_{e}": f"hop/pipelines/silver_{e}.hpl: aplica validacao.classificar_{f} (sql/silver.sql), separa aprovados e rejeitados (Filter rows)."
       for e, f in (("conteudo", "catalogo"), ("usuario", "usuarios"), ("interacao", "interacoes"),
                    ("comentario", "comentarios"), ("recomendacao", "recomendacoes"))},
    "silver_publicacao": "silver.publicar() (hop/workflows/silver.hwf): troca a Silver numa transação; dados mestres, pseudônimos e quarentena.",
    "qualidade": "qualidade.executar() (hop/workflows/qualidade.hwf): testes de sql/qualidade.sql; crítico reprovado bloqueia a Gold.",
    "gold": "gold.publicar() (hop/workflows/gold.hwf): reconstrói as tabelas de consumo numa transação.",
}


class OM:
    def __init__(self):
        senha = base64.b64encode(os.environ["OM_ADMIN_PASSWORD"].encode()).decode()
        r = requests.post(f"{API}/users/login", json={"email": os.environ["OM_ADMIN_EMAIL"], "password": senha}, timeout=30)
        r.raise_for_status()
        self.s = requests.Session()
        self.s.headers["Authorization"] = "Bearer " + r.json()["accessToken"]

    def chamar(self, metodo, caminho, ok=(200, 201), **kw):
        r = self.s.request(metodo, f"{API}/{caminho}", timeout=60, **kw)
        if r.status_code not in ok:
            raise SystemExit(f"{metodo} {caminho}: {r.status_code} {r.text[:600]}")
        return r.json() if r.content else {}

    def put(self, caminho, corpo):
        return self.chamar("PUT", caminho, json=corpo)

    def get(self, caminho, **params):
        return self.chamar("GET", caminho, params=params)

    def patch(self, caminho, operacoes):
        if operacoes:
            self.chamar("PATCH", caminho, json=operacoes, headers={"Content-Type": "application/json-patch+json"})


def gravar_token_bot(om: OM) -> None:
    bot = om.get("bots/name/ingestion-bot")
    token = om.get(f"users/auth-mechanism/{bot['botUser']['id']}")["config"]["JWTToken"]
    env = RAIZ / ".env"
    texto = env.read_text(encoding="utf-8")
    linha = f"OM_BOT_TOKEN={token}"
    texto = re.sub(r"^OM_BOT_TOKEN=.*$", linha, texto, flags=re.M) if re.search(r"^OM_BOT_TOKEN=", texto, re.M) \
        else texto.rstrip("\n") + "\n" + linha + "\n"
    env.write_text(texto, encoding="utf-8")
    print("token do ingestion-bot gravado em OM_BOT_TOKEN (.env)")


def ingestao(om: OM, servico: dict, tipo_servico: str, nome: str, config: dict) -> dict:
    pipe = om.put("services/ingestionPipelines", {
        "name": nome, "displayName": nome, "pipelineType": "metadata", "loggerLevel": "INFO",
        "service": {"id": servico["id"], "type": tipo_servico}, "sourceConfig": {"config": config},
        "airflowConfig": {}})
    om.chamar("POST", f"services/ingestionPipelines/deploy/{pipe['id']}")
    disparo_ms = int(time.time() * 1000) - 5000
    # o Airflow registra o DAG recem-publicado no proximo ciclo do dag-processor: tenta disparar ate la
    for _ in range(30):
        r = om.s.post(f"{API}/services/ingestionPipelines/trigger/{pipe['id']}", timeout=60)
        if r.status_code == 200:
            break
        time.sleep(10)
    else:
        raise SystemExit(f"nao foi possivel disparar {nome}: {r.status_code} {r.text[:300]}")
    inicio = time.time()
    while time.time() - inicio < 600:
        time.sleep(10)
        estado = om.get(f"services/ingestionPipelines/name/{pipe['fullyQualifiedName']}", fields="pipelineStatuses")
        status = estado.get("pipelineStatuses") or []
        status = status if isinstance(status, list) else [status]
        recentes = [x for x in status if (x.get("startDate") or x.get("timestamp") or 0) >= disparo_ms]
        situacao = max(recentes, key=lambda x: x.get("startDate") or x.get("timestamp") or 0)["pipelineState"] if recentes else None
        if situacao in ("success", "partialSuccess", "failed"):
            print(f"ingestao {pipe['fullyQualifiedName']}: {situacao} em {round(time.time() - inicio)}s")
            if situacao == "failed":
                raise SystemExit(f"ingestao {nome} falhou; ver os logs no OpenMetadata")
            return pipe
    raise SystemExit(f"ingestao {nome} nao terminou em 10 minutos")


def rotulo(tag: str) -> dict:
    fonte = "Glossary" if tag.startswith(GLOSSARIO + ".") else "Classification"
    return {"tagFQN": tag, "source": fonte, "labelType": "Manual", "state": "Confirmed"}


def marcar_tabela(om: OM, fqn: str, tags_tabela=(), tags_colunas: dict | None = None, dono: dict | None = None):
    t = om.get(f"tables/name/{fqn}", fields="columns,tags,owners")
    ops = []
    atuais = {x["tagFQN"] for x in t.get("tags", [])}
    ops += [{"op": "add", "path": "/tags/-", "value": rotulo(x)} for x in tags_tabela if x not in atuais]
    indice = {c["name"]: i for i, c in enumerate(t["columns"])}
    for coluna, tags in (tags_colunas or {}).items():
        if coluna not in indice:
            raise SystemExit(f"coluna {fqn}.{coluna} nao existe no catalogo")
        i = indice[coluna]
        existentes = {x["tagFQN"] for x in t["columns"][i].get("tags", [])}
        ops += [{"op": "add", "path": f"/columns/{i}/tags/-", "value": rotulo(x)} for x in tags if x not in existentes]
    if dono and dono["id"] not in {o["id"] for o in t.get("owners", [])}:
        ops.append({"op": "add", "path": "/owners", "value": [dono]})
    om.patch(f"tables/{t['id']}", ops)
    return t


def aresta(om: OM, de: dict, para: dict, descricao: str, pipeline: dict | None = None, colunas=None):
    detalhes = {"description": descricao, "source": "Manual"}
    if pipeline:
        detalhes["pipeline"] = {"id": pipeline["id"], "type": "pipeline"}
    if colunas:
        detalhes["columnsLineage"] = colunas
    om.put("lineage", {"edge": {"fromEntity": de, "toEntity": para, "lineageDetails": detalhes}})


def main() -> None:
    om = OM()
    gravar_token_bot(om)

    times = {n: om.put("teams", {"name": n, "displayName": d, "description": desc, "teamType": "Group"})
             for n, (d, desc) in TIMES.items()}
    ref = {n: {"id": t["id"], "type": "team"} for n, t in times.items()}

    # a classificacao antiga "Camada" foi renomeada para "Medalhao"; apagar remove tambem as tags aplicadas
    antiga = om.s.get(f"{API}/classifications/name/Camada", timeout=30)
    if antiga.status_code == 200:
        om.chamar("DELETE", f"classifications/{antiga.json()['id']}", params={"hardDelete": "true", "recursive": "true"})
    for nome, (descricao, tags) in CLASSIFICACOES.items():
        om.put("classifications", {"name": nome, "description": descricao, "mutuallyExclusive": False})
        for tag, desc in tags.items():
            om.put("tags", {"classification": nome, "name": tag, "description": desc})

    # --- servicos e ingestao de metadados tecnicos (RF27)
    banco = om.put("services/databaseServices", {
        "name": BANCO, "serviceType": "Postgres", "description": "PostgreSQL do projeto: camadas do Desafio 2 e banco do Desafio 1.",
        "owners": [ref["estudante3_governanca"]],
        "connection": {"config": {"type": "Postgres", "scheme": "postgresql+psycopg2", "hostPort": "postgres:5432",
                                  "username": os.environ["POSTGRES_USER"], "database": "desafio",
                                  "authType": {"password": os.environ["POSTGRES_PASSWORD"]}}}})
    ingestao(om, banco, "databaseService", f"{BANCO}_metadata", {
        # overrideMetadata: as descricoes vem de sql/catalogo.sql (COMMENT ON); a ingestao sobrescreve a versao do catalogo
        "type": "DatabaseMetadata", "includeViews": True, "includeTags": True, "includeDDL": True, "overrideMetadata": True,
        "markDeletedTables": True, "schemaFilterPattern": {"includes": [f"^{s}$" for s in SCHEMAS]}})

    paineis = om.put("services/dashboardServices", {
        "name": PAINEIS, "serviceType": "Superset", "description": "Superset da camada de consumo (dashboards do Desafio 2).",
        "owners": [ref["estudante3_governanca"]],
        "connection": {"config": {"type": "Superset", "hostPort": "http://superset:8088",
                                  "connection": {"provider": "db", "username": os.environ["SUPERSET_ADMIN_USER"],
                                                 "password": os.environ["SUPERSET_ADMIN_PASSWORD"]}}}})
    ingestao(om, paineis, "dashboardService", f"{PAINEIS}_metadata", {
        "type": "DashboardMetadata", "includeDataModels": True, "markDeletedDashboards": True,
        "dashboardFilterPattern": {"includes": ["^Desafio 2"]},
        "lineageInformation": {"dbServicePrefixes": [BANCO]}})

    # --- responsaveis e classificacao por camada (RF27, RF28, RF32)
    for schema in SCHEMAS:
        s = om.get(f"databaseSchemas/name/{DB}.{schema}", fields="owners")
        if ref[DONOS[schema]]["id"] not in {o["id"] for o in s.get("owners", [])}:
            om.patch(f"databaseSchemas/{s['id']}", [{"op": "add", "path": "/owners", "value": [ref[DONOS[schema]]]}])
        tabelas = om.get("tables", databaseSchema=f"{DB}.{schema}", limit=100)["data"]
        for t in tabelas:
            chave = f"{schema}.{t['name']}"
            marcar_tabela(om, t["fullyQualifiedName"], [f"Medalhao.{CAMADA_DO_SCHEMA[schema]}", TIER_DO_SCHEMA[schema]],
                          TAGS_COLUNA.get(chave), ref[DONOS[schema]])
    bd = om.get(f"databases/name/{DB}", fields="owners")
    ops = [] if bd.get("owners") else [{"op": "add", "path": "/owners", "value": [ref["estudante3_governanca"]]}]
    if not bd.get("description"):
        ops.append({"op": "add", "path": "/description", "value":
                    "Banco `desafio`: camadas Bronze, Silver e Gold do Desafio 2, quarentena, qualidade, controle e o "
                    "schema restrito; o schema public (Desafio 1) é fonte e fica fora do catálogo."})
    om.patch(f"databases/{bd['id']}", ops)

    # --- dashboards e datasets do Superset (vindos da ingestao): responsavel e descricao (RF27)
    for d in om.get("dashboards", service=PAINEIS, fields="owners", limit=50)["data"]:
        ops = [] if d.get("owners") else [{"op": "add", "path": "/owners", "value": [ref["estudante3_governanca"]]}]
        descricao = next((v for k, v in DESCRICAO_PAINEL.items() if d.get("displayName", "").startswith(k)), None)
        if descricao and d.get("description") != descricao:
            ops.append({"op": "add", "path": "/description", "value": descricao})
        om.patch(f"dashboards/{d['id']}", ops)
    for m in om.get("dashboard/datamodels", service=PAINEIS, fields="owners", limit=100)["data"]:
        if not m.get("owners"):
            om.patch(f"dashboard/datamodels/{m['id']}",
                     [{"op": "add", "path": "/owners", "value": [ref["estudante3_governanca"]]}])

    # --- glossario (RF28)
    om.put("glossaries", {"name": GLOSSARIO, "displayName": "Plataforma de conteúdos",
                          "description": "Termos de negócio usados nos KPIs, no dashboard e no storytelling do Desafio 2.",
                          "owners": [ref["estudante3_governanca"]]})
    for nome, (exibido, descricao, dono, colunas) in TERMOS.items():
        om.put("glossaryTerms", {"glossary": GLOSSARIO, "name": nome, "displayName": exibido, "description": descricao,
                                 "owners": [ref[dono]]})
        for coluna in colunas:
            tabela, campo = coluna.rsplit(".", 1)
            marcar_tabela(om, f"{DB}.{tabela}", tags_colunas={campo: [f"{GLOSSARIO}.{nome}"]})

    # --- linhagem (RF29): arquivos -> bronze -> silver -> gold, com as pipelines do Hop como transformacao
    om.put("services/storageServices", {"name": ARQUIVOS, "serviceType": "CustomStorage",
                                        "description": "Arquivos de origem em desafio_dados/dados/brutos/.",
                                        "owners": [ref["estudante1_ingestao"]],
                                        "connection": {"config": {"type": "CustomStorage"}}})
    om.put("services/pipelineServices", {"name": HOP, "serviceType": "CustomPipeline",
                                         "description": "Pipelines e workflows do Apache Hop (hop/) e etapas SQL orquestradas por eles.",
                                         "owners": [ref["estudante1_ingestao"]],
                                         "connection": {"config": {"type": "CustomPipeline"}}})
    pipes = {n: om.put("pipelines", {"name": n, "service": HOP, "description": d, "owners": [
        ref["estudante2_analitico"] if n in ("qualidade", "gold") else ref["estudante1_ingestao"]]})
             for n, d in PIPELINES.items()}

    def tabela(nome):
        return {"id": om.get(f"tables/name/{DB}.{nome}")["id"], "type": "table"}

    for caminho, destino in FONTES.items():
        nome = caminho.removeprefix("dados/brutos/").replace("/", "_")
        c = om.put("containers", {"name": nome, "service": ARQUIVOS, "fullPath": caminho,
                                  "fileFormats": ["csv" if caminho.endswith(".csv") else "json"],
                                  "description": f"Arquivo de origem `{caminho}` (fonte de bronze.{destino})."})
        aresta(om, {"id": c["id"], "type": "container"}, tabela(f"bronze.{destino}"),
               f"Ingestão sem transformação ({caminho}).", pipes[f"bronze_{destino}"])

    for entidade, fonte in (("conteudo", "catalogo"), ("usuario", "usuarios"), ("interacao", "interacoes"),
                            ("comentario", "comentarios"), ("recomendacao", "recomendacoes")):
        aresta(om, tabela(f"bronze.{fonte}"), tabela(f"silver.{entidade}"),
               "Validação, padronização e deduplicação; publicado por silver.publicar().", pipes[f"silver_{entidade}"])
        aresta(om, tabela(f"bronze.{fonte}"), tabela("quarentena.registro"),
               "Registros que violam uma regra de validação.", pipes[f"silver_{entidade}"])
    for destino in ("silver.usuario_mestre", "silver.usuario_correspondencia", "restrito.usuario_pseudonimo"):
        aresta(om, tabela("silver.usuario"), tabela(destino),
               "Dados mestres (mesmo cpf_hash ou email_hash) e pseudônimos.", pipes["silver_publicacao"])
    for origem in ("controle.etapa", "quarentena.registro", "silver.conteudo", "silver.usuario", "silver.interacao",
                   "silver.comentario", "silver.recomendacao"):
        aresta(om, tabela(origem), tabela("qualidade.resultado"), "Testes de qualidade por execução e fonte.",
               pipes["qualidade"])
    for origem, destino in (("silver.conteudo", "gold.dim_conteudo"), ("silver.usuario_mestre", "gold.dim_usuario"),
                            ("silver.interacao", "gold.fato_interacao"), ("silver.usuario_correspondencia", "gold.fato_interacao"),
                            ("silver.usuario_mestre", "gold.fato_interacao"), ("silver.recomendacao", "gold.fato_recomendacao"),
                            ("silver.usuario_correspondencia", "gold.fato_recomendacao"), ("gold.fato_interacao", "gold.fato_recomendacao"),
                            ("gold.fato_interacao", "gold.kpi_engajamento_mensal"), ("gold.dim_conteudo", "gold.kpi_engajamento_mensal"),
                            ("gold.fato_interacao", "gold.kpi_usuarios_ativos_mensal"), ("gold.dim_conteudo", "gold.kpi_taxa_conclusao"),
                            ("gold.fato_recomendacao", "gold.kpi_conversao_recomendacao"), ("gold.dim_conteudo", "gold.kpi_conversao_recomendacao"),
                            ("gold.fato_interacao", "gold.kpi_avaliacao"), ("gold.dim_conteudo", "gold.kpi_avaliacao")):
        aresta(om, tabela(origem), tabela(destino), "Publicado por gold.publicar() numa transação.", pipes["gold"])

    # KPI com linhagem ate a coluna: de onde vem cada valor de taxa_conclusao_pct
    kpi = f"{DB}.gold.kpi_taxa_conclusao"
    aresta(om, tabela("gold.fato_interacao"), tabela("gold.kpi_taxa_conclusao"),
           "Pares (pessoa, conteúdo) com consumo e concluídos; taxa = 100 * concluídos / consumo.", pipes["gold"], [
               {"fromColumns": [f"{DB}.gold.fato_interacao.{c}" for c in ("usuario_pseudo", "conteudo_id", "tipo_interacao")],
                "toColumn": f"{kpi}.pares_consumo", "function": "count(DISTINCT (usuario_pseudo, conteudo_id))"},
               {"fromColumns": [f"{DB}.gold.fato_interacao.{c}" for c in ("tipo_interacao", "percentual_conclusao")],
                "toColumn": f"{kpi}.pares_concluidos", "function": "bool_or(tipo_interacao = 'conclusão' OR percentual_conclusao >= 100)"},
               {"fromColumns": [f"{DB}.gold.fato_interacao.{c}" for c in ("tipo_interacao", "percentual_conclusao")],
                "toColumn": f"{kpi}.taxa_conclusao_pct", "function": "100 * pares_concluidos / pares_consumo"}])
    aresta(om, tabela("gold.dim_conteudo"), tabela("gold.kpi_taxa_conclusao"), "Atributos do conteúdo.", pipes["gold"], [
        {"fromColumns": [f"{DB}.gold.dim_conteudo.{c}"], "toColumn": f"{kpi}.{c}"} for c in ("categoria", "tipo", "nivel")])
    aresta(om, tabela("silver.interacao"), tabela("gold.fato_interacao"), "Interações por pessoa.", pipes["gold"], [
        {"fromColumns": [f"{DB}.silver.interacao.{c}"], "toColumn": f"{DB}.gold.fato_interacao.{c}"}
        for c in ("tipo_interacao", "percentual_conclusao", "conteudo_id")])

    print("governança aplicada: responsáveis, classificações, glossário e linhagem")


if __name__ == "__main__":
    main()
