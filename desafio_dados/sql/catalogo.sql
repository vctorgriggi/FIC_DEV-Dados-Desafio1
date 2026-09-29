-- Desafio 2 — descricoes do catalogo (RF27, RF28). Idempotente; aplicado pelo db-init por ultimo.
-- As descricoes ficam no proprio PostgreSQL (COMMENT ON): o OpenMetadata as ingere junto com os
-- metadados tecnicos, e elas tambem aparecem no psql (\d+). Classificacoes, glossario, responsaveis
-- e linhagem sao aplicados por openmetadata/provisionar.py.

-- schemas
COMMENT ON SCHEMA public IS 'Banco do Desafio 1 (fonte historica). Nao e lido pelas camadas do Desafio 2.';
COMMENT ON SCHEMA bronze IS 'Camada Bronze (RF20): copia auditavel das fontes, campos como texto, append-only por execucao. Contem dados pessoais: acesso so do dono do banco.';
COMMENT ON SCHEMA silver IS 'Camada Silver (RF21): dados tipados, padronizados, validados e deduplicados, sem dado pessoal direto. Publicada numa unica transacao por silver.publicar().';
COMMENT ON SCHEMA gold IS 'Camada Gold (RF26): tabelas de consumo orientadas aos KPIs. Sem dado pessoal; pessoas identificadas por pseudonimo. Lida pelo Superset com o papel consumo.';
COMMENT ON SCHEMA quarentena IS 'Registros rejeitados pela validacao da Silver, com a regra violada e o ciclo de correcao e reprocessamento (RF23).';
COMMENT ON SCHEMA qualidade IS 'Testes de qualidade e resultados por execucao e por fonte (RF31).';
COMMENT ON SCHEMA controle IS 'Execucoes e etapas do workflow do Apache Hop (RF22).';
COMMENT ON SCHEMA restrito IS 'Tabela de correspondencia entre usuario e pseudonimo, para reidentificacao controlada (RF33). Acesso restrito.';
COMMENT ON SCHEMA lgpd IS 'Funcoes de protecao de dados pessoais: pseudonimizacao, hash com salt, mascaramento e anonimizacao de texto (RF33).';
COMMENT ON SCHEMA validacao IS 'Regras de validacao da Silver e area de preparo temporaria de uma execucao. Nao e catalogado.';

-- controle
COMMENT ON TABLE controle.execucao IS 'Uma linha por execucao do fluxo (completa, isolada ou agendada), com o status final.';
COMMENT ON COLUMN controle.execucao.execucao_id IS 'UUID v4 da execucao; correlaciona logs, camadas, quarentena e qualidade.';
COMMENT ON COLUMN controle.execucao.status IS 'em_andamento, sucesso, sucesso_com_ressalvas (quarentena ou teste nao critico reprovado) ou falha.';
COMMENT ON TABLE controle.etapa IS 'Uma linha por etapa de cada execucao, com duracao, contagens e status.';
COMMENT ON COLUMN controle.etapa.quarentena IS 'Registros rejeitados na etapa (na etapa qualidade: testes reprovados).';

-- bronze
COMMENT ON TABLE bronze.catalogo IS 'Catalogo de conteudos como veio dos arquivos dados/brutos/catalogo.csv e lote_2/catalogo.csv.';
COMMENT ON TABLE bronze.usuarios IS 'Cadastro de usuarios como veio de dados/brutos/usuarios.csv e lote_2/usuarios.csv. Contem dados pessoais (ficticios).';
COMMENT ON TABLE bronze.interacoes IS 'Interacoes como vieram de dados/brutos/interacoes.json e lote_2/interacoes.json.';
COMMENT ON TABLE bronze.comentarios IS 'Comentarios e avaliacoes como vieram de dados/brutos/comentarios.json e lote_2/comentarios.json; o texto livre pode conter dados pessoais.';
COMMENT ON TABLE bronze.recomendacoes IS 'Recomendacoes entregues no Desafio 1 (snapshot fixo dados/brutos/recomendacoes_desafio1.json).';
COMMENT ON COLUMN bronze.usuarios.nome IS 'Nome completo. Dado pessoal.';
COMMENT ON COLUMN bronze.usuarios.email IS 'E-mail. Dado pessoal.';
COMMENT ON COLUMN bronze.usuarios.cpf IS 'CPF (ficticio, digito verificador invalido). Dado pessoal identificador.';
COMMENT ON COLUMN bronze.usuarios.telefone IS 'Telefone (ficticio, DDD 00). Dado pessoal.';
COMMENT ON COLUMN bronze.usuarios.data_nascimento IS 'Data de nascimento. Dado pessoal; indica criancas e adolescentes (LGPD art. 14).';
COMMENT ON COLUMN bronze.comentarios.comentario IS 'Texto livre; pode conter e-mail ou telefone digitados pelo usuario.';
-- colunas de auditoria: mesmas em todas as tabelas da bronze (e _execucao_id, _origem e _ingerido_em na silver)
DO $$
DECLARE
    t RECORD;
BEGIN
    FOR t IN SELECT c.table_schema, c.table_name, c.column_name FROM information_schema.columns c
              WHERE c.table_schema IN ('bronze', 'silver') AND c.column_name LIKE '\_%' LOOP
        EXECUTE format('COMMENT ON COLUMN %I.%I.%I IS %L', t.table_schema, t.table_name, t.column_name,
            CASE t.column_name
                WHEN '_execucao_id' THEN 'Execucao que ingeriu o registro na bronze (auditoria).'
                WHEN '_origem' THEN 'Arquivo de origem, relativo a desafio_dados/ (auditoria).'
                WHEN '_linha' THEN 'Posicao do registro no arquivo de origem (auditoria).'
                WHEN '_ingerido_em' THEN 'Instante da ingestao na bronze (auditoria).'
            END);
    END LOOP;
END;
$$;

-- silver
COMMENT ON TABLE silver.conteudo IS 'Conteudos validados; o lote 2 prevalece sobre o Desafio 1 quando o mesmo id aparece nas duas fontes.';
COMMENT ON TABLE silver.usuario IS 'Usuarios validados, um por usuario_id, so com campos protegidos (sem nome, e-mail, CPF, telefone ou nascimento).';
COMMENT ON COLUMN silver.usuario.usuario_pseudo IS 'Pseudonimo: HMAC-SHA256 do usuario_id com chave secreta. Permite associacao controlada via restrito.usuario_pseudonimo.';
COMMENT ON COLUMN silver.usuario.nome_mascarado IS 'Primeiro nome e inicial do ultimo sobrenome (ex.: Ana S***).';
COMMENT ON COLUMN silver.usuario.email_mascarado IS 'Primeira letra e dominio (ex.: a***@email.example).';
COMMENT ON COLUMN silver.usuario.email_hash IS 'SHA-256 com salt do e-mail normalizado; comparacao irreversivel, usada nos dados mestres.';
COMMENT ON COLUMN silver.usuario.cpf_hash IS 'SHA-256 com salt do CPF so com digitos; comparacao irreversivel, usada nos dados mestres.';
COMMENT ON COLUMN silver.usuario.faixa_etaria IS 'Faixa etaria derivada da data de nascimento, que nao sobe para a Silver. 0-17 = crianca ou adolescente.';
COMMENT ON TABLE silver.usuario_mestre IS 'Dado mestre (RF30): uma linha por pessoa, consolidando usuario_ids com o mesmo cpf_hash ou email_hash.';
COMMENT ON TABLE silver.usuario_correspondencia IS 'Associa cada usuario_id a sua pessoa (usuario mestre) e registra a regra de correspondencia.';
COMMENT ON TABLE silver.interacao IS 'Interacoes validadas, com referencia a usuario e conteudo aprovados.';
COMMENT ON TABLE silver.comentario IS 'Comentarios validados, com e-mails e telefones do texto livre substituidos por marcadores.';
COMMENT ON TABLE silver.recomendacao IS 'Recomendacoes do Desafio 1 validadas.';

-- quarentena, qualidade e restrito
COMMENT ON TABLE quarentena.registro IS 'Registros rejeitados, com regra, severidade e mensagem. Status: pendente, corrigido, reprocessado ou descartado. Pode conter dados pessoais do registro original.';
COMMENT ON COLUMN quarentena.registro.registro IS 'Registro em JSON; editavel para correcao. Pode conter dados pessoais.';
COMMENT ON COLUMN quarentena.registro.registro_original IS 'Registro como veio da Bronze; nunca muda. Pode conter dados pessoais.';
COMMENT ON TABLE qualidade.teste IS 'Definicao dos testes de qualidade: dimensao, formula, limite, severidade, acao e consulta.';
COMMENT ON TABLE qualidade.resultado IS 'Resultado de cada teste por execucao e por fonte.';
COMMENT ON COLUMN qualidade.resultado.limite_aceitavel IS 'Limite vigente quando o teste rodou (com operador e severidade); mudar o teste depois nao altera o historico.';
COMMENT ON VIEW qualidade.vw_resultado IS 'Resultados com o teste e a data da execucao; alimenta o grafico de evolucao da qualidade.';
COMMENT ON TABLE restrito.usuario_pseudonimo IS 'Correspondencia usuario_id <-> pseudonimo. Permite reidentificar; nunca exposta ao consumo.';

-- gold
COMMENT ON TABLE gold.dim_conteudo IS 'Dimensao de conteudos do catalogo.';
COMMENT ON TABLE gold.dim_usuario IS 'Dimensao de pessoas (usuario mestre), so com atributos de perfil agregaveis.';
COMMENT ON COLUMN gold.dim_usuario.nome_mascarado IS 'Primeiro nome e inicial do ultimo sobrenome (ex.: Ana S***). Unico campo derivado de dado pessoal exibido no consumo (RF33).';
COMMENT ON COLUMN gold.dim_usuario.usuario_pseudo IS 'Pseudonimo da pessoa (usuario mestre). Nao permite reidentificar sem a chave.';
COMMENT ON TABLE gold.fato_interacao IS 'Fato de interacoes, uma linha por interacao, por pessoa.';
COMMENT ON TABLE gold.fato_recomendacao IS 'Fato de recomendacoes, com a indicacao de conversao.';
COMMENT ON COLUMN gold.fato_recomendacao.convertida IS 'Verdadeiro se a pessoa consumiu o conteudo recomendado depois de gerado_em.';
COMMENT ON TABLE gold.kpi_engajamento_mensal IS 'Interacoes, pessoas ativas, conclusoes e minutos por mes e categoria. Mesma regra do pipeline Beam (RF25).';
COMMENT ON TABLE gold.kpi_usuarios_ativos_mensal IS 'KPI Usuario ativo: pessoas com ao menos uma interacao no mes, e retencao no mes seguinte.';
COMMENT ON COLUMN gold.kpi_usuarios_ativos_mensal.pessoas_ativas IS 'Pessoas (usuario mestre) com ao menos uma interacao no mes.';
COMMENT ON TABLE gold.kpi_taxa_conclusao IS 'KPI Taxa de conclusao por categoria, tipo e nivel.';
COMMENT ON COLUMN gold.kpi_taxa_conclusao.taxa_conclusao_pct IS '100 * pares (pessoa, conteudo) concluidos / pares com consumo.';
COMMENT ON TABLE gold.kpi_conversao_recomendacao IS 'KPI Conversao de recomendacao por classificacao e categoria.';
COMMENT ON COLUMN gold.kpi_conversao_recomendacao.conversao_pct IS '100 * recomendacoes convertidas / recomendacoes.';
COMMENT ON TABLE gold.kpi_avaliacao IS 'KPI Avaliacao media e percentual de avaliacoes positivas por categoria e tipo.';
COMMENT ON COLUMN gold.kpi_avaliacao.avaliacao_media IS 'Media das avaliacoes atribuidas, escala 1 a 5.';

-- gold: demais colunas (RF26: chaves, grao e regras de calculo documentadas no proprio catalogo)
COMMENT ON COLUMN gold.dim_conteudo.conteudo_id IS 'Chave do conteudo (a mesma da fonte).';
COMMENT ON COLUMN gold.dim_conteudo.titulo IS 'Titulo do conteudo.';
COMMENT ON COLUMN gold.dim_conteudo.tipo IS 'Formato: Artigo, Curso, Podcast ou Video.';
COMMENT ON COLUMN gold.dim_conteudo.categoria IS 'Categoria tematica do catalogo (8 categorias).';
COMMENT ON COLUMN gold.dim_conteudo.nivel IS 'Nivel: Basico, Intermediario ou Avancado.';
COMMENT ON COLUMN gold.dim_conteudo.carga_horaria_min IS 'Carga horaria em minutos.';
COMMENT ON COLUMN gold.dim_conteudo.data_publicacao IS 'Data de publicacao; interacoes anteriores a ela nao chegam a Gold.';
COMMENT ON COLUMN gold.dim_usuario.faixa_etaria IS 'Faixa etaria (0-17, 18-24, 25-34, 35-44, 45-59, 60+); substitui a data de nascimento.';
COMMENT ON COLUMN gold.dim_usuario.uf IS 'UF do cadastro sobrevivente; a cidade nao chega a Gold (minimizacao).';
COMMENT ON COLUMN gold.dim_usuario.data_cadastro IS 'Data do cadastro mais antigo da pessoa.';
COMMENT ON COLUMN gold.dim_usuario.registros_origem IS 'Quantos usuario_id da fonte foram consolidados nesta pessoa (RF30).';
COMMENT ON COLUMN gold.fato_interacao.interacao_id IS 'Chave da interacao (grao da tabela).';
COMMENT ON COLUMN gold.fato_interacao.usuario_pseudo IS 'Pseudonimo da pessoa (usuario mestre), e nao do id de origem.';
COMMENT ON COLUMN gold.fato_interacao.conteudo_id IS 'Conteudo da interacao (gold.dim_conteudo).';
COMMENT ON COLUMN gold.fato_interacao.tipo_interacao IS 'visualização, início, conclusão, avaliação, curtida ou compartilhamento (valores com acento).';
COMMENT ON COLUMN gold.fato_interacao.data_hora IS 'Momento da interacao, sem fuso.';
COMMENT ON COLUMN gold.fato_interacao.data IS 'data_hora::date.';
COMMENT ON COLUMN gold.fato_interacao.mes IS 'Primeiro dia do mes de data_hora.';
COMMENT ON COLUMN gold.fato_interacao.tempo_consumido IS 'Minutos consumidos na interacao.';
COMMENT ON COLUMN gold.fato_interacao.percentual_conclusao IS 'Percentual do conteudo concluido (0 a 100); 100 conta como conclusao.';
COMMENT ON COLUMN gold.fato_interacao.avaliacao_atribuida IS 'Nota de 1 a 5, quando a interacao tem avaliacao.';
COMMENT ON COLUMN gold.fato_recomendacao.usuario_pseudo IS 'Pseudonimo da pessoa que recebeu a recomendacao.';
COMMENT ON COLUMN gold.fato_recomendacao.conteudo_id IS 'Conteudo recomendado.';
COMMENT ON COLUMN gold.fato_recomendacao.pontuacao IS 'Pontuacao do motor de recomendacao do Desafio 1 (0 a 100).';
COMMENT ON COLUMN gold.fato_recomendacao.posicao IS 'Posicao na lista da pessoa (1 a 10).';
COMMENT ON COLUMN gold.fato_recomendacao.classificacao IS 'Faixa da pontuacao no Desafio 1: positivo (>= 70) ou estavel (40 a 70); as negativas nao sao recomendadas.';
COMMENT ON COLUMN gold.fato_recomendacao.gerado_em IS 'Momento em que a recomendacao foi gerada (snapshot do Desafio 1).';
COMMENT ON COLUMN gold.fato_recomendacao.convertida_em IS 'Primeiro consumo do conteudo pela pessoa depois de gerado_em; nulo se nao converteu.';
COMMENT ON COLUMN gold.kpi_engajamento_mensal.mes IS 'Mes no formato AAAA-MM (chave, com categoria).';
COMMENT ON COLUMN gold.kpi_engajamento_mensal.mes_referencia IS 'Primeiro dia do mes, para eixos de tempo.';
COMMENT ON COLUMN gold.kpi_engajamento_mensal.categoria IS 'Categoria do conteudo (chave, com mes).';
COMMENT ON COLUMN gold.kpi_engajamento_mensal.interacoes IS 'count(*) das interacoes no mes e na categoria.';
COMMENT ON COLUMN gold.kpi_engajamento_mensal.pessoas_ativas IS 'count(DISTINCT usuario_pseudo): pessoas, nao ids.';
COMMENT ON COLUMN gold.kpi_engajamento_mensal.conclusoes IS 'Interacoes do tipo conclusao.';
COMMENT ON COLUMN gold.kpi_engajamento_mensal.minutos_consumidos IS 'Soma de tempo_consumido.';
COMMENT ON COLUMN gold.kpi_usuarios_ativos_mensal.mes_referencia IS 'Primeiro dia do mes (chave).';
COMMENT ON COLUMN gold.kpi_usuarios_ativos_mensal.interacoes IS 'Interacoes no mes.';
COMMENT ON COLUMN gold.kpi_usuarios_ativos_mensal.interacoes_por_pessoa IS 'interacoes / pessoas_ativas.';
COMMENT ON COLUMN gold.kpi_usuarios_ativos_mensal.pessoas_retidas IS 'Pessoas ativas no mes que tambem estao ativas no mes seguinte; nulo no ultimo mes.';
COMMENT ON COLUMN gold.kpi_usuarios_ativos_mensal.retencao_pct IS '100 * pessoas_retidas / pessoas_ativas; nulo no ultimo mes.';
COMMENT ON COLUMN gold.kpi_usuarios_ativos_mensal.mes_completo IS 'Falso quando os dados terminam antes do fim do mes; comparacoes entre meses usam so os completos.';
COMMENT ON COLUMN gold.kpi_taxa_conclusao.categoria IS 'Categoria do conteudo (chave, com tipo e nivel).';
COMMENT ON COLUMN gold.kpi_taxa_conclusao.tipo IS 'Formato do conteudo.';
COMMENT ON COLUMN gold.kpi_taxa_conclusao.nivel IS 'Nivel do conteudo.';
COMMENT ON COLUMN gold.kpi_taxa_conclusao.pares_consumo IS 'Pares (pessoa, conteudo) com visualizacao, inicio ou conclusao. Denominador da taxa.';
COMMENT ON COLUMN gold.kpi_taxa_conclusao.pares_concluidos IS 'Pares com conclusao ou percentual_conclusao = 100. Numerador da taxa; agregue somando e dividindo.';
COMMENT ON COLUMN gold.kpi_conversao_recomendacao.classificacao IS 'Faixa da pontuacao (chave, com categoria).';
COMMENT ON COLUMN gold.kpi_conversao_recomendacao.categoria IS 'Categoria do conteudo recomendado.';
COMMENT ON COLUMN gold.kpi_conversao_recomendacao.recomendacoes IS 'Recomendacoes. Denominador da conversao.';
COMMENT ON COLUMN gold.kpi_conversao_recomendacao.convertidas IS 'Recomendacoes seguidas de consumo. Numerador da conversao.';
COMMENT ON COLUMN gold.kpi_avaliacao.categoria IS 'Categoria do conteudo (chave, com tipo).';
COMMENT ON COLUMN gold.kpi_avaliacao.tipo IS 'Formato do conteudo.';
COMMENT ON COLUMN gold.kpi_avaliacao.avaliacoes IS 'Interacoes com avaliacao. Peso para a media ponderada ao agregar.';
COMMENT ON COLUMN gold.kpi_avaliacao.pct_positivas IS '100 * avaliacoes >= 4 / avaliacoes.';

-- restrito
COMMENT ON COLUMN restrito.usuario_pseudonimo.usuario_id IS 'Id de origem do usuario. Com o pseudonimo, permite reidentificar.';
COMMENT ON COLUMN restrito.usuario_pseudonimo.usuario_pseudo IS 'HMAC-SHA256 do usuario_id com LGPD_CHAVE_PSEUDONIMO.';
COMMENT ON COLUMN restrito.usuario_pseudonimo.criado_em IS 'Quando o pseudonimo foi registrado.';
