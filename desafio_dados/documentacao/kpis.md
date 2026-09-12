# Métricas e KPIs (RF12)

Todas as definições estão em views do PostgreSQL (`sql/criar_banco.sql`, seção RF12), calculadas a cada execução por `src/metricas.py` e gravadas em `dados/processados/kpis.json`. Consultas de exemplo em `sql/consultas.sql`. Fonte comum: `vw_interacoes`, que junta `interacao` com `conteudo` e `categoria` e expõe `mes`, `categoria`, `tipo` e `nivel` como dimensões de filtro.

**Métrica operacional** mede um fato da operação (quanto, quando, por quanto tempo), sem meta associada. **KPI** é um indicador ligado a um objetivo da plataforma (situação-problema, seção 3) e à decisão que ele orienta.

## Métricas operacionais

### M1 — Volume da plataforma — `vw_metricas_gerais`

- **Objetivo:** dimensionar a base: usuários, usuários ativos, conteúdos, interações, tempo médio consumido, recomendações, cobertura da recomendação, embeddings.
- **Fórmula:** contagens diretas; `tempo_medio_min = avg(tempo_consumido)`; `cobertura_recomendacao_pct = usuários com ≥ 1 recomendação / usuários × 100`.
- **Fonte:** `usuario`, `conteudo`, `interacao`, `recomendacao`, `conteudo_embedding`.
- **Periodicidade:** a cada execução do pipeline (acumulado).
- **Interpretação:** cartões de contexto do dashboard. Hoje: 150 usuários (150 ativos), 1000 conteúdos, 1000 interações, 144,9 min de tempo médio, 1170 recomendações cobrindo 78 % dos usuários.

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
- **Interpretação:** ranking. Com 1000 interações para 1000 conteúdos, o topo tem 3 visualizações — os dados são esparsos, então o ranking é mais útil por categoria do que por conteúdo isolado.

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
- **Interpretação:** quanto maior, melhor. Categorias com taxa baixa e boa avaliação (ver KPI2) indicam conteúdo longo demais ou mal sequenciado, não conteúdo ruim → candidato a revisão de formato. Hoje: DevOps & Cloud 29,9 % (melhor) e Segurança & Governança 11,6 % (pior).
- **Por que não `conclusões / inícios`:** nos dados fornecidos há conclusões sem início correspondente, o que produzia taxas acima de 100 %. A base por par usuário/conteúdo é limitada a 0–100.

### KPI2 — Qualidade percebida — `vw_kpi_qualidade`

- **Objetivo:** avaliar a qualidade dos materiais pela ótica do usuário.
- **Fórmula:** por categoria, tipo e nível: `avaliacao_media = avg(avaliacao_atribuida)`; `pct_positivas = avaliações ≥ 4 / avaliações × 100`. Só interações com avaliação entram.
- **Fonte:** `vw_interacoes` (`avaliacao_atribuida`). As avaliações dos comentários (MongoDB) não entram; ver `mongodb/consultas.js` para a média por categoria naquela base.
- **Periodicidade:** acumulado; recalculado a cada execução.
- **Interpretação:** escala 1–5; `pct_positivas` é mais robusta que a média com poucas avaliações. Categorias abaixo da média geral (4,48) são candidatas a curadoria; cruzar com KPI1 para separar "não gostam" de "gostam mas não terminam". Hoje: Engenharia de Dados 4,75 (melhor) e Banco de Dados 4,31 (pior).

### KPI3 — Retenção e engajamento mensal — `vw_kpi_retencao_mensal`

- **Objetivo:** medir se a plataforma mantém os usuários voltando.
- **Fórmula:** por mês: `usuarios_ativos = count(distinct usuario_id)`; `interacoes_por_usuario = interações / usuários ativos`; `retencao_pct = usuários ativos no mês que também têm interação no mês seguinte / usuários ativos × 100` (nulo no último mês, que ainda não tem "mês seguinte").
- **Fonte:** `vw_interacoes`.
- **Periodicidade:** mensal.
- **Interpretação:** retenção em queda com uso estável indica rotatividade de público; retenção estável com engajamento em queda indica usuários que voltam mas consomem menos. Hoje: retenção entre 52 % e 63 %, engajamento entre 1,4 e 1,7 interações por usuário/mês.

### KPI4 — Cobertura e qualidade da recomendação — `vw_kpi_recomendacao`

- **Objetivo:** saber se o motor de recomendação atende a base e com que confiança.
- **Fórmula:** por classificação, categoria e tipo: `recomendacoes`, `usuarios` distintos, `pontuacao_media`, `cobertura_pct = usuários com recomendação / usuários × 100`.
- **Fonte:** `recomendacao`, `conteudo`, `categoria`, `usuario`.
- **Periodicidade:** a cada execução (snapshot).
- **Interpretação:** cobertura baixa aponta *cold start* (usuários sem histórico suficiente) → decisão: recomendação por popularidade para esses. Proporção de `positivo` vs `estavel` indica a confiança do motor. Hoje: 78 % de cobertura; 200 positivas e 970 estáveis; 33 usuários sem recomendação.

### Indicador do enunciado não calculado

- **Conversão de recomendações** (interação com um conteúdo após ele ter sido recomendado) exige interações posteriores à geração. Todas as interações fornecidas são anteriores à primeira execução do pipeline, então o valor seria zero por construção. A definição fica registrada para quando houver dados novos: `usuários que interagiram com conteúdo recomendado após gerado_em / usuários com recomendação`.

## Perguntas de negócio respondidas pelo dashboard (RF13)

_(preencher — pelo menos duas; sugestão: cruzar KPI1 × KPI2 por categoria e KPI3 ao longo do tempo)_

1.
2.

## Justificativa dos gráficos (RF13)

_(preencher — mínimo: três cartões, um gráfico de barras, um de linhas, dois filtros; views sugeridas na coluna "Dado")_

| Gráfico | Dado (view) | Por que esse tipo |
|---|---|---|
| Cartão 1 | `vw_metricas_gerais` | |
| Cartão 2 | `vw_metricas_gerais` | |
| Cartão 3 | `vw_metricas_gerais` | |
| Barras | `vw_kpi_taxa_conclusao` ou `vw_kpi_qualidade` | |
| Linhas | `vw_uso_mensal` ou `vw_kpi_retencao_mensal` | |
| Filtro 1 | `categoria` | |
| Filtro 2 | `tipo` | |
