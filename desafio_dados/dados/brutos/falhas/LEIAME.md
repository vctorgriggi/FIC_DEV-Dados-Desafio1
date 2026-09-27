# Arquivos defeituosos (RF23)

Fora do fluxo normal; aponte a ingestão para eles só para demonstrar falha de arquivo.

| Arquivo | Defeito |
| --- | --- |
| `interacoes_truncado.json` | JSON cortado no meio (não faz parse) |
| `catalogo_sem_coluna_categoria.csv` | cabeçalho sem a coluna obrigatória `categoria` |

Falha de conexão simulada: rodar uma etapa com `PG_PORT` apontando para uma porta sem serviço, ou com o `postgres` parado (`docker compose stop postgres`).
