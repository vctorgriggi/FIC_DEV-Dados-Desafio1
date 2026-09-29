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

Claude Code (Anthropic), usado pela equipe para transcrever o enunciado, preparar a infraestrutura Docker e os contratos, revisar as partes de cada integrante e produzir código, provisionamento e documentação.

### Exemplos de solicitações

- Preparar a infraestrutura multiplataforma (Hop, Beam no Spark, OpenMetadata, alertas do Superset) com versões fixas e sem segredos no repositório.
- Revisar o trabalho de cada integrante contra o enunciado e os contratos, e corrigir o que não estivesse sólido.
- Propor os testes de qualidade, os limites e a severidade de cada um.
- Revisar as técnicas de proteção (RF33) e o inventário LGPD.
- Conferir se os números do storytelling são sustentados pelos dados.

### Decisões apoiadas pela IA

- Arquitetura ELT com as regras em SQL e a separação entre aprovados e rejeitados no Hop; publicação atômica da Silver e da Gold.
- Identidade da quarentena por (fonte, arquivo, linha, hash), para que as correções substituam o registro da Bronze.
- Pessoa mestre por `cpf_hash` ou `email_hash` com transitividade (RF30).
- Particionamento do Parquet por mês.
- Linhagem registrada pela API onde os conectores não enxergam (funções PL/pgSQL e Hop).
- Narrativa gerada a partir da Gold, com premissas verificadas antes de publicar.

### Erros encontrados e corrigidos

Encontrados na verificação, fosse em respostas da IA, fosse no código:

- Deduplicação que calculava versões antes de separar as cópias idênticas, contando a mesma linha duas vezes.
- `db-init` que apagava a área de preparo da Silver a cada `docker compose run`.
- `JsonInput` do Hop com o arquivo listado duas vezes, duplicando a Bronze.
- Mensagem de etapa que chamava de "versões substituídas" também os registros descartados na triagem.
- Histórico da qualidade que exibia o limite atual do teste, e não o vigente na execução: a execução bloqueada parecia reprovada com valor acima do limite.
- Quadrante avaliação × conclusão calculado sobre a média simples das categorias, e não sobre a média do catálogo mostrada no dashboard.
- Recomendação do storytelling que incluía cursos, que são justamente o formato que mais conclui na categoria. Foi substituída por uma baseada na duração, verificada nos dados.
- Afirmação de que Segurança & Governança "é a que mais converte", quando está empatada com Programação & Software.
- Número de CPFs possíveis escrito como 10^11, quando são 10^9.
- Barras horizontais do Superset emitindo o valor numérico, em vez da categoria, no filtro cruzado.
- Disparo da ingestão do OpenMetadata antes de o Airflow registrar o DAG, e o token do bot aparecendo no log do Hop numa falha.

### Revisão independente antes da entrega

Um segundo agente de IA revisou o projeto contra o enunciado, requisito por requisito, no papel de avaliador exigente. Os problemas que ele apontou foram conferidos um a um e corrigidos:

- As amostras da Silver traziam `usuario_id` e pseudônimo na mesma linha: uma tabela de correspondência no repositório, o que o RF33 proíbe.
- Com o filtro de período, a conclusão do storytelling se invertia (Segurança & Governança melhora, Business Intelligence piora). A narrativa passou a declarar isso e a tratar a ação como piloto medido.
- O teste Q01 não detectava um arquivo inteiro quebrado, como a documentação dizia. Foi criado o Q08 (validade por arquivo), e o bloqueio foi demonstrado com o arquivo defeituoso.
- As falhas de arquivo e de conexão e a execução agendada estavam descritas, mas sem evidência. Foram executadas num ambiente limpo, com os logs guardados.
- Reprocessar uma etapa apagava a tentativa anterior; foi criado `controle.etapa_historico`.
- Os gráficos de evolução da qualidade não mostravam a evolução, por causa do eixo de tempo contínuo e da escala de 0 a 120.
- As descrições do catálogo estavam sem acento e não eram atualizadas pela ingestão.
- Havia senhas padrão e a chave Fernet no `docker-compose.yml` e no `.env.example`.
- O `arquitetura.pdf` exigido era o do Desafio 1.

### Alterações feitas pela equipe

Cada entrega foi executada de ponta a ponta e conferida contra um resultado independente:

- a Silver contra o oráculo `ANOMALIAS.md`;
- o Beam contra a Gold;
- o SQL Lab contra os KPIs;
- o bloqueio da Gold com um teste crítico reprovado;
- o papel `consumo` contra as tabelas protegidas.

As decisões finais e os limites de cada parte estão registrados em `documentacao/`, `qualidade/` e `lgpd/`.
