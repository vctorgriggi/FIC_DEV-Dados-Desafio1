# Desafio 1 — Pipeline de Recomendação e Dashboard de Conteúdos Educacionais

Enunciado completo em [../docs/](../docs/README.md). Estrutura conforme a seção 11 do enunciado.

## Requisitos

- Docker e Docker Compose

## Execução

```bash
cd desafio_dados
cp .env.example .env          # ajuste as senhas
docker compose up -d          # PostgreSQL+pgvector, MongoDB, Superset
docker compose run --rm app   # roda o pipeline (python -m src.main)
docker compose run --rm app python -m unittest   # testes
```

| Serviço    | Acesso                                                                |
| ---------- | --------------------------------------------------------------------- |
| PostgreSQL | `localhost:5432` (`POSTGRES_HOST_PORT`), banco `desafio`              |
| MongoDB    | `localhost:27017` (`MONGO_HOST_PORT`), banco `desafio`                |
| Superset   | http://localhost:8088 (`SUPERSET_HOST_PORT`; usuário/senha do `.env`) |

Conexão do Superset ao banco do desafio (SQLAlchemy URI):
`postgresql+psycopg2://desafio:desafio@postgres:5432/desafio`

Para zerar os bancos: `docker compose down -v`.

## Estrutura

```
desafio_dados/
├── README.md
├── config.yaml           parâmetros (caminhos, conexões, modelo, top_k)
├── .env                  senhas — fora do git
├── requirements.txt
├── docker-compose.yml    PostgreSQL+pgvector, MongoDB, Superset, app
├── docker/               Dockerfiles e configuração do Superset
├── src/
│   ├── main.py           orquestrador (python -m src.main)
│   ├── config.py, logger.py, db.py
│   └── metricas.py       métricas e KPIs (RF12)
├── ingestao/             leitura, validação, tratamento, carga no PostgreSQL (RF02–RF06)
├── mongodb/              carga e consultas MongoDB (RF07) — comentarios.py, consultas.js
├── recomendacao/         embeddings e busca semântica (RF08–RF09), motor (RF10–RF11)
├── tests/                testes unitários (validação com registros sujos)
├── sql/                  criar_banco.sql (aplicado ao subir o Postgres), consultas.sql
├── dados/
│   ├── brutos/           arquivos originais (não alterar)
│   └── processados/      saída tratada + resumo_ingestao.json
├── logs/                 registro de execução (RF14)
├── dashboard/evidencias/ prints e export do Superset
└── documentacao/         modelo_de_dados.pdf, arquitetura.pdf, kpis.md, uso_da_ia.md
```

## Decisões

- Ingestão, validação e tratamento: [documentacao/ingestao.md](documentacao/ingestao.md)
- _(preencher: escolha do MongoDB, modelo de embeddings, KPIs, limitações)_

## Uso de IA

Ver [documentacao/uso_da_ia.md](documentacao/uso_da_ia.md).
