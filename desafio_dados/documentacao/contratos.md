# Contratos entre as etapas — Desafio 2

A seção 5 do enunciado pede que a equipe trabalhe em paralelo "com dados de teste e contratos de entrada e saída previamente definidos". Este documento é esse contrato: o que cada etapa lê, o que escreve e em que formato. Assim, cada integrante desenvolve a sua parte sem esperar a do outro.

- **Fonte da verdade das estruturas:** [`sql/camadas.sql`](../sql/camadas.sql), aplicado automaticamente pelo serviço `db-init` a cada `docker compose up`. Aqui fica o resumo e as regras que o SQL não expressa.
- **Mudou o contrato?** Combine com quem consome, altere `sql/camadas.sql` e este documento no mesmo commit.
- A camada Gold ainda é uma **proposta**: o Estudante 2 implementa em `sql/camada_gold.sql` e pode ajustar, avisando o Estudante 3.

## Implementação Hop registrada nesta entrega

Esta entrega registra dezesseis arquivos de implementação alterados para o trabalho do Estudante 1. A Silver tem uma implementação híbrida: os transformers nativos do Apache Hop fazem a limpeza textual e o encadeamento da carga, enquanto o `TableInput` ainda concentra validações, conversões, deduplicação, regras relacionais e parte da normalização que depende do PostgreSQL.

| Arquivo | Implementação |
| --- | --- |
| `hop/pipelines/bronze_catalogo.hpl` | Lê os CSVs do Desafio 1 e do `lote_2`, acrescenta `_execucao_id`, `_origem` e `_linha`, e grava em `bronze.catalogo`. |
| `hop/pipelines/bronze_usuarios.hpl` | Lê os CSVs de usuários das duas fontes e grava os dados brutos em `bronze.usuarios`, mantendo o fluxo restrito por conter dados pessoais. |
| `hop/pipelines/bronze_interacoes.hpl` | Lê os arrays JSON de interações das duas fontes com `JsonInput` e paths `$.*.campo`, registra auditoria e grava em `bronze.interacoes`. |
| `hop/pipelines/bronze_comentarios.hpl` | Lê os arrays JSON de comentários das duas fontes, preserva `tags` como texto e grava em `bronze.comentarios`. |
| `hop/pipelines/bronze_recomendacoes.hpl` | Lê o snapshot fixo `recomendacoes_desafio1.json` e grava em `bronze.recomendacoes`, sem usar a recomendação recalculada do Desafio 1. |
| `hop/pipelines/controle_execucao.hpl` | Abre uma execução em `controle.execucao` usando `EXECUCAO_ID`, `FLUXO` e `MODO`. |
| `hop/pipelines/silver_conteudo.hpl` | Lê a Bronze, aplica `StringOperations` para limpeza textual e mantém no `TableInput` as validações, conversões, normalização de domínios e sobrevivência por `conteudo_id`. |
| `hop/pipelines/silver_usuario.hpl` | Usa `StringOperations` para limpeza textual; o `TableInput` ainda aplica deduplicação, conversões e as funções LGPD de pseudonimização, mascaramento e hashing. |
| `hop/pipelines/silver_interacao.hpl` | Usa `StringOperations` para limpeza de `tipo_interacao`; o `TableInput` ainda concentra conversões, regras de domínio e referências a usuário/conteúdo. |
| `hop/pipelines/silver_comentario.hpl` | Usa `StringOperations` para limpeza do texto; o `TableInput` ainda valida referências, data, avaliação, tags e aplica a anonimização. |
| `hop/pipelines/silver_recomendacao.hpl` | Usa `StringOperations` para limpeza de `classificacao`; o `TableInput` ainda valida chaves, pontuação, posição e classificação. |
| `hop/pipelines/quarentena_validacao.hpl` | Registra em `quarentena.registro` os registros que falham nas regras estruturais ou nas referências da Silver, preservando o payload original e evitando duplicar pendências. |
| `hop/pipelines/controle_finalizacao.hpl` | Executa a finalização da execução no banco e produz o estado operacional `sucesso` ou `sucesso_com_ressalvas`. |
| `hop/workflows/principal.hwf` | Orquestra controle, Bronze e todas as etapas Silver em sequência. Recebe `EXECUCAO_ID` e `MODO`; a etapa de metadados é apenas um placeholder de log para futura integração com OpenMetadata. |
| `sql/camadas.sql` | Habilita `unaccent` para comparações sem acento e cria índice único, função e trigger de idempotência para registros repetidos de `bronze.catalogo`. |
| `hop/project-config.json` | Define a exportação automática de metadados para `metadata.json` e mantém as variáveis do projeto preparadas para configuração posterior. |

### Limites atuais da implementação

- O agendamento é externo ao Hop: o workflow não possui gatilho interno e deve ser executado por Hop Run, Hop Web ou outro orquestrador, passando os parâmetros necessários.
- A publicação no OpenMetadata ainda não é chamada pelo workflow. A ação `preparar metadados` apenas registra a intenção e mantém o ponto de integração para uma etapa futura.
- A cobertura Silver desta entrega inclui `conteudo`, `usuario`, `interacao`, `comentario` e `recomendacao`. O encaminhamento automático das rejeições estruturais e referenciais para `quarentena.registro` e o fechamento de `controle.execucao` estão implementados; o reprocessamento de registros corrigidos e o fechamento detalhado de cada etapa em `controle.etapa` continuam como a próxima extensão operacional.

## Quem produz e quem consome

| Etapa | RF | Responsável | Lê | Escreve |
| --- | --- | --- | --- | --- |
| Bronze | RF20 | Estudante 1 | `dados/brutos/` (D1, `lote_2/` e `recomendacoes_desafio1.json`) | `bronze.*` |
| Silver | RF21, RF30 | Estudante 1 | `bronze.*` da execução corrente; leitura de `quarentena.registro` com status `corrigido` ainda prevista | `silver.*`, `quarentena.registro`, `restrito.usuario_pseudonimo` |
| Qualidade | RF31 | Estudante 2 | `silver.*` | `qualidade.teste`, `qualidade.resultado` |
| Parquet | RF24 | Estudante 2 | `silver.*` | `dados/silver/*.parquet` |
| Beam | RF25 | Estudante 2 | `dados/silver/*.parquet` | Parquet e evidências em `beam/evidencias/` |
| Gold | RF26 | Estudante 2 | `silver.*` (nunca `bronze.*`) | `gold.*` |
| Workflow | RF22, RF23 | Estudante 1 | orquestra as etapas acima e a publicação de metadados | `controle.execucao`, `controle.etapa` |
| Metadados | RF27–RF29 | Estudante 3 | todos os schemas, via OpenMetadata | catálogo, glossário, classificações, linhagem |
| LGPD | RF32, RF33 | Estudante 3 | `bronze.usuarios`, `silver.*` | funções `lgpd.*` (revisão), `lgpd/*.md` |
| Consumo | RF16–RF18 | Estudante 3 | `gold.*`, `qualidade.*`, `controle.*` com o papel `consumo` | SQL Lab, datasets virtuais, dashboard, alerta |

A publicação de metadados no workflow (RF22) é uma fronteira entre dois responsáveis. O Estudante 3 cria no OpenMetadata o pipeline de ingestão do PostgreSQL, e o workflow do Estudante 1 dispara esse pipeline pela API REST do OpenMetadata (`POST /api/v1/services/ingestionPipelines/trigger/{id}`).

## Convenções comuns

**Identificador de execução.** Um UUID v4, recebido como parâmetro `EXECUCAO_ID` em todo pipeline e workflow do Hop, e como `--execucao_id` nos scripts Python e Beam. O workflow principal gera o UUID e o repassa. Uma etapa rodada isoladamente sem esse parâmetro gera o próprio UUID e abre a sua execução com `fluxo` igual ao nome da etapa.

**Controle (RF22).** Toda execução, completa ou isolada, segue o mesmo ciclo:

1. Abre uma linha em `controle.execucao` com status `em_andamento`.
2. Cada etapa insere a sua linha em `controle.etapa` ao começar e a atualiza ao terminar, com `fim`, `status`, `lidos`, `gravados`, `quarentena` e `mensagem`. A coluna `duracao_s` é calculada pelo banco.
3. O status final da execução é:
   - `falha` quando uma etapa falha;
   - `sucesso_com_ressalvas` quando houve registros em quarentena ou teste de qualidade não crítico reprovado;
   - `sucesso` nos demais casos.

**Logs correlacionados.** Toda linha de log inclui o `execucao_id`. As tabelas de `controle`, `quarentena` e `qualidade` também o carregam, então basta um filtro por ele para reconstituir uma execução.

**Auditoria nas camadas.**

| Coluna | Conteúdo |
| --- | --- |
| `_execucao_id` | execução que ingeriu o registro |
| `_origem` | caminho relativo a `desafio_dados/`, ex. `dados/brutos/lote_2/catalogo.csv` |
| `_linha` | posição na fonte: 1 para a primeira linha de dados do CSV ou o primeiro elemento do array JSON (só na Bronze) |
| `_ingerido_em` | instante da ingestão na Bronze; a Silver herda o valor |

**Modo de carga.**

- **Bronze:** só acrescenta (append-only), uma carga por execução.
- **Silver:** recarga completa numa transação, a partir da Bronze da execução corrente. Se falhar, nada muda.
- **Gold:** recriada só depois que a qualidade aprova (RF31).

**Ordem das fontes e sobrevivência (proposta padrão; RF30 pode refinar):**

- **Conteúdos:** quando a mesma chave aparece em mais de uma fonte, o lote 2 prevalece sobre o Desafio 1. Dentro do mesmo arquivo, prevalece a última ocorrência.
- **Usuários:** prevalece o maior `atualizado_em`.

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

As restrições (`CHECK`, chaves estrangeiras, unicidade) são a última barreira. O pipeline valida antes e manda o que viola uma regra para a quarentena. Se algo inválido escapar, a transação falha inteira e nenhuma carga parcial fica gravada (RF23).

**Proteção aplicada na Silver.** As funções recebem a chave e o salt como parâmetro, vindos do `.env`:

| Campo na Silver | Função | Técnica |
| --- | --- | --- |
| `usuario_pseudo` | `lgpd.pseudonimizar(usuario_id::text, '${LGPD_CHAVE_PSEUDONIMO}')` | pseudonimização (HMAC-SHA256); a correspondência fica em `restrito.usuario_pseudonimo` |
| `email_hash`, `cpf_hash` | `lgpd.hash_salt(valor_normalizado, '${LGPD_SALT}')` | hashing com salt; comparação irreversível, usada no casamento do RF30 |
| `nome_mascarado`, `email_mascarado` | `lgpd.mascarar_nome(nome)`, `lgpd.mascarar_email(email)` | mascaramento para exibição |
| `comentario` | `lgpd.anonimizar_texto(comentario)` | substitui e-mails e telefones do texto livre |

A normalização antes do hash segue duas regras: e-mail com `lower(btrim(email))` e CPF só com dígitos. Sem isso, `L2-U02` (o mesmo e-mail em maiúsculas) não casa.

As funções em `sql/camadas.sql` são uma implementação inicial. O Estudante 3 é o dono da escolha das técnicas e da justificativa (RF33) e pode trocá-las, mantendo nome e assinatura.

### Quarentena (RF23)

Uma única tabela, `quarentena.registro`, recebe os registros rejeitados de todas as fontes, com o registro original em `JSONB` e os campos `execucao_id`, `camada`, `fonte`, `chave_registro`, `regra`, `severidade` e `mensagem`.

O ciclo de vida é `pendente` → `corrigido` → `reprocessado`, ou `pendente` → `descartado`:

1. **Corrigir:** editar `registro`, mudar `status` para `corrigido` e preencher `corrigido_em`.
2. **Reprocessar:** a próxima Silver lê a Bronze corrente mais os registros `corrigido`. Os que passarem viram `reprocessado`, com `reprocessado_em` e `reprocessado_execucao_id`. Os que falharem de novo geram uma nova linha `pendente`.

Uma falha de arquivo ou de conexão não vai para a quarentena. A etapa termina com `status = 'falha'` em `controle.etapa`, e a mensagem registra a causa.

**Códigos de regra.** São a lista inicial; o Estudante 1 pode acrescentar códigos, registrando-os aqui.

| Código | Quando | Severidade | Exemplos no lote 2 |
| --- | --- | --- | --- |
| `CAMPO_OBRIGATORIO` | campo obrigatório ausente ou vazio (registro "incompleto") | alta | C07, U06, I07, K02 |
| `TIPO_INVALIDO` | valor que não converte para o tipo, ex. id não numérico | alta | C08 |
| `DATA_INVALIDA` | data inexistente ou em formato não reconhecido | alta | C06, I06, K09 |
| `REF_USUARIO` | usuário inexistente | alta | I01, K07 |
| `REF_CONTEUDO` | conteúdo inexistente ou em quarentena | alta | I02, I13 |
| `DOMINIO` | valor fora do domínio (tipo, nível, tipo de interação, UF) | média | C05, I05, U10 |
| `FAIXA` | número fora da faixa: avaliação fora de 1–5, percentual fora de 0–100 | média | I04, I09, K01 |
| `VALOR_NEGATIVO` | carga horária ou tempo consumido negativo | média | C04, I03 |
| `DATA_FUTURA` | data ou data e hora depois de agora | média | I10, U05 |
| `DATA_ANTES_PUBLICACAO` | interação ou comentário anterior à publicação do conteúdo | média | I14, K06 |
| `CONSISTENCIA` | combinação incoerente, ex. conclusão com percentual < 100 | média | I11 |
| `FORMATO` | e-mail sem `@`, CPF fora de `000.000.000-00`, tags que não são lista | média | U03, U04, K03 |
| `DUPLICADO` | cópia idêntica de outro registro da mesma chave | baixa | C01, U07, I08, K08 |

O CPF dos dados de teste tem formato válido, mas dígito verificador propositalmente inválido, para nunca coincidir com um CPF real. A validação é só de formato.

### Qualidade (RF31)

- **`qualidade.teste`:** um registro por teste, com dimensão, alvo, fórmula, operador, limite, severidade e ação. As dimensões aceitas são `completude`, `validade`, `unicidade`, `consistencia` e `integridade_referencial`.
- **`qualidade.resultado`:** uma linha por execução, teste e fonte, com `valor_medido` e `aprovado`, em que aprovado = `valor_medido <operador> limite_aceitavel`.
- **Bloqueio da Gold:** um teste com severidade `critica` reprovado impede a publicação da Gold na mesma execução.
- **Dashboard:** o painel lê `qualidade.resultado` para mostrar a evolução das métricas entre execuções.

### Controle e acesso

| Papel | Acessa | Uso |
| --- | --- | --- |
| `desafio` (dono, `POSTGRES_USER`) | tudo | pipelines Hop, Beam, `app`, OpenMetadata |
| `consumo` (`CONSUMO_DB_USER`) | leitura de `gold`, `qualidade` e `controle` | conexão do Superset e SQL Lab da camada de consumo |

URI do Superset para o Desafio 2: `postgresql+psycopg2://consumo:<senha>@postgres:5432/desafio`. A conexão do Desafio 1 continua a mesma. Com o papel `consumo`, o dashboard não consegue ler Bronze, Silver nem o schema `restrito`, e isso já é a evidência de que nenhum valor original protegido chega ao consumo (RF33).

## Gold — proposta (RF26)

O Estudante 2 implementa em `sql/camada_gold.sql` e o Estudante 3 consome. Enquanto a Gold não existe, o Estudante 3 pode prototipar no SQL Lab sobre as views `public.vw_*` do Desafio 1 e trocar a fonte depois.

| Objeto | Grão | Colunas principais |
| --- | --- | --- |
| `gold.dim_conteudo` | 1 por conteúdo | `conteudo_id`, `titulo`, `tipo`, `categoria`, `nivel`, `carga_horaria_min`, `data_publicacao` |
| `gold.dim_usuario` | 1 por pessoa (mestre) | `usuario_pseudo`, `faixa_etaria`, `uf` |
| `gold.fato_interacao` | 1 por interação | `usuario_pseudo`, `conteudo_id`, `tipo_interacao`, `data_hora`, `data`, `mes`, `tempo_consumido`, `percentual_conclusao`, `avaliacao_atribuida` |
| `gold.fato_recomendacao` | 1 por recomendação | `usuario_pseudo`, `conteudo_id`, `pontuacao`, `posicao`, `classificacao`, `gerado_em`, `convertida`, `convertida_em` |
| `gold.kpi_*` | por período e dimensão | um objeto por KPI do glossário (abaixo) |

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

## Como executar cada etapa isoladamente (RF15)

```bash
docker compose up -d                                              # postgres, mongo, superset, db-init
docker compose run --rm hop pipelines/<pipeline>.hpl EXECUCAO_ID=<uuid>
docker compose run --rm hop workflows/<workflow>.hwf
docker compose run --rm beam beam/pipeline.py --runner direct     # ou --runner spark, com o perfil beam no ar
docker compose run --rm beam -m ferramentas.gerar_dados            # regenera os dados de teste (só biblioteca padrão)
```

Verificações da infraestrutura: `docker compose run --rm hop pipelines/verificar_ambiente.hpl` e `docker compose run --rm beam beam/verificar_runtime.py --runner {direct|spark}`.
