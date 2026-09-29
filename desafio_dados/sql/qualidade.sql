-- Desafio 2 — qualidade de dados (RF31). Idempotente; aplicado pelo db-init depois de sql/silver.sql.
--
-- Cada teste e uma linha de qualidade.teste com a consulta que o implementa: ela recebe a execucao ($1)
-- e devolve (fonte, total, falhos). valor_medido = 100 * (total - falhos) / total; aprovado quando
-- valor_medido <operador> limite_aceitavel. Este arquivo e a fonte da verdade dos testes: o INSERT
-- abaixo sobrescreve a configuracao a cada db-init.
--
-- hop/workflows/qualidade.hwf executa qualidade.executar(execucao) depois da Silver e interrompe o
-- fluxo, impedindo a Gold, se algum teste 'critica' reprovar.

INSERT INTO qualidade.teste (teste_id, nome, dimensao, alvo, formula, operador, limite_aceitavel, severidade, acao, consulta)
VALUES
('Q01_VALIDADE_FONTES',
 'Registros aprovados na validacao, por fonte', 'validade', 'bronze.* -> silver.*',
 '100 * (lidos - rejeitados) / lidos, por fonte, na validacao da Silver desta execucao',
 '>=', 90, 'critica',
 'Interrompe o fluxo antes da Gold: um lote com mais de 10% de rejeicao indica problema na fonte, nao em registros isolados. Tratar a quarentena e reprocessar.',
 $q$SELECT validacao.fonte_da_entidade(substr(etapa, 8)), lidos, quarentena
      FROM controle.etapa
     WHERE execucao_id = $1 AND etapa IN ('silver_conteudo', 'silver_usuario', 'silver_interacao',
                                          'silver_comentario', 'silver_recomendacao')$q$),

('Q02_INTEGRIDADE_REFERENCIAS',
 'Eventos que referenciam usuario e conteudo existentes, por fonte', 'integridade_referencial', 'bronze.interacoes, bronze.comentarios, bronze.recomendacoes',
 '100 * (lidos - rejeitados por REF_USUARIO ou REF_CONTEUDO) / lidos',
 '>=', 99, 'alta',
 'Etapa com ressalvas; os eventos orfaos ficam na quarentena. Verificar se o cadastro de usuarios ou o catalogo chegou incompleto.',
 $q$SELECT f.fonte, f.total, COALESCE(q.falhos, 0)
      FROM (SELECT 'interacoes' AS fonte, count(*) AS total FROM bronze.interacoes WHERE _execucao_id = $1
            UNION ALL SELECT 'comentarios', count(*) FROM bronze.comentarios WHERE _execucao_id = $1
            UNION ALL SELECT 'recomendacoes', count(*) FROM bronze.recomendacoes WHERE _execucao_id = $1) f
      LEFT JOIN (SELECT fonte, count(*) AS falhos FROM quarentena.registro
                  WHERE ultima_execucao_id = $1 AND status = 'pendente' AND regra IN ('REF_USUARIO', 'REF_CONTEUDO')
                  GROUP BY fonte) q USING (fonte)$q$),

('Q03_UNICIDADE_CHAVES',
 'Chaves de negocio unicas na Silver', 'unicidade', 'silver.*',
 '100 * chaves distintas / linhas, por tabela',
 '>=', 100, 'critica',
 'Interrompe o fluxo: duplicidade na Silver quebraria contagens da Gold. Revisar as regras de deduplicacao em sql/silver.sql.',
 $q$SELECT 'catalogo', count(*), count(*) - count(DISTINCT conteudo_id) FROM silver.conteudo
     UNION ALL SELECT 'usuarios', count(*), count(*) - count(DISTINCT usuario_id) FROM silver.usuario
     UNION ALL SELECT 'interacoes', count(*), count(*) - count(DISTINCT (usuario_id, conteudo_id, tipo_interacao, data_hora)) FROM silver.interacao
     UNION ALL SELECT 'comentarios', count(*), count(*) - count(DISTINCT (usuario_id, conteudo_id, data, md5(comentario))) FROM silver.comentario
     UNION ALL SELECT 'recomendacoes', count(*), count(*) - count(DISTINCT (usuario_id, conteudo_id, gerado_em)) FROM silver.recomendacao$q$),

('Q04_COMPLETUDE_CATALOGO',
 'Conteudos com descricao e autor preenchidos', 'completude', 'silver.conteudo',
 '100 * conteudos com descricao e autor / conteudos',
 '>=', 95, 'media',
 'Etapa com ressalvas; avisar o responsavel pelo catalogo para completar os cadastros.',
 $q$SELECT 'catalogo', count(*), count(*) FILTER (WHERE descricao IS NULL OR autor IS NULL) FROM silver.conteudo$q$),

('Q05_COMPLETUDE_USUARIOS',
 'Usuarios com cidade, data de cadastro e faixa etaria', 'completude', 'silver.usuario',
 '100 * usuarios com os tres campos / usuarios',
 '>=', 95, 'media',
 'Etapa com ressalvas; faixas etarias ausentes enfraquecem as analises por perfil.',
 $q$SELECT 'usuarios', count(*), count(*) FILTER (WHERE cidade IS NULL OR data_cadastro IS NULL OR faixa_etaria IS NULL)
      FROM silver.usuario$q$),

('Q06_CONSISTENCIA_TEMPORAL',
 'Eventos entre a publicacao do conteudo e o momento da execucao', 'consistencia', 'silver.interacao, silver.comentario',
 '100 * eventos com data >= data_publicacao e <= agora / eventos',
 '>=', 100, 'critica',
 'Interrompe o fluxo: evento fora do periodo possivel indica falha na regra DATA_ANTES_PUBLICACAO ou DATA_FUTURA.',
 $q$SELECT 'interacoes', count(*), count(*) FILTER (WHERE i.data_hora::date < c.data_publicacao OR i.data_hora > localtimestamp)
      FROM silver.interacao i JOIN silver.conteudo c USING (conteudo_id)
     UNION ALL
    SELECT 'comentarios', count(*), count(*) FILTER (WHERE m.data < c.data_publicacao OR m.data > current_date)
      FROM silver.comentario m JOIN silver.conteudo c USING (conteudo_id)$q$),

('Q07_COBERTURA_DADOS_MESTRES',
 'Usuarios associados a uma pessoa (dado mestre)', 'integridade_referencial', 'silver.usuario -> silver.usuario_correspondencia',
 '100 * usuarios com correspondencia / usuarios',
 '>=', 100, 'critica',
 'Interrompe o fluxo: sem o mestre, a Gold contaria ids em vez de pessoas (RF30).',
 $q$SELECT 'usuarios', count(*), count(*) FILTER (WHERE c.usuario_id IS NULL)
      FROM silver.usuario u LEFT JOIN silver.usuario_correspondencia c USING (usuario_id)$q$),

-- Q01 soma os arquivos de uma fonte (Desafio 1 + lote 2): um arquivo pequeno inteiro rejeitado quase nao
-- mexe no percentual. Q08 olha cada arquivo: mais da metade rejeitada e defeito estrutural (coluna faltando
-- ou deslocada, arquivo trocado), nao registros isolados.
('Q08_VALIDADE_POR_ARQUIVO',
 'Registros aprovados na validacao, por arquivo de origem', 'validade', 'bronze.* por _origem -> silver.*',
 '100 * (lidos - pendentes na quarentena) / lidos, por arquivo, nesta execucao',
 '>=', 50, 'critica',
 'Interrompe o fluxo antes da Gold: mais da metade de um arquivo rejeitada indica defeito na estrutura do arquivo. Conferir o cabecalho e a origem do arquivo e reprocessar.',
 $q$SELECT replace(l._origem, 'dados/brutos/', ''), l.lidos,
           (SELECT count(*) FROM quarentena.registro q
             WHERE q.origem = l._origem AND q.status = 'pendente' AND q.ultima_execucao_id = $1)
      FROM (SELECT _origem, count(*) AS lidos FROM bronze.catalogo WHERE _execucao_id = $1 GROUP BY 1
            UNION ALL SELECT _origem, count(*) FROM bronze.usuarios WHERE _execucao_id = $1 GROUP BY 1
            UNION ALL SELECT _origem, count(*) FROM bronze.interacoes WHERE _execucao_id = $1 GROUP BY 1
            UNION ALL SELECT _origem, count(*) FROM bronze.comentarios WHERE _execucao_id = $1 GROUP BY 1
            UNION ALL SELECT _origem, count(*) FROM bronze.recomendacoes WHERE _execucao_id = $1 GROUP BY 1) l$q$)
ON CONFLICT (teste_id) DO UPDATE
   SET nome = EXCLUDED.nome, dimensao = EXCLUDED.dimensao, alvo = EXCLUDED.alvo, formula = EXCLUDED.formula,
       operador = EXCLUDED.operador, limite_aceitavel = EXCLUDED.limite_aceitavel,
       severidade = EXCLUDED.severidade, acao = EXCLUDED.acao, consulta = EXCLUDED.consulta;

-- executa todos os testes para a execucao; rodar de novo substitui os resultados dela
CREATE OR REPLACE FUNCTION qualidade.executar(p_execucao_id TEXT)
RETURNS TABLE (teste_id TEXT, fonte TEXT, valor_medido NUMERIC, limite TEXT, severidade TEXT, aprovado BOOLEAN)
LANGUAGE plpgsql
AS $$
#variable_conflict use_column
DECLARE
    t RECORD;
    r RECORD;
    v_valor NUMERIC;
BEGIN
    DELETE FROM qualidade.resultado WHERE execucao_id = p_execucao_id;
    FOR t IN SELECT * FROM qualidade.teste ORDER BY teste_id LOOP
        -- colunas renomeadas por posicao e com tipo fixo: a consulta so precisa devolver fonte, total e falhos
        FOR r IN EXECUTE format('SELECT fonte::text, total::bigint, falhos::bigint FROM (%s) AS q (fonte, total, falhos)',
                                t.consulta) USING p_execucao_id LOOP
            v_valor := CASE WHEN r.total = 0 THEN 100 ELSE round(100.0 * (r.total - r.falhos) / r.total, 2) END;
            INSERT INTO qualidade.resultado (execucao_id, teste_id, fonte, total_registros, registros_falhos, valor_medido,
                                             aprovado, operador, limite_aceitavel, severidade)
            VALUES (p_execucao_id, t.teste_id, r.fonte, r.total, r.falhos, v_valor,
                    CASE t.operador WHEN '>=' THEN v_valor >= t.limite_aceitavel ELSE v_valor <= t.limite_aceitavel END,
                    t.operador, t.limite_aceitavel, t.severidade);
        END LOOP;
    END LOOP;
    RETURN QUERY
        SELECT r.teste_id, r.fonte, r.valor_medido, r.operador || ' ' || r.limite_aceitavel, r.severidade, r.aprovado
          FROM qualidade.resultado r
         WHERE r.execucao_id = p_execucao_id
         ORDER BY r.teste_id, r.fonte;
END;
$$;

-- resultados gravados antes de o limite e a severidade serem registrados por resultado recebem a
-- configuracao atual do teste (so preenche o que esta vazio; roda a cada db-init sem efeito depois)
UPDATE qualidade.resultado r
   SET operador = t.operador, limite_aceitavel = t.limite_aceitavel, severidade = t.severidade
  FROM qualidade.teste t
 WHERE t.teste_id = r.teste_id AND r.limite_aceitavel IS NULL;

-- resultados com o teste, para o dashboard e o SQL Lab (papel consumo le o schema qualidade);
-- limite e severidade sao os da execucao, nao os atuais do teste
CREATE OR REPLACE VIEW qualidade.vw_resultado AS
SELECT r.execucao_id, e.inicio AS executado_em, e.modo, r.teste_id, t.nome, t.dimensao, r.severidade,
       r.fonte, r.total_registros, r.registros_falhos, r.valor_medido,
       r.operador || ' ' || r.limite_aceitavel AS limite, r.aprovado,
       -- rotulo ordenavel de cada execucao (UTC), para os graficos de evolucao terem um ponto por execucao
       to_char(e.inicio AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS') AS execucao
  FROM qualidade.resultado r
  JOIN qualidade.teste t USING (teste_id)
  JOIN controle.execucao e USING (execucao_id);
