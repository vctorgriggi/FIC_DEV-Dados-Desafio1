# Ingestão — RF02 a RF06

Código em `ingestao/pipeline.py`. Testes com registros sujos em `tests/test_ingestao.py`
(`docker compose run --rm app python -m unittest`).

## Fluxo

1. **RF02 — leitura.** `catalogo.csv` (utf-8, tolera BOM), `interacoes.json` e `comentarios.json` (listas JSON). Nome do arquivo e quantidade de registros vão para o log.
2. **RF03 — validação.** Cada registro é classificado como válido, inválido, incompleto ou duplicado, nessa ordem de verificação: campos obrigatórios → conversões e domínios → referência ao catálogo → regras cruzadas → duplicidade. O motivo de cada rejeição vai para o log e para `dados/processados/rejeitados.json`, junto com o registro original, para auditoria sem abrir os arquivos brutos.
3. **RF04 — tratamento.** Aplicado só aos registros válidos. Saída em `dados/processados/` (`catalogo_processado.csv`, `interacoes_processadas.json`, `comentarios_processados.json`). Os brutos não são alterados.
4. **RF06 — carga.** PostgreSQL em uma única transação: `categoria`, `usuario` e `conteudo` por upsert (`ON CONFLICT`), para preservar embeddings e recomendações dos conteúdos que continuam válidos; `interacao` é substituída por completo. Ao final da mesma transação, tudo o que não veio nesta carga é removido (recomendações, embeddings, conteúdos, usuários e categorias órfãos), de modo que o banco reflita exatamente os dados válidos da execução. Comentários vão para o MongoDB (RF07, módulo `mongodb/`), com a mesma reconciliação.
5. **RF05 — resumo.** `dados/processados/resumo_ingestao.json`: lidos por fonte, válidos/inválidos/incompletos/duplicados/corrigidos (total e por fonte), carregados por banco, tempo por etapa e total.

## Regras de validação (RF03)

| Fonte | Obrigatórios | Inválido quando |
|---|---|---|
| catálogo | conteudo_id, titulo, tipo, categoria, nivel, carga_horaria_min, data_publicacao | id não inteiro ou ≤ 0; carga não inteira ou < 0; data não reconhecida; tipo fora de {Curso, Vídeo, Artigo, Podcast}; nível fora de {Básico, Intermediário, Avançado} |
| interações | usuario_id, conteudo_id, tipo_interacao, data_hora | ids não inteiros ou ≤ 0; conteudo_id ausente do catálogo; tipo fora dos 6 sugeridos; data_hora não ISO; **data_hora anterior à publicação do conteúdo**; data_hora no futuro; tempo_consumido < 0; percentual fora de 0–100; avaliação fora de 1–5; `conclusão` com percentual < 100; `avaliação` sem nota |
| comentários | usuario_id, conteudo_id, avaliacao, comentario, data | ids não inteiros ou ≤ 0; conteudo_id ausente do catálogo; avaliação fora de 1–5; data não reconhecida; **data anterior à publicação do conteúdo**; data no futuro; tags não é lista |

As regras em negrito cruzam fontes: a data de publicação vem do catálogo já validado. São as únicas que rejeitam algo nos dados fornecidos.

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

3000 lidos, **2871 válidos, 129 inválidos**, 0 incompletos, 0 duplicados, 0 corrigidos. Campo a campo os arquivos estão limpos; as rejeições vêm todas das regras cruzadas: 77 interações e 52 comentários datados **antes da publicação do conteúdo** (de 1 a 165 dias), listados em `rejeitados.json`. Carregados: 8 categorias, 150 usuários, 1000 conteúdos, 923 interações no PostgreSQL; 948 comentários no MongoDB. As demais regras são demonstradas pelos testes unitários.

Observações sobre os dados que **não** geram rejeição, por decisão:

- 189 títulos se repetem no catálogo, mas com autor, nível e data diferentes — são conteúdos distintos com título genérico; a chave de duplicidade é `conteudo_id`.
- 267 interações que não são `avaliação` trazem nota (toda `curtida` tem nota); tratado como informação válida e aproveitado no índice `Icur`.
- Quase todos os comentários são de usuários sem interação registrada com aquele conteúdo; as interações fornecidas são uma amostra, não o histórico completo.
