# Contratos entre as etapas — Desafio 2

A seção 5 do enunciado pede que a equipe trabalhe em paralelo "com dados de teste e contratos de entrada e saída previamente definidos". Este documento é esse contrato: o que cada etapa lê, o que escreve e em que formato. Assim, cada integrante desenvolve a sua parte sem esperar a do outro.

- **Fonte da verdade:** [`sql/camadas.sql`](../sql/camadas.sql) (estruturas e controle) e [`sql/silver.sql`](../sql/silver.sql) (regras de validação e publicação da Silver), aplicados automaticamente pelo serviço `db-init` a cada `docker compose up`. Aqui fica o resumo e as regras que o SQL não expressa.
- **Como a parte do Estudante 1 funciona e como demonstrá-la:** [`pipeline_hop.md`](pipeline_hop.md).
- **Mudou o contrato?** Combine com quem consome, altere `sql/camadas.sql` e este documento no mesmo commit.
- A camada Gold está implementada em `sql/camada_gold.sql`; grão, chaves e regras em [`camada_gold.md`](camada_gold.md).

## Quem produz e quem consome

| Etapa | RF | Responsável | Lê | Escreve |
| --- | --- | --- | --- | --- |
| Bronze | RF20 | Estudante 1 | `dados/brutos/` (D1, `lote_2/` e `recomendacoes_desafio1.json`) | `bronze.*` |
| Silver | RF21, RF30 | Estudante 1 | `bronze.*` da execução corrente, com as correções de `quarentena.registro` aplicadas | `silver.*`, `quarentena.registro`, `restrito.usuario_pseudonimo` |
| Qualidade | RF31 | Estudante 2 | `silver.*` | `qualidade.teste`, `qualidade.resultado` |
| Parquet | RF24 | Estudante 2 | `silver.*` | `dados/silver/*.parquet` |
| Beam | RF25 | Estudante 2 | `dados/silver/*.parquet` | Parquet e evidências em `beam/evidencias/` |
| Gold | RF26 | Estudante 2 | `silver.*` (nunca `bronze.*`) | `gold.*` |
| Workflow | RF22, RF23 | Estudante 1 | orquestra as etapas acima e a publicação de metadados | `controle.execucao`, `controle.etapa` |
| Metadados | RF27–RF29 | Estudante 3 | todos os schemas, via OpenMetadata | catálogo, glossário, classificações, linhagem |
| LGPD | RF32, RF33 | Estudante 3 | `bronze.usuarios`, `silver.*` | funções `lgpd.*` (revisão), `lgpd/*.md` |
| Consumo | RF16–RF18 | Estudante 3 | `gold.*`, `qualidade.*`, `controle.*` com o papel `consumo` | SQL Lab, datasets virtuais, dashboard, alerta |

A publicação de metadados no workflow (RF22) é uma fronteira entre dois responsáveis. O Estudante 3 cria no OpenMetadata as ingestões do PostgreSQL e do Superset (`openmetadata/provisionar.py`), e `hop/workflows/metadados.hwf` as dispara pela API REST do OpenMetadata (`POST /api/v1/services/ingestionPipelines/trigger/{id}`), com o token do bot em `OM_BOT_TOKEN`. Se o OpenMetadata estiver fora do ar, a etapa fica `ignorada` e o fluxo segue.

## Convenções comuns

**Identificador de execução.** Um UUID v4, recebido como parâmetro `EXECUCAO_ID` em todo pipeline e workflow do Hop, e como `--execucao_id` nos scripts Python e Beam. Quando o parâmetro vem vazio, o workflow gera o UUID (`pipelines/definir_execucao.hpl`) e o repassa às etapas. Para reprocessar uma camada de uma execução existente, informe o `EXECUCAO_ID` dela: a execução é reaberta e o status final é recalculado.

**Controle (RF22).** Toda execução, completa ou isolada, segue o mesmo ciclo:

1. Abre uma linha em `controle.execucao` com status `em_andamento`.
2. Cada etapa insere a sua linha em `controle.etapa` ao começar e a atualiza ao terminar, com `fim`, `status`, `lidos`, `gravados`, `quarentena` e `mensagem`. A coluna `duracao_s` é calculada pelo banco.
3. O status de cada etapa é `sucesso`, `sucesso_com_ressalvas` (terminou, mas mandou registros para a quarentena ou reprovou um teste não crítico), `falha` ou `ignorada` (prevista no fluxo, mas o workflow do responsável ainda não existe).
4. O status final da execução é:
   - `falha` quando alguma etapa falhou ou ficou `em_andamento` (processo interrompido);
   - `sucesso_com_ressalvas` quando alguma etapa terminou com ressalvas;
   - `sucesso` nos demais casos.

As funções `controle.abrir_execucao`, `iniciar_etapa`, `concluir_etapa`, `registrar_falha`, `registrar_ignorada` e `finalizar_execucao` fazem esse ciclo. `concluir_etapa` mede `lidos`, `gravados` e `quarentena` no próprio banco (`controle.medir_etapa`).

**Logs correlacionados.** Os workflows escrevem o `execucao_id` no log do Hop ao abrir a execução e ao iniciar cada etapa (`[<uuid>] etapa silver_conteudo: inicio`). As tabelas de `controle`, `quarentena` e `qualidade` também o carregam, então basta um filtro por ele para reconstituir uma execução.

**Auditoria nas camadas.**

| Coluna | Conteúdo |
| --- | --- |
| `_execucao_id` | execução que ingeriu o registro |
| `_origem` | caminho relativo a `desafio_dados/`, ex. `dados/brutos/lote_2/catalogo.csv` |
| `_linha` | posição na fonte: 1 para a primeira linha de dados do CSV ou o primeiro elemento do array JSON (só na Bronze) |
| `_ingerido_em` | instante da ingestão na Bronze; a Silver herda o valor |

**Modo de carga.**

- **Bronze:** só acrescenta (append-only), uma carga por execução.
- **Silver:** cada entidade é validada para a área de preparo (schema `validacao`), e `silver.publicar()` troca a Silver inteira numa única transação. Se qualquer passo falhar, a Silver anterior continua publicada.
- **Gold:** recriada só depois que a qualidade aprova (RF31).

**Deduplicação e sobrevivência** (implementadas em `sql/silver.sql`):

- **Cópia idêntica** do mesmo registro: fica a primeira ocorrência; as outras vão para a quarentena como `DUPLICADO`.
- **Conteúdos** com o mesmo id e valores diferentes: o lote 2 prevalece sobre o Desafio 1, sem erro (a versão vencida continua só na Bronze). No mesmo arquivo, prevalece a última ocorrência, e as anteriores vão para a quarentena como `CONFLITO_VERSAO`, para alguém revisar.
- **Usuários** com o mesmo id: prevalece o maior `atualizado_em`, com o mesmo tratamento de conflito no mesmo arquivo.
- **Interações, comentários e recomendações** (eventos): na mesma chave de negócio, fica a primeira ocorrência.
- **Pessoas** (RF30): ids diferentes com o mesmo `cpf_hash` ou `email_hash` são a mesma pessoa. O mestre é o menor id do grupo, e os atributos vêm do cadastro atualizado mais recentemente.

**Segredos.**

- Nunca entram em `hop/`, em `config.yaml` nem no código. Ficam só no `.env`.
- **No Hop:** use `${PG_USER}`, `${PG_PASSWORD}`, `${MONGO_USER}`, `${MONGO_PASSWORD}`, `${LGPD_SALT}` e `${LGPD_CHAVE_PSEUDONIMO}`. O arquivo com esses valores é gerado dentro do container por `docker/hop/segredos.sh`.
- **Em Python:** leia de `os.environ`.

**Tipos e nomes.**

- **Datas de negócio:** `DATE` ou `TIMESTAMP` sem fuso, como no Desafio 1.
- **Colunas de auditoria:** `TIMESTAMPTZ`.
- **Nomes:** `snake_case` em português. Tabelas da Bronze no plural, espelhando o arquivo (`bronze.interacoes`). Tabelas da Silver e da Gold no singular (`silver.interacao`).

**Caminhos.** O projeto é montado em `/app` em todos os containers (`hop`, `hop-web`, `beam`, `beam-worker-pool`, `app`). Um caminho como `/app/dados/silver/interacao.parquet` vale em qualquer um deles.

## Camadas

### Bronze — cópia auditável (RF20)

Todos os campos são `TEXT`, com o valor exatamente como veio da fonte, mais as colunas de auditoria. Não há validação nem transformação.

| Tabela | Fontes |
| --- | --- |
| `bronze.catalogo` | `dados/brutos/catalogo.csv`, `dados/brutos/lote_2/catalogo.csv` |
| `bronze.interacoes` | `dados/brutos/interacoes.json`, `dados/brutos/lote_2/interacoes.json` |
| `bronze.comentarios` | `dados/brutos/comentarios.json`, `dados/brutos/lote_2/comentarios.json`; `tags` guarda o JSON original |
| `bronze.usuarios` | `dados/brutos/usuarios.csv`, `dados/brutos/lote_2/usuarios.csv`; **dados pessoais**, só o dono do banco lê |
| `bronze.recomendacoes` | `dados/brutos/recomendacoes_desafio1.json` |

As recomendações vêm de `dados/brutos/recomendacoes_desafio1.json`, uma cópia fixa do resultado entregue no Desafio 1 (1200 recomendações, `gerado_em` = 2026-09-13), e não de `public.recomendacao` nem de `dados/processados/recomendacoes.json`. Cada execução do pipeline do Desafio 1 regrava esses dois com a data do dia, e a conversão de recomendação só é mensurável contra o snapshot fixo, que é o mesmo usado para gerar o lote 2. O RF15 pede reutilizar os resultados do Desafio 1; o RF20 exige banco de dados como destino.

### Silver — padronizada, validada e deduplicada (RF21, RF30, RF33)

| Tabela | Chave | Observações |
| --- | --- | --- |
| `silver.conteudo` | `conteudo_id` | domínios de tipo e nível como no Desafio 1 |
| `silver.usuario` | `usuario_id` | um registro por id da fonte; **sem dado pessoal direto**: pseudônimo, nome e e-mail mascarados, hashes de e-mail e CPF, faixa etária |
| `silver.usuario_mestre` | `usuario_mestre_id` | uma linha por pessoa (RF30); `usuario_pseudo` do mestre é o que a Gold usa |
| `silver.usuario_correspondencia` | `usuario_id` | aponta cada id para o seu mestre e registra a regra de correspondência (`proprio`, `cpf_hash`, `email_hash`) |
| `silver.interacao` | (`usuario_id`, `conteudo_id`, `tipo_interacao`, `data_hora`) | chaves estrangeiras para usuário e conteúdo |
| `silver.comentario` | (`usuario_id`, `conteudo_id`, `data`, md5 do texto) | texto já anonimizado com `lgpd.anonimizar_texto`; `tags` como `TEXT[]` |
| `silver.recomendacao` | (`usuario_id`, `conteudo_id`, `gerado_em`) | |

As regras de validação ficam só em `sql/silver.sql`, uma função `validacao.classificar_<fonte>` por fonte. As restrições das tabelas (`CHECK`, chaves estrangeiras, unicidade) são a última barreira: se algo inválido escapar, a publicação falha inteira e nenhuma carga parcial fica gravada (RF23). `faixa_etaria` usa as faixas `0-17`, `18-24`, `25-34`, `35-44`, `45-59` e `60+`; `0-17` identifica dado de criança ou adolescente (LGPD, art. 14).

**Proteção aplicada na Silver.** As funções recebem a chave e o salt como parâmetro, vindos do `.env`:

| Campo na Silver | Função | Técnica |
| --- | --- | --- |
| `usuario_pseudo` | `lgpd.pseudonimizar(usuario_id::text, '${LGPD_CHAVE_PSEUDONIMO}')` | pseudonimização (HMAC-SHA256); a correspondência fica em `restrito.usuario_pseudonimo` |
| `email_hash`, `cpf_hash` | `lgpd.hash_salt(valor_normalizado, '${LGPD_SALT}')` | hashing com salt; comparação irreversível, usada no casamento do RF30 |
| `nome_mascarado`, `email_mascarado` | `lgpd.mascarar_nome(nome)`, `lgpd.mascarar_email(email)` | mascaramento para exibição |
| `comentario` | `lgpd.anonimizar_texto(comentario)` | substitui e-mails e telefones do texto livre |

A normalização antes do hash segue duas regras: e-mail com `lower(btrim(email))` e CPF só com dígitos. Sem isso, `L2-U02` (o mesmo e-mail em maiúsculas) não casa.

As funções ficam em `sql/camadas.sql`. A escolha de cada técnica e a comparação entre elas estão em [`lgpd/tecnicas_de_protecao.md`](../lgpd/tecnicas_de_protecao.md) (RF33).

### Quarentena (RF23)

Uma única tabela, `quarentena.registro`, recebe os registros rejeitados de todas as fontes, com `regra`, `severidade`, `mensagem`, o registro em `JSONB` (`registro`, editável) e a versão original (`registro_original`, que nunca muda).

**Identidade.** Cada rejeição é identificada por (`fonte`, `origem`, `linha`, `hash_origem`): o arquivo, a linha e o md5 do conteúdo original. Como as fontes não mudam, a mesma rejeição encontrada de novo em outra execução só atualiza `ultima_execucao_id`, sem criar outra linha.

**Ciclo de vida.**

1. **`pendente`:** detectado. A Silver continua sem o registro.
2. **`corrigido`:** alguém editou `registro` e mudou o status. Na próxima Silver, a versão corrigida substitui a da Bronze.
3. **`reprocessado`:** o registro passou. Isso acontece tanto por correção quanto quando a causa era outro registro (ex.: `L2-I13` entra sozinho depois que o conteúdo 1041 é corrigido). A versão corrigida continua substituindo a da Bronze nas execuções seguintes. Se ela voltar a falhar, o registro volta a `pendente`.
4. **`descartado`:** decisão de não aproveitar; o registro sai do fluxo.

Uma falha de arquivo ou de conexão não vai para a quarentena. A etapa termina com `status = 'falha'` em `controle.etapa`, e a mensagem registra a causa.

**Códigos de regra.** Um código novo entra em `sql/silver.sql` (regra e `validacao.severidade`) e nesta tabela, no mesmo commit.

| Código | Quando | Severidade | Exemplos no lote 2 |
| --- | --- | --- | --- |
| `CAMPO_OBRIGATORIO` | campo obrigatório ausente ou vazio (registro "incompleto") | alta | C07, U06, I07, K02 |
| `TIPO_INVALIDO` | valor que não converte para o tipo, ex. id não numérico ou fracionário | alta | C08 |
| `DATA_INVALIDA` | data inexistente ou em formato não reconhecido | alta | C06, I06, K09 |
| `REF_USUARIO` | usuário inexistente | alta | I01, K07 |
| `REF_CONTEUDO` | conteúdo inexistente ou em quarentena | alta | I02, I13 |
| `DOMINIO` | valor fora do domínio (tipo, nível, tipo de interação, classificação, UF) | média | C05, I05, U10 |
| `FAIXA` | número fora da faixa: avaliação fora de 1–5, percentual ou pontuação fora de 0–100, id ou posição não positivos | média | I04, I09, K01 |
| `VALOR_NEGATIVO` | carga horária ou tempo consumido negativo | média | C04, I03 |
| `DATA_FUTURA` | data ou data e hora depois de agora | média | I10, U05 |
| `DATA_ANTES_PUBLICACAO` | interação ou comentário anterior à publicação do conteúdo | média | I14, K06 |
| `CONSISTENCIA` | combinação incoerente, ex. conclusão com percentual < 100 | média | I11 |
| `FORMATO` | e-mail sem `@`, CPF fora de `000.000.000-00`, tags que não são lista | média | U03, U04, K03 |
| `DUPLICADO` | cópia idêntica de outro registro da mesma chave | baixa | C01, U07, I08, K08 |
| `CONFLITO_VERSAO` | mesma chave repetida no mesmo arquivo com outros valores; vale a última ocorrência (conteúdos, usuários) ou a primeira (eventos) | baixa | C02 |

O CPF dos dados de teste tem formato válido, mas dígito verificador propositalmente inválido, para nunca coincidir com um CPF real. A validação é só de formato.

### Qualidade (RF31)

- **`qualidade.teste`:** um registro por teste, com dimensão, alvo, fórmula, operador, limite, severidade e ação. As dimensões aceitas são `completude`, `validade`, `unicidade`, `consistencia` e `integridade_referencial`.
- **`qualidade.resultado`:** uma linha por execução, teste e fonte, com `valor_medido` e `aprovado`, em que aprovado = `valor_medido <operador> limite_aceitavel`. Cada linha guarda também o operador, o limite e a severidade vigentes quando o teste rodou, para o histórico não mudar se o teste mudar.
- **Testes, limites e a demonstração do bloqueio:** [`qualidade/regras.md`](../qualidade/regras.md).
- **Bloqueio da Gold:** um teste com severidade `critica` reprovado impede a publicação da Gold na mesma execução. O bloqueio é verificado no workflow (`qualidade.hwf`) e de novo dentro de `gold.publicar()`.
- **Dashboard:** o painel lê `qualidade.resultado` para mostrar a evolução das métricas entre execuções.

### Controle e acesso

| Papel | Acessa | Uso |
| --- | --- | --- |
| `desafio` (dono, `POSTGRES_USER`) | tudo | pipelines Hop, Beam, `app`, OpenMetadata |
| `consumo` (`CONSUMO_DB_USER`) | leitura de `gold`, `qualidade` e `controle` | conexão do Superset e SQL Lab da camada de consumo |

URI do Superset para o Desafio 2: `postgresql+psycopg2://consumo:<senha>@postgres:5432/desafio`. A conexão do Desafio 1 continua a mesma. Com o papel `consumo`, o dashboard não consegue ler Bronze, Silver nem o schema `restrito`, e isso já é a evidência de que nenhum valor original protegido chega ao consumo (RF33).

## Gold (RF26)

Implementada em `sql/camada_gold.sql` (Estudante 2) e consumida pelo SQL Lab e pelo Superset (Estudante 3). Detalhes, contagens e decisões em [`camada_gold.md`](camada_gold.md).

| Objeto | Grão | Colunas principais |
| --- | --- | --- |
| `gold.dim_conteudo` | 1 por conteúdo | `conteudo_id`, `titulo`, `tipo`, `categoria`, `nivel`, `carga_horaria_min`, `data_publicacao` |
| `gold.dim_usuario` | 1 por pessoa (mestre) | `usuario_pseudo`, `nome_mascarado` (único campo derivado de dado pessoal no consumo), `faixa_etaria`, `uf`, `data_cadastro`, `registros_origem` |
| `gold.fato_interacao` | 1 por interação | `usuario_pseudo`, `conteudo_id`, `tipo_interacao`, `data_hora`, `data`, `mes`, `tempo_consumido`, `percentual_conclusao`, `avaliacao_atribuida` |
| `gold.fato_recomendacao` | 1 por recomendação | `usuario_pseudo`, `conteudo_id`, `pontuacao`, `posicao`, `classificacao`, `gerado_em`, `convertida`, `convertida_em` |
| `gold.kpi_*` | por período e dimensão | `kpi_engajamento_mensal`, `kpi_usuarios_ativos_mensal`, `kpi_taxa_conclusao`, `kpi_conversao_recomendacao`, `kpi_avaliacao`; guardam numerador e denominador |

**Regras da Gold:**

- Nenhum dado pessoal direto; `usuario_id` não aparece, só `usuario_pseudo`, e é o do mestre (RF30, RF32).
- Toda métrica por usuário conta pessoas, não ids: com `L2-U01`, os ids 12 e 171 são uma só pessoa.
- A Gold lê só a Silver; o dashboard lê só a Gold (RF26).

**Termos do glossário (RF28).** As definições precisam ser idênticas no SQL, no OpenMetadata e no dashboard:

| Termo | Definição |
| --- | --- |
| Usuário ativo | pessoa (mestre) com pelo menos uma interação válida no período |
| Taxa de conclusão | pares (pessoa, conteúdo) concluídos (interação `conclusão` ou `percentual_conclusao` = 100) ÷ pares com consumo (visualização, início ou conclusão); mesma regra de `documentacao/kpis.md` do Desafio 1 |
| Conversão de recomendação | recomendações em que a pessoa interagiu (visualização, início ou conclusão) com o conteúdo depois de `gerado_em` ÷ recomendações |
| Avaliação média | média de `avaliacao_atribuida` não nula, escala 1–5 |

## Dados de teste

| Arquivo | Conteúdo |
| --- | --- |
| `dados/brutos/usuarios.csv` | cadastro fictício dos 150 usuários do Desafio 1 (nova fonte; permite validar referência a usuário) |
| `dados/brutos/recomendacoes_desafio1.json` | snapshot fixo das recomendações entregues no Desafio 1 (fonte de `bronze.recomendacoes`); não regenerar |
| `dados/brutos/lote_2/` | segundo lote (26/08 a 26/09/2026): catálogo, usuários, interações e comentários novos, com 46 anomalias catalogadas |
| `dados/brutos/lote_2/ANOMALIAS.md` | **oráculo**: cada anomalia, onde está e o tratamento esperado; use-o para testar a Silver e os testes de qualidade |
| `dados/brutos/falhas/` | arquivo JSON truncado e CSV sem coluna obrigatória, para demonstrar falha de arquivo (RF23) |
| `dados/volume/interacoes.json` | não versionado; `python -m ferramentas.gerar_dados --volume 200000` gera volume para o RF24 e o RF25 |

Tudo é gerado por `ferramentas/gerar_dados.py` com semente fixa: rodar de novo produz os mesmos arquivos. Os arquivos do Desafio 1 não são alterados. Os e-mails usam o domínio reservado `.example`, os telefones o DDD `00` e os CPFs têm dígito verificador inválido. Os testes em `tests/test_gerar_dados.py` garantem essas três propriedades.

Como referência, as regras de validação do Desafio 1 aplicadas ao lote 2 aceitam 43 de 50 conteúdos, 404 de 416 interações e 113 de 119 comentários. A Silver do Desafio 2 deve rejeitar também `L2-I01` e `L2-K07` (usuário 999), que o Desafio 1 não conseguia verificar por falta de uma fonte de usuários.

## Como plugar uma etapa no fluxo (Estudantes 2 e 3)

O workflow principal (`hop/workflows/principal.hwf`) já prevê, depois da Silver e nesta ordem, as etapas `qualidade`, `gold` e `metadados`. Para cada uma, ele procura `hop/workflows/<etapa>.hwf`: se o arquivo existe, executa; se não, registra a etapa como `ignorada` e segue. Para plugar a sua:

1. Crie `hop/workflows/<etapa>.hwf` com o parâmetro `EXECUCAO_ID`.
2. Execute cada pipeline por meio de `hop/workflows/etapa.hwf` (parâmetros `EXECUCAO_ID`, `ETAPA` e `PIPELINE`), para que início, fim, contagens e falhas fiquem em `controle.etapa`. Para medir `lidos`, `gravados` e `quarentena` da sua etapa, acrescente um ramo em `controle.medir_etapa` (`sql/silver.sql`).
3. Em caso de falha, termine o workflow com falha (action Abort). É isso que impede as etapas dependentes, por exemplo a Gold depois de um teste crítico reprovado (RF31).

## Como executar (RF15)

```bash
docker compose up -d                                                # postgres, mongo, superset, db-init
docker compose run --rm hop workflows/principal.hwf                 # fluxo completo, com EXECUCAO_ID novo
docker compose run --rm hop workflows/isolado.hwf FLUXO=bronze      # só a Bronze, numa execução nova
docker compose run --rm hop workflows/isolado.hwf FLUXO=silver EXECUCAO_ID=<uuid>   # reprocessa a Silver
docker compose --profile agendamento up -d                          # agendamento diário (hop-agendador)
docker compose run --rm beam beam/pipeline.py --runner direct       # ou --runner spark, com o perfil beam no ar
docker compose run --rm beam -m ferramentas.gerar_dados              # regenera os dados de teste (só biblioteca padrão)
```

Verificações da infraestrutura: `docker compose run --rm hop pipelines/verificar_ambiente.hpl` e `docker compose run --rm beam beam/verificar_runtime.py --runner {direct|spark}`.
