# Uso da Inteligência Artificial

## Ferramenta utilizada

Claude Code (Anthropic).

## Exemplos de solicitações

- Explicar erros de execução (conflito de portas, versão do MongoDB incompatível com o Docker).
- Sugerir comandos SQL e consultas MongoDB.
- Revisar código já escrito pela equipe e apontar problemas.
- Sugerir métricas e KPIs a partir dos requisitos.
- Tirar dúvidas sobre trechos ambíguos do enunciado.
- Melhorar a redação da documentação.

## Decisões apoiadas pela IA

- Modelagem das tabelas e das views.
- Escolha do modelo de embeddings.
- Interpretação da fórmula de recomendação.
- Separação entre métricas operacionais e KPIs.

## Erros encontrados nas respostas

- Sugestão de contagem na ingestão com erro de comparação de tipos.
- Trecho de persistência que não gravava no banco por uso incorreto de transação.
- Fórmulas sugeridas que geravam resultados sem sentido nos dados (recomendação e taxa de conclusão).

## Alterações feitas pela equipe

Todas as sugestões foram testadas antes de serem aproveitadas. Os erros acima foram identificados e corrigidos pela equipe, e as decisões finais estão registradas em `documentacao/`.

## Desafio 2

### Ferramenta utilizada

Claude Code (Anthropic).

### Exemplos de solicitações

- Explicar erros de configuração do Docker, do Apache Hop e do OpenMetadata.
- Sugerir consultas SQL para as regras da Silver, os testes de qualidade e a Gold.
- Revisar código já escrito pela equipe e apontar problemas.
- Sugerir testes de qualidade e técnicas de proteção de dados pessoais.
- Tirar dúvidas sobre trechos ambíguos do enunciado.
- Melhorar a redação da documentação e do storytelling.

### Decisões apoiadas pela IA

- Organização das camadas Bronze, Silver e Gold e do fluxo de quarentena.
- Particionamento do Parquet por mês.
- Regras de correspondência dos dados mestres.
- Escolha das técnicas de LGPD para cada campo.

### Erros encontrados nas respostas

- Consulta de deduplicação que contava a mesma linha duas vezes.
- Configuração do Hop que carregava o mesmo arquivo duas vezes.
- Números e afirmações do storytelling que não batiam com os dados.

### Alterações feitas pela equipe

Todas as sugestões foram testadas antes de serem aproveitadas. Os erros acima foram identificados e corrigidos pela equipe, e as decisões finais estão registradas em `documentacao/`, `qualidade/` e `lgpd/`.
