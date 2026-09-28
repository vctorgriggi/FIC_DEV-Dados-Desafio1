-- Desafio 2: estruturas compartilhadas entre as etapas (contratos em documentacao/contratos.md).
-- Idempotente. Aplicado pelo servico db-init (docker/postgres/inicializar.sh), que define as
-- variaveis psql :consumo_usuario e :consumo_senha.
-- O schema public continua sendo o banco do Desafio 1 e e tratado como fonte, nunca alterado aqui.
-- Tabelas da camada Gold e regras de transformacao ficam com cada responsavel (sql/camada_gold.sql, hop/).

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- digest() e hmac() para as tecnicas de protecao (RF33)
CREATE EXTENSION IF NOT EXISTS unaccent;  -- comparacao sem acento nas validacoes da Silver

CREATE SCHEMA IF NOT EXISTS controle;    -- execucoes e etapas do workflow (RF22)
CREATE SCHEMA IF NOT EXISTS bronze;      -- copia auditavel das fontes (RF20)
CREATE SCHEMA IF NOT EXISTS silver;      -- dados padronizados, validados e deduplicados (RF21, RF30)
CREATE SCHEMA IF NOT EXISTS quarentena;  -- registros rejeitados e reprocessamento (RF23)
CREATE SCHEMA IF NOT EXISTS qualidade;   -- testes e resultados por execucao (RF31)
CREATE SCHEMA IF NOT EXISTS gold;        -- consumo analitico (RF26); objetos em sql/camada_gold.sql
CREATE SCHEMA IF NOT EXISTS restrito;    -- tabelas de correspondencia de pseudonimos (RF33)
CREATE SCHEMA IF NOT EXISTS lgpd;        -- funcoes de protecao (RF33)

-- ---------------------------------------------------------------
-- controle: toda execucao, completa ou de uma etapa isolada, abre uma linha em execucao
-- ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS controle.execucao (
    execucao_id  TEXT PRIMARY KEY,
    fluxo        TEXT NOT NULL,  -- 'completo' ou o nome da etapa executada isoladamente
    modo         TEXT NOT NULL DEFAULT 'manual' CHECK (modo IN ('manual', 'agendado')),
    inicio       TIMESTAMPTZ NOT NULL DEFAULT now(),
    fim          TIMESTAMPTZ,
    status       TEXT NOT NULL DEFAULT 'em_andamento'
                 CHECK (status IN ('em_andamento', 'sucesso', 'sucesso_com_ressalvas', 'falha')),
    mensagem     TEXT
);

CREATE TABLE IF NOT EXISTS controle.etapa (
    execucao_id  TEXT NOT NULL REFERENCES controle.execucao (execucao_id),
    etapa        TEXT NOT NULL,  -- bronze, silver, qualidade, gold, metadados, parquet, beam
    inicio       TIMESTAMPTZ NOT NULL DEFAULT now(),
    fim          TIMESTAMPTZ,
    duracao_s    NUMERIC(12, 3) GENERATED ALWAYS AS (EXTRACT(EPOCH FROM fim - inicio)) STORED,
    status       TEXT NOT NULL DEFAULT 'em_andamento'
                 CHECK (status IN ('em_andamento', 'sucesso', 'sucesso_com_ressalvas', 'falha', 'ignorada')),
    lidos        INTEGER,
    gravados     INTEGER,
    quarentena   INTEGER,
    mensagem     TEXT,
    PRIMARY KEY (execucao_id, etapa)
);

-- ---------------------------------------------------------------
-- bronze: campos como TEXT, exatamente como vieram; append-only.
-- Auditoria: _execucao_id, _origem (arquivo ou tabela), _linha (posicao na fonte), _ingerido_em.
-- ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS bronze.catalogo (
    conteudo_id TEXT, titulo TEXT, tipo TEXT, categoria TEXT, nivel TEXT,
    carga_horaria_min TEXT, data_publicacao TEXT, descricao TEXT, autor TEXT,
    _execucao_id TEXT NOT NULL, _origem TEXT NOT NULL, _linha INTEGER, _ingerido_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bronze.interacoes (
    usuario_id TEXT, conteudo_id TEXT, tipo_interacao TEXT, data_hora TEXT,
    tempo_consumido TEXT, percentual_conclusao TEXT, avaliacao_atribuida TEXT,
    _execucao_id TEXT NOT NULL, _origem TEXT NOT NULL, _linha INTEGER, _ingerido_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bronze.comentarios (
    usuario_id TEXT, conteudo_id TEXT, avaliacao TEXT, comentario TEXT,
    tags TEXT,  -- o valor JSON original, ex. '["lgpd","essencial"]'
    data TEXT,
    _execucao_id TEXT NOT NULL, _origem TEXT NOT NULL, _linha INTEGER, _ingerido_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- contem dados pessoais (ficticios): acesso restrito ao dono do banco
CREATE TABLE IF NOT EXISTS bronze.usuarios (
    usuario_id TEXT, nome TEXT, email TEXT, cpf TEXT, data_nascimento TEXT, telefone TEXT,
    cidade TEXT, uf TEXT, data_cadastro TEXT, atualizado_em TEXT,
    _execucao_id TEXT NOT NULL, _origem TEXT NOT NULL, _linha INTEGER, _ingerido_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- fonte: dados/brutos/recomendacoes_desafio1.json, snapshot fixo do resultado entregue no Desafio 1.
-- Nem public.recomendacao nem dados/processados/recomendacoes.json servem: cada execucao do
-- pipeline do Desafio 1 regrava os dois com gerado_em do dia, e a conversao deixa de ser mensuravel.
CREATE TABLE IF NOT EXISTS bronze.recomendacoes (
    usuario_id TEXT, conteudo_id TEXT, ivis TEXT, icur TEXT, iconc TEXT, pontuacao TEXT,
    classificacao TEXT, afinidade TEXT, posicao TEXT, gerado_em TEXT,
    _execucao_id TEXT NOT NULL, _origem TEXT NOT NULL, _linha INTEGER, _ingerido_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_bronze_catalogo_exec      ON bronze.catalogo (_execucao_id);
CREATE INDEX IF NOT EXISTS ix_bronze_interacoes_exec    ON bronze.interacoes (_execucao_id);
CREATE INDEX IF NOT EXISTS ix_bronze_comentarios_exec   ON bronze.comentarios (_execucao_id);
CREATE INDEX IF NOT EXISTS ix_bronze_usuarios_exec      ON bronze.usuarios (_execucao_id);
CREATE INDEX IF NOT EXISTS ix_bronze_recomendacoes_exec ON bronze.recomendacoes (_execucao_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_bronze_catalogo_exec_origem_linha
    ON bronze.catalogo (_execucao_id, _origem, _linha);

CREATE OR REPLACE FUNCTION bronze.ignorar_catalogo_repetido()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM bronze.catalogo
        WHERE _execucao_id = NEW._execucao_id
          AND _origem = NEW._origem
          AND _linha = NEW._linha
    ) THEN
        RETURN NULL;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_bronze_catalogo_idempotencia ON bronze.catalogo;
CREATE TRIGGER trg_bronze_catalogo_idempotencia
BEFORE INSERT ON bronze.catalogo
FOR EACH ROW
EXECUTE FUNCTION bronze.ignorar_catalogo_repetido();

-- ---------------------------------------------------------------
-- silver: tipada, padronizada, deduplicada; recarga completa a cada execucao, em transacao.
-- Auditoria herdada da bronze: _execucao_id, _origem, _ingerido_em.
-- Sem dado pessoal direto: nome, e-mail, CPF, telefone e nascimento so existem na bronze.
-- ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS silver.conteudo (
    conteudo_id        INTEGER PRIMARY KEY,
    titulo             TEXT NOT NULL,
    tipo               TEXT NOT NULL CHECK (tipo IN ('Curso', 'Vídeo', 'Artigo', 'Podcast')),
    categoria          TEXT NOT NULL,
    nivel              TEXT NOT NULL CHECK (nivel IN ('Básico', 'Intermediário', 'Avançado')),
    carga_horaria_min  INTEGER NOT NULL CHECK (carga_horaria_min >= 0),
    data_publicacao    DATE NOT NULL,
    descricao          TEXT,
    autor              TEXT,
    _execucao_id TEXT NOT NULL, _origem TEXT NOT NULL, _ingerido_em TIMESTAMPTZ NOT NULL
);

-- um registro por usuario_id da fonte, ja com as tecnicas de protecao aplicadas
CREATE TABLE IF NOT EXISTS silver.usuario (
    usuario_id       INTEGER PRIMARY KEY,
    usuario_pseudo   TEXT NOT NULL UNIQUE,  -- lgpd.pseudonimizar(usuario_id)
    nome_mascarado   TEXT,                  -- lgpd.mascarar_nome(nome)
    email_mascarado  TEXT,                  -- lgpd.mascarar_email(email)
    email_hash       TEXT,                  -- lgpd.hash_salt(e-mail normalizado)
    cpf_hash         TEXT,                  -- lgpd.hash_salt(CPF so com digitos)
    faixa_etaria     TEXT,                  -- derivada de data_nascimento, que nao sobe para a silver
    cidade           TEXT,
    uf               CHAR(2),
    data_cadastro    DATE,
    atualizado_em    TIMESTAMP,
    _execucao_id TEXT NOT NULL, _origem TEXT NOT NULL, _ingerido_em TIMESTAMPTZ NOT NULL
);

-- dados mestres (RF30): usuario_ids que representam a mesma pessoa apontam para um mestre
CREATE TABLE IF NOT EXISTS silver.usuario_mestre (
    usuario_mestre_id  INTEGER PRIMARY KEY,
    usuario_pseudo     TEXT NOT NULL UNIQUE,  -- pseudonimo do mestre, usado na gold
    nome_mascarado     TEXT,
    email_mascarado    TEXT,
    faixa_etaria       TEXT,
    cidade             TEXT,
    uf                 CHAR(2),
    data_cadastro      DATE,
    atualizado_em      TIMESTAMP,
    registros_origem   INTEGER NOT NULL,      -- quantos usuario_id foram consolidados
    _execucao_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS silver.usuario_correspondencia (
    usuario_id         INTEGER PRIMARY KEY REFERENCES silver.usuario (usuario_id),
    usuario_mestre_id  INTEGER NOT NULL REFERENCES silver.usuario_mestre (usuario_mestre_id),
    regra              TEXT NOT NULL,  -- ex.: 'proprio', 'cpf_hash', 'email_hash'
    _execucao_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS silver.interacao (
    interacao_id          BIGSERIAL PRIMARY KEY,
    usuario_id            INTEGER NOT NULL REFERENCES silver.usuario (usuario_id),
    conteudo_id           INTEGER NOT NULL REFERENCES silver.conteudo (conteudo_id),
    tipo_interacao        TEXT NOT NULL CHECK (tipo_interacao IN
                              ('visualização', 'início', 'conclusão', 'curtida', 'avaliação', 'compartilhamento')),
    data_hora             TIMESTAMP NOT NULL,
    tempo_consumido       INTEGER CHECK (tempo_consumido >= 0),
    percentual_conclusao  NUMERIC(5, 2) CHECK (percentual_conclusao BETWEEN 0 AND 100),
    avaliacao_atribuida   SMALLINT CHECK (avaliacao_atribuida BETWEEN 1 AND 5),
    _execucao_id TEXT NOT NULL, _origem TEXT NOT NULL, _ingerido_em TIMESTAMPTZ NOT NULL,
    UNIQUE (usuario_id, conteudo_id, tipo_interacao, data_hora)
);

-- comentario ja anonimizado: e-mails e telefones do texto livre substituidos (lgpd.anonimizar_texto)
CREATE TABLE IF NOT EXISTS silver.comentario (
    comentario_id  BIGSERIAL PRIMARY KEY,
    usuario_id     INTEGER NOT NULL REFERENCES silver.usuario (usuario_id),
    conteudo_id    INTEGER NOT NULL REFERENCES silver.conteudo (conteudo_id),
    avaliacao      SMALLINT NOT NULL CHECK (avaliacao BETWEEN 1 AND 5),
    comentario     TEXT NOT NULL,
    tags           TEXT[] NOT NULL DEFAULT '{}',
    data           DATE NOT NULL,
    _execucao_id TEXT NOT NULL, _origem TEXT NOT NULL, _ingerido_em TIMESTAMPTZ NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_silver_comentario_chave
    ON silver.comentario (usuario_id, conteudo_id, data, md5(comentario));

CREATE TABLE IF NOT EXISTS silver.recomendacao (
    usuario_id     INTEGER NOT NULL REFERENCES silver.usuario (usuario_id),
    conteudo_id    INTEGER NOT NULL REFERENCES silver.conteudo (conteudo_id),
    pontuacao      NUMERIC(5, 2) NOT NULL CHECK (pontuacao BETWEEN 0 AND 100),
    posicao        INTEGER NOT NULL CHECK (posicao > 0),
    classificacao  TEXT NOT NULL CHECK (classificacao IN ('positivo', 'estavel', 'negativo')),
    gerado_em      TIMESTAMP NOT NULL,
    _execucao_id TEXT NOT NULL, _origem TEXT NOT NULL, _ingerido_em TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (usuario_id, conteudo_id, gerado_em)
);

-- ---------------------------------------------------------------
-- quarentena (RF23): uma tabela para todas as fontes; o registro original vai em JSONB.
-- Correcao: editar registro, status -> 'corrigido'; a proxima silver o reprocessa e marca 'reprocessado'.
-- ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS quarentena.registro (
    quarentena_id             BIGSERIAL PRIMARY KEY,
    execucao_id               TEXT NOT NULL,
    camada                    TEXT NOT NULL CHECK (camada IN ('bronze', 'silver', 'gold')),
    fonte                     TEXT NOT NULL,  -- catalogo, interacoes, comentarios, usuarios, recomendacoes
    chave_registro            TEXT,           -- id de negocio quando existir; senao a _linha da bronze
    regra                     TEXT NOT NULL,  -- codigo da regra violada (documentacao/contratos.md)
    severidade                TEXT NOT NULL CHECK (severidade IN ('critica', 'alta', 'media', 'baixa')),
    mensagem                  TEXT NOT NULL,
    registro                  JSONB NOT NULL,
    criado_em                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    status                    TEXT NOT NULL DEFAULT 'pendente'
                              CHECK (status IN ('pendente', 'corrigido', 'reprocessado', 'descartado')),
    corrigido_em              TIMESTAMPTZ,
    reprocessado_em           TIMESTAMPTZ,
    reprocessado_execucao_id  TEXT
);
CREATE INDEX IF NOT EXISTS ix_quarentena_status   ON quarentena.registro (status);
CREATE INDEX IF NOT EXISTS ix_quarentena_execucao ON quarentena.registro (execucao_id);

CREATE OR REPLACE FUNCTION controle.finalizar_execucao(p_execucao_id TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_status TEXT;
BEGIN
    v_status := CASE
        WHEN EXISTS (
            SELECT 1 FROM quarentena.registro
             WHERE execucao_id = p_execucao_id
               AND status = 'pendente'
        ) THEN 'sucesso_com_ressalvas'
        ELSE 'sucesso'
    END;

    UPDATE controle.execucao
       SET status = v_status,
           fim = COALESCE(fim, now()),
           mensagem = CASE WHEN v_status = 'sucesso_com_ressalvas'
                           THEN 'Execucao concluida com registros pendentes na quarentena'
                           ELSE 'Execucao concluida'
                      END
     WHERE execucao_id = p_execucao_id
       AND status = 'em_andamento';

    RETURN v_status;
END;
$$;

-- ---------------------------------------------------------------
-- qualidade (RF31): definicao dos testes e resultado por execucao e por fonte
-- ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS qualidade.teste (
    teste_id          TEXT PRIMARY KEY,  -- ex.: 'Q01_COMPLETUDE_CONTEUDO'
    nome              TEXT NOT NULL,
    dimensao          TEXT NOT NULL CHECK (dimensao IN
                          ('completude', 'validade', 'unicidade', 'consistencia', 'integridade_referencial')),
    alvo              TEXT NOT NULL,     -- tabela ou tabela.campo avaliado
    formula           TEXT NOT NULL,
    operador          TEXT NOT NULL CHECK (operador IN ('>=', '<=')),
    limite_aceitavel  NUMERIC NOT NULL,  -- valor_medido <operador> limite_aceitavel => aprovado
    severidade        TEXT NOT NULL CHECK (severidade IN ('critica', 'alta', 'media', 'baixa')),
    acao              TEXT NOT NULL      -- o que acontece quando reprova (critica bloqueia a gold)
);

CREATE TABLE IF NOT EXISTS qualidade.resultado (
    resultado_id       BIGSERIAL PRIMARY KEY,
    execucao_id        TEXT NOT NULL,
    teste_id           TEXT NOT NULL REFERENCES qualidade.teste (teste_id),
    fonte              TEXT NOT NULL,
    total_registros    INTEGER NOT NULL,
    registros_falhos   INTEGER NOT NULL,
    valor_medido       NUMERIC NOT NULL,
    aprovado           BOOLEAN NOT NULL,
    executado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (execucao_id, teste_id, fonte)
);

-- ---------------------------------------------------------------
-- restrito (RF33): correspondencia usuario_id <-> pseudonimo, para reidentificacao controlada
-- ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS restrito.usuario_pseudonimo (
    usuario_id      INTEGER PRIMARY KEY,
    usuario_pseudo  TEXT NOT NULL UNIQUE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------
-- lgpd (RF33): funcoes de protecao. Chave e salt vem do .env (LGPD_CHAVE_PSEUDONIMO, LGPD_SALT)
-- como parametro; nunca ficam gravados no banco nem no repositorio.
-- ---------------------------------------------------------------

-- pseudonimizacao: HMAC-SHA256 com chave secreta; deterministica, permite associacao controlada
CREATE OR REPLACE FUNCTION lgpd.pseudonimizar(valor TEXT, chave TEXT) RETURNS TEXT
    LANGUAGE sql IMMUTABLE STRICT
    RETURN encode(hmac(valor, chave, 'sha256'), 'hex');

-- hashing com salt: SHA-256(salt || valor); comparacao irreversivel
CREATE OR REPLACE FUNCTION lgpd.hash_salt(valor TEXT, salt TEXT) RETURNS TEXT
    LANGUAGE sql IMMUTABLE STRICT
    RETURN encode(digest(salt || valor, 'sha256'), 'hex');

-- mascaramento para exibicao: 'ana.souza@plataforma.example' -> 'a***@plataforma.example'
CREATE OR REPLACE FUNCTION lgpd.mascarar_email(email TEXT) RETURNS TEXT
    LANGUAGE sql IMMUTABLE STRICT
    RETURN left(email, 1) || '***' || substring(email FROM '@.*$');

-- mascaramento para exibicao: 'Ana Paula Souza' -> 'Ana S***'; nome unico 'Ana' -> 'A***'
CREATE OR REPLACE FUNCTION lgpd.mascarar_nome(nome TEXT) RETURNS TEXT
    LANGUAGE sql IMMUTABLE STRICT
    RETURN CASE WHEN btrim(nome) ~ '\s'
                THEN split_part(btrim(nome), ' ', 1) || ' ' || left(substring(btrim(nome) FROM '(\S+)$'), 1) || '***'
                ELSE left(btrim(nome), 1) || '***' END;

-- texto livre: substitui e-mails e telefones por marcadores
CREATE OR REPLACE FUNCTION lgpd.anonimizar_texto(texto TEXT) RETURNS TEXT
    LANGUAGE sql IMMUTABLE STRICT
    RETURN regexp_replace(
             regexp_replace(texto, '[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}', '[email]', 'g'),
             '\(?\d{2}\)?\s?9?\d{4}-?\d{4}', '[telefone]', 'g');

-- ---------------------------------------------------------------
-- papel de consumo: somente leitura de gold, qualidade e controle (Superset, SQL Lab)
-- ---------------------------------------------------------------

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'consumo_usuario', :'consumo_senha')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'consumo_usuario') \gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'consumo_usuario', :'consumo_senha') \gexec

GRANT USAGE ON SCHEMA gold, qualidade, controle TO :"consumo_usuario";
GRANT SELECT ON ALL TABLES IN SCHEMA gold, qualidade, controle TO :"consumo_usuario";
ALTER DEFAULT PRIVILEGES IN SCHEMA gold, qualidade, controle GRANT SELECT ON TABLES TO :"consumo_usuario";
