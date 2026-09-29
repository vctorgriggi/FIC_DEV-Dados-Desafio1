-- Desafio 2 — descricoes do catalogo (RF27, RF28). Idempotente; aplicado pelo db-init por ultimo.
-- As descricoes ficam no proprio PostgreSQL (COMMENT ON): o OpenMetadata as ingere junto com os
-- metadados tecnicos, e elas tambem aparecem no psql (\d+). Classificacoes, glossario, responsaveis
-- e linhagem sao aplicados por openmetadata/provisionar.py.

-- schemas
COMMENT ON SCHEMA public IS 'Banco do Desafio 1 (fonte histórica). Não é lido pelas camadas do Desafio 2.';
COMMENT ON SCHEMA bronze IS 'Camada Bronze (RF20): cópia auditável das fontes, campos como texto, append-only por execução. Contém dados pessoais: acesso só do dono do banco.';
COMMENT ON SCHEMA silver IS 'Camada Silver (RF21): dados tipados, padronizados, validados e deduplicados, sem dado pessoal direto. Publicada numa única transação por silver.publicar().';
COMMENT ON SCHEMA gold IS 'Camada Gold (RF26): tabelas de consumo orientadas aos KPIs. Sem dado pessoal; pessoas identificadas por pseudônimo. Lida pelo Superset com o papel consumo.';
COMMENT ON SCHEMA quarentena IS 'Registros rejeitados pela validação da Silver, com a regra violada e o ciclo de correção e reprocessamento (RF23).';
COMMENT ON SCHEMA qualidade IS 'Testes de qualidade e resultados por execução e por fonte (RF31).';
COMMENT ON SCHEMA controle IS 'Execuções e etapas do workflow do Apache Hop (RF22).';
COMMENT ON SCHEMA restrito IS 'Tabela de correspondência entre usuário e pseudônimo, para reidentificação controlada (RF33). Acesso restrito.';
COMMENT ON SCHEMA lgpd IS 'Funções de proteção de dados pessoais: pseudonimização, hash com salt, mascaramento e anonimização de texto (RF33).';
COMMENT ON SCHEMA validacao IS 'Regras de validação da Silver e área de preparo temporária de uma execução. Não é catalogado.';

-- controle
COMMENT ON TABLE controle.execucao IS 'Uma linha por execução do fluxo (completa, isolada ou agendada), com o status final.';
COMMENT ON COLUMN controle.execucao.execucao_id IS 'UUID v4 da execução; correlaciona logs, camadas, quarentena e qualidade.';
COMMENT ON COLUMN controle.execucao.status IS 'em_andamento, sucesso, sucesso_com_ressalvas (quarentena ou teste não crítico reprovado) ou falha.';
COMMENT ON TABLE controle.etapa IS 'Uma linha por etapa de cada execução, com duração, contagens e status.';
COMMENT ON TABLE controle.etapa_historico IS 'Tentativas anteriores de uma etapa, guardadas quando a etapa é reprocessada.';
COMMENT ON COLUMN controle.etapa.quarentena IS 'Registros rejeitados na etapa (na etapa qualidade: testes reprovados).';

-- bronze
COMMENT ON TABLE bronze.catalogo IS 'Catálogo de conteúdos como veio dos arquivos dados/brutos/catalogo.csv e lote_2/catalogo.csv.';
COMMENT ON TABLE bronze.usuarios IS 'Cadastro de usuários como veio de dados/brutos/usuarios.csv e lote_2/usuarios.csv. Contém dados pessoais (fictícios).';
COMMENT ON TABLE bronze.interacoes IS 'Interações como vieram de dados/brutos/interacoes.json e lote_2/interacoes.json.';
COMMENT ON TABLE bronze.comentarios IS 'Comentários e avaliações como vieram de dados/brutos/comentarios.json e lote_2/comentarios.json; o texto livre pode conter dados pessoais.';
COMMENT ON TABLE bronze.recomendacoes IS 'Recomendações entregues no Desafio 1 (snapshot fixo dados/brutos/recomendacoes_desafio1.json).';
COMMENT ON COLUMN bronze.usuarios.nome IS 'Nome completo. Dado pessoal.';
COMMENT ON COLUMN bronze.usuarios.email IS 'E-mail. Dado pessoal.';
COMMENT ON COLUMN bronze.usuarios.cpf IS 'CPF (fictício, dígito verificador inválido). Dado pessoal identificador.';
COMMENT ON COLUMN bronze.usuarios.telefone IS 'Telefone (fictício, DDD 00). Dado pessoal.';
COMMENT ON COLUMN bronze.usuarios.data_nascimento IS 'Data de nascimento. Dado pessoal; indica crianças e adolescentes (LGPD art. 14).';
COMMENT ON COLUMN bronze.comentarios.comentario IS 'Texto livre; pode conter e-mail ou telefone digitados pelo usuário.';
-- colunas de auditoria: mesmas em todas as tabelas da bronze (e _execucao_id, _origem e _ingerido_em na silver)
DO $$
DECLARE
    t RECORD;
BEGIN
    FOR t IN SELECT c.table_schema, c.table_name, c.column_name FROM information_schema.columns c
              WHERE c.table_schema IN ('bronze', 'silver') AND c.column_name LIKE '\_%' LOOP
        EXECUTE format('COMMENT ON COLUMN %I.%I.%I IS %L', t.table_schema, t.table_name, t.column_name,
            CASE t.column_name
                WHEN '_execucao_id' THEN 'Execução que ingeriu o registro na Bronze (auditoria).'
                WHEN '_origem' THEN 'Arquivo de origem, relativo a desafio_dados/ (auditoria).'
                WHEN '_linha' THEN 'Posição do registro no arquivo de origem, a partir de 1 (auditoria).'
                WHEN '_ingerido_em' THEN 'Instante da ingestão na Bronze; a Silver herda o valor (auditoria).'
            END);
    END LOOP;
END;
$$;

-- silver
COMMENT ON TABLE silver.conteudo IS 'Conteúdos validados; o lote 2 prevalece sobre o Desafio 1 quando o mesmo id aparece nas duas fontes.';
COMMENT ON TABLE silver.usuario IS 'Usuários validados, um por usuario_id, só com campos protegidos (sem nome, e-mail, CPF, telefone ou nascimento).';
COMMENT ON COLUMN silver.usuario.usuario_pseudo IS 'Pseudônimo: HMAC-SHA256 do usuario_id com chave secreta. Permite associação controlada via restrito.usuario_pseudonimo.';
COMMENT ON COLUMN silver.usuario.nome_mascarado IS 'Primeiro nome e inicial do último sobrenome (ex.: Ana S***).';
COMMENT ON COLUMN silver.usuario.email_mascarado IS 'Primeira letra e domínio (ex.: a***@email.example).';
COMMENT ON COLUMN silver.usuario.email_hash IS 'SHA-256 com salt do e-mail normalizado; comparação irreversível, usada nos dados mestres.';
COMMENT ON COLUMN silver.usuario.cpf_hash IS 'SHA-256 com salt do CPF só com dígitos; comparação irreversível, usada nos dados mestres.';
COMMENT ON COLUMN silver.usuario.faixa_etaria IS 'Faixa etária derivada da data de nascimento, que não sobe para a Silver. 0-17 = criança ou adolescente.';
COMMENT ON TABLE silver.usuario_mestre IS 'Dado mestre (RF30): uma linha por pessoa, consolidando usuario_ids com o mesmo cpf_hash ou email_hash.';
COMMENT ON TABLE silver.usuario_correspondencia IS 'Associa cada usuario_id à sua pessoa (usuário mestre) e registra a regra de correspondência.';
COMMENT ON TABLE silver.interacao IS 'Interações validadas, com referência a usuário e conteúdo aprovados.';
COMMENT ON TABLE silver.comentario IS 'Comentários validados, com e-mails e telefones do texto livre substituídos por marcadores.';
COMMENT ON TABLE silver.recomendacao IS 'Recomendações do Desafio 1 validadas.';

-- quarentena, qualidade e restrito
COMMENT ON TABLE quarentena.registro IS 'Registros rejeitados, com regra, severidade e mensagem. Status: pendente, corrigido, reprocessado ou descartado. Pode conter dados pessoais do registro original.';
COMMENT ON COLUMN quarentena.registro.registro IS 'Registro em JSON; editável para correção. Pode conter dados pessoais.';
COMMENT ON COLUMN quarentena.registro.registro_original IS 'Registro como veio da Bronze; nunca muda. Pode conter dados pessoais.';
COMMENT ON TABLE qualidade.teste IS 'Definição dos testes de qualidade: dimensão, fórmula, limite, severidade, ação e consulta.';
COMMENT ON TABLE qualidade.resultado IS 'Resultado de cada teste por execução e por fonte.';
COMMENT ON COLUMN qualidade.resultado.limite_aceitavel IS 'Limite vigente quando o teste rodou (com operador e severidade); mudar o teste depois não altera o histórico.';
COMMENT ON VIEW qualidade.vw_resultado IS 'Resultados com o teste e a data da execução; alimenta o gráfico de evolução da qualidade.';
COMMENT ON TABLE restrito.usuario_pseudonimo IS 'Correspondência usuario_id <-> pseudônimo. Permite reidentificar; nunca exposta ao consumo.';

-- gold
COMMENT ON TABLE gold.dim_conteudo IS 'Dimensão de conteúdos do catálogo.';
COMMENT ON TABLE gold.dim_usuario IS 'Dimensão de pessoas (usuário mestre), só com atributos de perfil agregáveis.';
COMMENT ON COLUMN gold.dim_usuario.nome_mascarado IS 'Primeiro nome e inicial do último sobrenome (ex.: Ana S***). Único campo derivado de dado pessoal exibido no consumo (RF33).';
COMMENT ON COLUMN gold.dim_usuario.usuario_pseudo IS 'Pseudônimo da pessoa (usuário mestre). Não permite reidentificar sem a chave.';
COMMENT ON TABLE gold.fato_interacao IS 'Fato de interações, uma linha por interação, por pessoa.';
COMMENT ON TABLE gold.fato_recomendacao IS 'Fato de recomendações, com a indicação de conversão.';
COMMENT ON COLUMN gold.fato_recomendacao.convertida IS 'Verdadeiro se a pessoa consumiu o conteúdo recomendado depois de gerado_em.';
COMMENT ON TABLE gold.kpi_engajamento_mensal IS 'Interações, pessoas ativas, conclusões e minutos por mês e categoria. Mesma regra do pipeline Beam (RF25).';
COMMENT ON TABLE gold.kpi_usuarios_ativos_mensal IS 'KPI Usuário ativo: pessoas com ao menos uma interação no mês, e retenção no mês seguinte.';
COMMENT ON COLUMN gold.kpi_usuarios_ativos_mensal.pessoas_ativas IS 'Pessoas (usuário mestre) com ao menos uma interação no mês.';
COMMENT ON TABLE gold.kpi_taxa_conclusao IS 'KPI Taxa de conclusão por categoria, tipo e nível.';
COMMENT ON COLUMN gold.kpi_taxa_conclusao.taxa_conclusao_pct IS '100 * pares (pessoa, conteúdo) concluídos / pares com consumo.';
COMMENT ON TABLE gold.kpi_conversao_recomendacao IS 'KPI Conversão de recomendação por classificação e categoria.';
COMMENT ON COLUMN gold.kpi_conversao_recomendacao.conversao_pct IS '100 * recomendações convertidas / recomendações.';
COMMENT ON TABLE gold.kpi_avaliacao IS 'KPI Avaliação média e percentual de avaliações positivas por categoria e tipo.';
COMMENT ON COLUMN gold.kpi_avaliacao.avaliacao_media IS 'Média das avaliações atribuídas, escala 1 a 5.';

-- gold: demais colunas (RF26: chaves, grao e regras de calculo documentadas no proprio catalogo)
COMMENT ON COLUMN gold.dim_conteudo.conteudo_id IS 'Chave do conteúdo (a mesma da fonte).';
COMMENT ON COLUMN gold.dim_conteudo.titulo IS 'Título do conteúdo.';
COMMENT ON COLUMN gold.dim_conteudo.tipo IS 'Formato: Artigo, Curso, Podcast ou Vídeo.';
COMMENT ON COLUMN gold.dim_conteudo.categoria IS 'Categoria temática do catálogo (8 categorias).';
COMMENT ON COLUMN gold.dim_conteudo.nivel IS 'Nível: Básico, Intermediário ou Avançado.';
COMMENT ON COLUMN gold.dim_conteudo.carga_horaria_min IS 'Carga horária em minutos.';
COMMENT ON COLUMN gold.dim_conteudo.data_publicacao IS 'Data de publicação; interações anteriores a ela não chegam à Gold.';
COMMENT ON COLUMN gold.dim_usuario.faixa_etaria IS 'Faixa etária (0-17, 18-24, 25-34, 35-44, 45-59, 60+); substitui a data de nascimento.';
COMMENT ON COLUMN gold.dim_usuario.uf IS 'UF do cadastro sobrevivente; a cidade não chega à Gold (minimização).';
COMMENT ON COLUMN gold.dim_usuario.data_cadastro IS 'Data do cadastro mais antigo da pessoa.';
COMMENT ON COLUMN gold.dim_usuario.registros_origem IS 'Quantos usuario_id da fonte foram consolidados nesta pessoa (RF30).';
COMMENT ON COLUMN gold.fato_interacao.interacao_id IS 'Chave da interação (grão da tabela).';
COMMENT ON COLUMN gold.fato_interacao.usuario_pseudo IS 'Pseudônimo da pessoa (usuário mestre), e não do id de origem.';
COMMENT ON COLUMN gold.fato_interacao.conteudo_id IS 'Conteúdo da interação (gold.dim_conteudo).';
COMMENT ON COLUMN gold.fato_interacao.tipo_interacao IS 'visualização, início, conclusão, avaliação, curtida ou compartilhamento (valores com acento).';
COMMENT ON COLUMN gold.fato_interacao.data_hora IS 'Momento da interação, sem fuso.';
COMMENT ON COLUMN gold.fato_interacao.data IS 'data_hora::date.';
COMMENT ON COLUMN gold.fato_interacao.mes IS 'Primeiro dia do mês de data_hora.';
COMMENT ON COLUMN gold.fato_interacao.tempo_consumido IS 'Minutos consumidos na interação.';
COMMENT ON COLUMN gold.fato_interacao.percentual_conclusao IS 'Percentual do conteúdo concluído (0 a 100); 100 conta como conclusão.';
COMMENT ON COLUMN gold.fato_interacao.avaliacao_atribuida IS 'Nota de 1 a 5, quando a interação tem avaliação.';
COMMENT ON COLUMN gold.fato_recomendacao.usuario_pseudo IS 'Pseudônimo da pessoa que recebeu a recomendação.';
COMMENT ON COLUMN gold.fato_recomendacao.conteudo_id IS 'Conteúdo recomendado.';
COMMENT ON COLUMN gold.fato_recomendacao.pontuacao IS 'Pontuação do motor de recomendação do Desafio 1 (0 a 100).';
COMMENT ON COLUMN gold.fato_recomendacao.posicao IS 'Posição na lista da pessoa (1 a 10).';
COMMENT ON COLUMN gold.fato_recomendacao.classificacao IS 'Faixa da pontuação no Desafio 1: positivo (>= 70) ou estavel (40 a 70); as negativas não são recomendadas.';
COMMENT ON COLUMN gold.fato_recomendacao.gerado_em IS 'Momento em que a recomendação foi gerada (snapshot do Desafio 1).';
COMMENT ON COLUMN gold.fato_recomendacao.convertida_em IS 'Primeiro consumo do conteúdo pela pessoa depois de gerado_em; nulo se não converteu.';
COMMENT ON COLUMN gold.kpi_engajamento_mensal.mes IS 'Mês no formato AAAA-MM (chave, com categoria).';
COMMENT ON COLUMN gold.kpi_engajamento_mensal.mes_referencia IS 'Primeiro dia do mês, para eixos de tempo.';
COMMENT ON COLUMN gold.kpi_engajamento_mensal.categoria IS 'Categoria do conteúdo (chave, com mês).';
COMMENT ON COLUMN gold.kpi_engajamento_mensal.interacoes IS 'count(*) das interações no mês e na categoria.';
COMMENT ON COLUMN gold.kpi_engajamento_mensal.pessoas_ativas IS 'count(DISTINCT usuario_pseudo): pessoas, não ids.';
COMMENT ON COLUMN gold.kpi_engajamento_mensal.conclusoes IS 'Interações do tipo conclusão.';
COMMENT ON COLUMN gold.kpi_engajamento_mensal.minutos_consumidos IS 'Soma de tempo_consumido.';
COMMENT ON COLUMN gold.kpi_usuarios_ativos_mensal.mes_referencia IS 'Primeiro dia do mês (chave).';
COMMENT ON COLUMN gold.kpi_usuarios_ativos_mensal.interacoes IS 'Interações no mês.';
COMMENT ON COLUMN gold.kpi_usuarios_ativos_mensal.interacoes_por_pessoa IS 'interações / pessoas_ativas.';
COMMENT ON COLUMN gold.kpi_usuarios_ativos_mensal.pessoas_retidas IS 'Pessoas ativas no mês que também estão ativas no mês seguinte; nulo no último mês.';
COMMENT ON COLUMN gold.kpi_usuarios_ativos_mensal.retencao_pct IS '100 * pessoas_retidas / pessoas_ativas; nulo no último mês.';
COMMENT ON COLUMN gold.kpi_usuarios_ativos_mensal.mes_completo IS 'Falso quando os dados terminam antes do fim do mês; comparações entre meses usam só os completos.';
COMMENT ON COLUMN gold.kpi_taxa_conclusao.categoria IS 'Categoria do conteúdo (chave, com tipo e nível).';
COMMENT ON COLUMN gold.kpi_taxa_conclusao.tipo IS 'Formato do conteúdo.';
COMMENT ON COLUMN gold.kpi_taxa_conclusao.nivel IS 'Nível do conteúdo.';
COMMENT ON COLUMN gold.kpi_taxa_conclusao.pares_consumo IS 'Pares (pessoa, conteúdo) com visualização, início ou conclusão. Denominador da taxa.';
COMMENT ON COLUMN gold.kpi_taxa_conclusao.pares_concluidos IS 'Pares com conclusão ou percentual_conclusao = 100. Numerador da taxa; agregue somando e dividindo.';
COMMENT ON COLUMN gold.kpi_conversao_recomendacao.classificacao IS 'Faixa da pontuação (chave, com categoria).';
COMMENT ON COLUMN gold.kpi_conversao_recomendacao.categoria IS 'Categoria do conteúdo recomendado.';
COMMENT ON COLUMN gold.kpi_conversao_recomendacao.recomendacoes IS 'Recomendações. Denominador da conversão.';
COMMENT ON COLUMN gold.kpi_conversao_recomendacao.convertidas IS 'Recomendações seguidas de consumo. Numerador da conversão.';
COMMENT ON COLUMN gold.kpi_avaliacao.categoria IS 'Categoria do conteúdo (chave, com tipo).';
COMMENT ON COLUMN gold.kpi_avaliacao.tipo IS 'Formato do conteúdo.';
COMMENT ON COLUMN gold.kpi_avaliacao.avaliacoes IS 'Interações com avaliação. Peso para a média ponderada ao agregar.';
COMMENT ON COLUMN gold.kpi_avaliacao.pct_positivas IS '100 * avaliações >= 4 / avaliações.';

-- restrito
COMMENT ON COLUMN restrito.usuario_pseudonimo.usuario_id IS 'Id de origem do usuário. Com o pseudônimo, permite reidentificar.';
COMMENT ON COLUMN restrito.usuario_pseudonimo.usuario_pseudo IS 'HMAC-SHA256 do usuario_id com LGPD_CHAVE_PSEUDONIMO.';
COMMENT ON COLUMN restrito.usuario_pseudonimo.criado_em IS 'Quando o pseudônimo foi registrado.';

-- colunas de usuarios que aparecem nas evidencias do catalogo (bronze e silver)
COMMENT ON COLUMN bronze.usuarios.usuario_id IS 'Id do usuário na fonte, como texto. Identificador indireto.';
COMMENT ON COLUMN bronze.usuarios.cidade IS 'Cidade do cadastro. Identificador indireto; não chega à Gold.';
COMMENT ON COLUMN bronze.usuarios.uf IS 'UF do cadastro. Identificador indireto.';
COMMENT ON COLUMN bronze.usuarios.data_cadastro IS 'Data do cadastro, como texto. Identificador indireto em conjunto com outros campos.';
COMMENT ON COLUMN bronze.usuarios.atualizado_em IS 'Última atualização do cadastro; decide qual versão sobrevive.';
COMMENT ON COLUMN silver.usuario.usuario_id IS 'Chave do usuário na fonte. Não chega à Gold, que usa o pseudônimo da pessoa.';
COMMENT ON COLUMN silver.usuario.cidade IS 'Cidade do cadastro. Identificador indireto; não chega à Gold.';
COMMENT ON COLUMN silver.usuario.uf IS 'UF do cadastro, validada contra a lista de UFs.';
COMMENT ON COLUMN silver.usuario.data_cadastro IS 'Data do cadastro.';
COMMENT ON COLUMN silver.usuario.atualizado_em IS 'Última atualização do cadastro; entre versões do mesmo id, vale a mais recente.';
