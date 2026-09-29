# Arquivos defeituosos (RF23)

Fora do fluxo normal. Para demonstrar uma falha de arquivo, copie um deles por cima da fonte correspondente em `lote_2/` e restaure depois (`git checkout -- dados/brutos/lote_2/`).

| Arquivo | Defeito |
| --- | --- |
| `interacoes_truncado.json` | JSON cortado no meio (não faz parse) |
| `catalogo_sem_coluna_categoria.csv` | cabeçalho sem a coluna obrigatória `categoria`. O Hop lê CSV por posição, então a Bronze aceita o arquivo e a Silver rejeita as linhas; o teste crítico Q08 (validade por arquivo) bloqueia a Gold. Veja `hop/evidencias/ambiente_limpo/06_falha_estrutura_do_arquivo.log` |

Falha de conexão simulada: rodar uma etapa com `PG_PORT` apontando para uma porta sem serviço, ou com o `postgres` parado (`docker compose stop postgres`).
