# Métricas e KPIs (RF12)

Todas as definições estão em views do PostgreSQL (`sql/criar_banco.sql`, seção RF12), calculadas a cada execução por `src/metricas.py` e gravadas em `dados/processados/kpis.json`. Consultas de exemplo em `sql/consultas.sql`. Fonte comum: `vw_interacoes`, que junta `interacao` com `conteudo` e `categoria` e expõe `mes`, `categoria`, `tipo` e `nivel` como dimensões de filtro.

**Métrica operacional** mede um fato da operação (quanto, quando, por quanto tempo), sem meta associada. **KPI** é um indicador ligado a um objetivo da plataforma (situação-problema, seção 3) e à decisão que ele orienta.

## Métricas operacionais

### M1 — Volume da plataforma — `vw_metricas_gerais`

- **Objetivo:** dimensionar a base: usuários, usuários ativos, conteúdos, interações, tempo médio consumido, recomendações, cobertura da recomendação, embeddings.
- **Fórmula:** contagens diretas; `tempo_medio_min = avg(tempo_consumido)`; `cobertura_recomendacao_pct = usuários com ≥ 1 recomendação / usuários × 100`.
- **Fonte:** `usuario`, `conteudo`, `interacao`, `recomendacao`, `conteudo_embedding`.
- **Periodicidade:** a cada execução do pipeline (acumulado).
- **Interpretação:** cartões de contexto do dashboard. Hoje: 150 usuários (150 ativos), 1000 conteúdos, 923 interações válidas, 144,5 min de tempo médio, 1200 recomendações cobrindo 80 % dos usuários.

### M2 — Uso mensal — `vw_uso_mensal`

- **Objetivo:** acompanhar a evolução do uso no tempo.
- **Fórmula:** por mês (e categoria/tipo): `interacoes = count(*)`; `visualizacoes = count(tipo_interacao = 'visualização')`; `usuarios_ativos = count(distinct usuario_id)`; `tempo_total_min = sum(tempo_consumido)`.
- **Fonte:** `vw_interacoes`.
- **Periodicidade:** mensal (jan–ago/2026 nos dados fornecidos).
- **Interpretação:** série para o gráfico de linhas; quedas ou picos indicam sazonalidade ou efeito de novos conteúdos. Filtrável por categoria e tipo.

### M3 — Conteúdos mais procurados — `vw_conteudos_populares`

- **Objetivo:** identificar os materiais mais consumidos (demanda explícita da situação-problema).
- **Fórmula:** por conteúdo: `visualizacoes`, `usuarios` distintos, `tempo_medio_min`, `avaliacao_media`.
- **Fonte:** `vw_interacoes`.
- **Periodicidade:** acumulado; pode ser cortado por mês via `vw_interacoes`.
- **Interpretação:** ranking. Com 923 interações para 1000 conteúdos, o topo tem 3 visualizações — os dados são esparsos, então o ranking é mais útil por categoria do que por conteúdo isolado.

### M4 — Execução do pipeline — tabela `execucao_pipeline`

- **Objetivo:** histórico operacional do próprio processamento (DataOps, seção 9; RF05/RF14).
- **Fórmula:** uma linha por execução: registros lidos, válidos, inválidos, incompletos, duplicados, corrigidos, comentários no MongoDB, embeddings gerados, recomendações.
- **Fonte:** resumo da ingestão (`resumo_ingestao.json`), gravado por `src/metricas.py`.
- **Periodicidade:** por execução.
- **Interpretação:** permite ver se a qualidade dos dados de entrada muda entre cargas (aumento de inválidos ou duplicados) e quantas recomendações cada execução gerou.

## KPIs

### KPI1 — Taxa de conclusão — `vw_kpi_taxa_conclusao`

- **Objetivo:** medir se os usuários terminam o que começam (comportamento e engajamento).
- **Fórmula:** para cada par (usuário, conteúdo) com alguma interação de consumo (`visualização`, `início`, `conclusão`), o par é *concluído* se houver `conclusão` ou `percentual_conclusao = 100`. `taxa_conclusao_pct = pares concluídos / pares com consumo × 100`, por categoria, tipo e nível.
- **Fonte:** `vw_interacoes`.
- **Periodicidade:** acumulado; recalculado a cada execução.
- **Interpretação:** quanto maior, melhor. Categorias com taxa baixa e boa avaliação (ver KPI2) indicam conteúdo longo demais ou mal sequenciado, não conteúdo ruim → candidato a revisão de formato. Hoje: DevOps & Cloud 30,0 % (melhor) e Segurança & Governança 11,4 % (pior).
- **Por que não `conclusões / inícios`:** nos dados fornecidos há conclusões sem início correspondente, o que produzia taxas acima de 100 %. A base por par usuário/conteúdo é limitada a 0–100.

### KPI2 — Qualidade percebida — `vw_kpi_qualidade`

- **Objetivo:** avaliar a qualidade dos materiais pela ótica do usuário.
- **Fórmula:** por categoria, tipo e nível: `avaliacao_media = avg(avaliacao_atribuida)`; `pct_positivas = avaliações ≥ 4 / avaliações × 100`. Só interações com avaliação entram.
- **Fonte:** `vw_interacoes` (`avaliacao_atribuida`). As avaliações dos comentários (MongoDB) não entram; ver `mongodb/consultas.js` para a média por categoria naquela base.
- **Periodicidade:** acumulado; recalculado a cada execução.
- **Interpretação:** escala 1–5; `pct_positivas` é mais robusta que a média com poucas avaliações. Categorias abaixo da média geral (4,46) são candidatas a curadoria; cruzar com KPI1 para separar "não gostam" de "gostam mas não terminam". Hoje: Engenharia de Dados 4,72 (melhor) e Ciência de Dados 4,29 (pior).

### KPI3 — Retenção e crescimento mensal — `vw_kpi_retencao_mensal`

- **Objetivo:** medir se a plataforma mantém os usuários voltando.
- **Fórmula:** por mês: `usuarios_ativos = count(distinct usuario_id)`; `interacoes_por_usuario = interações / usuários ativos`; `retencao_pct = usuários ativos no mês que também têm interação no mês seguinte / usuários ativos × 100` (nulo no último mês, que ainda não tem "mês seguinte").
- **Fonte:** `vw_interacoes`.
- **Periodicidade:** mensal.
- **Interpretação:** o dashboard cruza retenção e usuários ativos na mesma série temporal. Retenção e usuários subindo indicam crescimento saudável; usuários subindo com retenção caindo sugerem entrada de novos usuários e rotatividade; ambas as séries caindo sugerem churn ou sazonalidade. Nos dados fornecidos, há 64–93 usuários ativos por mês e retenção entre 48,1 % e 61,1 % de janeiro a julho; agosto tem retenção nula porque ainda não existe o mês seguinte para comparação.

### KPI4 — Cobertura e qualidade da recomendação — `vw_kpi_recomendacao`

- **Objetivo:** saber se o motor de recomendação atende a base e com que confiança.
- **Fórmula:** por classificação, categoria e tipo: `recomendacoes`, `usuarios` distintos, `pontuacao_media`, `cobertura_pct = usuários com recomendação / usuários × 100`.
- **Fonte:** `recomendacao`, `conteudo`, `categoria`, `usuario`.
- **Periodicidade:** a cada execução (snapshot).
- **Interpretação:** cobertura baixa aponta *cold start* (usuários sem histórico suficiente) → decisão: recomendação por popularidade para esses. Proporção de `positivo` vs `estavel` indica a confiança do motor. Hoje: 80 % de cobertura; 190 positivas e 1010 estáveis; 30 usuários sem recomendação.

### Indicador do enunciado não calculado

- **Conversão de recomendações** (interação com um conteúdo após ele ter sido recomendado) exige interações posteriores à geração. Todas as interações fornecidas são anteriores à primeira execução do pipeline, então o valor seria zero por construção. A definição fica registrada para quando houver dados novos: `usuários que interagiram com conteúdo recomendado após gerado_em / usuários com recomendação`.

## Perguntas de negócio respondidas pelo dashboard (RF13)

O dashboard "Indicadores da Plataforma" abre com um bloco de texto enunciando as duas perguntas, e o layout responde a cada uma:

1. **Quais categorias precisam ser revisadas?** O gráfico de barras mostra a taxa de conclusão ponderada por categoria; o cartão de avaliação média, filtrado pela mesma categoria, diz se o problema é de qualidade ou de formato. Segurança & Governança é o principal caso: 11,4 % de conclusão com avaliação média de 4,67 — conteúdo bem avaliado que não é terminado, candidato a revisão de formato ou sequência.
2. **Estamos crescendo e retendo os usuários?** O gráfico combinado mostra usuários ativos (barras) e retenção (linha) mês a mês em eixos separados. Maio tem o pico de usuários ativos (93) com retenção de 51,6 %: entrada de novos usuários com rotatividade, não crescimento retido.

Os filtros de categoria e tipo refinam cartões, barras e tabela. A série mensal e os cartões de volume não filtram porque suas views são agregadas.

## Justificativa dos gráficos (RF13)

O painel separa **métricas de volume** (contexto: quanto) de **indicadores de desempenho** (KPIs: quão bem), em duas seções com título. Todo indicador tem formato explícito (`%`, escala 1–5) e subtítulo dizendo o que está sendo medido.

| Gráfico | Dado (view) | Por que esse tipo |
|---|---|---|
| Cartões de volume — usuários ativos, conteúdos, interações válidas, cobertura da recomendação | `vw_metricas_gerais` | Números de contexto; um valor só, sem comparação, pede cartão. Cobertura em % mostra o alcance do motor de recomendação. |
| Cartão — Avaliação média (1 a 5) | `vw_interacoes` | KPI de qualidade percebida; construído sobre a view-fato para responder aos filtros. |
| Cartão — Taxa de conclusão (%) | `vw_kpi_taxa_conclusao` | KPI de engajamento; métrica `sum(conclusoes)/sum(consumos)` para não fazer média de médias entre grupos de tamanhos diferentes. |
| Barras horizontais — Taxa de conclusão por categoria | `vw_kpi_taxa_conclusao` | Comparação de uma medida entre poucas categorias com nomes longos: barras horizontais ordenadas, com rótulo de valor. Mesma métrica ponderada do cartão. |
| Barras + linha, eixo duplo — Usuários ativos e retenção por mês | `vw_kpi_retencao_mensal` | Série temporal com duas grandezas de unidades diferentes (contagem e %): barras para volume, linha para taxa, cada uma no seu eixo. Retenção fica vazia no último mês por não haver mês seguinte. |
| Tabela — Top 10 conteúdos mais procurados | `vw_conteudos_populares` | Ranking com vários atributos por linha (título, categoria, tipo, visualizações, usuários, avaliação): tabela é o formato natural; responde diretamente à situação-problema. |
| Filtro — Categoria | `vw_interacoes.categoria` | Isola áreas temáticas e refiltra cartões, barras e tabela. |
| Filtro — Tipo | `vw_interacoes.tipo` | Compara formatos (Curso, Vídeo, Artigo, Podcast). |
