-- Demonstracao das tecnicas de protecao (RF33). Roda como dono do banco e troca de papel com SET ROLE.
--   docker compose exec -T postgres psql -U desafio -d desafio -f - < lgpd/demonstracao.sql
-- Os erros "permission denied" da parte 1 sao o resultado esperado.
\pset footer off

\echo '=== 1. O consumo (papel do Superset e do SQL Lab) nao le dado pessoal'
SET ROLE consumo;
SELECT current_user AS papel;
SELECT nome, email, cpf FROM bronze.usuarios LIMIT 1;
SELECT usuario_id, email_hash FROM silver.usuario LIMIT 1;
SELECT * FROM restrito.usuario_pseudonimo LIMIT 1;
\echo 'o que o consumo ve da pessoa:'
SELECT nome_mascarado, left(usuario_pseudo, 16) || '...' AS pseudonimo, faixa_etaria, uf
  FROM gold.dim_usuario ORDER BY usuario_pseudo LIMIT 3;

\echo '=== 2. Nenhum e-mail, CPF ou telefone em texto na Gold (varredura de todas as linhas)'
WITH padrao AS (
    SELECT '[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}|\(?[0-9]{2}\)?[ ]?9?[0-9]{4}-[0-9]{4}' AS re
)
SELECT 'gold.dim_usuario' AS tabela, count(*) FILTER (WHERE d::text ~ re) AS ocorrencias, count(*) AS linhas
  FROM gold.dim_usuario d, padrao
UNION ALL SELECT 'gold.fato_interacao', count(*) FILTER (WHERE f::text ~ re), count(*) FROM gold.fato_interacao f, padrao
UNION ALL SELECT 'gold.fato_recomendacao', count(*) FILTER (WHERE r::text ~ re), count(*) FROM gold.fato_recomendacao r, padrao;
RESET ROLE;

\echo '=== 3. Mascaramento: o original fica na bronze; o consumo ve so a versao mascarada'
SELECT b.nome AS nome_original_bronze, s.nome_mascarado, b.email AS email_original_bronze, s.email_mascarado
  FROM silver.usuario s
  JOIN bronze.usuarios b ON btrim(b.usuario_id)::int = s.usuario_id AND b._execucao_id = s._execucao_id
 WHERE s.usuario_id = 12 LIMIT 1;

\echo '=== 4. Hash com salt: comparar sem revelar (usuarios 12 e 171 tem o mesmo CPF: L2-U01)'
SELECT usuario_id, left(cpf_hash, 16) || '...' AS cpf_hash,
       cpf_hash = (SELECT cpf_hash FROM silver.usuario WHERE usuario_id = 12) AS mesmo_cpf_que_12
  FROM silver.usuario WHERE usuario_id IN (12, 171, 30) ORDER BY usuario_id;
\echo 'sem o salt secreto, o mesmo CPF gera outro hash (sem salt, bastaria calcular o hash dos 10^9 CPFs possiveis para reverter):'
SELECT left(encode(digest(regexp_replace(cpf, '[^0-9]', '', 'g'), 'sha256'), 'hex'), 16) || '...' AS sha256_sem_salt
  FROM bronze.usuarios WHERE btrim(usuario_id) = '12' LIMIT 1;

\echo '=== 5. Pseudonimizacao: associacao controlada so pela tabela restrita (dono do banco)'
SELECT m.usuario_mestre_id, left(m.usuario_pseudo, 16) || '...' AS pseudonimo_na_gold, r.usuario_id AS reidentificado_por_restrito
  FROM silver.usuario_mestre m
  JOIN restrito.usuario_pseudonimo r ON r.usuario_pseudo = m.usuario_pseudo
 WHERE m.usuario_mestre_id IN (12, 30);

\echo '=== 6. Anonimizacao do texto livre (L2-K04 e L2-K05)'
SELECT b.comentario AS original_bronze, s.comentario AS silver
  FROM silver.comentario s
  JOIN bronze.comentarios b ON b._execucao_id = s._execucao_id AND b._origem = s._origem
   AND btrim(b.usuario_id)::int = s.usuario_id AND btrim(b.conteudo_id)::int = s.conteudo_id AND b.data = s.data::text
 WHERE s.comentario ~ '\[(email|telefone)\]';
