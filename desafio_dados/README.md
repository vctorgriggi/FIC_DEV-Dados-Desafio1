# Pipeline de Recomendação e Dashboard de Conteúdos Educacionais

FIC_DEV — Programador de Sistemas com IA · Fundamentos de Dados para IA · Desafio Prático 1

> **Desafio Prático 2 em andamento.** A solução do Desafio 1 continua funcionando como está; a base do Desafio 2 (infraestrutura, contratos e dados de teste) está na seção [Desafio 2](#desafio-2--base-de-infraestrutura-contratos-e-dados-de-teste). Enunciado em [`../docs/desafio-2/`](../docs/desafio-2/README.md).

**Equipe**

- Vinycius Yuji Mogami — ingestão, validação, tratamento e PostgreSQL (RF01–RF06)
- Victor Griggi Moreira Regis da Silva — MongoDB, embeddings, busca semântica, recomendação e métricas (RF07–RF12)
- Kevin da Silva Medeiros — dashboard no Superset, modelo de dados e documentação (RF13)

## O que a solução faz

Um único comando (`python -m src.main`, dentro do container `app`) executa o fluxo completo:

| Etapa | RF | O que acontece | Saída |
|---|---|---|---|
| Ingestão | RF02–RF05 | lê `catalogo.csv`, `interacoes.json` e `comentarios.json`; classifica cada registro como válido, inválido, incompleto ou duplicado; padroniza; grava os tratados | `dados/processados/*`, `rejeitados.json`, `resumo_ingestao.json` |
| PostgreSQL | RF06 | carga transacional e idempotente em `categoria`, `usuario`, `conteudo`, `interacao` | tabelas |
| MongoDB | RF07 | comentários e avaliações como documentos, com índices e consultas | coleção `comentarios` |
| Embeddings | RF08 | um vetor por conteúdo (título + descrição) em `pgvector`, sem regerar os existentes | `conteudo_embedding` |
| Busca semântica | RF09 | três consultas de demonstração em linguagem natural | `busca_semantica.json` |
| Recomendação | RF10–RF11 | `Pontuação = ((Ivis + Icur)/2) × 100 × Iconc` para cada usuário; top 10 persistido | `recomendacao`, `recomendacoes.json` |
| Métricas e KPIs | RF12 | views no PostgreSQL para o Superset; histórico de execuções | `vw_*`, `vw_kpi_*`, `execucao_pipeline`, `kpis.json` |
| Registro | RF14 | início/fim, arquivos, contagens, rejeições, falhas e tempo por etapa | `logs/execucao.log` |

## Arquitetura

| Etapa | Tecnologia |
|---|---|
| Fontes | CSV e JSON em `dados/brutos/` |
| Ingestão | Python 3.12 (`ingestao/`) |
| Dados estruturados | PostgreSQL 17 |
| Dados semiestruturados | MongoDB 8.2 |
| Dados vetoriais | pgvector 0.8 (extensão do mesmo PostgreSQL) |
| Embeddings | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensões, CPU |
| Processamento | busca semântica e motor de recomendação (`recomendacao/`) |
| Apresentação | Apache Superset 6.1 conectado ao PostgreSQL |
| Orquestração | Docker Compose — nada é instalado na máquina além do Docker |

Diagrama e modelo de dados: `documentacao/arquitetura.pdf` e `documentacao/modelo_de_dados.pdf`.

## Instalação e execução

Requisito: Docker com Docker Compose v2 (Linux, macOS ou Windows com WSL2).

```bash
cp .env.example .env            # senhas e portas; edite se quiser
docker compose up -d            # sobe PostgreSQL+pgvector, MongoDB e Superset
docker compose run --rm app     # executa o pipeline (python -m src.main)
```

A primeira execução baixa o modelo de embeddings (~470 MB, cacheado em volume) e gera os 1000 vetores (~20–40 s em CPU). Execuções seguintes levam menos de 10 s.

| Serviço | Acesso |
|---|---|
| PostgreSQL | `localhost:5432` (`POSTGRES_HOST_PORT`), banco `desafio`, usuário/senha do `.env` |
| MongoDB | `localhost:27017` (`MONGO_HOST_PORT`), banco `desafio`, usuário/senha do `.env` |
| Superset | http://localhost:8088 (`SUPERSET_HOST_PORT`), `SUPERSET_ADMIN_USER` / `SUPERSET_ADMIN_PASSWORD` |

No Superset, conectar ao banco com a URI `postgresql+psycopg2://desafio:desafio@postgres:5432/desafio` (ajuste usuário/senha conforme o `.env`). As views `vw_*` e `vw_kpi_*` já estão criadas.

## Dashboard no Superset (RF13)

O dashboard **Indicadores da Plataforma** (export e capturas em `dashboard/evidencias/`) abre com as duas perguntas de negócio que ele responde e se divide em duas seções, para separar o que é contexto do que é indicador:

**Visão geral — métricas de volume:** usuários ativos, conteúdos no catálogo, interações válidas e cobertura da recomendação (cartões).

**Indicadores de desempenho — KPIs:**

| Elemento | Fonte | Leitura |
|---|---|---|
| Avaliação média (cartão) | `vw_interacoes` | escala 1–5; responde aos filtros |
| Taxa de conclusão (cartão) | `vw_kpi_taxa_conclusao` | `sum(conclusoes) / sum(consumos)`, ponderada; responde aos filtros |
| Taxa de conclusão por categoria (barras horizontais) | `vw_kpi_taxa_conclusao` | mesma métrica ponderada, com rótulos; ordena da maior para a menor |
| Usuários ativos e retenção por mês (linhas, eixo duplo) | `vw_kpi_retencao_mensal` | usuários ativos (contagem, eixo esquerdo) e retenção (%, eixo direito); agosto é incompleto (dados até 25/08) |
| Top 10 conteúdos mais procurados (tabela) | `vw_conteudos_populares` | visualizações, usuários e avaliação média |
| Filtros de categoria e tipo | `vw_interacoes` | multi-seleção; a série mensal não filtra porque a view é agregada por mês |

Evidências: `01_dashboard_completo.png` (painel inteiro) e `02_dashboard_filtro_seguranca_governanca.png` (filtro aplicado: a categoria com a 2ª melhor avaliação, 4,67, e a pior conclusão, 11,4 %). Importar em outra máquina: *Dashboards → Import*, escolher o zip e informar a senha do PostgreSQL do `.env`. Perguntas de negócio, fórmulas e justificativa de cada gráfico em [`documentacao/kpis.md`](documentacao/kpis.md).

Outros comandos:

```bash
docker compose run --rm app python -m unittest      # testes (validação com registros sujos, fórmula de recomendação)
docker compose exec -T postgres psql -U desafio -d desafio -f - < sql/consultas.sql
docker compose exec -T mongo mongosh -u desafio -p desafio --authenticationDatabase admin desafio < mongodb/consultas.js
docker compose down -v                              # apaga bancos e volumes
```

Se uma porta já estiver em uso na máquina, mude `*_HOST_PORT` no `.env`. Configurações não sensíveis (caminhos, modelo, `top_k`, consultas de demonstração) ficam em `config.yaml`; senhas só no `.env`, que está no `.gitignore`.

## Desafio 2 — base de infraestrutura, contratos e dados de teste

O Desafio 2 evolui esta mesma pasta. Nada do Desafio 1 foi alterado: o schema `public`, os arquivos de `dados/brutos/` e `python -m src.main` seguem iguais e passam a ser **fontes** das camadas novas. A base prepara o terreno para os três integrantes trabalharem em paralelo; os requisitos RF15–RF34 ainda são implementados por cada responsável.

**Contratos entre as etapas** (quem lê e escreve o quê, convenções, códigos de regra, proposta da Gold): [`documentacao/contratos.md`](documentacao/contratos.md). Leitura obrigatória antes de começar.

**Bronze, Silver, workflow e quarentena no Apache Hop** (arquitetura ELT, como executar, como corrigir e reprocessar, roteiro de demonstração do RF23): [`documentacao/pipeline_hop.md`](documentacao/pipeline_hop.md).

### Serviços e perfis

Os serviços novos ficam em perfis do Compose, para cada integrante subir só o que usa:

| Perfil | Serviços | Acesso |
|---|---|---|
| *(nenhum)* | `postgres`, `mongo`, `superset`, `db-init` | como no Desafio 1 |
| `hop` | `hop-web` (designer do Apache Hop no navegador) | http://localhost:8081/ui (`HOP_WEB_HOST_PORT`) |
| `beam` | `spark-master`, `spark-worker`, `beam-job-server`, `beam-worker-pool` | UI do Spark em http://localhost:8090 (`SPARK_UI_HOST_PORT`) |
| `governanca` | `elasticsearch`, `om-migrar`, `openmetadata`, `om-ingestao` (Airflow) | http://localhost:8585 (`admin@open-metadata.org` / `admin`); Airflow em http://localhost:8082 |
| `agendamento` | `hop-agendador`: fluxo completo todo dia às 05:00 UTC (02:00 de Brasília) | `docker compose --profile agendamento up -d` |
| `pipeline` | executores avulsos: `app` (Desafio 1), `hop`, `beam` | `docker compose run --rm <serviço> ...` |

`db-init` roda a cada `up` (e a cada `docker compose run` de um serviço que depende dele) e é idempotente e não destrutivo. Ele cria os bancos do OpenMetadata e do Airflow no mesmo PostgreSQL e aplica [`sql/camadas.sql`](sql/camadas.sql) e [`sql/silver.sql`](sql/silver.sql): schemas das camadas, quarentena, controle, funções `lgpd.*`, regras da Silver e o papel somente leitura `consumo`. Funciona também sobre um volume já criado no Desafio 1.

```bash
cp .env.example .env                               # quem já tem .env: copie as variáveis novas do bloco "Desafio 2"
docker compose up -d                               # base
docker compose --profile hop up -d                 # + Hop Web
docker compose --profile beam up -d                # + cluster Spark para o Beam
docker compose --profile governanca up -d          # + OpenMetadata (a primeira subida migra o banco e demora mais)

docker compose run --rm hop pipelines/verificar_ambiente.hpl           # Hop: conexão, variáveis e schemas
docker compose run --rm hop workflows/principal.hwf                    # fluxo Bronze → Silver com controle e quarentena
docker compose run --rm beam beam/verificar_runtime.py --runner direct # Beam no DirectRunner
docker compose run --rm beam beam/verificar_runtime.py --runner spark  # Beam no cluster Spark (perfil beam)
docker compose run --rm beam -m ferramentas.gerar_dados                # regenera os dados de teste
```

**Memória** (medida em repouso): a base usa ~0,7 GB; o perfil `governanca` ~3,5 GB (OpenMetadata, Elasticsearch e Airflow); o perfil `beam` ~1,3 GB, mais até 2 GB do executor durante um job (`SPARK_WORKER_MEMORY`). Com tudo no ar, reserve pelo menos 10 GB no Docker Desktop; com menos, suba um perfil de cada vez (`docker compose --profile <perfil> stop` libera).

### Versões (RF15)

| Componente | Versão | Imagem |
|---|---|---|
| Apache Hop | 2.19.0 | `apache/hop`, `apache/hop-web` |
| Apache Beam (SDK Python e job server) | 2.77.0 | `apache/beam_python3.12_sdk`, `apache/beam_spark3_job_server` |
| Apache Spark | 3.5.0 (Scala 2.12, Java 11) | `apache/spark:3.5.0-scala2.12-java11-ubuntu` — a mesma versão embutida no job server do Beam 2.77 |
| OpenMetadata (servidor e ingestão) | 2.0.2 | `docker.getcollate.io/openmetadata/server`, `.../ingestion` |
| Elasticsearch | 9.3.0 | versão do compose oficial do OpenMetadata 2.0.2 |
| Apache Superset | 6.1.0 | como no Desafio 1 |
| PostgreSQL + pgvector | 17 + 0.8 | como no Desafio 1 |

Todas as imagens têm build para amd64 e arm64 (Linux, macOS Intel e Apple Silicon, Windows com WSL2).

### Configuração e segredos (RF15)

- **Segredos** só no `.env`: senhas, `LGPD_SALT`, `LGPD_CHAVE_PSEUDONIMO`, papel `consumo`, bancos do OpenMetadata.
- **Parâmetros não sensíveis:** `config.yaml` (seções `fontes_desafio2`, `camadas`, `beam`) para o código Python e [`hop/environments/docker.json`](hop/environments/docker.json) para o Hop.
- **Hop:** não lê variáveis de ambiente do sistema. Por isso [`docker/hop/segredos.sh`](docker/hop/segredos.sh) gera, dentro do container e com permissão 600, um segundo arquivo de ambiente com os valores do `.env`. As conexões usam `${PG_PASSWORD}` etc., sem senha gravada no projeto nem no log.
- **Superset do Desafio 2:** conecta com o papel `consumo` (`postgresql+psycopg2://consumo:<senha>@postgres:5432/desafio`), que só lê `gold`, `qualidade` e `controle`.

### Dados de teste

Gerados por [`ferramentas/gerar_dados.py`](ferramentas/gerar_dados.py), deterministicamente e sem dados pessoais reais (e-mails `.example`, DDD `00`, CPF com dígito verificador inválido):

- `dados/brutos/usuarios.csv` — cadastro fictício dos 150 usuários, nova fonte para a LGPD e para a integridade referencial;
- `dados/brutos/recomendacoes_desafio1.json` — cópia fixa das recomendações entregues no Desafio 1 (`gerado_em` 2026-09-13). Rodar `python -m src.main` regrava `dados/processados/recomendacoes.json` com a data do dia; a Bronze lê a cópia fixa para a conversão de recomendação continuar mensurável;
- `dados/brutos/lote_2/` — segundo lote com 46 anomalias catalogadas em [`ANOMALIAS.md`](dados/brutos/lote_2/ANOMALIAS.md), o oráculo para testar Silver, quarentena, dados mestres e qualidade;
- `dados/brutos/falhas/` — arquivos defeituosos para demonstrar falha de arquivo;
- `dados/volume/` — não versionado; `--volume N` gera N interações para medir Parquet e Beam.

## Estrutura

```
desafio_dados/
├── README.md
├── config.yaml             parâmetros do pipeline
├── .env.example            modelo do .env (senhas e portas)
├── requirements.txt
├── docker-compose.yml      postgres, mongo, superset-init, superset, app
├── docker/                 Dockerfiles do app e do Superset, init do Postgres
├── src/                    main.py (orquestrador), config.py, logger.py, db.py, metricas.py
├── ingestao/               pipeline.py — RF02 a RF06
├── mongodb/                comentarios.py (carga e consultas), consultas.js — RF07
├── recomendacao/           embeddings.py (RF08, RF09), motor.py (RF10, RF11)
├── tests/                  testes unitários
├── sql/                    criar_banco.sql (tabelas, índices, views), consultas.sql
├── dados/brutos/           arquivos originais, nunca alterados
├── dados/processados/      tratados, rejeitados, resumo, busca, recomendações, kpis
├── logs/                   execucao.log
├── dashboard/evidencias/   export e capturas do dashboard
├── documentacao/           ingestao.md, recomendacao.md, kpis.md, uso_da_ia.md, modelo_de_dados.pdf, arquitetura.pdf,
│                           contratos.md (Desafio 2)
│
│   Desafio 2
├── dados/bronze|silver|gold|quarentena/   amostras e Parquet das camadas (as tabelas ficam no PostgreSQL)
├── dados/brutos/usuarios.csv, lote_2/, falhas/, recomendacoes_desafio1.json   fontes novas
├── hop/                    projeto Apache Hop: workflows/ (principal, bronze, silver, agendado...), pipelines/, environments/, metadata/
├── beam/                   pipeline Apache Beam, verificar_runtime.py, evidencias/
├── sql/camadas.sql         schemas e tabelas compartilhadas, controle, quarentena, funções lgpd.*, papel consumo
├── sql/silver.sql          regras de validação da Silver, área de preparo e publicação atômica
├── superset/, openmetadata/, qualidade/, lgpd/   evidências e documentação por requisito
└── ferramentas/            gerar_dados.py
```

O enunciado sugere `ingestao/` e `recomendacao/` na raiz e exige `python -m src.main`; por isso o orquestrador e o código comum ficam em `src/` e os módulos de domínio nas pastas sugeridas.

## Decisões e limitações

Detalhes em `documentacao/`. Resumo do que vale saber antes de avaliar:

- **Campo a campo os dados são limpos; as rejeições vêm de regras cruzadas.** 77 interações e 52 comentários acontecem antes da data de publicação do conteúdo e são marcados inválidos com motivo (3000 lidos, 2871 válidos). As demais regras são demonstradas por testes com registros sujos (`tests/`). Não há fonte de usuários; a tabela `usuario` é derivada das interações e comentários. → `ingestao.md`
- **Recarga reconcilia:** o que deixa de existir ou de ser válido nas fontes é removido dos bancos na execução seguinte (interações, comentários, conteúdos, usuários, embeddings e recomendações órfãos); o que continua válido é preservado por upsert, sem regerar embeddings. → `ingestao.md`
- **Falhas são explícitas:** conexão indisponível ou erro em qualquer etapa interrompe o pipeline com código de saída 1, traceback no log e `status: falha` no resumo, que registra até onde a execução chegou. → RF14
- **MongoDB recebe os comentários** com `categoria`, `titulo` e `tipo` desnormalizados, o que permite agregar por categoria sem join. → `recomendacao.md`
- **Modelo de embeddings multilíngue**, porque o catálogo é em português. → `recomendacao.md`
- **Ivis e Icur usam a proporção por categoria**, não a similaridade vetorial. A vetorial foi testada e descartada: as descrições seguem o mesmo molde e a similaridade ficou entre 0,38 e 0,85, classificando tudo como "positivo". O pgvector é usado na busca semântica e no desempate. → `recomendacao.md`
- **Faixa "Estável"** do enunciado (`40 > Pontuação < 70`) interpretada como `40 < Pontuação < 70`. Negativos são descartados; 30 usuários ficam sem recomendação. → `recomendacao.md`
- **Taxa de conclusão** calculada por par usuário/conteúdo, porque `conclusões ÷ inícios` passava de 100 % nesses dados. **Conversão de recomendações** não é mensurável: todas as interações são anteriores à primeira execução. → `kpis.md`
- Cada execução **substitui** as recomendações anteriores (snapshot único); o histórico de execuções fica em `execucao_pipeline`.

## Uso de Inteligência Artificial

Registro em `documentacao/uso_da_ia.md`.
