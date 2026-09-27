# 1. Orientações gerais

Este desafio dá continuidade à solução construída no Desafio Prático 1 e integra os conteúdos das aulas 9 a 17 do curso Fundamentos de Dados para IA. A equipe deverá evoluir o pipeline existente para uma arquitetura automatizada, escalável, governada e compatível com os princípios de proteção de dados pessoais.

- Leia integralmente o enunciado antes de alterar a solução do Desafio 1.
- Utilize dados fictícios e preserve os arquivos e bancos originais para permitir comparação e reprocessamento.
- Mantenha a solução dentro do escopo proposto para que seja concluída em aproximadamente 18 horas.
- Registre decisões de arquitetura, limitações, dependências e instruções de execução no README.md.
- As funcionalidades adicionais não substituem requisitos obrigatórios ausentes.
- Todos os integrantes deverão compreender a solução completa e saber justificar as escolhas realizadas.

# 2. Objetivos de aprendizagem

Ao concluir o desafio, espera-se que o discente seja capaz de:

- construir uma narrativa executiva baseada em dados e consultas produzidas no SQL Lab;
- aplicar filtros cruzados e configurar alertas no Apache Superset;
- diferenciar ETL de ELT e justificar a arquitetura adotada;
- implementar pipelines e workflows no Apache Hop;
- organizar dados nas camadas Bronze, Silver e Gold;
- padronizar dados, controlar falhas e encaminhar registros inválidos para quarentena;
- processar dados em formato Parquet com Apache Beam e runtime Spark ou Flink;
- catalogar ativos, metadados, termos de negócio e linhagem no OpenMetadata;
- definir dados mestres e executar testes de qualidade;
- identificar dados pessoais e aplicar técnicas adequadas de mascaramento, pseudonimização ou hashing.

# 3. Situação-problema

Uma plataforma fictícia disponibiliza cursos, vídeos, artigos, podcasts e outros materiais educacionais. Atualmente, os dados estão distribuídos em diferentes arquivos e formatos, dificultando a identificação dos conteúdos mais procurados, a análise do comportamento dos usuários, a avaliação da qualidade dos materiais, a recomendação de conteúdos relacionados e a construção de indicadores para apoiar decisões.

A instituição deseja organizar esses dados, produzir recomendações simples e acompanhar os principais resultados em um dashboard.

Após a primeira entrega, a plataforma passou a receber um volume maior de dados e precisa tornar o fluxo mais confiável e auditável. A instituição também necessita documentar os ativos, rastrear a origem dos indicadores, controlar a qualidade, proteger dados pessoais e apresentar os resultados por meio de uma narrativa executiva que apoie decisões.

> **Produto esperado:** evolução do pipeline do Desafio 1 para um fluxo automatizado em Apache Hop, com camadas Bronze, Silver e Gold, processamento distribuído, governança no OpenMetadata, controles de qualidade e LGPD e apresentação executiva no Apache Superset.

# 4. Problema proposto

Cada equipe deverá utilizar a solução funcional do Desafio Prático 1 como ponto de partida e acrescentar capacidades para:

- comunicar resultados por meio de storytelling executivo;
- modelar consultas e conjuntos de dados virtuais no SQL Lab;
- automatizar ingestão, transformação e carga com Apache Hop;
- separar dados brutos, padronizados e analíticos em camadas;
- orquestrar o fluxo, tratar erros e permitir reprocessamento controlado;
- executar ao menos uma etapa de processamento distribuído com Apache Beam;
- catalogar ativos, termos, classificações e linhagem no OpenMetadata;
- definir dados mestres e critérios mensuráveis de qualidade;
- identificar e proteger dados pessoais durante o processamento e o consumo.

A solução deverá formar um fluxo integrado, reproduzível e demonstrável, desde as fontes do Desafio 1 até a camada de consumo, mantendo evidências técnicas de execução, qualidade, governança e proteção de dados.

# 5. Organização das equipes

O desafio deverá ser realizado pela mesma equipe de estudantes do desafio 1. A divisão das responsabilidades fica a cargo da equipe. Uma sugestão para divisão inicial é:

| Integrante  | Responsabilidade inicial                                                      |
| ----------- | ----------------------------------------------------------------------------- |
| Estudante 1 | Apache Hop, camadas Bronze e Silver, workflows e tratamento de erros.         |
| Estudante 2 | Parquet, Apache Beam, runtime distribuído, camada Gold e testes de qualidade. |
| Estudante 3 | OpenMetadata, LGPD, SQL Lab, storytelling e recursos avançados do Superset.   |

> **Importante:** a divisão é apenas uma orientação de trabalho. Todos os integrantes deverão compreender e saber explicar a solução completa.

**ATENÇÃO**:

Algumas atividades possuem dependências. Por exemplo, a camada Silver depende da Bronze, e o dashboard depende da Gold. Assim, os integrantes devem trabalhar paralelamente com dados de teste e contratos de entrada e saída previamente definidos.

A recomendação é a de que as responsabilidades iniciais sejam bem delimitadas, considerando-se que e integração obrigatória ao final.

A apresentação também deve verificar se todos compreendem a solução completa.
