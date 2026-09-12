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

CREATE INDEX IF NOT EXISTS ix_interacao_usuario     ON interacao (usuario_id);
CREATE INDEX IF NOT EXISTS ix_interacao_conteudo    ON interacao (conteudo_id);
CREATE INDEX IF NOT EXISTS ix_interacao_data        ON interacao (data_hora);
CREATE INDEX IF NOT EXISTS ix_recomendacao_usuario  ON recomendacao (usuario_id);
CREATE INDEX IF NOT EXISTS ix_embedding_cosine      ON conteudo_embedding USING hnsw (embedding vector_cosine_ops);
