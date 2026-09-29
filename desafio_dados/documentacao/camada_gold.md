# Camada Gold (RF26)

A Gold é a única camada que o consumo enxerga. O SQL Lab e o Superset se conectam com o papel `consumo`, que lê `gold`, `qualidade` e `controle` e não tem permissão em `bronze`, `silver`, `quarentena` nem `restrito`. Por isso o dashboard não tem como consultar a Bronze (RF26) nem um dado pessoal original (RF33).

- **Definição:** [`sql/camada_gold.sql`](../sql/camada_gold.sql).
- **Descrição de cada tabela e coluna:** [`sql/catalogo.sql`](../sql/catalogo.sql) (`COMMENT ON`), que o OpenMetadata ingere.
- **Amostras:** [`dados/gold/`](../dados/gold/), com os KPIs completos e os fatos e dimensões limitados a 20 linhas.

## Como é publicada

`gold.publicar(execucao)` é chamada por `hop/workflows/gold.hwf` depois que a qualidade aprova. A função:

1. **Confere as pré-condições.** A Silver publicada tem que ser da mesma execução, a qualidade dessa execução tem que ter sido avaliada e nenhum teste crítico pode ter reprovado ([`qualidade/regras.md`](../qualidade/regras.md)). Se alguma falhar, ela para com erro e a Gold anterior continua publicada.
2. **Reconstrói as 9 tabelas numa única transação.** Quem consulta durante a publicação vê a Gold anterior inteira ou a nova inteira, nunca uma mistura.
3. **Devolve a contagem** de cada tabela; `controle.etapa` registra o total (3965 linhas na execução final).

As tabelas são materializadas, e não views, por três motivos:

- o dashboard lê tabelas pequenas e prontas;
- o conteúdo muda só quando a qualidade aprova;
- o OpenMetadata cataloga cada KPI como um ativo, com responsável, termo do glossário e linhagem.

## Objetos, grão e chaves

| Objeto | Grão (uma linha por...) | Chave | Linhas | Origem |
| --- | --- | --- | --- | --- |
| `dim_conteudo` | conteúdo | `conteudo_id` | 1043 | `silver.conteudo` |
| `dim_usuario` | pessoa (usuário mestre, RF30) | `usuario_pseudo` | 171 | `silver.usuario_mestre` |
| `fato_interacao` | interação | `interacao_id`; FKs para as duas dimensões | 1327 | `silver.interacao` + correspondência id → pessoa |
| `fato_recomendacao` | recomendação por pessoa | (`usuario_pseudo`, `conteudo_id`, `gerado_em`) | 1200 | `silver.recomendacao` + `fato_interacao` (conversão) |
| `kpi_engajamento_mensal` | mês × categoria | (`mes`, `categoria`) | 72 | `fato_interacao` + `dim_conteudo` |
| `kpi_usuarios_ativos_mensal` | mês | `mes_referencia` | 9 | `fato_interacao` |
| `kpi_taxa_conclusao` | categoria × tipo × nível | (`categoria`, `tipo`, `nivel`) | 96 | `fato_interacao` + `dim_conteudo` |
| `kpi_conversao_recomendacao` | classificação × categoria | (`classificacao`, `categoria`) | 15 | `fato_recomendacao` + `dim_conteudo` |
| `kpi_avaliacao` | categoria × tipo | (`categoria`, `tipo`) | 32 | `fato_interacao` + `dim_conteudo` |

Os KPIs guardam **numerador e denominador**, além da taxa arredondada: `pares_consumo` e `pares_concluidos`, `recomendacoes` e `convertidas`. Ao agregar (a taxa de uma categoria somando tipos e níveis, por exemplo), o dashboard calcula `100 × soma(numerador) ÷ soma(denominador)` e nunca a média das taxas, que daria peso igual a grupos de tamanhos diferentes.

## Regras de cálculo

As definições são as mesmas no SQL, no glossário do OpenMetadata (RF28) e nos textos do dashboard.

| KPI | Regra | Valor geral (execução final) |
| --- | --- | --- |
| **Usuário ativo** | pessoa com pelo menos uma interação válida no mês: `count(DISTINCT usuario_pseudo)`. Ids diferentes da mesma pessoa contam uma vez | 64 (jan) → 104 (ago); setembro, incompleto, tem 151 até o dia 26 |
| **Retenção** | % das pessoas ativas no mês que voltam no mês seguinte; vazia no último mês | 48% a 67% de jan a jul; 90% em agosto, puxada pelo lote 2 |
| **Taxa de conclusão** | 100 × pares (pessoa, conteúdo) concluídos ÷ pares com consumo (visualização, início ou conclusão). Um par é concluído com uma interação `conclusão` ou `percentual_conclusao` = 100. Mesma regra do Desafio 1 (`documentacao/kpis.md`) | 22,3% |
| **Conversão de recomendação** | 100 × recomendações seguidas de consumo do conteúdo pela mesma pessoa depois de `gerado_em` ÷ recomendações | 3,3% |
| **Avaliação média** | média de `avaliacao_atribuida` não nula (1 a 5); ao agregar, ponderada pelo número de avaliações | 4,48 |
| **Engajamento mensal** | por mês e categoria: interações, pessoas ativas, conclusões (interações `conclusão`) e minutos (`tempo_consumido`) | a mesma tabela é recalculada pelo Beam e conferida (RF25) |

## Decisões

- **Pessoas, não ids.** A Gold usa o usuário mestre (RF30): `L2-U01` (ids 12 e 171, mesmo CPF) e `L2-U02` (ids 30 e 172, mesmo e-mail) são uma pessoa cada. Por isso a Gold tem 171 pessoas para 173 cadastros. Se dois ids da mesma pessoa receberam a mesma recomendação, fica a de melhor posição.
- **Sem dado pessoal direto (RF32).** Não há nome, e-mail, CPF, telefone, nascimento, cidade nem `usuario_id`. A pessoa aparece como:
  - `usuario_pseudo` (HMAC);
  - `nome_mascarado`, usado só para rotular a lista de pessoas mais engajadas;
  - atributos agregáveis: faixa etária, UF e data de cadastro.
- **Mês completo.** `kpi_usuarios_ativos_mensal.mes_completo` marca se os dados cobrem o mês inteiro. O storytelling compara só meses completos (janeiro a agosto), para não ler uma queda falsa no mês corrente.
- **Conversão depende da data.** A conversão só é mensurável porque as recomendações vêm do snapshot fixo do Desafio 1 (`gerado_em` = 13/09/2026) e o lote 2 traz interações posteriores. Regerar as recomendações com a data de hoje zeraria o KPI (veja `contratos.md`).

## Consumo

| Quem | Como | Lê |
| --- | --- | --- |
| SQL Lab | banco "Desafio 2 - Gold (papel consumo)" | as 4 consultas de [`sql/sql_lab.sql`](../sql/sql_lab.sql), todas sobre a Gold |
| Superset | datasets físicos (`kpi_*`, `dim_usuario`) e virtuais (`vd_*`) | Gold e `qualidade.vw_resultado` |
| Beam | `igual_a_gold` em `beam/pipeline.py` | `kpi_engajamento_mensal`, para conferir o resultado |

As consultas do SQL Lab foram escritas para bater com os KPIs. Por exemplo, a soma de `vd_conclusao_coorte` em todos os meses dá os mesmos 928 pares com consumo e 207 concluídos de `kpi_taxa_conclusao`, ou seja, 22,3%.
