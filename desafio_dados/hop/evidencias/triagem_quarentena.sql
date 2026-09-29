-- Triagem da quarentena na demonstracao (RF23): rodada 1 entre as execucoes A e B, rodada 2 entre B e C.
--   docker compose exec -T postgres psql -U desafio -d desafio -f - < hop/evidencias/triagem_quarentena.sql
-- Correcao: edita o registro e marca 'corrigido'; a proxima Silver usa a versao corrigida no lugar da bronze.
-- Descarte: decisao revisada de nao aproveitar o registro; ele sai do fluxo.

-- ---------------------------------------------------------------- rodada 1 (entre A e B)

-- L2-C04: carga horaria digitada com sinal trocado
UPDATE quarentena.registro
   SET registro = jsonb_set(registro, '{carga_horaria_min}', '"45"'), status = 'corrigido', corrigido_em = now()
 WHERE fonte = 'catalogo' AND chave_registro = '1041' AND regra = 'VALOR_NEGATIVO';

-- L2-K09: data inexistente (31/09) corrigida para 30/09. A execucao B rodou em 29/09, entao a correcao ainda
-- violava uma regra (DATA_FUTURA): o registro voltou a pendente com a nova regra, em vez de entrar na Silver.
UPDATE quarentena.registro
   SET registro = jsonb_set(registro, '{data}', '"2026-09-30"'), status = 'corrigido', corrigido_em = now()
 WHERE fonte = 'comentarios' AND regra = 'DATA_INVALIDA' AND registro ->> 'data' = '2026-09-31';

-- copias identicas e a versao conflitante do conteudo 1010, revisadas: nao ha o que aproveitar
UPDATE quarentena.registro SET status = 'descartado'
 WHERE regra IN ('DUPLICADO', 'CONFLITO_VERSAO') AND status = 'pendente';

-- ---------------------------------------------------------------- rodada 2 (entre B e C)

-- L2-K09: nova correcao, com a data confirmada pela fonte (20/09)
UPDATE quarentena.registro
   SET registro = jsonb_set(registro, '{data}', '"2026-09-20"'), status = 'corrigido', corrigido_em = now()
 WHERE fonte = 'comentarios' AND registro_original ->> 'data' = '2026-09-31' AND status = 'pendente';

SELECT fonte, regra, status, count(*) FROM quarentena.registro
 WHERE status <> 'pendente' GROUP BY 1, 2, 3 ORDER BY 1, 2;
