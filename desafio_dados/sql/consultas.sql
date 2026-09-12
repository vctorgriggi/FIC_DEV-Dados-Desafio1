-- Consultas de apoio (RF06: consultar registros armazenados; RF12: metricas e KPIs)
-- uso: docker compose exec -T postgres psql -U desafio -d desafio -f - < sql/consultas.sql

-- RF06: registros por tabela
SELECT 'categoria' tabela, count(*) FROM categoria
UNION ALL SELECT 'usuario', count(*) FROM usuario
UNION ALL SELECT 'conteudo', count(*) FROM conteudo
UNION ALL SELECT 'interacao', count(*) FROM interacao
UNION ALL SELECT 'conteudo_embedding', count(*) FROM conteudo_embedding
UNION ALL SELECT 'recomendacao', count(*) FROM recomendacao;

-- RF06: conteudos de uma categoria com seus autores
SELECT c.conteudo_id, c.titulo, c.tipo, c.nivel, c.autor
FROM conteudo c JOIN categoria cat ON cat.categoria_id = c.categoria_id
WHERE cat.nome = 'Banco de Dados'
ORDER BY c.data_publicacao DESC
LIMIT 10;

-- RF06: historico de um usuario
SELECT i.data_hora, i.tipo_interacao, c.titulo, i.tempo_consumido, i.avaliacao_atribuida
FROM interacao i JOIN conteudo c USING (conteudo_id)
WHERE i.usuario_id = 1
ORDER BY i.data_hora;

-- RF11: recomendacoes de um usuario
SELECT r.posicao, r.conteudo_id, c.titulo, cat.nome AS categoria, r.pontuacao, r.classificacao, r.gerado_em
FROM recomendacao r
JOIN conteudo c USING (conteudo_id)
JOIN categoria cat ON cat.categoria_id = c.categoria_id
WHERE r.usuario_id = 1
ORDER BY r.posicao;

-- RF09: busca vetorial direta (vetor de exemplo: o do conteudo 1)
SELECT c.conteudo_id, c.titulo, 1 - (e.embedding <=> (SELECT embedding FROM conteudo_embedding WHERE conteudo_id = 1)) AS similaridade
FROM conteudo_embedding e JOIN conteudo c USING (conteudo_id)
ORDER BY e.embedding <=> (SELECT embedding FROM conteudo_embedding WHERE conteudo_id = 1)
LIMIT 5;

-- RF12 M1: volume da plataforma
SELECT * FROM vw_metricas_gerais;

-- RF12 M2: uso mensal
SELECT mes, sum(interacoes) interacoes, sum(visualizacoes) visualizacoes, sum(usuarios_ativos) usuarios_ativos
FROM vw_uso_mensal GROUP BY mes ORDER BY mes;

-- RF12 M3: conteudos mais procurados
SELECT titulo, categoria, tipo, visualizacoes, usuarios, avaliacao_media
FROM vw_conteudos_populares ORDER BY visualizacoes DESC, usuarios DESC LIMIT 10;

-- RF12 KPI1: taxa de conclusao por categoria
SELECT categoria, sum(consumos) consumos, sum(conclusoes) conclusoes,
       round(100.0 * sum(conclusoes) / sum(consumos), 1) taxa_conclusao_pct
FROM vw_kpi_taxa_conclusao GROUP BY categoria ORDER BY taxa_conclusao_pct DESC;

-- RF12 KPI2: qualidade percebida por tipo de conteudo
SELECT tipo, sum(avaliacoes) avaliacoes,
       round(sum(avaliacao_media * avaliacoes) / sum(avaliacoes), 2) avaliacao_media
FROM vw_kpi_qualidade GROUP BY tipo ORDER BY avaliacao_media DESC;

-- RF12 KPI3: retencao e engajamento mensal
SELECT * FROM vw_kpi_retencao_mensal ORDER BY mes;

-- RF12 KPI4: cobertura e distribuicao das recomendacoes
SELECT classificacao, sum(recomendacoes) recomendacoes, sum(usuarios) usuarios, round(avg(pontuacao_media), 1) pontuacao_media
FROM vw_kpi_recomendacao GROUP BY classificacao;

-- RF12: qualidade x conclusao por categoria (onde os alunos gostam mas nao terminam?)
SELECT q.categoria, q.avaliacao_media, t.taxa_conclusao_pct
FROM (SELECT categoria, round(sum(avaliacao_media * avaliacoes) / sum(avaliacoes), 2) avaliacao_media
      FROM vw_kpi_qualidade GROUP BY categoria) q
JOIN (SELECT categoria, round(100.0 * sum(conclusoes) / sum(consumos), 1) taxa_conclusao_pct
      FROM vw_kpi_taxa_conclusao GROUP BY categoria) t USING (categoria)
ORDER BY t.taxa_conclusao_pct;

-- RF14: historico de execucoes do pipeline
SELECT * FROM execucao_pipeline ORDER BY executado_em DESC;
