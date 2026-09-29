# Pipeline de Recomendação e Dashboard de Conteúdos Educacionais

FIC_DEV — Programador de Sistemas com IA · Fundamentos de Dados para IA · Desafios Práticos 1 e 2

> **Desafio Prático 2.** A solução do Desafio 1 continua funcionando como está. O Desafio 2 (camadas Bronze, Silver e Gold no Apache Hop, Parquet e Apache Beam, qualidade, OpenMetadata, LGPD e storytelling) está na seção [Desafio 2](#desafio-2--plataforma-de-dados-em-camadas). Enunciado em [`../docs/desafio-2/`](../docs/desafio-2/README.md) (no repositório, fora desta pasta).

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

Diagrama e modelo de dados: `documentacao/arquitetura_desafio1.pdf` e `documentacao/modelo_de_dados.pdf`. A arquitetura do Desafio 2 está em `documentacao/arquitetura.pdf`.

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

## Desafio 2 — plataforma de dados em camadas

O Desafio 2 evolui esta mesma pasta. Nada do Desafio 1 foi alterado: o schema `public`, os arquivos de `dados/brutos/` e `python -m src.main` seguem iguais e passam a ser **fontes** das camadas novas.

**Visão geral e decisão ELT/híbrida (RF19):** [`documentacao/arquitetura.md`](documentacao/arquitetura.md), também em PDF (`arquitetura.pdf`).

| Integrante | Parte no Desafio 2 |
|---|---|
| Kevin da Silva Medeiros (Estudante 1) | Apache Hop: Bronze, Silver, workflow, quarentena (RF20–RF23), aplicação dos dados mestres (RF30) |
| Vinycius Yuji Mogami (Estudante 2) | Parquet, Apache Beam, Gold e qualidade (RF24–RF26, RF31) |
| Victor Griggi Moreira Regis da Silva (Estudante 3) | OpenMetadata, LGPD, SQL Lab, Superset e storytelling (RF16–RF18, RF27–RF29, RF32, RF33) |

### Requisitos e onde estão

| RF | O que foi feito | Documento | Evidência |
|---|---|---|---|
| RF15 | configuração fora do código, segredos só no `.env`, etapas isoladas, versões registradas | [`arquitetura.md`](documentacao/arquitetura.md) | `.env.example`, `config.yaml`, `hop/environments/` |
| RF16 | storytelling: pergunta, contexto → evidência → descoberta → ação, fato × hipótese × recomendação | [`storytelling.md`](documentacao/storytelling.md) (+ PDF) | `superset/exportacao_e_evidencias/01_storytelling.png` |
| RF17 | 4 consultas no SQL Lab, salvas e como datasets virtuais | [`storytelling.md`](documentacao/storytelling.md), [`sql/sql_lab.sql`](sql/sql_lab.sql) | `06_sql_lab_consultas_salvas.png`, `consultas_sql_lab.zip` |
| RF18 | filtros de período e categoria, filtro cruzado, alerta com e-mail entregue | [`storytelling.md`](documentacao/storytelling.md) | capturas 02–08, `alerta_execucao.json`, `alerta_email.html` |
| RF19 | ELT no fluxo principal, híbrido com o ramo Beam; justificativa e limites do Desafio 1 | [`arquitetura.md`](documentacao/arquitetura.md) (+ PDF) | — |
| RF20–RF23 | Bronze, Silver (com regras de valores ausentes), workflow com execução manual, isolada e agendada, quarentena, correção e reprocessamento, falhas de arquivo, estrutura, regra e conexão | [`pipeline_hop.md`](documentacao/pipeline_hop.md), [`contratos.md`](documentacao/contratos.md) | `hop/` exportado, `hop/evidencias/` (inclusive `ambiente_limpo/`, com os logs de cada falha e do agendamento), `dados/bronze/`, `dados/silver/amostras/`, `dados/quarentena/` (registros e correções) |
| RF24 | Silver em Parquet particionado por mês; comparação com CSV e JSON | [`parquet_beam.md`](documentacao/parquet_beam.md) | `dados/silver/`, `beam/evidencias/rf24_medicoes.json` |
| RF25 | pipeline Beam no DirectRunner e no Spark, mesmo resultado, conferido com a Gold | [`parquet_beam.md`](documentacao/parquet_beam.md) | `beam/evidencias/rf25_*.json`, `spark_master_aplicacoes.png`, `dados/gold/engajamento_mensal_beam/` |
| RF26 | Gold: 2 dimensões, 2 fatos, 5 KPIs; o dashboard só lê a Gold | [`camada_gold.md`](documentacao/camada_gold.md), [`sql/camada_gold.sql`](sql/camada_gold.sql) | `dados/gold/` |
| RF27, RF28 | OpenMetadata com PostgreSQL e Superset ingeridos, donos, descrições, glossário com 5 termos, classificações LGPD, Medalhão e Tier | [`governanca.md`](documentacao/governanca.md) | `openmetadata/evidencias/01–04, 07–09, 11` |
| RF29 | linhagem arquivo → Bronze → Silver → Gold → dataset → dashboard, com um KPI até a coluna | [`linhagem.md`](documentacao/linhagem.md) (+ PDF) | `openmetadata/evidencias/05, 06, 10, 12` (ponta a ponta), `13` (por coluna) |
| RF30 | pessoa mestre por CPF ou e-mail (hash), sobrevivência, dois conflitos demonstrados | [`governanca.md`](documentacao/governanca.md) | `dados/silver/amostras/usuario_mestre.csv`, `usuario_correspondencia.csv` |
| RF31 | 8 testes nas 5 dimensões; resultado por execução e fonte ou arquivo; evolução de duas métricas; bloqueio da Gold demonstrado duas vezes | [`qualidade/regras.md`](qualidade/regras.md) | `qualidade/resultados/resultados.csv`, captura 02 (evolução do Q01 e do Q02) |
| RF32, RF33 | inventário, mascaramento, pseudonimização, hash com salt, papel `consumo` | [`lgpd/`](lgpd/) | `lgpd/demonstracao_resultado.txt` |
| RF34 | evidências de todos os itens acima | esta tabela | — |

### Execução completa

```bash
cp .env.example .env                    # quem já tem .env: copie as variáveis novas do bloco "Desafio 2"
                                        # preencha LGPD_SALT e LGPD_CHAVE_PSEUDONIMO (valores combinados em privado)
                                        # e gere OM_FERNET_KEY (comando no .env.example) antes de subir a governança
docker compose up -d                                          # base: PostgreSQL, MongoDB, Superset, db-init
docker compose --profile governanca up -d                     # OpenMetadata (a primeira subida migra o banco e demora)
docker compose run --rm beam openmetadata/provisionar.py      # serviços, ingestões, donos, tags, glossário, linhagem

docker compose run --rm hop workflows/principal.hwf           # Bronze → Silver → qualidade → Gold → metadados
docker compose run --rm beam beam/exportar_silver.py --volume # RF24 (o volume vem de ferramentas.gerar_dados --volume 200000)
docker compose run --rm beam beam/pipeline.py --runner direct # RF25
docker compose --profile beam up -d                           # cluster Spark
docker compose run --rm beam beam/pipeline.py --runner spark

docker compose run --rm beam superset/provisionar.py          # datasets, consultas, dashboards e alerta
docker compose --profile alertas up -d                        # Celery + Mailpit para o alerta
docker compose run --rm beam superset/provisionar.py --demonstrar-alerta

docker compose run --rm beam ferramentas/exportar_amostras.py                 # amostras das camadas e registros
docker compose run --rm evidencias ferramentas/evidencias.py superset         # capturas (também: alerta, openmetadata)
docker compose run --rm evidencias ferramentas/gerar_pdfs.py                  # PDFs da documentação
docker compose exec -T postgres sh -c 'stdbuf -o0 psql -U desafio -d desafio 2>&1' < lgpd/demonstracao.sql > lgpd/demonstracao_resultado.txt
```

Os testes rodam com `docker compose run --rm app python -m unittest` (Desafio 1) e `docker compose run --rm beam -m unittest tests.test_beam tests.test_gerar_dados`.

**Demonstrações** com o passo a passo:

- falhas de arquivo, estrutura, regra e conexão, execução agendada, correção e reprocessamento (RF22, RF23), todas num ambiente limpo: [`pipeline_hop.md`](documentacao/pipeline_hop.md#roteiro-de-demonstração-do-rf23);
- bloqueio da Gold por teste crítico (RF31): [`qualidade/regras.md`](qualidade/regras.md#demonstração-do-bloqueio-da-gold-execução-d) e [por arquivo com estrutura errada](qualidade/regras.md#segunda-demonstração-arquivo-com-a-estrutura-errada-ambiente-limpo);
- origem de um valor do dashboard (RF29): [`linhagem.md`](documentacao/linhagem.md#como-localizar-a-origem-de-um-valor-do-dashboard);
- dois cadastros conflitantes (RF30): [`governanca.md`](documentacao/governanca.md#demonstração-dois-pares-conflitantes);
- técnicas de proteção (RF33): [`lgpd/demonstracao_resultado.txt`](lgpd/demonstracao_resultado.txt).

**Números da execução de referência** (`943c1278`, 29/09/2026), a mesma em todas as evidências do banco principal:

- 4804 registros na Silver e 154 pendentes na quarentena;
- 173 cadastros em 171 pessoas;
- 8 testes, com 27 resultados (por fonte ou arquivo), todos aprovados;
- 3965 linhas na Gold;
- taxa de conclusão 22,3%, conversão 3,3%, avaliação 4,48;
- Beam: 72 grupos (mês × categoria), iguais no DirectRunner, no Spark e na Gold.

### Limitações conhecidas do Desafio 2

Cada documento tem as suas; as principais:

- **Ambiente:** a memória total pedida é de 10 a 12 GB; com 8 GB, suba um perfil por vez.
- **Evidências:** as do banco principal saem de uma mesma execução de referência, mas as medições de tempo (Parquet, Beam) variam de uma rodada para outra.
- **Storytelling:** as taxas por categoria oscilam com amostras de 44 a 136 pares; a recomendação é um piloto medido, não uma conclusão definitiva ([`storytelling.md`](documentacao/storytelling.md)).
- **Linhagem:** a parte que os conectores não enxergam (funções PL/pgSQL, Hop, arquivos) é registrada por código e precisa acompanhar o código que descreve ([`linhagem.md`](documentacao/linhagem.md)).
- **Hop:** o CSV é lido por posição; um arquivo com coluna faltando só é barrado depois da Silver, pelo teste Q08 ([`pipeline_hop.md`](documentacao/pipeline_hop.md#limitações-conhecidas)).
- **Spark:** o cluster é de demonstração (1 worker), então o Spark é mais lento que o DirectRunner neste volume ([`parquet_beam.md`](documentacao/parquet_beam.md)).

### Serviços e perfis

Os serviços ficam em perfis do Compose, para subir só o que se usa:

| Perfil | Serviços | Acesso |
|---|---|---|
| *(nenhum)* | `postgres`, `mongo`, `superset`, `db-init` | como no Desafio 1 |
| `hop` | `hop-web` (designer do Apache Hop no navegador) | http://localhost:8081/ui (`HOP_WEB_HOST_PORT`) |
| `beam` | `spark-master`, `spark-worker`, `beam-job-server`, `beam-worker-pool` | UI do Spark em http://localhost:8090 (`SPARK_UI_HOST_PORT`) |
| `governanca` | `elasticsearch`, `om-migrar`, `openmetadata`, `om-ingestao` (Airflow) | http://localhost:8585 (`OM_ADMIN_EMAIL` / `OM_ADMIN_PASSWORD`); Airflow em http://localhost:8082 |
| `alertas` | `redis`, `superset-worker`, `superset-beat` (Celery), `mailpit` (e-mail de teste) | caixa de entrada em http://localhost:8025 (`MAILPIT_HOST_PORT`) |
| `agendamento` | `hop-agendador`: fluxo completo todo dia às 05:00 UTC (02:00 de Brasília) | `docker compose --profile agendamento up -d` |
| `pipeline` | executores avulsos: `app` (Desafio 1), `hop`, `beam`, `evidencias` (Playwright: capturas e PDFs) | `docker compose run --rm <serviço> ...` |

`db-init` roda a cada `up` (e a cada `docker compose run` de um serviço que depende dele) e é idempotente e não destrutivo. Ele cria os bancos do OpenMetadata e do Airflow no mesmo PostgreSQL e aplica, nesta ordem, [`sql/camadas.sql`](sql/camadas.sql), [`sql/silver.sql`](sql/silver.sql), [`sql/qualidade.sql`](sql/qualidade.sql), [`sql/camada_gold.sql`](sql/camada_gold.sql) e [`sql/catalogo.sql`](sql/catalogo.sql). Funciona também sobre um volume já criado no Desafio 1. Nunca use `docker compose down -v` para "limpar": isso apaga os bancos.

Verificações da infraestrutura: `docker compose run --rm hop pipelines/verificar_ambiente.hpl` e `docker compose run --rm beam beam/verificar_runtime.py --runner {direct|spark}`.

**Memória** (medida em repouso):

| Parte | Memória |
|---|---|
| base | ~0,7 GB |
| perfil `governanca` (OpenMetadata, Elasticsearch e Airflow) | ~3,5 GB |
| perfil `beam` | ~1,3 GB, mais até 2 GB do executor durante um job (`SPARK_WORKER_MEMORY`) |
| perfil `alertas` | ~0,5 GB, além do Superset |

Com tudo no ar, reserve 10 a 12 GB no Docker Desktop. Com 8 GB, suba um perfil de cada vez (`docker compose --profile <perfil> stop` libera); foi assim que as evidências foram produzidas.

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
├── docker-compose.yml      serviços do Desafio 1 e, em perfis, os do Desafio 2
├── docker/                 Dockerfiles (app, Superset, Beam, evidências), init do Postgres, segredos do Hop
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
├── documentacao/           ingestao.md, recomendacao.md, kpis.md, uso_da_ia.md, modelo_de_dados.pdf, arquitetura_desafio1.pdf
│
│   Desafio 2
├── documentacao/           arquitetura (.md/.pdf), linhagem (.md/.pdf), storytelling (.md/.pdf),
│                           contratos.md, pipeline_hop.md, parquet_beam.md, camada_gold.md, governanca.md
├── dados/brutos/           + usuarios.csv, lote_2/, falhas/, recomendacoes_desafio1.json (fontes novas)
├── dados/bronze/           amostras da Bronze (sem as colunas pessoais)
├── dados/silver/           Parquet particionado (interacao/mes=AAAA-MM/), manifesto e amostras/ em CSV
├── dados/gold/             amostras e KPIs completos; engajamento_mensal_beam/ (saída do Beam)
├── dados/quarentena/       registros da quarentena e o seu status
├── hop/                    projeto Apache Hop: workflows/, pipelines/, environments/, metadata/, evidencias/
├── beam/                   exportar_silver.py (RF24), pipeline.py (RF25), verificar_runtime.py, evidencias/
├── sql/                    camadas.sql, silver.sql, qualidade.sql, camada_gold.sql, catalogo.sql, sql_lab.sql
├── qualidade/              regras.md, resultados/
├── lgpd/                   inventário, técnicas de proteção, demonstração e o seu resultado
├── superset/               provisionar.py, exportacao_e_evidencias/
├── openmetadata/           provisionar.py, evidencias/
└── ferramentas/            gerar_dados.py, exportar_amostras.py, evidencias.py, gerar_pdfs.py
```

O enunciado sugere `ingestao/` e `recomendacao/` na raiz e exige `python -m src.main`; por isso o orquestrador e o código comum ficam em `src/` e os módulos de domínio nas pastas sugeridas.

## Decisões e limitações do Desafio 1

Detalhes em `documentacao/`. Resumo do que vale saber antes de avaliar o Desafio 1. Duas limitações daqui foram resolvidas no Desafio 2: agora há uma fonte de usuários (`usuarios.csv`, fictícia), e a conversão de recomendações passou a ser mensurável (3,3%) com o lote 2.

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
