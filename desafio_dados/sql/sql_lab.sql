-- Desafio 2 — consultas do SQL Lab (RF17), executadas com o papel "consumo" (so le gold, qualidade e controle).
--
-- Cada bloco comeca com "-- nome:" e vira, no Superset, uma consulta salva e um conjunto de dados virtual
-- com o mesmo nome (superset/provisionar.py le este arquivo; o SQL existe so aqui). Todas partem da
-- camada Gold, entao os resultados sao reproduziveis a partir dela.

-- nome: vd_conclusao_coorte
-- finalidade: taxa de conclusao por mes, filtravel por periodo, categoria, tipo e nivel, sem divergir
--   de gold.kpi_taxa_conclusao. Cada par (pessoa, conteudo) entra uma unica vez, no mes em que o
--   consumo comecou (coorte); por isso a soma de todos os meses e igual ao KPI da Gold.
-- campos calculados:
--   mes_inicio        date_trunc do primeiro consumo do par (funcao de data)
--   pares_consumo     pares com visualizacao, inicio ou conclusao
--   pares_concluidos  pares com conclusao ou percentual 100 (CASE)
--   taxa no grafico   100 * SUM(pares_concluidos) / SUM(pares_consumo)
WITH pares AS (
    SELECT f.usuario_pseudo,
           f.conteudo_id,
           date_trunc('month', min(f.data_hora))::date AS mes_inicio,
           bool_or(f.tipo_interacao = 'conclusão' OR f.percentual_conclusao >= 100) AS concluiu
      FROM gold.fato_interacao f
     WHERE f.tipo_interacao IN ('visualização', 'início', 'conclusão')
     GROUP BY f.usuario_pseudo, f.conteudo_id
)
SELECT p.mes_inicio,
       d.categoria,
       d.tipo,
       d.nivel,
       count(*) AS pares_consumo,
       sum(CASE WHEN p.concluiu THEN 1 ELSE 0 END) AS pares_concluidos
  FROM pares p
  JOIN gold.dim_conteudo d ON d.conteudo_id = p.conteudo_id
 GROUP BY p.mes_inicio, d.categoria, d.tipo, d.nivel;

-- nome: vd_recomendacoes
-- finalidade: conversao das recomendacoes por categoria, classificacao e posicao na lista, e o tempo
--   ate a conversao. Soma igual a gold.kpi_conversao_recomendacao.
-- campos calculados:
--   data_geracao         gerado_em::date (funcao de data)
--   faixa_posicao        1 a 3, 4 a 6 ou 7 a 10 (CASE; ordem alfabetica = ordem da lista)
--   convertidas          recomendacoes seguidas de consumo do conteudo pela mesma pessoa (CASE)
--   dias_ate_converter   media de (convertida_em - gerado_em) em dias, so das convertidas
--   conversao no grafico 100 * SUM(convertidas) / SUM(recomendacoes)
SELECT r.gerado_em::date AS data_geracao,
       d.categoria,
       d.nivel,
       r.classificacao,
       CASE WHEN r.posicao <= 3 THEN '1 a 3'
            WHEN r.posicao <= 6 THEN '4 a 6'
            ELSE '7 a 10' END AS faixa_posicao,
       count(*) AS recomendacoes,
       sum(CASE WHEN r.convertida THEN 1 ELSE 0 END) AS convertidas,
       round(avg(EXTRACT(EPOCH FROM r.convertida_em - r.gerado_em) / 86400)
             FILTER (WHERE r.convertida)::numeric, 1) AS dias_ate_converter
  FROM gold.fato_recomendacao r
  JOIN gold.dim_conteudo d ON d.conteudo_id = r.conteudo_id
 GROUP BY 1, 2, 3, 4, 5;

-- nome: vd_avaliacao_x_conclusao
-- finalidade: cruzar qualidade percebida e conclusao por categoria, para separar "conteudo ruim"
--   de "conteudo bom que nao e terminado" (pergunta do storytelling, RF16).
-- campos calculados:
--   avaliacao_media   media ponderada pelas avaliacoes (1 a 5)
--   taxa_conclusao    100 * pares concluidos / pares com consumo
--   quadrante         posicao da categoria em relacao as medias do catalogo inteiro, as dos cartoes (CASE)
WITH conclusao AS (
    SELECT categoria,
           round(100.0 * sum(pares_concluidos) / sum(pares_consumo), 1) AS taxa_conclusao,
           sum(pares_consumo) AS pares_consumo
      FROM gold.kpi_taxa_conclusao
     GROUP BY categoria
), avaliacao AS (
    SELECT categoria,
           round(sum(avaliacao_media * avaliacoes) / sum(avaliacoes), 2) AS avaliacao_media,
           sum(avaliacoes) AS avaliacoes
      FROM gold.kpi_avaliacao
     GROUP BY categoria
), geral AS (  -- medias do catalogo inteiro (as dos cartoes do dashboard), e nao a media simples das categorias
    SELECT (SELECT 100.0 * sum(pares_concluidos) / sum(pares_consumo) FROM gold.kpi_taxa_conclusao) AS conclusao_media,
           (SELECT sum(avaliacao_media * avaliacoes) / sum(avaliacoes) FROM gold.kpi_avaliacao) AS avaliacao_geral
)
SELECT c.categoria,
       a.avaliacao_media,
       c.taxa_conclusao,
       c.pares_consumo,
       a.avaliacoes,
       CASE WHEN a.avaliacao_media >= g.avaliacao_geral AND c.taxa_conclusao < g.conclusao_media
                 THEN 'bem avaliada, pouco concluída'
            WHEN a.avaliacao_media >= g.avaliacao_geral THEN 'bem avaliada e concluída'
            WHEN c.taxa_conclusao < g.conclusao_media THEN 'avaliação e conclusão abaixo da média'
            ELSE 'concluída, avaliação abaixo da média' END AS quadrante
  FROM conclusao c
  JOIN avaliacao a USING (categoria)
 CROSS JOIN geral g
 ORDER BY c.taxa_conclusao;

-- nome: vd_pessoas_engajadas
-- finalidade: listar as pessoas mais engajadas sem expor dado pessoal: a pessoa aparece so pelo nome
--   mascarado e pelo pseudonimo (RF33). Mostra o que o consumo ve no lugar dos dados originais.
-- campos calculados:
--   interacoes         total de interacoes da pessoa (agregacao)
--   conteudos          conteudos distintos com interacao
--   conclusoes         interacoes do tipo conclusao (CASE)
--   ultima_interacao   data da ultima interacao (funcao de data)
SELECT u.nome_mascarado,
       left(u.usuario_pseudo, 12) AS pseudonimo,
       u.faixa_etaria,
       u.uf,
       count(*) AS interacoes,
       count(DISTINCT f.conteudo_id) AS conteudos,
       sum(CASE WHEN f.tipo_interacao = 'conclusão' THEN 1 ELSE 0 END) AS conclusoes,
       max(f.data_hora)::date AS ultima_interacao
  FROM gold.fato_interacao f
  JOIN gold.dim_usuario u ON u.usuario_pseudo = f.usuario_pseudo
 GROUP BY u.usuario_pseudo, u.nome_mascarado, u.faixa_etaria, u.uf;
