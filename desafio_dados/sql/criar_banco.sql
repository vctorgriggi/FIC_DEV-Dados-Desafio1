-- Modelo relacional do desafio (RF06) + vetores (RF08).
-- Idempotente: pode rodar mais de uma vez.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS categoria (
    categoria_id  SERIAL PRIMARY KEY,
    nome          TEXT NOT NULL UNIQUE
);

-- nao ha fonte de usuarios: sao derivados das interacoes e comentarios
CREATE TABLE IF NOT EXISTS usuario (
    usuario_id    INTEGER PRIMARY KEY,
    criado_em     TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conteudo (
    conteudo_id        INTEGER PRIMARY KEY,
    titulo             TEXT NOT NULL,
    tipo               TEXT NOT NULL CHECK (tipo IN ('Curso', 'Vídeo', 'Artigo', 'Podcast')),
    categoria_id       INTEGER NOT NULL REFERENCES categoria (categoria_id),
    nivel              TEXT NOT NULL CHECK (nivel IN ('Básico', 'Intermediário', 'Avançado')),
    carga_horaria_min  INTEGER NOT NULL CHECK (carga_horaria_min >= 0),
    data_publicacao    DATE NOT NULL,
    descricao          TEXT,
    autor              TEXT
);

CREATE TABLE IF NOT EXISTS interacao (
    interacao_id          BIGSERIAL PRIMARY KEY,
    usuario_id            INTEGER NOT NULL REFERENCES usuario (usuario_id),
    conteudo_id           INTEGER NOT NULL REFERENCES conteudo (conteudo_id),
    tipo_interacao        TEXT NOT NULL CHECK (tipo_interacao IN
                              ('visualização', 'início', 'conclusão', 'curtida', 'avaliação', 'compartilhamento')),
    data_hora             TIMESTAMP NOT NULL,
    tempo_consumido       INTEGER CHECK (tempo_consumido >= 0),
    percentual_conclusao  NUMERIC(5, 2) CHECK (percentual_conclusao BETWEEN 0 AND 100),
    avaliacao_atribuida   SMALLINT CHECK (avaliacao_atribuida BETWEEN 1 AND 5),
    UNIQUE (usuario_id, conteudo_id, tipo_interacao, data_hora)
);

-- um embedding por conteudo; dimensao fixada pelo modelo em config.yaml
CREATE TABLE IF NOT EXISTS conteudo_embedding (
    conteudo_id  INTEGER PRIMARY KEY REFERENCES conteudo (conteudo_id),
    modelo       TEXT NOT NULL,
    embedding    VECTOR(384) NOT NULL,
    gerado_em    TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recomendacao (
    recomendacao_id  BIGSERIAL PRIMARY KEY,
    usuario_id       INTEGER NOT NULL REFERENCES usuario (usuario_id),
    conteudo_id      INTEGER NOT NULL REFERENCES conteudo (conteudo_id),
    pontuacao        NUMERIC(5, 2) NOT NULL CHECK (pontuacao BETWEEN 0 AND 100),
    posicao          INTEGER NOT NULL CHECK (posicao > 0),
    classificacao    TEXT NOT NULL CHECK (classificacao IN ('positivo', 'estavel', 'negativo')),
    gerado_em        TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (usuario_id, conteudo_id, gerado_em)
);

-- metrica operacional do proprio pipeline: uma linha por execucao (RF05/RF14)
CREATE TABLE IF NOT EXISTS execucao_pipeline (
    execucao_id       BIGSERIAL PRIMARY KEY,
    executado_em      TIMESTAMP NOT NULL DEFAULT now(),
    registros_lidos   INTEGER NOT NULL,
    validos           INTEGER NOT NULL,
    invalidos         INTEGER NOT NULL,
    incompletos       INTEGER NOT NULL,
    duplicados        INTEGER NOT NULL,
    corrigidos        INTEGER NOT NULL,
    comentarios_mongo INTEGER,
    embeddings_gerados INTEGER,
    recomendacoes     INTEGER
);

CREATE INDEX IF NOT EXISTS ix_interacao_usuario     ON interacao (usuario_id);
CREATE INDEX IF NOT EXISTS ix_interacao_conteudo    ON interacao (conteudo_id);
CREATE INDEX IF NOT EXISTS ix_interacao_data        ON interacao (data_hora);
CREATE INDEX IF NOT EXISTS ix_recomendacao_usuario  ON recomendacao (usuario_id);
CREATE INDEX IF NOT EXISTS ix_embedding_cosine      ON conteudo_embedding USING hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------
-- RF12: metricas operacionais (vw_*) e KPIs (vw_kpi_*) para o Superset
-- views sao dropadas e recriadas para permitir mudanca de colunas
-- ---------------------------------------------------------------

-- objeto de versao anterior; removido para manter bancos ja criados consistentes
DROP VIEW IF EXISTS vw_recomendacoes;

-- fato: interacoes com atributos do conteudo (base de filtros: categoria, tipo, nivel, mes)
DROP VIEW IF EXISTS vw_interacoes CASCADE;
CREATE VIEW vw_interacoes AS
SELECT i.interacao_id, i.usuario_id, i.conteudo_id, i.tipo_interacao, i.data_hora,
       date_trunc('month', i.data_hora)::date AS mes,
       i.tempo_consumido, i.percentual_conclusao, i.avaliacao_atribuida,
       c.titulo, c.tipo, c.nivel, cat.nome AS categoria
FROM interacao i
JOIN conteudo c    ON c.conteudo_id = i.conteudo_id
JOIN categoria cat ON cat.categoria_id = c.categoria_id;

-- M1: volume da plataforma (cartoes)
DROP VIEW IF EXISTS vw_metricas_gerais;
CREATE VIEW vw_metricas_gerais AS
SELECT (SELECT count(*) FROM usuario)                             AS usuarios,
       (SELECT count(DISTINCT usuario_id) FROM interacao)         AS usuarios_ativos,
       (SELECT count(*) FROM conteudo)                            AS conteudos,
       (SELECT count(*) FROM interacao)                           AS interacoes,
       (SELECT round(avg(tempo_consumido), 1) FROM interacao)     AS tempo_medio_min,
       (SELECT count(*) FROM recomendacao)                        AS recomendacoes,
       (SELECT round(100.0 * count(DISTINCT usuario_id) / NULLIF((SELECT count(*) FROM usuario), 0), 1)
          FROM recomendacao)                                       AS cobertura_recomendacao_pct,
       (SELECT count(*) FROM conteudo_embedding)                  AS embeddings;

-- M2: uso mensal (linhas), com categoria/tipo para os filtros
DROP VIEW IF EXISTS vw_uso_mensal;
CREATE VIEW vw_uso_mensal AS
SELECT mes, categoria, tipo,
       count(*)                                                 AS interacoes,
       count(*) FILTER (WHERE tipo_interacao = 'visualização')  AS visualizacoes,
       count(DISTINCT usuario_id)                               AS usuarios_ativos,
       sum(tempo_consumido)                                     AS tempo_total_min
FROM vw_interacoes
GROUP BY mes, categoria, tipo;

-- M3: conteudos mais procurados
DROP VIEW IF EXISTS vw_conteudos_populares;
CREATE VIEW vw_conteudos_populares AS
SELECT conteudo_id, titulo, categoria, tipo, nivel,
       count(*) FILTER (WHERE tipo_interacao = 'visualização') AS visualizacoes,
       count(DISTINCT usuario_id)                              AS usuarios,
       round(avg(tempo_consumido), 1)                          AS tempo_medio_min,
       round(avg(avaliacao_atribuida), 2)                      AS avaliacao_media
FROM vw_interacoes
GROUP BY conteudo_id, titulo, categoria, tipo, nivel;

-- KPI1: taxa de conclusao = pares (usuario, conteudo) concluidos / pares com consumo
DROP VIEW IF EXISTS vw_kpi_taxa_conclusao;
CREATE VIEW vw_kpi_taxa_conclusao AS
WITH consumo AS (
    SELECT usuario_id, conteudo_id, categoria, tipo, nivel,
           bool_or(tipo_interacao = 'conclusão' OR percentual_conclusao >= 100) AS concluiu
    FROM vw_interacoes
    WHERE tipo_interacao IN ('visualização', 'início', 'conclusão')
    GROUP BY usuario_id, conteudo_id, categoria, tipo, nivel
)
SELECT categoria, tipo, nivel,
       count(*)                         AS consumos,
       count(*) FILTER (WHERE concluiu) AS conclusoes,
       round(100.0 * count(*) FILTER (WHERE concluiu) / count(*), 1) AS taxa_conclusao_pct
FROM consumo
GROUP BY categoria, tipo, nivel;

-- KPI2: qualidade percebida = avaliacao media e % de avaliacoes positivas (>= 4)
DROP VIEW IF EXISTS vw_kpi_qualidade;
CREATE VIEW vw_kpi_qualidade AS
SELECT categoria, tipo, nivel,
       count(avaliacao_atribuida)         AS avaliacoes,
       round(avg(avaliacao_atribuida), 2) AS avaliacao_media,
       round(100.0 * count(*) FILTER (WHERE avaliacao_atribuida >= 4)
             / NULLIF(count(avaliacao_atribuida), 0), 1) AS pct_positivas
FROM vw_interacoes
WHERE avaliacao_atribuida IS NOT NULL
GROUP BY categoria, tipo, nivel;

-- KPI3: retencao mensal = usuarios ativos no mes que voltam no mes seguinte; engajamento = interacoes por usuario ativo
DROP VIEW IF EXISTS vw_kpi_retencao_mensal;
CREATE VIEW vw_kpi_retencao_mensal AS
WITH ativos AS (
    SELECT usuario_id, mes, count(*) AS interacoes FROM vw_interacoes GROUP BY usuario_id, mes
), meses AS (
    SELECT mes, max(mes) OVER () AS ultimo_mes FROM ativos GROUP BY mes
)
SELECT a.mes,
       count(DISTINCT a.usuario_id)                           AS usuarios_ativos,
       sum(a.interacoes)                                      AS interacoes,
       round(sum(a.interacoes)::numeric / count(DISTINCT a.usuario_id), 2) AS interacoes_por_usuario,
       CASE WHEN m.mes = m.ultimo_mes THEN NULL
            ELSE count(DISTINCT b.usuario_id) END              AS usuarios_retidos,
       CASE WHEN m.mes = m.ultimo_mes THEN NULL
            ELSE round(100.0 * count(DISTINCT b.usuario_id) / count(DISTINCT a.usuario_id), 1) END AS retencao_pct
FROM ativos a
JOIN meses m ON m.mes = a.mes
LEFT JOIN ativos b ON b.usuario_id = a.usuario_id AND b.mes = (a.mes + interval '1 month')::date
GROUP BY a.mes, m.mes, m.ultimo_mes;

-- KPI4: cobertura da recomendacao = usuarios com recomendacao / usuarios, e distribuicao por classificacao
DROP VIEW IF EXISTS vw_kpi_recomendacao;
CREATE VIEW vw_kpi_recomendacao AS
SELECT r.classificacao, cat.nome AS categoria, c.tipo,
       count(*)                                    AS recomendacoes,
       count(DISTINCT r.usuario_id)                AS usuarios,
       round(avg(r.pontuacao), 1)                  AS pontuacao_media,
       round(100.0 * count(DISTINCT r.usuario_id) / (SELECT count(*) FROM usuario), 1) AS cobertura_pct
FROM recomendacao r
JOIN conteudo c    ON c.conteudo_id = r.conteudo_id
JOIN categoria cat ON cat.categoria_id = c.categoria_id
GROUP BY r.classificacao, cat.nome, c.tipo;
