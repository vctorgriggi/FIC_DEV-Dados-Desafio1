# 1. Orientações gerais

Este desafio integra os conteúdos das aulas 1 a 8 do curso Fundamentos de Dados para IA. A equipe deverá construir um fluxo completo de dados, desde a ingestão e o armazenamento até a recomendação e a apresentação de indicadores em um dashboard.

- Leia integralmente o enunciado antes de iniciar a implementação.
- Utilize dados fictícios e preserve os arquivos originais de entrada.
- Mantenha a solução dentro do escopo proposto para que seja concluída em aproximadamente 12 horas.
- Registre decisões, limitações e instruções de execução no README.md.
- As funcionalidades adicionais não substituem requisitos obrigatórios ausentes.
- Todos os integrantes deverão compreender a solução completa.

# 2. Objetivos de aprendizagem

Ao concluir o desafio, espera-se que o discente seja capaz de:

- ingerir e validar dados provenientes de diferentes fontes e formatos;
- modelar e armazenar dados estruturados em um banco relacional;
- armazenar e consultar dados semiestruturados em um banco NoSQL;
- representar descrições textuais por meio de embeddings;
- realizar busca por similaridade semântica;
- implementar uma estratégia simples de recomendação;
- definir métricas e KPIs orientados à tomada de decisão;
- construir visualizações e um dashboard no Apache Superset;
- Aplicar práticas básicas de DataOps e documentar o uso de Inteligência Artificial.

# 3. Situação-problema

Uma plataforma fictícia disponibiliza cursos, vídeos, artigos, podcasts e outros materiais educacionais. Atualmente, os dados estão distribuídos em diferentes arquivos e formatos, dificultando a identificação dos conteúdos mais procurados, a análise do comportamento dos usuários, a avaliação da qualidade dos materiais, a recomendação de conteúdos relacionados e a construção de indicadores para apoiar decisões.

A instituição deseja organizar esses dados, produzir recomendações simples e acompanhar os principais resultados em um dashboard.

> **Produto esperado:** pipeline reproduzível que integre ingestão, PostgreSQL, MongoDB, armazenamento vetorial, recomendações e um dashboard no Apache Superset.

# 4. Problema proposto

Cada equipe deverá desenvolver uma solução de dados capaz de:

1. ingerir dados provenientes de diferentes fontes e formatos;
2. armazenar dados estruturados em um banco relacional;
3. armazenar dados semiestruturados em um banco NoSQL;
4. representar descrições textuais por meio de embeddings;
5. recuperar conteúdos semanticamente semelhantes;
6. gerar recomendações simples;
7. disponibilizar métricas e KPIs em um dashboard no Apache Superset.

A solução deverá formar um fluxo integrado e reproduzível, desde a leitura dos dados de origem até sua apresentação no dashboard.

# 5. Organização das equipes

O desafio deverá ser realizado por equipes de 3 (três) estudantes, NO MÁXIMO. A divisão das responsabilidades fica a cargo da equipe. Uma sugestão para divisão inicial de responsabilidades é:

| Integrante  | Responsabilidade inicial                     |
| ----------- | -------------------------------------------- |
| Estudante 1 | Ingestão, tratamento e PostgreSQL.           |
| Estudante 2 | MongoDB, embeddings e recomendações.         |
| Estudante 3 | Métricas, consultas e dashboard no Superset. |

> **Importante:** a divisão é apenas uma orientação de trabalho. Todos os integrantes deverão compreender e saber explicar a solução completa.
