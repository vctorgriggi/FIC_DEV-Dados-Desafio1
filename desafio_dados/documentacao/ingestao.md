# Ingestão — RF02 a RF06

Código em `ingestao/pipeline.py`. Testes com registros sujos em `tests/test_ingestao.py`
(`docker compose run --rm app python -m unittest`).

## Fluxo

1. **RF02 — leitura.** `catalogo.csv` (utf-8, tolera BOM), `interacoes.json` e `comentarios.json` (listas JSON). Nome do arquivo e quantidade de registros vão para o log.
2. **RF03 — validação.** Cada registro é classificado como válido, inválido, incompleto ou duplicado, nessa ordem de verificação: campos obrigatórios → conversões e domínios → referência ao catálogo → duplicidade. O motivo de cada rejeição vai para o log e para `dados/processados/rejeitados.json`.
3. **RF04 — tratamento.** Aplicado só aos registros válidos. Saída em `dados/processados/` (`catalogo_processado.csv`, `interacoes_processadas.json`, `comentarios_processados.json`). Os brutos não são alterados.
4. **RF06 — carga.** PostgreSQL em uma única transação, idempotente (`ON CONFLICT`): `categoria`, `usuario`, `conteudo`, `interacao`. Comentários vão para o MongoDB (RF07, módulo `mongodb/`).
5. **RF05 — resumo.** `dados/processados/resumo_ingestao.json`: lidos por fonte, válidos/inválidos/incompletos/duplicados/corrigidos (total e por fonte), carregados por banco, tempo por etapa e total.

## Regras de validação (RF03)

| Fonte | Obrigatórios | Inválido quando |
|---|---|---|
| catálogo | conteudo_id, titulo, tipo, categoria, nivel, carga_horaria_min, data_publicacao | id não inteiro ou ≤ 0; carga não inteira ou < 0; data não reconhecida; tipo fora de {Curso, Vídeo, Artigo, Podcast}; nível fora de {Básico, Intermediário, Avançado} |
| interações | usuario_id, conteudo_id, tipo_interacao, data_hora | ids não inteiros ou ≤ 0; conteudo_id ausente do catálogo; tipo fora dos 6 sugeridos; data_hora não ISO; tempo_consumido < 0; percentual fora de 0–100; avaliação fora de 1–5 |
| comentários | usuario_id, conteudo_id, avaliacao, comentario, data | ids não inteiros ou ≤ 0; conteudo_id ausente do catálogo; avaliação fora de 1–5; data não reconhecida; tags não é lista |

Duplicidade: catálogo por `conteudo_id`; interações por (usuário, conteúdo, tipo, data_hora); comentários por (usuário, conteúdo, data, texto).

Não há fonte de usuários, então "referência a usuário inexistente" não se aplica: a tabela `usuario` é derivada dos ids encontrados em interações e comentários.

## Decisões de tratamento (RF04)

- **Texto:** espaços nas pontas e internos colapsados (`"a   b"` → `"a b"`).
- **Caixa e acento:** tipo, nível e tipo de interação são comparados sem acento e em minúsculas e gravados na forma canônica (`" video "` → `"Vídeo"`, `"CONCLUSAO"` → `"conclusão"`). Categoria usa a mesma chave de comparação e mantém a primeira grafia encontrada, evitando `"Banco de Dados"` e `"banco de dados"` virarem duas categorias.
- **Datas:** aceitas em `YYYY-MM-DD`, `DD/MM/YYYY` e `YYYY/MM/DD`; gravadas em `YYYY-MM-DD`. `data_hora` em ISO 8601 com segundos.
- **Numéricos:** inteiros estritos — `"7.0"` vira 7, `"7.9"` é inválido (id ou duração fracionária não é corrigível). Percentual como float.
- **Tags:** minúsculas, espaços removidos, vazias descartadas; acentos preservados.
- **Ausentes:** `tempo_consumido`, `percentual_conclusao` e `avaliacao_atribuida` podem ser nulos (nem toda interação tem avaliação); `descricao` e `autor` também.
- **Corrigidos:** registro válido em que algum valor mudou na normalização.

## Resultado nos dados fornecidos

Os três arquivos estão limpos: 3000 lidos, 3000 válidos, 0 inválidos/incompletos/duplicados/corrigidos. Carregados no PostgreSQL: 8 categorias, 150 usuários, 1000 conteúdos, 1000 interações. Por isso a validação é demonstrada pelos testes unitários, que cobrem cada regra acima.
