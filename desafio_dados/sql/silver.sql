-- Desafio 2 — Silver (RF21, RF23, RF30, RF33): regras de validacao, area de preparo e publicacao.
-- Idempotente. Aplicado pelo db-init depois de sql/camadas.sql. Contratos: documentacao/contratos.md.
--
-- Fluxo (orquestrado por hop/workflows/silver.hwf):
--   1. validacao.classificar_<fonte>(execucao) le a bronze da execucao (ja com as correcoes da
--      quarentena) e devolve cada registro tipado e padronizado, com a primeira regra violada.
--      As regras de validacao existem so aqui.
--   2. O pipeline hop/pipelines/silver_<entidade>.hpl separa aprovados e rejeitados (Filter rows)
--      e grava em validacao.<entidade> e validacao.<entidade>_rejeitado (area de preparo).
--   3. silver.publicar(execucao) troca a Silver inteira, os dados mestres, os pseudonimos e a
--      quarentena numa unica transacao: se algo falhar, a Silver anterior continua valendo.

CREATE SCHEMA IF NOT EXISTS validacao;  -- regras da Silver e area de preparo (sem dados permanentes)

-- ---------------------------------------------------------------
-- conversao e padronizacao: devolvem NULL quando o valor nao e valido
-- ---------------------------------------------------------------

-- remove espacos nas pontas e colapsa os internos; vazio vira NULL
CREATE OR REPLACE FUNCTION validacao.texto(v TEXT) RETURNS TEXT
    LANGUAGE sql IMMUTABLE
    RETURN NULLIF(regexp_replace(btrim(v), '\s+', ' ', 'g'), '');

-- chave de comparacao de dominios: sem acento e em minusculas
CREATE OR REPLACE FUNCTION validacao.chave(v TEXT) RETURNS TEXT
    LANGUAGE sql STABLE
    RETURN lower(unaccent(validacao.texto(v)));

-- inteiro estrito: '7', ' 7 ', '7.0' e '-45' convertem; '7.9' e 'abc' nao (como no Desafio 1)
CREATE OR REPLACE FUNCTION validacao.inteiro(v TEXT) RETURNS INTEGER
    LANGUAGE sql IMMUTABLE
    RETURN CASE WHEN btrim(v) ~ '^-?[0-9]{1,9}(\.0+)?$' THEN split_part(btrim(v), '.', 1)::integer END;

CREATE OR REPLACE FUNCTION validacao.numero(v TEXT) RETURNS NUMERIC
    LANGUAGE sql IMMUTABLE
    RETURN CASE WHEN btrim(v) ~ '^-?[0-9]{1,12}(\.[0-9]+)?$' THEN btrim(v)::numeric END;

-- datas aceitas: AAAA-MM-DD, DD/MM/AAAA e AAAA/MM/DD (como no Desafio 1); data inexistente vira NULL
CREATE OR REPLACE FUNCTION validacao.data(v TEXT) RETURNS DATE
    LANGUAGE plpgsql IMMUTABLE
AS $$
DECLARE
    t TEXT := btrim(v);
BEGIN
    IF t ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' OR t ~ '^[0-9]{4}/[0-9]{2}/[0-9]{2}$' THEN
        RETURN make_date(substr(t, 1, 4)::int, substr(t, 6, 2)::int, substr(t, 9, 2)::int);
    ELSIF t ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$' THEN
        RETURN make_date(substr(t, 7, 4)::int, substr(t, 4, 2)::int, substr(t, 1, 2)::int);
    END IF;
    RETURN NULL;
EXCEPTION WHEN datetime_field_overflow OR invalid_datetime_format THEN
    RETURN NULL;
END;
$$;

-- data e hora ISO 8601 com segundos, separador 'T' ou espaco
CREATE OR REPLACE FUNCTION validacao.data_hora(v TEXT) RETURNS TIMESTAMP
    LANGUAGE plpgsql IMMUTABLE
AS $$
BEGIN
    IF btrim(v) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}$' THEN
        RETURN replace(btrim(v), 'T', ' ')::timestamp;
    END IF;
    RETURN NULL;
EXCEPTION WHEN datetime_field_overflow OR invalid_datetime_format THEN
    RETURN NULL;
END;
$$;

-- lista JSON (ex.: tags); qualquer outra coisa vira NULL
CREATE OR REPLACE FUNCTION validacao.lista_json(v TEXT) RETURNS JSONB
    LANGUAGE plpgsql IMMUTABLE
AS $$
DECLARE
    j JSONB;
BEGIN
    j := v::jsonb;
    RETURN CASE WHEN jsonb_typeof(j) = 'array' THEN j END;
EXCEPTION WHEN invalid_text_representation THEN
    RETURN NULL;
END;
$$;

-- nomes dos campos obrigatorios ausentes ou vazios, ou NULL se estao todos presentes
CREATE OR REPLACE FUNCTION validacao.ausentes(p_registro JSONB, p_campos TEXT[]) RETURNS TEXT
    LANGUAGE sql IMMUTABLE
    RETURN (SELECT string_agg(c, ', ' ORDER BY i)
              FROM unnest(p_campos) WITH ORDINALITY AS u(c, i)
             WHERE validacao.texto(p_registro ->> c) IS NULL);

-- dominios: grafia canonica a partir da chave sem acento
CREATE OR REPLACE FUNCTION validacao.tipo_conteudo(v TEXT) RETURNS TEXT
    LANGUAGE sql STABLE
    RETURN CASE validacao.chave(v)
             WHEN 'curso' THEN 'Curso' WHEN 'video' THEN 'Vídeo'
             WHEN 'artigo' THEN 'Artigo' WHEN 'podcast' THEN 'Podcast' END;

CREATE OR REPLACE FUNCTION validacao.nivel(v TEXT) RETURNS TEXT
    LANGUAGE sql STABLE
    RETURN CASE validacao.chave(v)
             WHEN 'basico' THEN 'Básico' WHEN 'intermediario' THEN 'Intermediário'
             WHEN 'avancado' THEN 'Avançado' END;

CREATE OR REPLACE FUNCTION validacao.tipo_interacao(v TEXT) RETURNS TEXT
    LANGUAGE sql STABLE
    RETURN CASE validacao.chave(v)
             WHEN 'visualizacao' THEN 'visualização' WHEN 'inicio' THEN 'início'
             WHEN 'conclusao' THEN 'conclusão' WHEN 'curtida' THEN 'curtida'
             WHEN 'avaliacao' THEN 'avaliação' WHEN 'compartilhamento' THEN 'compartilhamento' END;

CREATE OR REPLACE FUNCTION validacao.classificacao_recomendacao(v TEXT) RETURNS TEXT
    LANGUAGE sql STABLE
    RETURN CASE validacao.chave(v)
             WHEN 'positivo' THEN 'positivo' WHEN 'estavel' THEN 'estavel' WHEN 'negativo' THEN 'negativo' END;

CREATE OR REPLACE FUNCTION validacao.uf(v TEXT) RETURNS CHAR(2)
    LANGUAGE sql IMMUTABLE
    RETURN CASE WHEN upper(btrim(v)) IN ('AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS',
                                         'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC',
                                         'SP', 'SE', 'TO')
                THEN upper(btrim(v)) END;

-- lote mais recente prevalece sobre o Desafio 1 na sobrevivencia (contratos.md)
CREATE OR REPLACE FUNCTION validacao.prioridade(p_origem TEXT) RETURNS INTEGER
    LANGUAGE sql IMMUTABLE
    RETURN CASE WHEN p_origem LIKE 'dados/brutos/lote_2/%' THEN 2 ELSE 1 END;

-- severidade padrao de cada codigo de regra (tabela "Codigos de regra" em contratos.md)
CREATE OR REPLACE FUNCTION validacao.severidade(p_regra TEXT) RETURNS TEXT
    LANGUAGE sql IMMUTABLE
    RETURN CASE
             WHEN p_regra IS NULL THEN NULL
             WHEN p_regra IN ('CAMPO_OBRIGATORIO', 'TIPO_INVALIDO', 'DATA_INVALIDA', 'REF_USUARIO', 'REF_CONTEUDO')
                  THEN 'alta'
             WHEN p_regra IN ('DUPLICADO', 'CONFLITO_VERSAO') THEN 'baixa'
             ELSE 'media'
           END;

-- segredos da LGPD vem do .env como parametro; vazio ou valor de exemplo interrompe a etapa
CREATE OR REPLACE FUNCTION validacao.segredo(p_valor TEXT, p_nome TEXT) RETURNS TEXT
    LANGUAGE plpgsql IMMUTABLE
AS $$
BEGIN
    IF p_valor IS NULL OR length(p_valor) < 16 OR p_valor LIKE 'troque-por%' OR p_valor LIKE '${%' THEN
        RAISE EXCEPTION '% nao configurado no .env (gere um valor aleatorio; ver .env.example)', p_nome;
    END IF;
    RETURN p_valor;
END;
$$;

-- ---------------------------------------------------------------
-- entrada: registros da bronze de uma execucao, ja com as correcoes da quarentena
-- ---------------------------------------------------------------

-- Cada registro e identificado por (fonte, _origem, _linha, md5 do conteudo). Se a quarentena tem
-- esse registro como 'corrigido' ou 'reprocessado', a versao editada substitui a da bronze;
-- se esta 'descartado', o registro sai do fluxo.
CREATE OR REPLACE FUNCTION validacao.entrada(p_execucao_id TEXT, p_fonte TEXT)
RETURNS TABLE (origem TEXT, linha INTEGER, ingerido_em TIMESTAMPTZ, hash_origem TEXT,
               reg JSONB, original JSONB)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN QUERY EXECUTE format($q$
        SELECT b._origem, b._linha, b._ingerido_em, md5(o.reg::text),
               CASE WHEN q.status IN ('corrigido', 'reprocessado') THEN q.registro ELSE o.reg END,
               o.reg
          FROM bronze.%I b
         CROSS JOIN LATERAL (SELECT to_jsonb(b) - '_execucao_id' - '_origem' - '_linha' - '_ingerido_em' AS reg) o
          LEFT JOIN quarentena.registro q
                 ON q.fonte = %L AND q.origem = b._origem AND q.linha = b._linha
                AND q.hash_origem = md5(o.reg::text)
         WHERE b._execucao_id = $1
           AND q.status IS DISTINCT FROM 'descartado'
    $q$, p_fonte, p_fonte) USING p_execucao_id;
END;
$$;

-- ---------------------------------------------------------------
-- area de preparo: cada pipeline silver_* esvazia e preenche as suas duas tabelas; a publicacao
-- esvazia todas ao final. O db-init roda a cada "docker compose run", entao nada aqui e destrutivo.
-- aprovados: colunas da silver + _linha e _hash_origem; rejeitados: linha futura da quarentena
-- ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS validacao.conteudo (
    conteudo_id INTEGER, titulo TEXT, tipo TEXT, categoria TEXT, nivel TEXT, carga_horaria_min INTEGER,
    data_publicacao DATE, descricao TEXT, autor TEXT,
    _execucao_id TEXT, _origem TEXT, _linha INTEGER, _ingerido_em TIMESTAMPTZ, _hash_origem TEXT
);
CREATE TABLE IF NOT EXISTS validacao.usuario (
    usuario_id INTEGER, usuario_pseudo TEXT, nome_mascarado TEXT, email_mascarado TEXT, email_hash TEXT,
    cpf_hash TEXT, faixa_etaria TEXT, cidade TEXT, uf TEXT, data_cadastro DATE, atualizado_em TIMESTAMP,
    _execucao_id TEXT, _origem TEXT, _linha INTEGER, _ingerido_em TIMESTAMPTZ, _hash_origem TEXT
);
CREATE TABLE IF NOT EXISTS validacao.interacao (
    usuario_id INTEGER, conteudo_id INTEGER, tipo_interacao TEXT, data_hora TIMESTAMP,
    tempo_consumido INTEGER, percentual_conclusao NUMERIC(5, 2), avaliacao_atribuida SMALLINT,
    _execucao_id TEXT, _origem TEXT, _linha INTEGER, _ingerido_em TIMESTAMPTZ, _hash_origem TEXT
);
CREATE TABLE IF NOT EXISTS validacao.comentario (
    usuario_id INTEGER, conteudo_id INTEGER, avaliacao SMALLINT, comentario TEXT,
    tags TEXT,  -- lista JSON; vira TEXT[] na publicacao
    data DATE,
    _execucao_id TEXT, _origem TEXT, _linha INTEGER, _ingerido_em TIMESTAMPTZ, _hash_origem TEXT
);
CREATE TABLE IF NOT EXISTS validacao.recomendacao (
    usuario_id INTEGER, conteudo_id INTEGER, pontuacao NUMERIC(5, 2), posicao INTEGER, classificacao TEXT,
    gerado_em TIMESTAMP,
    _execucao_id TEXT, _origem TEXT, _linha INTEGER, _ingerido_em TIMESTAMPTZ, _hash_origem TEXT
);
CREATE TABLE IF NOT EXISTS validacao.conteudo_rejeitado (
    execucao_id TEXT, fonte TEXT, origem TEXT, linha INTEGER, hash_origem TEXT, chave_registro TEXT,
    regra TEXT, severidade TEXT, mensagem TEXT,
    registro TEXT, registro_original TEXT  -- JSON; vira JSONB na publicacao
);
CREATE TABLE IF NOT EXISTS validacao.usuario_rejeitado (LIKE validacao.conteudo_rejeitado);
CREATE TABLE IF NOT EXISTS validacao.interacao_rejeitado (LIKE validacao.conteudo_rejeitado);
CREATE TABLE IF NOT EXISTS validacao.comentario_rejeitado (LIKE validacao.conteudo_rejeitado);
CREATE TABLE IF NOT EXISTS validacao.recomendacao_rejeitado (LIKE validacao.conteudo_rejeitado);

-- ---------------------------------------------------------------
-- classificacao por fonte: regra = primeira violada, na ordem abaixo; NULL = aprovado.
-- Versoes vencidas pela sobrevivencia entre fontes (ex.: conteudo 7 do Desafio 1 reenviado no
-- lote 2) nao sao erro: nao aparecem no resultado e continuam so na bronze.
-- ---------------------------------------------------------------

CREATE OR REPLACE FUNCTION validacao.classificar_catalogo(p_execucao_id TEXT)
RETURNS TABLE (
    conteudo_id INTEGER, titulo TEXT, tipo TEXT, categoria TEXT, nivel TEXT, carga_horaria_min INTEGER,
    data_publicacao DATE, descricao TEXT, autor TEXT,
    _execucao_id TEXT, _origem TEXT, _linha INTEGER, _ingerido_em TIMESTAMPTZ, _hash_origem TEXT,
    fonte TEXT, chave_registro TEXT, regra TEXT, severidade TEXT, mensagem TEXT,
    registro TEXT, registro_original TEXT)
LANGUAGE sql STABLE
AS $$
WITH t AS (
    SELECT e.*,
           validacao.prioridade(e.origem)                  AS prioridade,
           validacao.inteiro(e.reg ->> 'conteudo_id')       AS v_id,
           validacao.texto(e.reg ->> 'titulo')              AS v_titulo,
           validacao.tipo_conteudo(e.reg ->> 'tipo')        AS v_tipo,
           validacao.texto(e.reg ->> 'categoria')           AS v_categoria,
           validacao.nivel(e.reg ->> 'nivel')               AS v_nivel,
           validacao.inteiro(e.reg ->> 'carga_horaria_min') AS v_carga,
           validacao.data(e.reg ->> 'data_publicacao')      AS v_data,
           validacao.ausentes(e.reg, ARRAY['conteudo_id', 'titulo', 'tipo', 'categoria', 'nivel',
                                           'carga_horaria_min', 'data_publicacao']) AS v_ausentes
      FROM validacao.entrada(p_execucao_id, 'catalogo') e
), r AS (
    SELECT t.*,
           CASE
             WHEN v_ausentes IS NOT NULL THEN ARRAY['CAMPO_OBRIGATORIO', 'campos ausentes: ' || v_ausentes]
             WHEN v_id IS NULL THEN ARRAY['TIPO_INVALIDO', format('conteudo_id %L nao e inteiro', reg ->> 'conteudo_id')]
             WHEN v_carga IS NULL THEN ARRAY['TIPO_INVALIDO', format('carga_horaria_min %L nao e inteira', reg ->> 'carga_horaria_min')]
             WHEN v_data IS NULL THEN ARRAY['DATA_INVALIDA', format('data_publicacao %L nao e uma data valida', reg ->> 'data_publicacao')]
             WHEN v_tipo IS NULL THEN ARRAY['DOMINIO', format('tipo %L fora de Curso, Vídeo, Artigo, Podcast', reg ->> 'tipo')]
             WHEN v_nivel IS NULL THEN ARRAY['DOMINIO', format('nivel %L fora de Básico, Intermediário, Avançado', reg ->> 'nivel')]
             WHEN v_id <= 0 THEN ARRAY['FAIXA', format('conteudo_id %s deve ser positivo', v_id)]
             WHEN v_carga < 0 THEN ARRAY['VALOR_NEGATIVO', format('carga_horaria_min %s negativa', v_carga)]
           END AS falha
      FROM t
), d AS (  -- copia identica de um registro valido: fica a primeira ocorrencia
    SELECT r.*,
           first_value(linha) OVER copia AS linha_original,
           row_number()       OVER copia AS n_copia
      FROM r
    WINDOW copia AS (PARTITION BY falha IS NULL, v_id, hash_origem ORDER BY prioridade, linha)
), v AS (  -- versoes diferentes do mesmo id: vence o lote mais recente e, no mesmo arquivo, a ultima linha
    SELECT d.*,
           row_number()        OVER versao AS n_versao,
           first_value(origem) OVER versao AS origem_vencedora,
           first_value(linha)  OVER versao AS linha_vencedora,
           -- categoria: mantem a primeira grafia encontrada (como no Desafio 1)
           first_value(v_categoria) OVER (PARTITION BY falha IS NULL, validacao.chave(v_categoria)
                                          ORDER BY prioridade, origem, linha) AS categoria_canonica
      FROM d
    WINDOW versao AS (PARTITION BY falha IS NULL AND n_copia = 1, v_id ORDER BY prioridade DESC, linha DESC)
), c AS (
    SELECT v.*,
           CASE
             WHEN falha IS NOT NULL THEN falha
             WHEN n_copia > 1 THEN ARRAY['DUPLICADO', format('copia identica da linha %s', linha_original)]
             WHEN n_versao > 1 AND origem = origem_vencedora
                  THEN ARRAY['CONFLITO_VERSAO', format('mesmo conteudo_id da linha %s, que prevalece (ultima ocorrencia no arquivo)', linha_vencedora)]
           END AS resultado,
           (falha IS NULL AND n_copia = 1 AND n_versao > 1 AND origem <> origem_vencedora) AS substituido
      FROM v
)
SELECT v_id, v_titulo, v_tipo, categoria_canonica, v_nivel, v_carga, v_data,
       validacao.texto(reg ->> 'descricao'), validacao.texto(reg ->> 'autor'),
       p_execucao_id, origem, linha, ingerido_em, hash_origem,
       'catalogo', COALESCE(reg ->> 'conteudo_id', 'linha ' || linha),
       resultado[1], validacao.severidade(resultado[1]), resultado[2],
       reg::text, original::text
  FROM c
 WHERE NOT substituido;
$$;

-- usuarios: os campos pessoais so saem daqui protegidos (RF33); a bronze e a unica copia original
CREATE OR REPLACE FUNCTION validacao.classificar_usuarios(p_execucao_id TEXT, p_chave TEXT, p_salt TEXT)
RETURNS TABLE (
    usuario_id INTEGER, usuario_pseudo TEXT, nome_mascarado TEXT, email_mascarado TEXT, email_hash TEXT,
    cpf_hash TEXT, faixa_etaria TEXT, cidade TEXT, uf TEXT, data_cadastro DATE, atualizado_em TIMESTAMP,
    _execucao_id TEXT, _origem TEXT, _linha INTEGER, _ingerido_em TIMESTAMPTZ, _hash_origem TEXT,
    fonte TEXT, chave_registro TEXT, regra TEXT, severidade TEXT, mensagem TEXT,
    registro TEXT, registro_original TEXT)
LANGUAGE sql STABLE
AS $$
WITH s AS (
    SELECT validacao.segredo(p_chave, 'LGPD_CHAVE_PSEUDONIMO') AS chave,
           validacao.segredo(p_salt, 'LGPD_SALT')              AS salt
), t AS (
    SELECT e.*,
           validacao.prioridade(e.origem)                         AS prioridade,
           validacao.inteiro(e.reg ->> 'usuario_id')              AS v_id,
           validacao.texto(e.reg ->> 'nome')                      AS v_nome,
           lower(validacao.texto(e.reg ->> 'email'))              AS v_email,
           regexp_replace(e.reg ->> 'cpf', '[^0-9]', '', 'g')     AS v_cpf_digitos,
           validacao.data(e.reg ->> 'data_nascimento')            AS v_nascimento,
           validacao.uf(e.reg ->> 'uf')                           AS v_uf,
           validacao.data(e.reg ->> 'data_cadastro')              AS v_cadastro,
           validacao.data_hora(e.reg ->> 'atualizado_em')         AS v_atualizado,
           validacao.ausentes(e.reg, ARRAY['usuario_id', 'nome', 'email', 'cpf', 'data_nascimento', 'uf']) AS v_ausentes
      FROM validacao.entrada(p_execucao_id, 'usuarios') e
), r AS (
    SELECT t.*,
           CASE
             WHEN v_ausentes IS NOT NULL THEN ARRAY['CAMPO_OBRIGATORIO', 'campos ausentes: ' || v_ausentes]
             WHEN v_id IS NULL THEN ARRAY['TIPO_INVALIDO', format('usuario_id %L nao e inteiro', reg ->> 'usuario_id')]
             WHEN v_email !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'
                  THEN ARRAY['FORMATO', 'e-mail fora do formato nome@dominio']
             WHEN btrim(reg ->> 'cpf') !~ '^([0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}|[0-9]{11})$'
                  THEN ARRAY['FORMATO', 'CPF fora do formato 000.000.000-00']
             WHEN v_nascimento IS NULL THEN ARRAY['DATA_INVALIDA', 'data_nascimento nao e uma data valida']
             WHEN validacao.texto(reg ->> 'data_cadastro') IS NOT NULL AND v_cadastro IS NULL
                  THEN ARRAY['DATA_INVALIDA', format('data_cadastro %L nao e uma data valida', reg ->> 'data_cadastro')]
             WHEN validacao.texto(reg ->> 'atualizado_em') IS NOT NULL AND v_atualizado IS NULL
                  THEN ARRAY['DATA_INVALIDA', format('atualizado_em %L nao e data e hora valida', reg ->> 'atualizado_em')]
             WHEN v_uf IS NULL THEN ARRAY['DOMINIO', format('uf %L nao e uma unidade da federacao', reg ->> 'uf')]
             WHEN v_id <= 0 THEN ARRAY['FAIXA', format('usuario_id %s deve ser positivo', v_id)]
             WHEN v_nascimento > current_date THEN ARRAY['DATA_FUTURA', 'data_nascimento no futuro']
             WHEN v_cadastro > current_date THEN ARRAY['DATA_FUTURA', 'data_cadastro no futuro']
           END AS falha
      FROM t
), d AS (  -- copia identica de um registro valido: fica a primeira ocorrencia
    SELECT r.*,
           first_value(linha) OVER copia AS linha_original,
           row_number()       OVER copia AS n_copia
      FROM r
    WINDOW copia AS (PARTITION BY falha IS NULL, v_id, hash_origem ORDER BY prioridade, linha)
), v AS (  -- mesmo usuario_id: vence o cadastro atualizado mais recentemente (contratos.md)
    SELECT d.*,
           row_number()        OVER versao AS n_versao,
           first_value(origem) OVER versao AS origem_vencedora,
           first_value(linha)  OVER versao AS linha_vencedora
      FROM d
    WINDOW versao AS (PARTITION BY falha IS NULL AND n_copia = 1, v_id
                      ORDER BY v_atualizado DESC NULLS LAST, prioridade DESC, linha DESC)
), c AS (
    SELECT v.*,
           CASE
             WHEN falha IS NOT NULL THEN falha
             WHEN n_copia > 1 THEN ARRAY['DUPLICADO', format('copia identica da linha %s', linha_original)]
             WHEN n_versao > 1 AND origem = origem_vencedora
                  THEN ARRAY['CONFLITO_VERSAO', format('mesmo usuario_id da linha %s, atualizada mais recentemente', linha_vencedora)]
           END AS resultado,
           (falha IS NULL AND n_copia = 1 AND n_versao > 1 AND origem <> origem_vencedora) AS substituido
      FROM v
)
SELECT v_id,
       lgpd.pseudonimizar(v_id::text, s.chave),
       lgpd.mascarar_nome(v_nome),
       lgpd.mascarar_email(v_email),
       lgpd.hash_salt(v_email, s.salt),
       lgpd.hash_salt(v_cpf_digitos, s.salt),
       CASE WHEN v_nascimento IS NULL THEN NULL
            WHEN age(current_date, v_nascimento) < interval '18 years' THEN '0-17'
            WHEN age(current_date, v_nascimento) < interval '25 years' THEN '18-24'
            WHEN age(current_date, v_nascimento) < interval '35 years' THEN '25-34'
            WHEN age(current_date, v_nascimento) < interval '45 years' THEN '35-44'
            WHEN age(current_date, v_nascimento) < interval '60 years' THEN '45-59'
            ELSE '60+' END,
       validacao.texto(reg ->> 'cidade'), v_uf, v_cadastro, v_atualizado,
       p_execucao_id, origem, linha, ingerido_em, hash_origem,
       'usuarios', COALESCE(reg ->> 'usuario_id', 'linha ' || linha),
       resultado[1], validacao.severidade(resultado[1]), resultado[2],
       reg::text, original::text
  FROM c CROSS JOIN s
 WHERE NOT substituido;
$$;

-- interacoes: referencias conferidas contra os usuarios e conteudos aprovados nesta execucao
CREATE OR REPLACE FUNCTION validacao.classificar_interacoes(p_execucao_id TEXT)
RETURNS TABLE (
    usuario_id INTEGER, conteudo_id INTEGER, tipo_interacao TEXT, data_hora TIMESTAMP,
    tempo_consumido INTEGER, percentual_conclusao NUMERIC(5, 2), avaliacao_atribuida SMALLINT,
    _execucao_id TEXT, _origem TEXT, _linha INTEGER, _ingerido_em TIMESTAMPTZ, _hash_origem TEXT,
    fonte TEXT, chave_registro TEXT, regra TEXT, severidade TEXT, mensagem TEXT,
    registro TEXT, registro_original TEXT)
LANGUAGE sql STABLE
AS $$
WITH t AS (
    SELECT e.*,
           validacao.prioridade(e.origem)                        AS prioridade,
           validacao.inteiro(e.reg ->> 'usuario_id')             AS v_usuario,
           validacao.inteiro(e.reg ->> 'conteudo_id')            AS v_conteudo,
           validacao.tipo_interacao(e.reg ->> 'tipo_interacao')  AS v_tipo,
           validacao.data_hora(e.reg ->> 'data_hora')            AS v_data_hora,
           validacao.inteiro(e.reg ->> 'tempo_consumido')        AS v_tempo,
           validacao.numero(e.reg ->> 'percentual_conclusao')    AS v_percentual,
           validacao.inteiro(e.reg ->> 'avaliacao_atribuida')    AS v_nota,
           validacao.ausentes(e.reg, ARRAY['usuario_id', 'conteudo_id', 'tipo_interacao', 'data_hora']) AS v_ausentes
      FROM validacao.entrada(p_execucao_id, 'interacoes') e
), r AS (
    SELECT t.*,
           CASE
             WHEN v_ausentes IS NOT NULL THEN ARRAY['CAMPO_OBRIGATORIO', 'campos ausentes: ' || v_ausentes]
             WHEN v_usuario IS NULL OR v_conteudo IS NULL
                  THEN ARRAY['TIPO_INVALIDO', format('usuario_id %L ou conteudo_id %L nao e inteiro', reg ->> 'usuario_id', reg ->> 'conteudo_id')]
             WHEN validacao.texto(reg ->> 'tempo_consumido') IS NOT NULL AND v_tempo IS NULL
                  THEN ARRAY['TIPO_INVALIDO', format('tempo_consumido %L nao e inteiro', reg ->> 'tempo_consumido')]
             WHEN validacao.texto(reg ->> 'percentual_conclusao') IS NOT NULL AND v_percentual IS NULL
                  THEN ARRAY['TIPO_INVALIDO', format('percentual_conclusao %L nao e numero', reg ->> 'percentual_conclusao')]
             WHEN validacao.texto(reg ->> 'avaliacao_atribuida') IS NOT NULL AND v_nota IS NULL
                  THEN ARRAY['TIPO_INVALIDO', format('avaliacao_atribuida %L nao e inteira', reg ->> 'avaliacao_atribuida')]
             WHEN v_data_hora IS NULL THEN ARRAY['DATA_INVALIDA', format('data_hora %L nao e data e hora ISO valida', reg ->> 'data_hora')]
             WHEN v_tipo IS NULL THEN ARRAY['DOMINIO', format('tipo_interacao %L fora dos seis tipos', reg ->> 'tipo_interacao')]
             WHEN v_usuario <= 0 OR v_conteudo <= 0 THEN ARRAY['FAIXA', 'usuario_id e conteudo_id devem ser positivos']
             WHEN v_percentual NOT BETWEEN 0 AND 100 THEN ARRAY['FAIXA', format('percentual_conclusao %s fora de 0-100', v_percentual)]
             WHEN v_nota NOT BETWEEN 1 AND 5 THEN ARRAY['FAIXA', format('avaliacao_atribuida %s fora de 1-5', v_nota)]
             WHEN v_tempo < 0 THEN ARRAY['VALOR_NEGATIVO', format('tempo_consumido %s negativo', v_tempo)]
             WHEN v_data_hora > localtimestamp THEN ARRAY['DATA_FUTURA', format('data_hora %s no futuro', v_data_hora)]
             WHEN u.usuario_id IS NULL THEN ARRAY['REF_USUARIO', format('usuario %s nao existe entre os usuarios aprovados', v_usuario)]
             WHEN k.conteudo_id IS NULL THEN ARRAY['REF_CONTEUDO', format('conteudo %s nao existe entre os conteudos aprovados', v_conteudo)]
             WHEN v_data_hora::date < k.data_publicacao
                  THEN ARRAY['DATA_ANTES_PUBLICACAO', format('data_hora %s anterior a publicacao do conteudo (%s)', v_data_hora, k.data_publicacao)]
             WHEN v_tipo = 'conclusão' AND v_percentual IS DISTINCT FROM 100
                  THEN ARRAY['CONSISTENCIA', format('conclusao com percentual_conclusao %s', COALESCE(v_percentual::text, 'vazio'))]
             WHEN v_tipo = 'avaliação' AND v_nota IS NULL
                  THEN ARRAY['CONSISTENCIA', 'interacao do tipo avaliacao sem nota']
           END AS falha
      FROM t
      LEFT JOIN validacao.usuario u  ON u.usuario_id = t.v_usuario AND u._execucao_id = p_execucao_id
      LEFT JOIN validacao.conteudo k ON k.conteudo_id = t.v_conteudo AND k._execucao_id = p_execucao_id
), c AS (
    -- chave de negocio (usuario, conteudo, tipo, data_hora): fica a primeira ocorrencia
    SELECT r.*,
           CASE
             WHEN falha IS NOT NULL THEN falha
             WHEN row_number() OVER chave > 1 AND hash_origem = first_value(hash_origem) OVER chave
                  THEN ARRAY['DUPLICADO', format('copia identica da linha %s de %s', first_value(linha) OVER chave, first_value(origem) OVER chave)]
             WHEN row_number() OVER chave > 1
                  THEN ARRAY['CONFLITO_VERSAO', format('mesma chave de negocio da linha %s de %s, com outros valores', first_value(linha) OVER chave, first_value(origem) OVER chave)]
           END AS resultado
      FROM r
    WINDOW chave AS (PARTITION BY falha IS NULL, v_usuario, v_conteudo, v_tipo, v_data_hora ORDER BY prioridade, linha)
)
SELECT v_usuario, v_conteudo, v_tipo, v_data_hora, v_tempo, v_percentual::numeric(5, 2), v_nota::smallint,
       p_execucao_id, origem, linha, ingerido_em, hash_origem,
       'interacoes', format('usuario %s, conteudo %s, %s', reg ->> 'usuario_id', reg ->> 'conteudo_id', reg ->> 'data_hora'),
       resultado[1], validacao.severidade(resultado[1]), resultado[2],
       reg::text, original::text
  FROM c;
$$;

-- comentarios: texto livre anonimizado (e-mails e telefones) antes de sair da validacao
CREATE OR REPLACE FUNCTION validacao.classificar_comentarios(p_execucao_id TEXT)
RETURNS TABLE (
    usuario_id INTEGER, conteudo_id INTEGER, avaliacao SMALLINT, comentario TEXT, tags TEXT, data DATE,
    _execucao_id TEXT, _origem TEXT, _linha INTEGER, _ingerido_em TIMESTAMPTZ, _hash_origem TEXT,
    fonte TEXT, chave_registro TEXT, regra TEXT, severidade TEXT, mensagem TEXT,
    registro TEXT, registro_original TEXT)
LANGUAGE sql STABLE
AS $$
WITH t AS (
    SELECT e.*,
           validacao.prioridade(e.origem)                 AS prioridade,
           validacao.inteiro(e.reg ->> 'usuario_id')      AS v_usuario,
           validacao.inteiro(e.reg ->> 'conteudo_id')     AS v_conteudo,
           validacao.inteiro(e.reg ->> 'avaliacao')       AS v_nota,
           validacao.texto(e.reg ->> 'comentario')        AS v_texto,
           CASE WHEN validacao.texto(e.reg ->> 'tags') IS NULL THEN '[]'::jsonb
                ELSE validacao.lista_json(e.reg ->> 'tags') END AS v_tags,
           validacao.data(e.reg ->> 'data')               AS v_data,
           validacao.ausentes(e.reg, ARRAY['usuario_id', 'conteudo_id', 'avaliacao', 'comentario', 'data']) AS v_ausentes
      FROM validacao.entrada(p_execucao_id, 'comentarios') e
), r AS (
    SELECT t.*,
           CASE
             WHEN v_ausentes IS NOT NULL THEN ARRAY['CAMPO_OBRIGATORIO', 'campos ausentes: ' || v_ausentes]
             WHEN v_usuario IS NULL OR v_conteudo IS NULL
                  THEN ARRAY['TIPO_INVALIDO', format('usuario_id %L ou conteudo_id %L nao e inteiro', reg ->> 'usuario_id', reg ->> 'conteudo_id')]
             WHEN v_nota IS NULL THEN ARRAY['TIPO_INVALIDO', format('avaliacao %L nao e inteira', reg ->> 'avaliacao')]
             WHEN v_data IS NULL THEN ARRAY['DATA_INVALIDA', format('data %L nao e uma data valida', reg ->> 'data')]
             WHEN v_tags IS NULL THEN ARRAY['FORMATO', format('tags %L nao e uma lista JSON', reg ->> 'tags')]
             WHEN v_usuario <= 0 OR v_conteudo <= 0 THEN ARRAY['FAIXA', 'usuario_id e conteudo_id devem ser positivos']
             WHEN v_nota NOT BETWEEN 1 AND 5 THEN ARRAY['FAIXA', format('avaliacao %s fora de 1-5', v_nota)]
             WHEN v_data > current_date THEN ARRAY['DATA_FUTURA', format('data %s no futuro', v_data)]
             WHEN u.usuario_id IS NULL THEN ARRAY['REF_USUARIO', format('usuario %s nao existe entre os usuarios aprovados', v_usuario)]
             WHEN k.conteudo_id IS NULL THEN ARRAY['REF_CONTEUDO', format('conteudo %s nao existe entre os conteudos aprovados', v_conteudo)]
             WHEN v_data < k.data_publicacao
                  THEN ARRAY['DATA_ANTES_PUBLICACAO', format('data %s anterior a publicacao do conteudo (%s)', v_data, k.data_publicacao)]
           END AS falha
      FROM t
      LEFT JOIN validacao.usuario u  ON u.usuario_id = t.v_usuario AND u._execucao_id = p_execucao_id
      LEFT JOIN validacao.conteudo k ON k.conteudo_id = t.v_conteudo AND k._execucao_id = p_execucao_id
), c AS (
    -- chave (usuario, conteudo, data, texto): fica a primeira ocorrencia
    SELECT r.*,
           CASE
             WHEN falha IS NOT NULL THEN falha
             WHEN row_number() OVER chave > 1
                  THEN ARRAY['DUPLICADO', format('mesmo comentario da linha %s de %s', first_value(linha) OVER chave, first_value(origem) OVER chave)]
           END AS resultado
      FROM r
    WINDOW chave AS (PARTITION BY falha IS NULL, v_usuario, v_conteudo, v_data, v_texto ORDER BY prioridade, linha)
)
SELECT v_usuario, v_conteudo, v_nota::smallint, lgpd.anonimizar_texto(v_texto),
       (SELECT COALESCE(jsonb_agg(lower(btrim(x)) ORDER BY i), '[]'::jsonb)::text
          FROM jsonb_array_elements_text(CASE WHEN jsonb_typeof(v_tags) = 'array' THEN v_tags ELSE '[]' END)
               WITH ORDINALITY AS a(x, i)
         WHERE btrim(x) <> ''),
       v_data,
       p_execucao_id, origem, linha, ingerido_em, hash_origem,
       'comentarios', format('usuario %s, conteudo %s, %s', reg ->> 'usuario_id', reg ->> 'conteudo_id', reg ->> 'data'),
       resultado[1], validacao.severidade(resultado[1]), resultado[2],
       reg::text, original::text
  FROM c;
$$;

CREATE OR REPLACE FUNCTION validacao.classificar_recomendacoes(p_execucao_id TEXT)
RETURNS TABLE (
    usuario_id INTEGER, conteudo_id INTEGER, pontuacao NUMERIC(5, 2), posicao INTEGER, classificacao TEXT,
    gerado_em TIMESTAMP,
    _execucao_id TEXT, _origem TEXT, _linha INTEGER, _ingerido_em TIMESTAMPTZ, _hash_origem TEXT,
    fonte TEXT, chave_registro TEXT, regra TEXT, severidade TEXT, mensagem TEXT,
    registro TEXT, registro_original TEXT)
LANGUAGE sql STABLE
AS $$
WITH t AS (
    SELECT e.*,
           validacao.prioridade(e.origem)                                 AS prioridade,
           validacao.inteiro(e.reg ->> 'usuario_id')                      AS v_usuario,
           validacao.inteiro(e.reg ->> 'conteudo_id')                     AS v_conteudo,
           validacao.numero(e.reg ->> 'pontuacao')                        AS v_pontuacao,
           validacao.inteiro(e.reg ->> 'posicao')                         AS v_posicao,
           validacao.classificacao_recomendacao(e.reg ->> 'classificacao') AS v_classificacao,
           validacao.data_hora(e.reg ->> 'gerado_em')                     AS v_gerado,
           validacao.ausentes(e.reg, ARRAY['usuario_id', 'conteudo_id', 'pontuacao', 'posicao',
                                           'classificacao', 'gerado_em']) AS v_ausentes
      FROM validacao.entrada(p_execucao_id, 'recomendacoes') e
), r AS (
    SELECT t.*,
           CASE
             WHEN v_ausentes IS NOT NULL THEN ARRAY['CAMPO_OBRIGATORIO', 'campos ausentes: ' || v_ausentes]
             WHEN v_usuario IS NULL OR v_conteudo IS NULL OR v_posicao IS NULL OR v_pontuacao IS NULL
                  THEN ARRAY['TIPO_INVALIDO', 'usuario_id, conteudo_id, posicao ou pontuacao fora do tipo numerico']
             WHEN v_gerado IS NULL THEN ARRAY['DATA_INVALIDA', format('gerado_em %L nao e data e hora ISO valida', reg ->> 'gerado_em')]
             WHEN v_classificacao IS NULL THEN ARRAY['DOMINIO', format('classificacao %L fora de positivo, estavel, negativo', reg ->> 'classificacao')]
             WHEN v_pontuacao NOT BETWEEN 0 AND 100 THEN ARRAY['FAIXA', format('pontuacao %s fora de 0-100', v_pontuacao)]
             WHEN v_posicao <= 0 THEN ARRAY['FAIXA', format('posicao %s deve ser positiva', v_posicao)]
             WHEN u.usuario_id IS NULL THEN ARRAY['REF_USUARIO', format('usuario %s nao existe entre os usuarios aprovados', v_usuario)]
             WHEN k.conteudo_id IS NULL THEN ARRAY['REF_CONTEUDO', format('conteudo %s nao existe entre os conteudos aprovados', v_conteudo)]
           END AS falha
      FROM t
      LEFT JOIN validacao.usuario u  ON u.usuario_id = t.v_usuario AND u._execucao_id = p_execucao_id
      LEFT JOIN validacao.conteudo k ON k.conteudo_id = t.v_conteudo AND k._execucao_id = p_execucao_id
), c AS (
    SELECT r.*,
           CASE
             WHEN falha IS NOT NULL THEN falha
             WHEN row_number() OVER chave > 1
                  THEN ARRAY['DUPLICADO', format('mesma recomendacao da linha %s', first_value(linha) OVER chave)]
           END AS resultado
      FROM r
    WINDOW chave AS (PARTITION BY falha IS NULL, v_usuario, v_conteudo, v_gerado ORDER BY prioridade, linha)
)
SELECT v_usuario, v_conteudo, v_pontuacao::numeric(5, 2), v_posicao, v_classificacao, v_gerado,
       p_execucao_id, origem, linha, ingerido_em, hash_origem,
       'recomendacoes', format('usuario %s, conteudo %s', reg ->> 'usuario_id', reg ->> 'conteudo_id'),
       resultado[1], validacao.severidade(resultado[1]), resultado[2],
       reg::text, original::text
  FROM c;
$$;

-- ---------------------------------------------------------------
-- publicacao atomica da Silver (RF21, RF23, RF30, RF33)
-- ---------------------------------------------------------------

CREATE OR REPLACE FUNCTION silver.publicar(p_execucao_id TEXT)
RETURNS TABLE (objeto TEXT, registros BIGINT)
LANGUAGE plpgsql
AS $$
#variable_conflict use_column
DECLARE
    v_outras BIGINT;
BEGIN
    -- a area de preparo precisa conter exatamente as cinco validacoes desta execucao
    SELECT count(*) INTO v_outras FROM (
        SELECT _execucao_id FROM validacao.conteudo UNION ALL SELECT _execucao_id FROM validacao.usuario
        UNION ALL SELECT _execucao_id FROM validacao.interacao UNION ALL SELECT _execucao_id FROM validacao.comentario
        UNION ALL SELECT _execucao_id FROM validacao.recomendacao
    ) x WHERE x._execucao_id IS DISTINCT FROM p_execucao_id;
    IF v_outras > 0 THEN
        RAISE EXCEPTION 'area de preparo tem % registros de outra execucao: rode todas as validacoes da execucao % antes de publicar',
            v_outras, p_execucao_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM validacao.conteudo) OR NOT EXISTS (SELECT 1 FROM validacao.usuario) THEN
        RAISE EXCEPTION 'nenhum conteudo ou usuario aprovado na execucao %: nada a publicar', p_execucao_id;
    END IF;

    TRUNCATE silver.recomendacao, silver.comentario, silver.interacao, silver.usuario_correspondencia,
             silver.usuario_mestre, silver.usuario, silver.conteudo;

    INSERT INTO silver.conteudo (conteudo_id, titulo, tipo, categoria, nivel, carga_horaria_min, data_publicacao,
                                 descricao, autor, _execucao_id, _origem, _ingerido_em)
    SELECT conteudo_id, titulo, tipo, categoria, nivel, carga_horaria_min, data_publicacao,
           descricao, autor, _execucao_id, _origem, _ingerido_em
      FROM validacao.conteudo;

    INSERT INTO silver.usuario (usuario_id, usuario_pseudo, nome_mascarado, email_mascarado, email_hash, cpf_hash,
                                faixa_etaria, cidade, uf, data_cadastro, atualizado_em, _execucao_id, _origem, _ingerido_em)
    SELECT usuario_id, usuario_pseudo, nome_mascarado, email_mascarado, email_hash, cpf_hash,
           faixa_etaria, cidade, uf, data_cadastro, atualizado_em, _execucao_id, _origem, _ingerido_em
      FROM validacao.usuario;

    -- dados mestres (RF30): mesma pessoa = mesmo cpf_hash ou mesmo email_hash, inclusive por transitividade.
    -- O mestre e o menor usuario_id do grupo; os atributos vem do cadastro atualizado mais recentemente.
    WITH RECURSIVE ligacao AS (
        SELECT a.usuario_id AS de, b.usuario_id AS para
          FROM silver.usuario a
          JOIN silver.usuario b ON a.usuario_id <> b.usuario_id
                               AND (a.cpf_hash = b.cpf_hash OR a.email_hash = b.email_hash)
    ), alcance (de, para) AS (
        SELECT usuario_id, usuario_id FROM silver.usuario
        UNION
        SELECT a.de, l.para FROM alcance a JOIN ligacao l ON l.de = a.para
    ), grupo AS (
        SELECT de AS usuario_id, min(para) AS usuario_mestre_id FROM alcance GROUP BY de
    ), sobrevivente AS (
        SELECT DISTINCT ON (g.usuario_mestre_id) g.usuario_mestre_id, u.*
          FROM grupo g JOIN silver.usuario u USING (usuario_id)
         ORDER BY g.usuario_mestre_id, u.atualizado_em DESC NULLS LAST, u.usuario_id
    )
    INSERT INTO silver.usuario_mestre (usuario_mestre_id, usuario_pseudo, nome_mascarado, email_mascarado, faixa_etaria,
                                       cidade, uf, data_cadastro, atualizado_em, registros_origem, _execucao_id)
    SELECT s.usuario_mestre_id, m.usuario_pseudo, s.nome_mascarado, s.email_mascarado, s.faixa_etaria,
           s.cidade, s.uf, (SELECT min(u.data_cadastro) FROM grupo g JOIN silver.usuario u USING (usuario_id)
                             WHERE g.usuario_mestre_id = s.usuario_mestre_id),
           s.atualizado_em,
           (SELECT count(*) FROM grupo g WHERE g.usuario_mestre_id = s.usuario_mestre_id),
           p_execucao_id
      FROM sobrevivente s
      JOIN silver.usuario m ON m.usuario_id = s.usuario_mestre_id;

    WITH RECURSIVE ligacao AS (
        SELECT a.usuario_id AS de, b.usuario_id AS para
          FROM silver.usuario a
          JOIN silver.usuario b ON a.usuario_id <> b.usuario_id
                               AND (a.cpf_hash = b.cpf_hash OR a.email_hash = b.email_hash)
    ), alcance (de, para) AS (
        SELECT usuario_id, usuario_id FROM silver.usuario
        UNION
        SELECT a.de, l.para FROM alcance a JOIN ligacao l ON l.de = a.para
    ), grupo AS (
        SELECT de AS usuario_id, min(para) AS usuario_mestre_id FROM alcance GROUP BY de
    )
    INSERT INTO silver.usuario_correspondencia (usuario_id, usuario_mestre_id, regra, _execucao_id)
    SELECT g.usuario_id, g.usuario_mestre_id,
           CASE WHEN g.usuario_id = g.usuario_mestre_id THEN 'proprio'
                WHEN u.cpf_hash = m.cpf_hash THEN 'cpf_hash'
                WHEN u.email_hash = m.email_hash THEN 'email_hash'
                ELSE 'transitivo' END,
           p_execucao_id
      FROM grupo g
      JOIN silver.usuario u ON u.usuario_id = g.usuario_id
      JOIN silver.usuario m ON m.usuario_id = g.usuario_mestre_id;

    INSERT INTO silver.interacao (usuario_id, conteudo_id, tipo_interacao, data_hora, tempo_consumido,
                                  percentual_conclusao, avaliacao_atribuida, _execucao_id, _origem, _ingerido_em)
    SELECT usuario_id, conteudo_id, tipo_interacao, data_hora, tempo_consumido,
           percentual_conclusao, avaliacao_atribuida, _execucao_id, _origem, _ingerido_em
      FROM validacao.interacao;

    INSERT INTO silver.comentario (usuario_id, conteudo_id, avaliacao, comentario, tags, data,
                                   _execucao_id, _origem, _ingerido_em)
    SELECT usuario_id, conteudo_id, avaliacao, comentario,
           ARRAY(SELECT jsonb_array_elements_text(tags::jsonb)), data,
           _execucao_id, _origem, _ingerido_em
      FROM validacao.comentario;

    INSERT INTO silver.recomendacao (usuario_id, conteudo_id, pontuacao, posicao, classificacao, gerado_em,
                                     _execucao_id, _origem, _ingerido_em)
    SELECT usuario_id, conteudo_id, pontuacao, posicao, classificacao, gerado_em,
           _execucao_id, _origem, _ingerido_em
      FROM validacao.recomendacao;

    -- tabela de correspondencia para reidentificacao controlada (RF33)
    INSERT INTO restrito.usuario_pseudonimo (usuario_id, usuario_pseudo)
    SELECT usuario_id, usuario_pseudo FROM silver.usuario
    ON CONFLICT (usuario_id) DO UPDATE SET usuario_pseudo = EXCLUDED.usuario_pseudo;

    -- quarentena: aprovado agora resolve a pendencia (correcao aplicada ou dependencia resolvida)
    UPDATE quarentena.registro q
       SET status = 'reprocessado', reprocessado_em = now(), reprocessado_execucao_id = p_execucao_id
      FROM (SELECT 'catalogo' AS fonte, _origem, _linha, _hash_origem FROM validacao.conteudo
            UNION ALL SELECT 'usuarios', _origem, _linha, _hash_origem FROM validacao.usuario
            UNION ALL SELECT 'interacoes', _origem, _linha, _hash_origem FROM validacao.interacao
            UNION ALL SELECT 'comentarios', _origem, _linha, _hash_origem FROM validacao.comentario
            UNION ALL SELECT 'recomendacoes', _origem, _linha, _hash_origem FROM validacao.recomendacao) a
     WHERE q.fonte = a.fonte AND q.origem = a._origem AND q.linha = a._linha AND q.hash_origem = a._hash_origem
       AND q.status IN ('pendente', 'corrigido');

    -- rejeitados: novos entram como pendentes; os ja conhecidos so registram a nova deteccao.
    -- Uma correcao que continua falhando volta a pendente, com a regra da nova tentativa.
    INSERT INTO quarentena.registro AS q (execucao_id, camada, fonte, chave_registro, regra, severidade, mensagem,
                                          registro, registro_original, origem, linha, hash_origem, ultima_execucao_id)
    SELECT execucao_id, 'silver', fonte, chave_registro, regra, severidade, mensagem,
           registro::jsonb, registro_original::jsonb, origem, linha, hash_origem, execucao_id
      FROM (SELECT * FROM validacao.conteudo_rejeitado
            UNION ALL SELECT * FROM validacao.usuario_rejeitado
            UNION ALL SELECT * FROM validacao.interacao_rejeitado
            UNION ALL SELECT * FROM validacao.comentario_rejeitado
            UNION ALL SELECT * FROM validacao.recomendacao_rejeitado) r
    ON CONFLICT (fonte, origem, linha, hash_origem) DO UPDATE
       SET ultima_execucao_id = EXCLUDED.ultima_execucao_id,
           regra = EXCLUDED.regra, severidade = EXCLUDED.severidade, mensagem = EXCLUDED.mensagem,
           status = CASE WHEN q.status IN ('corrigido', 'reprocessado') THEN 'pendente' ELSE q.status END;

    TRUNCATE validacao.conteudo, validacao.usuario, validacao.interacao, validacao.comentario,
             validacao.recomendacao, validacao.conteudo_rejeitado, validacao.usuario_rejeitado,
             validacao.interacao_rejeitado, validacao.comentario_rejeitado, validacao.recomendacao_rejeitado;

    RETURN QUERY
        SELECT 'silver.conteudo', count(*) FROM silver.conteudo
        UNION ALL SELECT 'silver.usuario', count(*) FROM silver.usuario
        UNION ALL SELECT 'silver.usuario_mestre', count(*) FROM silver.usuario_mestre
        UNION ALL SELECT 'silver.interacao', count(*) FROM silver.interacao
        UNION ALL SELECT 'silver.comentario', count(*) FROM silver.comentario
        UNION ALL SELECT 'silver.recomendacao', count(*) FROM silver.recomendacao
        UNION ALL SELECT 'quarentena pendente nesta execucao', count(*) FROM quarentena.registro
                   WHERE ultima_execucao_id = p_execucao_id AND status = 'pendente';
END;
$$;

-- entidade da Silver -> fonte da bronze (usada por controle.medir_etapa, em sql/camadas.sql)
CREATE OR REPLACE FUNCTION validacao.fonte_da_entidade(p_entidade TEXT) RETURNS TEXT
    LANGUAGE sql IMMUTABLE
    RETURN CASE p_entidade WHEN 'conteudo' THEN 'catalogo' WHEN 'usuario' THEN 'usuarios'
                           WHEN 'interacao' THEN 'interacoes' WHEN 'comentario' THEN 'comentarios'
                           WHEN 'recomendacao' THEN 'recomendacoes' END;
