-- Desafio 2 — camada Gold (RF26). Idempotente; aplicado pelo db-init depois de sql/qualidade.sql.
--
-- Tabelas materializadas, reconstruidas por gold.publicar(execucao) numa unica transacao, chamada por
-- hop/workflows/gold.hwf depois que a qualidade aprova. Le so a Silver; o dashboard le so a Gold.
-- Sem dado pessoal: a pessoa aparece como usuario_pseudo do usuario mestre (RF30, RF32), e as
-- metricas contam pessoas, nao ids. O papel consumo (Superset) le tudo que esta no schema gold.
-- Definicoes dos termos (usuario ativo, taxa de conclusao, conversao, avaliacao): documentacao/contratos.md.

CREATE TABLE IF NOT EXISTS gold.dim_conteudo (
    conteudo_id        INTEGER PRIMARY KEY,
    titulo             TEXT NOT NULL,
    tipo               TEXT NOT NULL,
    categoria          TEXT NOT NULL,
    nivel              TEXT NOT NULL,
    carga_horaria_min  INTEGER NOT NULL,
    data_publicacao    DATE NOT NULL
);

-- uma linha por pessoa; sem nome, e-mail, CPF nem cidade. nome_mascarado e o unico campo derivado de dado
-- pessoal no consumo (RF33: mascaramento de campo exibido), usado so para rotular listas no dashboard.
CREATE TABLE IF NOT EXISTS gold.dim_usuario (
    usuario_pseudo    TEXT PRIMARY KEY,
    nome_mascarado    TEXT,
    faixa_etaria      TEXT,
    uf                CHAR(2),
    data_cadastro     DATE,
    registros_origem  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.fato_interacao (
    interacao_id          BIGINT PRIMARY KEY,
    usuario_pseudo        TEXT NOT NULL REFERENCES gold.dim_usuario (usuario_pseudo),
    conteudo_id           INTEGER NOT NULL REFERENCES gold.dim_conteudo (conteudo_id),
    tipo_interacao        TEXT NOT NULL,
    data_hora             TIMESTAMP NOT NULL,
    data                  DATE NOT NULL,
    mes                   DATE NOT NULL,  -- primeiro dia do mes
    tempo_consumido       INTEGER,
    percentual_conclusao  NUMERIC(5, 2),
    avaliacao_atribuida   SMALLINT
);

-- convertida: a pessoa consumiu (visualizacao, inicio ou conclusao) o conteudo recomendado depois de gerado_em
CREATE TABLE IF NOT EXISTS gold.fato_recomendacao (
    usuario_pseudo  TEXT NOT NULL REFERENCES gold.dim_usuario (usuario_pseudo),
    conteudo_id     INTEGER NOT NULL REFERENCES gold.dim_conteudo (conteudo_id),
    pontuacao       NUMERIC(5, 2) NOT NULL,
    posicao         INTEGER NOT NULL,
    classificacao   TEXT NOT NULL,
    gerado_em       TIMESTAMP NOT NULL,
    convertida      BOOLEAN NOT NULL,
    convertida_em   TIMESTAMP,
    PRIMARY KEY (usuario_pseudo, conteudo_id, gerado_em)
);

ALTER TABLE gold.dim_usuario ADD COLUMN IF NOT EXISTS nome_mascarado TEXT;  -- bancos criados antes da coluna

-- mesma regra do pipeline Beam (beam/pipeline.py, RF25), que confere o resultado contra esta tabela
CREATE TABLE IF NOT EXISTS gold.kpi_engajamento_mensal (
    mes                 TEXT NOT NULL,  -- AAAA-MM
    mes_referencia      DATE NOT NULL,
    categoria           TEXT NOT NULL,
    interacoes          BIGINT NOT NULL,
    pessoas_ativas      BIGINT NOT NULL,
    conclusoes          BIGINT NOT NULL,
    minutos_consumidos  BIGINT NOT NULL,
    PRIMARY KEY (mes, categoria)
);

-- usuario ativo: pessoa com pelo menos uma interacao no mes; retencao: ativos que voltam no mes seguinte
CREATE TABLE IF NOT EXISTS gold.kpi_usuarios_ativos_mensal (
    mes_referencia          DATE PRIMARY KEY,
    pessoas_ativas          BIGINT NOT NULL,
    interacoes              BIGINT NOT NULL,
    interacoes_por_pessoa   NUMERIC(8, 2) NOT NULL,
    pessoas_retidas         BIGINT,          -- NULL no ultimo mes: ainda nao ha mes seguinte
    retencao_pct            NUMERIC(5, 1),
    mes_completo            BOOLEAN NOT NULL  -- FALSE quando os dados terminam antes do fim do mes
);

-- taxa de conclusao: pares (pessoa, conteudo) concluidos / pares com consumo
CREATE TABLE IF NOT EXISTS gold.kpi_taxa_conclusao (
    categoria           TEXT NOT NULL,
    tipo                TEXT NOT NULL,
    nivel               TEXT NOT NULL,
    pares_consumo       BIGINT NOT NULL,
    pares_concluidos    BIGINT NOT NULL,
    taxa_conclusao_pct  NUMERIC(5, 1) NOT NULL,
    PRIMARY KEY (categoria, tipo, nivel)
);

-- conversao de recomendacao: recomendacoes convertidas / recomendacoes
CREATE TABLE IF NOT EXISTS gold.kpi_conversao_recomendacao (
    classificacao   TEXT NOT NULL,
    categoria       TEXT NOT NULL,
    recomendacoes   BIGINT NOT NULL,
    convertidas     BIGINT NOT NULL,
    conversao_pct   NUMERIC(5, 1) NOT NULL,
    PRIMARY KEY (classificacao, categoria)
);

-- avaliacao media (escala 1-5) e percentual de avaliacoes positivas (>= 4)
CREATE TABLE IF NOT EXISTS gold.kpi_avaliacao (
    categoria        TEXT NOT NULL,
    tipo             TEXT NOT NULL,
    avaliacoes       BIGINT NOT NULL,
    avaliacao_media  NUMERIC(3, 2) NOT NULL,
    pct_positivas    NUMERIC(5, 1) NOT NULL,
    PRIMARY KEY (categoria, tipo)
);

-- linhas publicadas, para controle.medir_etapa
CREATE OR REPLACE FUNCTION gold.contar_linhas() RETURNS BIGINT
    LANGUAGE sql STABLE
    RETURN (SELECT count(*) FROM gold.dim_conteudo) + (SELECT count(*) FROM gold.dim_usuario)
         + (SELECT count(*) FROM gold.fato_interacao) + (SELECT count(*) FROM gold.fato_recomendacao)
         + (SELECT count(*) FROM gold.kpi_engajamento_mensal) + (SELECT count(*) FROM gold.kpi_usuarios_ativos_mensal)
         + (SELECT count(*) FROM gold.kpi_taxa_conclusao) + (SELECT count(*) FROM gold.kpi_conversao_recomendacao)
         + (SELECT count(*) FROM gold.kpi_avaliacao);

CREATE OR REPLACE FUNCTION gold.publicar(p_execucao_id TEXT)
RETURNS TABLE (objeto TEXT, registros BIGINT)
LANGUAGE plpgsql
AS $$
#variable_conflict use_column
DECLARE
    v_silver TEXT;
BEGIN
    -- a Gold so e publicada a partir da Silver desta execucao, depois que a qualidade aprovou
    SELECT string_agg(DISTINCT _execucao_id, ', ') INTO v_silver FROM silver.conteudo;
    IF v_silver IS DISTINCT FROM p_execucao_id THEN
        RAISE EXCEPTION 'a Silver publicada e da execucao %, nao de %', v_silver, p_execucao_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM qualidade.resultado WHERE execucao_id = p_execucao_id) THEN
        RAISE EXCEPTION 'a qualidade da execucao % ainda nao foi avaliada', p_execucao_id;
    END IF;
    IF EXISTS (SELECT 1 FROM qualidade.resultado r
                WHERE r.execucao_id = p_execucao_id AND NOT r.aprovado AND r.severidade = 'critica') THEN
        RAISE EXCEPTION 'teste critico reprovado na execucao %: Gold nao publicada', p_execucao_id;
    END IF;

    TRUNCATE gold.fato_interacao, gold.fato_recomendacao, gold.dim_usuario, gold.dim_conteudo,
             gold.kpi_engajamento_mensal, gold.kpi_usuarios_ativos_mensal, gold.kpi_taxa_conclusao,
             gold.kpi_conversao_recomendacao, gold.kpi_avaliacao;

    INSERT INTO gold.dim_conteudo (conteudo_id, titulo, tipo, categoria, nivel, carga_horaria_min, data_publicacao)
    SELECT conteudo_id, titulo, tipo, categoria, nivel, carga_horaria_min, data_publicacao FROM silver.conteudo;

    INSERT INTO gold.dim_usuario (usuario_pseudo, nome_mascarado, faixa_etaria, uf, data_cadastro, registros_origem)
    SELECT usuario_pseudo, nome_mascarado, faixa_etaria, uf, data_cadastro, registros_origem FROM silver.usuario_mestre;

    INSERT INTO gold.fato_interacao (interacao_id, usuario_pseudo, conteudo_id, tipo_interacao, data_hora, data, mes,
                                     tempo_consumido, percentual_conclusao, avaliacao_atribuida)
    SELECT i.interacao_id, m.usuario_pseudo, i.conteudo_id, i.tipo_interacao, i.data_hora, i.data_hora::date,
           date_trunc('month', i.data_hora)::date, i.tempo_consumido, i.percentual_conclusao, i.avaliacao_atribuida
      FROM silver.interacao i
      JOIN silver.usuario_correspondencia c USING (usuario_id)
      JOIN silver.usuario_mestre m USING (usuario_mestre_id);

    -- ids diferentes da mesma pessoa podem ter recebido a mesma recomendacao: fica a de melhor posicao
    INSERT INTO gold.fato_recomendacao (usuario_pseudo, conteudo_id, pontuacao, posicao, classificacao, gerado_em,
                                        convertida, convertida_em)
    SELECT DISTINCT ON (m.usuario_pseudo, r.conteudo_id, r.gerado_em)
           m.usuario_pseudo, r.conteudo_id, r.pontuacao, r.posicao, r.classificacao, r.gerado_em,
           conv.primeira IS NOT NULL, conv.primeira
      FROM silver.recomendacao r
      JOIN silver.usuario_correspondencia c USING (usuario_id)
      JOIN silver.usuario_mestre m USING (usuario_mestre_id)
      LEFT JOIN LATERAL (
          SELECT min(f.data_hora) AS primeira
            FROM gold.fato_interacao f
           WHERE f.usuario_pseudo = m.usuario_pseudo AND f.conteudo_id = r.conteudo_id
             AND f.data_hora > r.gerado_em AND f.tipo_interacao IN ('visualização', 'início', 'conclusão')
      ) conv ON TRUE
     ORDER BY m.usuario_pseudo, r.conteudo_id, r.gerado_em, r.posicao;

    INSERT INTO gold.kpi_engajamento_mensal (mes, mes_referencia, categoria, interacoes, pessoas_ativas, conclusoes,
                                             minutos_consumidos)
    SELECT to_char(f.mes, 'YYYY-MM'), f.mes, d.categoria, count(*), count(DISTINCT f.usuario_pseudo),
           count(*) FILTER (WHERE f.tipo_interacao = 'conclusão'), COALESCE(sum(f.tempo_consumido), 0)
      FROM gold.fato_interacao f JOIN gold.dim_conteudo d USING (conteudo_id)
     GROUP BY f.mes, d.categoria;

    WITH ativos AS (
        SELECT mes, usuario_pseudo, count(*) AS interacoes FROM gold.fato_interacao GROUP BY mes, usuario_pseudo
    ), limite AS (
        SELECT max(data_hora) AS ultima FROM gold.fato_interacao
    )
    INSERT INTO gold.kpi_usuarios_ativos_mensal (mes_referencia, pessoas_ativas, interacoes, interacoes_por_pessoa,
                                                 pessoas_retidas, retencao_pct, mes_completo)
    SELECT a.mes, count(DISTINCT a.usuario_pseudo), sum(a.interacoes),
           round(sum(a.interacoes)::numeric / count(DISTINCT a.usuario_pseudo), 2),
           CASE WHEN a.mes = date_trunc('month', l.ultima)::date THEN NULL ELSE count(DISTINCT b.usuario_pseudo) END,
           CASE WHEN a.mes = date_trunc('month', l.ultima)::date THEN NULL
                ELSE round(100.0 * count(DISTINCT b.usuario_pseudo) / count(DISTINCT a.usuario_pseudo), 1) END,
           (a.mes + interval '1 month') <= date_trunc('day', l.ultima) + interval '1 day'
      FROM ativos a
      CROSS JOIN limite l
      LEFT JOIN ativos b ON b.usuario_pseudo = a.usuario_pseudo AND b.mes = (a.mes + interval '1 month')::date
     GROUP BY a.mes, l.ultima;

    -- mesma regra do Desafio 1 (documentacao/kpis.md): par concluido = conclusao ou percentual 100
    WITH pares AS (
        SELECT f.usuario_pseudo, f.conteudo_id, d.categoria, d.tipo, d.nivel,
               bool_or(f.tipo_interacao = 'conclusão' OR f.percentual_conclusao >= 100) AS concluiu
          FROM gold.fato_interacao f JOIN gold.dim_conteudo d USING (conteudo_id)
         WHERE f.tipo_interacao IN ('visualização', 'início', 'conclusão')
         GROUP BY f.usuario_pseudo, f.conteudo_id, d.categoria, d.tipo, d.nivel
    )
    INSERT INTO gold.kpi_taxa_conclusao (categoria, tipo, nivel, pares_consumo, pares_concluidos, taxa_conclusao_pct)
    SELECT categoria, tipo, nivel, count(*), count(*) FILTER (WHERE concluiu),
           round(100.0 * count(*) FILTER (WHERE concluiu) / count(*), 1)
      FROM pares GROUP BY categoria, tipo, nivel;

    INSERT INTO gold.kpi_conversao_recomendacao (classificacao, categoria, recomendacoes, convertidas, conversao_pct)
    SELECT r.classificacao, d.categoria, count(*), count(*) FILTER (WHERE r.convertida),
           round(100.0 * count(*) FILTER (WHERE r.convertida) / count(*), 1)
      FROM gold.fato_recomendacao r JOIN gold.dim_conteudo d USING (conteudo_id)
     GROUP BY r.classificacao, d.categoria;

    INSERT INTO gold.kpi_avaliacao (categoria, tipo, avaliacoes, avaliacao_media, pct_positivas)
    SELECT d.categoria, d.tipo, count(f.avaliacao_atribuida), round(avg(f.avaliacao_atribuida), 2),
           round(100.0 * count(*) FILTER (WHERE f.avaliacao_atribuida >= 4) / count(f.avaliacao_atribuida), 1)
      FROM gold.fato_interacao f JOIN gold.dim_conteudo d USING (conteudo_id)
     WHERE f.avaliacao_atribuida IS NOT NULL
     GROUP BY d.categoria, d.tipo;

    RETURN QUERY
        SELECT 'gold.dim_conteudo', count(*) FROM gold.dim_conteudo
        UNION ALL SELECT 'gold.dim_usuario', count(*) FROM gold.dim_usuario
        UNION ALL SELECT 'gold.fato_interacao', count(*) FROM gold.fato_interacao
        UNION ALL SELECT 'gold.fato_recomendacao', count(*) FROM gold.fato_recomendacao
        UNION ALL SELECT 'gold.kpi_engajamento_mensal', count(*) FROM gold.kpi_engajamento_mensal
        UNION ALL SELECT 'gold.kpi_usuarios_ativos_mensal', count(*) FROM gold.kpi_usuarios_ativos_mensal
        UNION ALL SELECT 'gold.kpi_taxa_conclusao', count(*) FROM gold.kpi_taxa_conclusao
        UNION ALL SELECT 'gold.kpi_conversao_recomendacao', count(*) FROM gold.kpi_conversao_recomendacao
        UNION ALL SELECT 'gold.kpi_avaliacao', count(*) FROM gold.kpi_avaliacao;
END;
$$;
