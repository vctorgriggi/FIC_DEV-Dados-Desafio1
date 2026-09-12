# Pipeline de Recomendação e Dashboard de Conteúdos Educacionais

FIC_DEV — Programador de Sistemas com IA · Fundamentos de Dados para IA · Desafio Prático 1

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

Outros comandos:

```bash
docker compose run --rm app python -m unittest      # testes (validação com registros sujos, fórmula de recomendação)
docker compose exec -T postgres psql -U desafio -d desafio -f - < sql/consultas.sql
docker compose exec -T mongo mongosh -u desafio -p desafio --authenticationDatabase admin desafio < mongodb/consultas.js
docker compose down -v                              # apaga bancos e volumes
```

Se uma porta já estiver em uso na máquina, mude `*_HOST_PORT` no `.env`. Configurações não sensíveis (caminhos, modelo, `top_k`, consultas de demonstração) ficam em `config.yaml`; senhas só no `.env`, que está no `.gitignore`.

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
└── documentacao/           ingestao.md, recomendacao.md, kpis.md, uso_da_ia.md, modelo_de_dados.pdf, arquitetura.pdf
```

O enunciado sugere `ingestao/` e `recomendacao/` na raiz e exige `python -m src.main`; por isso o orquestrador e o código comum ficam em `src/` e os módulos de domínio nas pastas sugeridas.

## Decisões e limitações

Detalhes em `documentacao/`. Resumo do que vale saber antes de avaliar:

- **Validação nunca rejeita nada nos dados fornecidos** porque eles são limpos (3000 lidos, 3000 válidos). As regras são demonstradas por testes com registros sujos (`tests/`). Não há fonte de usuários; a tabela `usuario` é derivada das interações e comentários. → `ingestao.md`
- **MongoDB recebe os comentários** com `categoria`, `titulo` e `tipo` desnormalizados, o que permite agregar por categoria sem join. → `recomendacao.md`
- **Modelo de embeddings multilíngue**, porque o catálogo é em português. → `recomendacao.md`
- **Ivis e Icur usam a proporção por categoria**, não a similaridade vetorial. A vetorial foi testada e descartada: as descrições seguem o mesmo molde e a similaridade ficou entre 0,38 e 0,85, classificando tudo como "positivo". O pgvector é usado na busca semântica e no desempate. → `recomendacao.md`
- **Faixa "Estável"** do enunciado (`40 > Pontuação < 70`) interpretada como `40 < Pontuação < 70`. Negativos são descartados; 33 usuários ficam sem recomendação. → `recomendacao.md`
- **Taxa de conclusão** calculada por par usuário/conteúdo, porque `conclusões ÷ inícios` passava de 100 % nesses dados. **Conversão de recomendações** não é mensurável: todas as interações são anteriores à primeira execução. → `kpis.md`
- Cada execução **substitui** as recomendações anteriores (snapshot único); o histórico de execuções fica em `execucao_pipeline`.

## Uso de Inteligência Artificial

Registro em `documentacao/uso_da_ia.md`.
