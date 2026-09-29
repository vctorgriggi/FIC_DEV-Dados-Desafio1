# Storytelling, SQL Lab, filtros e alerta (RF16, RF17, RF18)

Parte do Estudante 3. O consumo tem três peças, todas no Superset e provisionadas por código ([`superset/provisionar.py`](../superset/provisionar.py)):

- o dashboard de storytelling, que responde a uma pergunta;
- o dashboard de exploração, com filtros e a evolução da qualidade;
- o alerta.

O Superset se conecta com o papel `consumo`, que só lê a Gold, a qualidade e o controle.

```bash
docker compose up -d                                           # Superset em http://localhost:8088
docker compose run --rm beam superset/provisionar.py           # banco, datasets, consultas, gráficos, dashboards, alerta
docker compose --profile alertas up -d                         # Redis, worker e beat do Celery, Mailpit (e-mail de teste)
docker compose run --rm beam superset/provisionar.py --demonstrar-alerta
docker compose run --rm evidencias ferramentas/evidencias.py superset   # capturas 01-07
docker compose run --rm evidencias ferramentas/evidencias.py alerta     # captura 08 (e-mail no Mailpit)
```

Evidências em [`superset/exportacao_e_evidencias/`](../superset/exportacao_e_evidencias/):

- capturas 01 a 08;
- `dashboards_desafio2.zip`, a exportação dos dois dashboards para *Dashboards → Import*;
- `consultas_sql_lab.zip`, as consultas salvas;
- `alerta_execucao.json` e `alerta_email.html`, a prova do disparo.

**Os números não são digitados.** Os títulos e textos do dashboard são gerados a partir da Gold no momento do provisionamento. O script também confere as premissas da narrativa; se os dados deixarem de sustentá-las, ele para em vez de publicar uma história falsa. As premissas conferidas:

- a categoria tem a menor conclusão;
- está entre as 3 mais bem avaliadas;
- lidera a conversão, ou empata;
- o nível avançado é o de menor conclusão;
- conteúdos curtos concluem mais que os de média duração;
- a taxa está abaixo do limite do alerta.

## RF16 — Narrativa executiva

Dashboard **"Desafio 2 - Por que Segurança & Governança não é concluída?"** (`01_storytelling.png`).

**Pergunta decisória:** em qual categoria agir primeiro para aumentar a conclusão de conteúdos, e como?

A legenda no topo separa os três tipos de afirmação, e cada texto começa com o rótulo:

- **Fato:** medido nos dados;
- **Hipótese:** explicação a testar;
- **Recomendação:** ação proposta.

A descrição de cada gráfico no Superset repete a classificação e avisa quando a amostra é pequena.

| Etapa | Visualização | Título informativo | Tipo |
| --- | --- | --- | --- |
| **Contexto** | 3 números e a série mensal | "Pessoas ativas cresceram de 64 para 104 entre janeiro e agosto"; conclusão geral 22,3%; conversão 3,3%; avaliação 4,48 | Fato |
| **Evidência** | barras por categoria | "Segurança & Governança conclui 15% do que começa: a menor taxa do catálogo" | Fato |
| | tabela avaliação × conclusão | "Mesmo assim é a 2ª categoria mais bem avaliada: o problema não parece ser qualidade" | Fato; descarta a hipótese "conteúdo ruim" |
| **Descoberta** | barras por nível, na categoria | "Em Segurança & Governança, o nível avançado conclui só 7,1%" | Fato, com amostra pequena (28 pares) |
| | barras por tipo, na categoria | "Vídeos e podcasts de Segurança & Governança quase não são concluídos" (7,7% e 8,7%) | Fato, com amostra pequena |
| | barras de conversão por categoria | "Recomendações de Segurança & Governança estão no topo da conversão (5%): há demanda" | Fato; empatada com Programação & Software |
| **Ação** | texto | piloto, priorização e meta | Recomendação |

**O raciocínio, em quatro passos:**

1. **Contexto.** A plataforma cresce, mas só 22,3% do que é iniciado é concluído.
2. **Evidência.** Segurança & Governança é a pior categoria (15%) e, ao mesmo tempo, a 2ª mais bem avaliada (4,58). Quem termina gosta, então o problema não é a qualidade do conteúdo.
3. **Descoberta.** A queda se concentra:
   - no nível avançado (7,1%);
   - em vídeos e podcasts (7,7% e 8,7%);
   - nos conteúdos de 31 a 90 minutos (7,1%, contra 19,5% dos de até 30 minutos).

   A categoria não tem mais conteúdo avançado que as outras: 33% do catálogo, no meio das oito. Logo, a explicação não é só dificuldade. As recomendações da categoria estão entre as que mais convertem (5%), então há interesse. *Hipótese:* falta um caminho para terminar conteúdos densos de média duração.
4. **Ação recomendada:**
   - **Recomendação.** Piloto de 60 dias em Segurança & Governança: dividir vídeos e podcasts, começando pelos de nível avançado, em módulos de até 30 minutos, com um conteúdo básico como porta de entrada.
   - **Recomendação.** Priorizar essa trilha na recomendação para quem já iniciou conteúdo da categoria.
   - **Meta e acompanhamento.** Levar a conclusão da categoria de 15% para 22%, a média do catálogo, acompanhada pelo alerta diário (RF18).

**Limites declarados no próprio dashboard:**

- os recortes por nível e tipo têm poucos pares (23 a 38 por tipo);
- a conversão foi medida só duas semanas depois das recomendações (geradas em 13/09/2026);
- Business Intelligence (16,2%) também está abaixo do limite do alerta e é a candidata seguinte.

## RF17 — SQL Lab e conjuntos de dados virtuais

As consultas ficam em [`sql/sql_lab.sql`](../sql/sql_lab.sql), cada uma com finalidade e campos calculados documentados no cabeçalho. O provisionamento lê o arquivo e cria, para cada bloco, uma **consulta salva** no SQL Lab e um **dataset virtual** com o mesmo SQL. O SQL existe num lugar só, e todas as consultas partem da Gold e rodam com o papel `consumo`.

| Consulta / dataset | Finalidade | Junção | Agregação | Condicional | Data | Usada em |
| --- | --- | --- | --- | --- | --- | --- |
| `vd_conclusao_coorte` | taxa de conclusão por mês de início, categoria, tipo e nível; cada par entra uma vez, no mês em que o consumo começou | `fato_interacao` × `dim_conteudo` | `count`, `sum`, `bool_or` | `CASE` (par concluído) | `date_trunc('month', ...)` | cartão de conclusão, barras por categoria, nível e tipo, filtro cruzado, alerta |
| `vd_recomendacoes` | conversão por categoria, classificação e faixa de posição, e dias até converter | `fato_recomendacao` × `dim_conteudo` | `count`, `sum`, `avg` | `CASE` (faixa 1 a 3, 4 a 6, 7 a 10; convertida) | `::date`, `EXTRACT(EPOCH ...)` | cartão de conversão, conversão por categoria e por posição |
| `vd_avaliacao_x_conclusao` | avaliação e conclusão por categoria e o quadrante em relação às médias do catálogo | `kpi_taxa_conclusao` × `kpi_avaliacao` | média ponderada, `sum` | `CASE` (quadrante) | — | tabela do storytelling |
| `vd_pessoas_engajadas` | pessoas mais engajadas, só com nome mascarado e pseudônimo (RF33) | `fato_interacao` × `dim_usuario` | `count`, `count(DISTINCT)`, `max` | `CASE` (conclusões) | `max(data_hora)::date` | tabela da exploração |

**Reprodutibilidade:**

- a soma de `vd_conclusao_coorte` em todos os meses dá os 928 pares com consumo e 207 concluídos de `gold.kpi_taxa_conclusao` (22,3%);
- a soma de `vd_recomendacoes` dá as 1200 recomendações de `gold.kpi_conversao_recomendacao`;
- as métricas dos datasets são sempre `100 × SUM(numerador) ÷ SUM(denominador)`, nunca a média de taxas.

Captura: `06_sql_lab_consultas_salvas.png`.

## RF18 — Filtros cruzados, filtros globais e alerta

Dashboard **"Desafio 2 - Exploração, filtros e qualidade"** (`02_exploracao.png`).

**Filtros globais** (painel à esquerda):

| Filtro | Tipo | Age sobre | Não age sobre |
| --- | --- | --- | --- |
| **Período** | intervalo de datas | o mês de início do consumo, de geração da recomendação ou de referência, conforme o gráfico | a evolução da qualidade (o eixo é a execução), a lista de pessoas e o conteúdo do alerta |
| **Categoria** (dimensão de negócio) | seleção múltipla, valores de `vd_conclusao_coorte` | todos os gráficos com categoria | a evolução da qualidade e a lista de pessoas |

Evidências:

- `03_exploracao_filtro_categoria.png`: categoria = Segurança & Governança;
- `04_exploracao_filtro_periodo.png`: junho a setembro.

**Filtro cruzado.** Um clique numa barra de *Taxa de conclusão por categoria (clique para filtrar)* filtra quatro gráficos por aquela categoria: taxa por tipo, conversão por posição, interações por mês e a tabela do alerta.

A captura `05_exploracao_filtro_cruzado.png` foi feita clicando de fato na barra de Segurança & Governança. O script confere que o filtro aplicado é essa categoria. Com ele, a conversão por posição passa a mostrar 4,2%, 4,2% e 6,3%.

O gráfico emissor usa barras verticais de propósito. No Superset 6.1, o clique numa barra horizontal emite o valor numérico em vez da categoria.

**Alerta** (`07_alerta_configurado.png`):

| Item | Valor |
| --- | --- |
| Nome | Taxa de conclusão de alguma categoria abaixo de 18% |
| Condição | `SELECT min(taxa) FROM (SELECT categoria, 100.0 * sum(pares_concluidos) / sum(pares_consumo) AS taxa FROM gold.kpi_taxa_conclusao GROUP BY categoria) t` **< 18** |
| Periodicidade | diário às 08:00, fuso America/Sao_Paulo (`0 8 * * *`) |
| Destinatário (fictício) | `coordenacao.conteudo@plataforma.example` |
| Conteúdo | tabela "Taxa de conclusão por categoria (conteúdo do alerta)", da menor para a maior |
| Ação esperada | a coordenação de conteúdo revisa a categoria indicada e decide entre dividir conteúdos em módulos ou criar uma trilha de entrada. É a meta da ação 3 do storytelling |

**Por que 18%.** A média do catálogo é 22,3%, e as seis categorias saudáveis ficam entre 22,7% e 26,6%. 18% separa com folga "abaixo da média" de "problema": dispara hoje para Segurança & Governança (15,0%) e Business Intelligence (16,2%), e deixa de disparar quando o piloto levar a categoria perto da meta.

**Demonstração do envio.** O envio foi demonstrado de verdade, e não só a avaliação da condição. O Superset avalia os alertas com o Celery (worker e beat) e envia por SMTP para o Mailpit, um servidor de e-mail de teste. Nada sai da máquina.

`--demonstrar-alerta` faz o seguinte:

1. muda o agendamento para "a cada minuto";
2. espera a execução;
3. lê o e-mail recebido pela API do Mailpit;
4. grava a prova;
5. volta ao agendamento diário.

Registrado em `alerta_execucao.json`:

- estado `Success`, com valor medido 15,0, que é menor que 18;
- enviado de `alertas@plataforma.example` para `coordenacao.conteudo@plataforma.example`, 51 s depois de agendado.

O e-mail (`alerta_email.html`, captura `08_alerta_email_recebido.png`) traz a descrição do alerta, com a ação esperada, e a tabela das oito categorias.

## Proteção dos dados no consumo (RF33)

- A conexão usa o papel `consumo`: a Bronze, a Silver e o schema `restrito` ficam inacessíveis, inclusive no SQL Lab. A demonstração está em [`lgpd/demonstracao_resultado.txt`](../lgpd/demonstracao_resultado.txt).
- A única lista de pessoas mostra `nome_mascarado` (ex.: `André N***`) e os 12 primeiros caracteres do pseudônimo.
