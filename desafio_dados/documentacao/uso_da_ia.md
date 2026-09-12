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
