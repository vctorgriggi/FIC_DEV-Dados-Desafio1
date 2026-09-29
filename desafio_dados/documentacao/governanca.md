# Governança: OpenMetadata, catálogo, glossário e dados mestres (RF27, RF28, RF30)

Parte do Estudante 3, exceto os dados mestres (RF30), aplicados na Silver pelo Estudante 1 e documentados aqui porque são uma decisão de governança. A linhagem (RF29) tem documento próprio: [`linhagem.md`](linhagem.md). A LGPD (RF32, RF33) está em [`../lgpd/`](../lgpd/).

Tudo o que está no OpenMetadata é criado por código, idempotente e versionado: [`openmetadata/provisionar.py`](../openmetadata/provisionar.py). Rodar de novo não duplica nada e reaplica o que tiver sido removido à mão. As capturas estão em [`openmetadata/evidencias/`](../openmetadata/evidencias/).

```bash
docker compose --profile governanca up -d                  # OpenMetadata 2.0.2, Elasticsearch e Airflow (~3,5 GB)
docker compose run --rm beam openmetadata/provisionar.py    # serviços, ingestões, times, tags, glossário, linhagem
docker compose run --rm evidencias ferramentas/evidencias.py openmetadata   # capturas
```

Acesso: http://localhost:8585, com `OM_ADMIN_EMAIL` / `OM_ADMIN_PASSWORD` do `.env`.

## RF27 — Implantação e integração

**Instância.** São quatro serviços do perfil `governanca`:

- `openmetadata`: servidor 2.0.2;
- `elasticsearch`: busca;
- `om-ingestao`: Airflow com os conectores de ingestão;
- `om-migrar`: migração do esquema na primeira subida.

Os bancos do OpenMetadata e do Airflow ficam no mesmo PostgreSQL do projeto, criados pelo `db-init`.

**Serviços conectados:**

| Serviço no OpenMetadata | Tipo | O que registra | Como |
| --- | --- | --- | --- |
| `postgres_desafio` | Postgres | os 7 schemas das camadas: `bronze`, `silver`, `gold`, `quarentena`, `qualidade`, `controle`, `restrito` | ingestão automática de metadados técnicos, com tabelas, colunas, tipos, DDL, views e descrições |
| `superset_desafio` | Superset | os 2 dashboards "Desafio 2", os 16 gráficos e os datasets, inclusive os virtuais do SQL Lab | ingestão automática; a linhagem dataset → dashboard vem dela |
| `arquivos_desafio` | CustomStorage | os 9 arquivos de origem em `dados/brutos/` | registrados pela API: o OpenMetadata não tem conector para arquivos locais |
| `apache_hop` | CustomPipeline | as 13 etapas do Hop (5 Bronze, 5 Silver, publicação da Silver, qualidade e Gold) | registradas pela API: o OpenMetadata não tem conector para o Hop |

**Ingestão a cada execução.** As ingestões ficam cadastradas no OpenMetadata e rodam no Airflow. A etapa `metadados` do workflow do Hop (`hop/workflows/metadados.hwf`) dispara as duas pela API REST ao fim de cada execução bem-sucedida (RF22). Assim, o catálogo acompanha o banco sem ninguém lembrar de atualizá-lo. Se o OpenMetadata estiver fora do ar, a etapa fica `ignorada` e o fluxo não falha por isso.

**Proprietários.** Três times, um por integrante. Cada schema tem um time dono, herdado por todas as tabelas dele:

| Time | Responsável por |
| --- | --- |
| Estudante 1 - Ingestão (Kevin) | `bronze`, `silver`, `quarentena`, `controle`; etapas Bronze e Silver do Hop; termo "Pessoa" |
| Estudante 2 - Analítico (Vinycius) | `gold`, `qualidade`; etapas de qualidade e Gold; termos de KPI |
| Estudante 3 - Governança e consumo (Victor) | `restrito`; glossário; dashboards e datasets do Superset |

Os serviços também têm dono e descrição: `postgres_desafio` e `superset_desafio` são do Estudante 3; `arquivos_desafio` e `apache_hop`, do Estudante 1. O banco `desafio` tem descrição e o Estudante 3 como dono (captura 01).

**Descrições.** A fonte é o próprio banco: [`sql/catalogo.sql`](../sql/catalogo.sql) aplica `COMMENT ON` em schemas, tabelas e colunas, e a ingestão as traz. A descrição mora ao lado da estrutura, versionada no mesmo commit, e não se perde se o OpenMetadata for recriado. Todas as 29 tabelas e views dos 7 schemas têm descrição. Também têm descrição todas as colunas da Gold e do schema `restrito`, as colunas de auditoria e as colunas de usuários da Bronze e da Silver. Os dashboards recebem descrição e responsável pela API. A ingestão usa `overrideMetadata`: se uma descrição mudar no banco, a do catálogo acompanha. As tags aplicadas pelo provisionamento não são afetadas, o que foi verificado disparando a ingestão sozinha.

### Controles contra o Data Swamp

Um catálogo vira pântano quando entra qualquer coisa, sem dono, sem descrição e sem data de validade. Os controles aplicados:

| Controle | Como é garantido |
| --- | --- |
| **Só entra o que é governado** | a ingestão do PostgreSQL filtra os 7 schemas (`schemaFilterPattern`) e a do Superset só os dashboards "Desafio 2" (`dashboardFilterPattern`). O schema `public` do Desafio 1, os bancos do OpenMetadata e do Airflow e os dashboards de teste ficam de fora |
| **Todo ativo tem dono** | o dono é definido por schema, e toda tabela nova herda o do seu schema na próxima execução do provisionamento |
| **Todo ativo tem descrição** | as descrições vêm de `sql/catalogo.sql`. A consulta de verificação abaixo deve devolver zero |
| **Todo ativo tem camada e criticidade** | tag `Medalhao.Bronze/Silver/Gold/Operacional/Restrita` e o Tier nativo em todas as tabelas: Tier1 para a Gold (consumo), Tier2 para a Silver e o schema restrito, Tier3 para a Bronze e as tabelas operacionais. Dá para filtrar o que é consumo e o que é intermediário |
| **Nada fica órfão** | `markDeletedTables` e `markDeletedDashboards`: o que some da fonte é marcado como apagado no catálogo e não fica como ativo fantasma |
| **Catálogo atualizado** | a ingestão roda ao fim de cada execução do workflow |
| **Significado único** | os KPIs têm termo no glossário, com definição, regra de cálculo e dono, ligado às colunas que os implementam |
| **Dado sensível visível** | colunas com dado pessoal têm as tags `LGPD.*` e `PII.*`; a busca por tag mostra onde há dado pessoal |
| **Reprodutível** | a configuração inteira é código. Uma instância nova fica igual rodando o script |

```sql
-- verificação de descrições: tabelas sem descrição nos schemas catalogados (esperado: 0)
SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname IN ('bronze','silver','gold','quarentena','qualidade','controle','restrito')
   AND c.relkind IN ('r','v') AND obj_description(c.oid, 'pg_class') IS NULL;
```

## RF28 — Catálogo, classificação e glossário

**Catálogo.** As tabelas da Silver (7) e da Gold (9) estão catalogadas, com colunas, tipos, descrição, dono e camada. Capturas:

- `01_catalogo_schemas.png`;
- `03_silver_usuario_protecao.png`;
- `04_gold_kpi_taxa_conclusao_glossario.png`.

**Glossário `plataforma_conteudos`** (`07_glossario.png`, `08_termo_taxa_de_conclusao.png`): cinco termos, todos aprovados, cada um com definição, regra de cálculo, dono e colunas associadas.

| Termo | Definição e regra | Dono | Associado a |
| --- | --- | --- | --- |
| **Usuário ativo** | pessoa (usuário mestre) com ao menos uma interação válida no período; `count(DISTINCT usuario_pseudo)` no mês | Estudante 2 | `gold.kpi_usuarios_ativos_mensal.pessoas_ativas`, `gold.kpi_engajamento_mensal.pessoas_ativas` |
| **Taxa de conclusão** | 100 × pares (pessoa, conteúdo) concluídos ÷ pares com consumo; concluído = interação `conclusão` ou percentual 100 | Estudante 2 | `gold.kpi_taxa_conclusao.taxa_conclusao_pct` |
| **Conversão de recomendação** | 100 × recomendações seguidas de consumo depois de `gerado_em` ÷ recomendações | Estudante 2 | `gold.kpi_conversao_recomendacao.conversao_pct`, `gold.fato_recomendacao.convertida` |
| **Avaliação média** | média de `avaliacao_atribuida` não nula (1 a 5), ponderada pelo número de avaliações ao agregar | Estudante 2 | `gold.kpi_avaliacao.avaliacao_media` |
| **Pessoa (usuário mestre)** | indivíduo por trás de um ou mais cadastros; mesmo `cpf_hash` ou `email_hash` = mesma pessoa | Estudante 1 | `gold.dim_usuario.usuario_pseudo`, `silver.usuario_mestre.usuario_pseudo` |

As definições são as mesmas em três lugares, conferidos um contra o outro: o SQL da Gold ([`camada_gold.md`](camada_gold.md)), o glossário e os textos do dashboard.

**Classificações:**

| Classificação | Tags | Onde |
| --- | --- | --- |
| `LGPD` (criada) | `DadoPessoal`, `IdentificadorIndireto`, `DadoDeCriancaOuAdolescente`, `Pseudonimizado`, `HashComSalt`, `Mascarado`, `Anonimizado`, `TabelaDeCorrespondencia` | colunas de `bronze.usuarios`, `bronze.comentarios`, `silver.usuario`, `silver.usuario_mestre`, `silver.comentario`, `quarentena.registro`, `restrito.usuario_pseudonimo` e das tabelas da Gold com `usuario_pseudo` e `nome_mascarado` |
| `PII` (padrão do OpenMetadata) | `Sensitive`, `NonSensitive` | colunas de dado pessoal em `bronze.usuarios` e `bronze.comentarios` |
| `Medalhao` (criada) | `Bronze`, `Silver`, `Gold`, `Operacional`, `Restrita` | todas as tabelas |
| `Tier` (nativa) | `Tier1`, `Tier2`, `Tier3` | todas as tabelas (criticidade para o negócio; aparece no cabeçalho como "Camada") |

A classificação criada se chama `Medalhao`, e não `Camada`, porque a interface do OpenMetadata em português já traduz o Tier nativo como "Camada".

A classificação completa, com base legal e retenção, está no [inventário LGPD](../lgpd/inventario_de_dados.md). A captura `02_bronze_usuarios_dados_pessoais.png` mostra as tags nas colunas, e a `09_classificacao_lgpd.png` mostra a classificação.

## RF30 — Dados mestres: a entidade Pessoa

| Item | Definição |
| --- | --- |
| **Entidade mestre** | Pessoa: o indivíduo por trás dos cadastros de usuário |
| **Chave de negócio** | `usuario_mestre_id` (o menor `usuario_id` do grupo), exposto como `usuario_pseudo` (HMAC) |
| **Atributos essenciais** | nome e e-mail mascarados, faixa etária, cidade, UF, data de cadastro, atualizado em, registros de origem |
| **Fonte de referência** | cadastro de usuários (`usuarios.csv` do Desafio 1 e do lote 2), já validado na Silver |
| **Correspondência** | mesmo `cpf_hash` **ou** mesmo `email_hash`, inclusive por transitividade (A~B e B~C → A, B e C são uma pessoa). O hash é calculado sobre o valor normalizado: e-mail em minúsculas e sem espaços, CPF só com dígitos |
| **Deduplicação** | o mesmo `usuario_id` repetido é tratado antes, na validação: cópia idêntica vai para a quarentena, e entre versões diferentes vale a de maior `atualizado_em` |
| **Sobrevivência** | os atributos vêm do cadastro com o maior `atualizado_em` do grupo; a data de cadastro é a mais antiga |
| **Saída** | `silver.usuario_mestre` (uma linha por pessoa) e `silver.usuario_correspondencia` (cada `usuario_id` → mestre, com a regra que casou: `proprio`, `cpf_hash` ou `email_hash`) |

Implementação: `silver.publicar()` em [`sql/silver.sql`](../sql/silver.sql), com uma CTE recursiva para a transitividade. O teste de qualidade Q07 garante que todo usuário tem mestre ([`qualidade/regras.md`](../qualidade/regras.md)).

### Demonstração: dois pares conflitantes

O lote 2 traz dois casos, catalogados em [`ANOMALIAS.md`](../dados/brutos/lote_2/ANOMALIAS.md). Os valores estão como aparecem na Silver: mascarados e com hash truncado.

**L2-U01: mesmo CPF, nome escrito diferente, outro e-mail.**

| `usuario_id` | Nome | CPF (hash) | E-mail (hash) | Cidade | Atualizado em | Regra |
| --- | --- | --- | --- | --- | --- | --- |
| 12 | Otávio C\*\*\* | `2574401a09…` | `1d862447d5…` | São Paulo | 20/09/2026 | próprio (mestre) |
| 171 | OTAVIO C\*\*\* | `2574401a09…` | `409db570d1…` | Uberlândia | 01/09/2026 | `cpf_hash` → 12 |

**L2-U02: mesmo e-mail, com maiúsculas e espaços, outro CPF.**

| `usuario_id` | Nome | CPF (hash) | E-mail (hash) | Cidade | Atualizado em | Regra |
| --- | --- | --- | --- | --- | --- | --- |
| 30 | Beatriz V\*\*\* | `6f0fa82f16…` | `4d65d339bb…` | Natal | 29/01/2026 | próprio (mestre) |
| 172 | Beatriz V\*\*\* | `e561636c88…` | `4d65d339bb…` | Santos | 01/09/2026 | `email_hash` → 30 |

**Registros mestres resultantes (`silver.usuario_mestre`):**

| Mestre | Nome | Cidade (sobrevivente) | Cadastro (mais antigo) | Registros de origem |
| --- | --- | --- | --- | --- |
| 12 | Otávio C\*\*\* | São Paulo, do cadastro 12 (atualizado em 20/09, o mais recente) | 06/01/2026 | 2 |
| 30 | Beatriz V\*\*\* | Santos, do cadastro 172 (atualizado em 01/09, o mais recente) | 13/10/2025 | 2 |

Mais três pontos dessa demonstração:

- O usuário 12 também aparece duas vezes na Bronze: no arquivo do Desafio 1 (Uberlândia, 20/06) e no lote 2 (São Paulo, 20/09, `L2-U08`). A deduplicação por id fica com a versão de 20/09 antes mesmo da correspondência.
- O `L2-U02` só casa porque o e-mail é normalizado antes do hash. O cadastro 172 traz o e-mail em maiúsculas e com espaços; sem a normalização, os hashes seriam diferentes.
- Efeito no consumo: são 173 cadastros para 171 pessoas. Na Gold, as interações dos ids 171 e 172 contam para as pessoas 12 e 30, e "usuário ativo" conta pessoas, não cadastros.

A consulta 4 da [demonstração LGPD](../lgpd/demonstracao_resultado.txt) mostra os hashes de CPF iguais sem revelar o CPF. A consulta 5 mostra a reidentificação controlada pelo schema `restrito`.

## Limitações

- **Arquivos e etapas do Hop entram pela API.** O OpenMetadata não tem conector para arquivos locais nem para o Apache Hop, então eles são registrados pela API. Se um pipeline novo for criado no Hop, ele só aparece no catálogo depois de entrar em `PIPELINES` no script.
- **Descrições de coluna fora da Gold.** A Bronze e a Silver têm descrição em todas as tabelas, mas não em todas as colunas: os campos de conteúdos, interações, comentários e recomendações repetem os nomes das fontes e estão documentados em [`contratos.md`](contratos.md). A prioridade foi a camada de consumo e os campos com dado pessoal.
- **Glossário por API.** Os termos são aprovados na criação. Numa operação real, a mudança de um termo passaria por revisão no fluxo do próprio OpenMetadata.
