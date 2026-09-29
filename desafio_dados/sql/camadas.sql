-- Desafio 2: estruturas compartilhadas entre as etapas (contratos em documentacao/contratos.md).
-- Idempotente. Aplicado pelo servico db-init (docker/postgres/inicializar.sh), que define as
-- variaveis psql :consumo_usuario e :consumo_senha.
-- O schema public continua sendo o banco do Desafio 1 e e tratado como fonte, nunca alterado aqui.
-- Regras de validacao e publicacao da Silver: sql/silver.sql. Gold: sql/camada_gold.sql (Estudante 2).

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- digest() e hmac() para as tecnicas de protecao (RF33)
CREATE EXTENSION IF NOT EXISTS unaccent;  -- comparacao de dominios sem acento (sql/silver.sql)

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

-- tentativas anteriores de uma etapa: reprocessar uma etapa (workflows/isolado.hwf) reabre a linha de
-- controle.etapa; a versao anterior vem para ca antes, para a auditoria nao perder a execucao original
CREATE TABLE IF NOT EXISTS controle.etapa_historico (
    execucao_id   TEXT NOT NULL,
    etapa         TEXT NOT NULL,
    inicio        TIMESTAMPTZ NOT NULL,
    fim           TIMESTAMPTZ,
    duracao_s     NUMERIC(12, 3),
    status        TEXT NOT NULL,
    lidos         INTEGER,
    gravados      INTEGER,
    quarentena    INTEGER,
    mensagem      TEXT,
    substituida_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (execucao_id, etapa, inicio)
);

-- Ciclo de controle usado pelos workflows do Hop (hop/workflows/):
--   abrir_execucao -> iniciar_etapa -> concluir_etapa | registrar_falha | registrar_ignorada -> finalizar_execucao

-- abre uma execucao, ou reabre uma existente para reprocessar etapas; gera o UUID quando vazio
CREATE OR REPLACE FUNCTION controle.abrir_execucao(p_execucao_id TEXT, p_fluxo TEXT, p_modo TEXT DEFAULT 'manual')
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_id TEXT := COALESCE(NULLIF(btrim(p_execucao_id), ''), gen_random_uuid()::text);
BEGIN
    INSERT INTO controle.execucao (execucao_id, fluxo, modo)
    VALUES (v_id, p_fluxo, COALESCE(NULLIF(btrim(p_modo), ''), 'manual'))
    ON CONFLICT (execucao_id) DO UPDATE
       SET status = 'em_andamento', fim = NULL, mensagem = NULL;
    RETURN v_id;
END;
$$;

-- guarda em controle.etapa_historico a tentativa anterior de uma etapa antes de ela ser sobrescrita;
-- p_so_concluida: nao arquiva a tentativa em andamento (registrar_falha fecha a propria tentativa)
CREATE OR REPLACE FUNCTION controle.arquivar_etapa(p_execucao_id TEXT, p_etapa TEXT, p_so_concluida BOOLEAN)
RETURNS VOID
LANGUAGE sql
AS $$
    INSERT INTO controle.etapa_historico (execucao_id, etapa, inicio, fim, duracao_s, status, lidos, gravados,
                                          quarentena, mensagem)
    SELECT execucao_id, etapa, inicio, fim, duracao_s, status, lidos, gravados, quarentena, mensagem
      FROM controle.etapa
     WHERE execucao_id = p_execucao_id AND etapa = p_etapa
       AND NOT (p_so_concluida AND status = 'em_andamento')
    ON CONFLICT DO NOTHING;
$$;

CREATE OR REPLACE FUNCTION controle.iniciar_etapa(p_execucao_id TEXT, p_etapa TEXT)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM controle.arquivar_etapa(p_execucao_id, p_etapa, FALSE);
    INSERT INTO controle.etapa (execucao_id, etapa, status)
    VALUES (p_execucao_id, p_etapa, 'em_andamento')
    ON CONFLICT (execucao_id, etapa) DO UPDATE
       SET inicio = now(), fim = NULL, status = 'em_andamento',
           lidos = NULL, gravados = NULL, quarentena = NULL, mensagem = NULL;
END;
$$;

-- encerra a etapa com as contagens medidas no banco (controle.medir_etapa, abaixo);
-- registros em quarentena tornam a etapa 'sucesso_com_ressalvas'
CREATE OR REPLACE FUNCTION controle.concluir_etapa(p_execucao_id TEXT, p_etapa TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    m RECORD;
    v_status TEXT;
BEGIN
    SELECT * INTO m FROM controle.medir_etapa(p_execucao_id, p_etapa);
    v_status := CASE WHEN COALESCE(m.quarentena, 0) > 0 THEN 'sucesso_com_ressalvas' ELSE 'sucesso' END;
    UPDATE controle.etapa
       SET fim = now(), status = v_status,
           lidos = m.lidos, gravados = m.gravados, quarentena = m.quarentena, mensagem = m.mensagem
     WHERE execucao_id = p_execucao_id AND etapa = p_etapa;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'etapa % nao foi iniciada na execucao %', p_etapa, p_execucao_id;
    END IF;
    RETURN v_status;
END;
$$;

-- lidos, gravados e quarentena de cada etapa, medidos no banco. Cada etapa nova do fluxo ganha um ramo aqui.
--   bronze_<fonte>        linhas ingeridas nesta execucao
--   silver_<entidade>     bronze lida, aprovados e rejeitados na area de preparo (sql/silver.sql)
--   silver_publicacao     linhas publicadas e pendencias da quarentena encontradas nesta execucao
--   qualidade             testes avaliados, aprovados e reprovados (sql/qualidade.sql)
--   gold                  linhas publicadas na camada Gold (sql/camada_gold.sql)
CREATE OR REPLACE FUNCTION controle.medir_etapa(p_execucao_id TEXT, p_etapa TEXT)
RETURNS TABLE (lidos INTEGER, gravados INTEGER, quarentena INTEGER, mensagem TEXT)
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_nome TEXT := substr(p_etapa, 8);
    v_fonte TEXT;
    v_lidos INTEGER;
    v_gravados INTEGER;
    v_quarentena INTEGER;
    v_descartados INTEGER;
BEGIN
    IF p_etapa LIKE 'bronze\_%' THEN
        EXECUTE format('SELECT count(*) FROM bronze.%I WHERE _execucao_id = $1', v_nome) INTO v_lidos USING p_execucao_id;
        RETURN QUERY SELECT v_lidos, v_lidos, 0, NULL::text;
    ELSIF p_etapa = 'silver_publicacao' THEN
        SELECT (SELECT count(*) FROM silver.conteudo) + (SELECT count(*) FROM silver.usuario)
             + (SELECT count(*) FROM silver.interacao) + (SELECT count(*) FROM silver.comentario)
             + (SELECT count(*) FROM silver.recomendacao)
          INTO v_gravados;
        SELECT count(*) INTO v_quarentena FROM quarentena.registro q
         WHERE q.ultima_execucao_id = p_execucao_id AND q.status = 'pendente';
        RETURN QUERY SELECT NULL::integer, v_gravados, v_quarentena,
            format('%s usuarios consolidados em %s pessoas', (SELECT count(*) FROM silver.usuario),
                   (SELECT count(*) FROM silver.usuario_mestre));
    ELSIF p_etapa LIKE 'silver\_%' AND validacao.fonte_da_entidade(v_nome) IS NOT NULL THEN
        v_fonte := validacao.fonte_da_entidade(v_nome);
        EXECUTE format('SELECT count(*) FROM bronze.%I WHERE _execucao_id = $1', v_fonte) INTO v_lidos USING p_execucao_id;
        EXECUTE format('SELECT count(*) FROM validacao.%I WHERE _execucao_id = $1', v_nome) INTO v_gravados USING p_execucao_id;
        EXECUTE format('SELECT count(*) FROM validacao.%I WHERE execucao_id = $1', v_nome || '_rejeitado') INTO v_quarentena USING p_execucao_id;
        -- o que foi lido e nao esta nem na silver nem na quarentena: descartado na triagem, ou versao vencida
        -- por sobrevivencia (outra versao do mesmo registro prevaleceu); os dois continuam na bronze
        EXECUTE format($q$
            SELECT count(*) FROM bronze.%I b
              JOIN quarentena.registro q
                ON q.fonte = %L AND q.origem = b._origem AND q.linha = b._linha AND q.status = 'descartado'
               AND q.hash_origem = md5((to_jsonb(b) - '_execucao_id' - '_origem' - '_linha' - '_ingerido_em')::text)
             WHERE b._execucao_id = $1$q$, v_fonte, v_fonte) INTO v_descartados USING p_execucao_id;
        RETURN QUERY SELECT v_lidos, v_gravados, v_quarentena,
            NULLIF(concat_ws('; ',
                CASE WHEN v_lidos - v_gravados - v_quarentena - v_descartados > 0
                     THEN format('versoes vencidas por sobrevivencia: %s', v_lidos - v_gravados - v_quarentena - v_descartados) END,
                CASE WHEN v_descartados > 0
                     THEN format('descartados na triagem da quarentena: %s', v_descartados) END), '')
            || ' (continuam na bronze)';
    ELSIF p_etapa = 'qualidade' THEN
        -- reprovado nao critico deixa a etapa com ressalvas; reprovado critico e tratado pelo workflow como falha
        RETURN QUERY
            SELECT count(*)::integer, (count(*) FILTER (WHERE r.aprovado))::integer,
                   (count(*) FILTER (WHERE NOT r.aprovado))::integer,
                   CASE WHEN bool_and(r.aprovado) THEN 'todos os testes aprovados'
                        ELSE 'reprovados: ' || string_agg(DISTINCT r.teste_id || ' (' || r.fonte || ')', ', ')
                                               FILTER (WHERE NOT r.aprovado) END
              FROM qualidade.resultado r WHERE r.execucao_id = p_execucao_id;
    ELSIF p_etapa = 'metadados' THEN
        RETURN QUERY SELECT NULL::integer, NULL::integer, 0,
            'ingestoes do PostgreSQL e do Superset disparadas no OpenMetadata'::text;
    ELSIF p_etapa = 'gold' THEN
        RETURN QUERY
            SELECT NULL::integer, gold.contar_linhas()::integer, 0, NULL::text;
    ELSE
        RETURN QUERY SELECT NULL::integer, NULL::integer, NULL::integer, NULL::text;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION controle.registrar_falha(p_execucao_id TEXT, p_etapa TEXT, p_mensagem TEXT)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM controle.arquivar_etapa(p_execucao_id, p_etapa, TRUE);
    INSERT INTO controle.etapa (execucao_id, etapa, status, fim, mensagem)
    VALUES (p_execucao_id, p_etapa, 'falha', now(), p_mensagem)
    ON CONFLICT (execucao_id, etapa) DO UPDATE
       SET status = 'falha', fim = now(), mensagem = EXCLUDED.mensagem;
END;
$$;

-- etapa prevista no fluxo que nao roda nesta execucao: workflow ausente (opcional.hwf) ou servico fora do ar
-- (metadados sem o OpenMetadata)
CREATE OR REPLACE FUNCTION controle.registrar_ignorada(p_execucao_id TEXT, p_etapa TEXT, p_motivo TEXT)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM controle.arquivar_etapa(p_execucao_id, p_etapa, TRUE);
    INSERT INTO controle.etapa (execucao_id, etapa, status, fim, mensagem)
    VALUES (p_execucao_id, p_etapa, 'ignorada', now(), p_motivo)
    ON CONFLICT (execucao_id, etapa) DO UPDATE
       SET inicio = now(), status = 'ignorada', fim = now(), mensagem = EXCLUDED.mensagem,
           lidos = NULL, gravados = NULL, quarentena = NULL;
END;
$$;

-- status final a partir das etapas: falha > sucesso_com_ressalvas > sucesso.
-- Etapa ainda 'em_andamento' no fechamento significa que o processo foi interrompido: conta como falha.
CREATE OR REPLACE FUNCTION controle.finalizar_execucao(p_execucao_id TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_status TEXT;
BEGIN
    SELECT CASE
             WHEN bool_or(status IN ('falha', 'em_andamento')) THEN 'falha'
             WHEN bool_or(status = 'sucesso_com_ressalvas') THEN 'sucesso_com_ressalvas'
             ELSE 'sucesso'
           END
      INTO v_status
      FROM controle.etapa
     WHERE execucao_id = p_execucao_id;

    UPDATE controle.execucao
       SET status = COALESCE(v_status, 'falha'),
           fim = now(),
           mensagem = CASE COALESCE(v_status, 'falha')
                        WHEN 'falha' THEN 'encerrada por falha; ver controle.etapa'
                        WHEN 'sucesso_com_ressalvas' THEN 'concluida com registros em quarentena'
                        ELSE 'concluida'
                      END
     WHERE execucao_id = p_execucao_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'execucao % nao existe', p_execucao_id;
    END IF;
    RETURN COALESCE(v_status, 'falha');
END;
$$;

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

-- objetos de versoes anteriores desta base, removidos de bancos ja criados:
-- a bronze e append-only por execucao e nao precisa de trigger para ignorar repeticoes
DROP TRIGGER IF EXISTS trg_bronze_catalogo_idempotencia ON bronze.catalogo;
DROP FUNCTION IF EXISTS bronze.ignorar_catalogo_repetido();
DROP INDEX IF EXISTS bronze.ux_bronze_catalogo_exec_origem_linha;
DROP FUNCTION IF EXISTS controle.data_segura(TEXT);
DROP FUNCTION IF EXISTS controle.timestamp_seguro(TEXT);
DROP FUNCTION IF EXISTS controle.jsonb_seguro(TEXT);
DROP FUNCTION IF EXISTS controle.finalizar_etapa(TEXT, TEXT, TEXT, INTEGER, INTEGER, INTEGER, TEXT);

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
-- quarentena (RF23): uma linha por registro de origem rejeitado, para todas as fontes.
-- Identidade: (fonte, origem, linha, hash_origem). Como os arquivos de origem nao mudam, a mesma
-- rejeicao detectada de novo em outra execucao atualiza ultima_execucao_id em vez de duplicar.
-- Correcao: editar registro e mudar status para 'corrigido'. Da proxima vez que a Silver roda, a
-- versao corrigida substitui a da bronze; se passar, vira 'reprocessado' (e continua substituindo
-- nas execucoes seguintes). 'descartado' tira o registro do fluxo.
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
    registro                  JSONB NOT NULL,  -- editavel: e a versao usada no reprocessamento
    registro_original         JSONB,           -- como veio da bronze; nunca muda
    origem                    TEXT,            -- _origem da bronze
    linha                     INTEGER,         -- _linha da bronze
    hash_origem               TEXT,            -- md5 do registro original
    ultima_execucao_id        TEXT,            -- ultima execucao que ainda encontrou o problema
    criado_em                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    status                    TEXT NOT NULL DEFAULT 'pendente'
                              CHECK (status IN ('pendente', 'corrigido', 'reprocessado', 'descartado')),
    corrigido_em              TIMESTAMPTZ,
    reprocessado_em           TIMESTAMPTZ,
    reprocessado_execucao_id  TEXT
);
-- bancos criados antes das colunas de identidade
ALTER TABLE quarentena.registro
    ADD COLUMN IF NOT EXISTS registro_original JSONB,
    ADD COLUMN IF NOT EXISTS origem TEXT,
    ADD COLUMN IF NOT EXISTS linha INTEGER,
    ADD COLUMN IF NOT EXISTS hash_origem TEXT,
    ADD COLUMN IF NOT EXISTS ultima_execucao_id TEXT;
CREATE INDEX IF NOT EXISTS ix_quarentena_status   ON quarentena.registro (status);
CREATE INDEX IF NOT EXISTS ix_quarentena_execucao ON quarentena.registro (execucao_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_quarentena_origem
    ON quarentena.registro (fonte, origem, linha, hash_origem);

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
    acao              TEXT NOT NULL,     -- o que acontece quando reprova (critica bloqueia a gold)
    consulta          TEXT NOT NULL      -- SQL que devolve (fonte, total, falhos); $1 = execucao_id
);
ALTER TABLE qualidade.teste ADD COLUMN IF NOT EXISTS consulta TEXT;  -- bancos criados antes da coluna

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
    -- configuracao do teste quando ele rodou: o teste pode mudar depois, o historico nao
    operador           TEXT,
    limite_aceitavel   NUMERIC,
    severidade         TEXT,
    UNIQUE (execucao_id, teste_id, fonte)
);
ALTER TABLE qualidade.resultado  -- bancos criados antes das colunas; o preenchimento fica em sql/qualidade.sql
    ADD COLUMN IF NOT EXISTS operador TEXT,
    ADD COLUMN IF NOT EXISTS limite_aceitavel NUMERIC,
    ADD COLUMN IF NOT EXISTS severidade TEXT;

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
