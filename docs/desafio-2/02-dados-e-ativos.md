# 6. Dados e ativos de continuidade

O Desafio 2 deverá reaproveitar as fontes e os bancos do Desafio 1.

| Ativo                    | Origem                        | Uso no Desafio 2                                                               |
| ------------------------ | ----------------------------- | ------------------------------------------------------------------------------ |
| Catálogo de conteúdos    | CSV e PostgreSQL              | Ingestão Bronze, padronização Silver, dados mestres e classificação de campos. |
| Interações dos usuários  | JSON e PostgreSQL             | Processamento temporal, agregações, KPIs e testes de integridade.              |
| Comentários e avaliações | JSON ou MongoDB               | Integração de dados semiestruturados, análise de PII e qualidade.              |
| Recomendações            | PostgreSQL                    | Camada Gold, conversão de recomendações e storytelling executivo.              |
| Metadados técnicos       | Apache Hop, bancos e arquivos | Catalogação, linhagem, responsáveis e documentação no OpenMetadata.            |
