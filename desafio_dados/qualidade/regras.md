# Regras de qualidade de dados (RF31)

Os testes rodam a cada execução, depois da Silver e antes da Gold (`hop/workflows/qualidade.hwf`).

- **Definição:** cada teste é uma linha de `qualidade.teste`, com a consulta SQL que o implementa. A fonte da verdade é [`sql/qualidade.sql`](../sql/qualidade.sql), reaplicado pelo `db-init`.
- **Resultado:** uma linha por execução, teste e fonte em `qualidade.resultado`.
- **Consulta:** `qualidade.vw_resultado`, que o dashboard usa.
- **Evidência:** a exportação de todas as execuções está em [`resultados/resultados.csv`](resultados/resultados.csv).

## Como um teste é avaliado

A consulta de cada teste recebe a execução e devolve `(fonte, total, falhos)`:

```
valor_medido = 100 × (total − falhos) ÷ total          (100 quando total = 0)
aprovado     = valor_medido <operador> limite_aceitavel
```

Todos os testes medem "% de registros que passam", então os limites ficam na mesma escala e o gráfico de evolução compara testes diferentes.

Cada resultado grava o operador, o limite e a severidade **vigentes quando o teste rodou**. Se o teste mudar depois, o histórico continua dizendo por que cada execução passou ou reprovou.

## Os testes

| Teste | Dimensão | Alvo | Fórmula | Limite | Severidade | Ação quando reprova |
| --- | --- | --- | --- | --- | --- | --- |
| **Q01** Validade das fontes | validade | Bronze → Silver, por fonte | 100 × (lidos − rejeitados) ÷ lidos na validação da execução | ≥ 90 | **crítica** | Interrompe o fluxo antes da Gold. Mais de 10% de rejeição indica problema na fonte, e não em registros isolados: tratar a quarentena e reprocessar |
| **Q02** Integridade das referências | integridade referencial | interações, comentários, recomendações | 100 × (lidos − rejeitados por `REF_USUARIO` ou `REF_CONTEUDO`) ÷ lidos | ≥ 99 | alta | Etapa com ressalvas; os órfãos ficam na quarentena. Verificar se o cadastro ou o catálogo chegou incompleto |
| **Q03** Unicidade das chaves | unicidade | as 5 tabelas da Silver | 100 × chaves de negócio distintas ÷ linhas | = 100 | **crítica** | Interrompe o fluxo: uma duplicata na Silver inflaria as contagens da Gold. Revisar a deduplicação em `sql/silver.sql` |
| **Q04** Completude do catálogo | completude | `silver.conteudo` | 100 × conteúdos com descrição e autor ÷ conteúdos | ≥ 95 | média | Etapa com ressalvas; avisar o responsável pelo catálogo |
| **Q05** Completude dos usuários | completude | `silver.usuario` | 100 × usuários com cidade, data de cadastro e faixa etária ÷ usuários | ≥ 95 | média | Etapa com ressalvas; faixas ausentes enfraquecem as análises por perfil |
| **Q06** Consistência temporal | consistência | `silver.interacao`, `silver.comentario` | 100 × eventos entre a publicação do conteúdo e o momento da execução ÷ eventos | = 100 | **crítica** | Interrompe o fluxo: a regra `DATA_ANTES_PUBLICACAO` ou `DATA_FUTURA` deixou passar um evento impossível |
| **Q07** Cobertura dos dados mestres | integridade referencial | `silver.usuario` → `silver.usuario_correspondencia` | 100 × usuários com pessoa associada ÷ usuários | = 100 | **crítica** | Interrompe o fluxo: sem o mestre, a Gold contaria ids em vez de pessoas (RF30) |

As cinco dimensões pedidas estão cobertas: completude (Q04, Q05), validade (Q01), unicidade (Q03), consistência (Q06) e integridade referencial (Q02, Q07).

**Por que os limites são esses:**

- **Q01 ≥ 90%:** o lote 2 tem 46 anomalias propositais e o Desafio 1 já tinha 77 interações e 52 comentários anteriores à publicação. Nesse cenário a rejeição normal fica entre 0 e 7% (interações: 6,2%). Passar de 10% indica um arquivo inteiro com problema, como uma coluna deslocada.
- **Q02 ≥ 99%:** órfãos isolados são esperados (o usuário 999 do lote 2), mas não em massa.
- **Q03, Q06 e Q07 = 100%:** não são estatísticas, são invariantes. Qualquer falha é um defeito das regras da Silver, e não do dado.

## Severidade e ação

| Severidade | Efeito na execução |
| --- | --- |
| crítica | `qualidade` termina com `falha`, a Gold **não é publicada** e a execução termina com `falha`. A Gold anterior continua no ar |
| alta, média | `qualidade` termina com `sucesso_com_ressalvas` e o fluxo segue |

O bloqueio acontece em dois lugares independentes:

1. **Workflow:** `qualidade.hwf` verifica que não há teste crítico reprovado na execução (action `Evaluate rows number in a table`). Se houver, aborta, e o `principal.hwf` não chega à Gold.
2. **Banco:** `gold.publicar(execucao)` recusa publicar se a qualidade da execução não foi avaliada ou se há teste crítico reprovado. Mesmo uma chamada manual, fora do Hop, não passa.

## Resultados da execução final (`5696f833`)

Os 18 resultados (7 testes × fontes) foram aprovados:

| Teste | catálogo | usuários | interações | comentários | recomendações |
| --- | --- | --- | --- | --- | --- |
| Q01 Validade (≥ 90) | 99,62 | 97,22 | 93,79 | 94,91 | 100,00 |
| Q02 Referências (≥ 99) | — | — | 99,86 | 99,91 | 100,00 |
| Q03 Unicidade (= 100) | 100,00 | 100,00 | 100,00 | 100,00 | 100,00 |
| Q04 Completude do catálogo (≥ 95) | 100,00 | — | — | — | — |
| Q05 Completude dos usuários (≥ 95) | — | 100,00 | — | — | — |
| Q06 Consistência temporal (= 100) | — | — | 100,00 | 100,00 | — |
| Q07 Cobertura dos mestres (= 100) | — | 100,00 | — | — | — |

## Evolução entre execuções

Seis execuções completas do workflow, com a triagem da quarentena entre elas ([`hop/evidencias/triagem_quarentena.sql`](../hop/evidencias/triagem_quarentena.sql)):

| Execução | O que mudou antes dela | Q01 catálogo | Q01 interações | Q01 comentários | Q02 interações | Reprovados | Gold |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A `1cac1195` | primeira carga | 99,33 | 93,64 | 94,73 | 99,79 | 0 | publicada |
| B `fc6374ce` | triagem 1: `L2-C04` corrigido; cópias e versão conflitante descartadas | 99,62 | 93,79 | 94,82 | 99,86 | 0 | publicada |
| C `7dbd4209` | triagem 2: `L2-K09` corrigido com data válida | 99,62 | 93,79 | 94,91 | 99,86 | 0 | publicada |
| D `a98b2a5a` | **demonstração do bloqueio**: limite do Q01 elevado para 99 | 99,62 | 93,79 ✗ | 94,91 ✗ | 99,86 | **3** | **bloqueada** |
| E `a2f8a3b3` | limite restaurado (`db-init`) | 99,62 | 93,79 | 94,91 | 99,86 | 0 | publicada |
| F `5696f833` | execução final de referência | 99,62 | 93,79 | 94,91 | 99,86 | 0 | publicada |

Como ler a evolução:

- **Q01 catálogo, de 99,33 para 99,62:** o conteúdo 1041 foi corrigido e duas cópias foram descartadas. Um registro descartado deixa de contar como rejeitado.
- **Q01 e Q02 interações:** a interação `L2-I13` entrou sozinha quando o conteúdo 1041, do qual dependia, foi corrigido.
- **Q01 comentários, de 94,73 para 94,91, em dois passos:**
  - Na execução B, a primeira correção do `L2-K09` (31/09 → 30/09) ainda era uma data futura. O registro voltou a `pendente` com a regra nova, e a melhora dessa execução veio só do descarte da cópia do `L2-K08`.
  - Na execução C, a data foi corrigida para 20/09 e o comentário entrou.

O dashboard de exploração mostra essa série no gráfico "Evolução da validade das fontes (Q01) por execução" (`superset/exportacao_e_evidencias/02_exploracao.png`).

## Demonstração do bloqueio da Gold (execução D)

Um teste crítico reprovado precisa impedir a Gold sem apagar a Gold anterior. Para demonstrar isso sem estragar os dados, o limite do Q01 foi elevado temporariamente de 90 para 99. Três fontes ficaram abaixo dele:

```sql
UPDATE qualidade.teste SET limite_aceitavel = 99 WHERE teste_id = 'Q01_VALIDADE_FONTES';
-- docker compose run --rm hop workflows/principal.hwf
-- docker compose run --rm db-init          (restaura o limite de sql/qualidade.sql)
```

Resultado registrado:

| Onde | O que ficou gravado |
| --- | --- |
| `qualidade.vw_resultado` | Q01 `usuarios` 97,22, `interacoes` 93,79 e `comentarios` 94,91 reprovados, com limite `>= 99` e severidade `critica` |
| `controle.etapa` | `qualidade`: `falha`, "teste critico reprovado; Gold bloqueada; ver qualidade.vw_resultado"; as etapas `gold` e `metadados` não existem nessa execução |
| `controle.execucao` | `falha`, "encerrada por falha; ver controle.etapa" |
| Gold | intacta: continuou com as 3965 linhas publicadas pela execução C |

Para repetir sem gerar uma execução nova, o mesmo teste pode ser feito numa transação desfeita:

```sql
BEGIN;
UPDATE qualidade.teste SET limite_aceitavel = 99 WHERE teste_id = 'Q01_VALIDADE_FONTES';
SELECT * FROM qualidade.executar('<execucao>') WHERE NOT aprovado;   -- 3 fontes reprovadas
SELECT gold.publicar('<execucao>');   -- ERROR: teste critico reprovado na execucao ...: Gold nao publicada
ROLLBACK;
```

## Consultas úteis

```sql
-- resultado de uma execução
SELECT teste_id, fonte, valor_medido, limite, severidade, aprovado
  FROM qualidade.vw_resultado WHERE execucao_id = '<uuid>' ORDER BY teste_id, fonte;

-- evolução de uma métrica
SELECT executado_em, fonte, valor_medido FROM qualidade.vw_resultado
 WHERE teste_id = 'Q01_VALIDADE_FONTES' ORDER BY executado_em, fonte;
```

## Limitações

- O Q01 mede a rejeição da execução inteira, que relê o Desafio 1 e o lote 2 a cada vez. As 77 interações do Desafio 1 anteriores à publicação pesam em todas as execuções: a métrica é da carga acumulada, não do lote novo.
- Os testes rodam sobre a Silver publicada da execução. Um problema que a Silver deixa passar e que nenhum teste cobre chega à Gold. Os testes críticos (Q03, Q06, Q07) existem para pegar as falhas das próprias regras.
