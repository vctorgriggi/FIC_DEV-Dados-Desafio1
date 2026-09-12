# MongoDB, embeddings, busca e recomendação — RF07 a RF11

Código em `mongodb/` e `recomendacao/`. Testes em `tests/test_recomendacao.py`.

## RF07 — MongoDB

**O que vai para o MongoDB e por quê.** Os comentários/avaliações (`comentarios.json`). São o dado semiestruturado do desafio: texto livre, array de `tags` de tamanho variável e sem esquema fixo — um documento por comentário é a modelagem natural, enquanto no relacional exigiria tabela auxiliar para tags. O restante (catálogo, interações, recomendações) é tabular, com relacionamentos e integridade referencial, e fica no PostgreSQL.

**Modelo do documento.** Os campos originais mais `categoria`, `titulo` e `tipo` copiados do catálogo (desnormalização). Isso permite a agregação por categoria exigida pelo RF07 sem consultar o PostgreSQL, ao custo de repetir três campos por documento — aceitável porque o catálogo é estável.

```json
{
  "usuario_id": 137, "conteudo_id": 587, "avaliacao": 5,
  "comentario": "Conteúdo introdutório, claro e objetivo.",
  "tags": ["anonimizacao", "lgpd", "essencial"], "data": "2026-03-02",
  "categoria": "Segurança & Governança", "titulo": "…", "tipo": "Artigo"
}
```

**Carga.** `mongodb/comentarios.py` lê `dados/processados/comentarios_processados.json` (já validado pela ingestão) e faz *upsert* pela chave (usuário, conteúdo, data, comentário) com índice único — reexecuções não duplicam. Índices em `conteudo_id`, `tags`, `avaliacao` e `categoria`.

**Operações.** Em Python (`por_conteudo`, `por_tag`, `por_nota`, `agregar_por_categoria`) e em `mongodb/consultas.js` (inserir, comentários de um conteúdo, por tag, por nota, contagem e média por categoria).

## RF08 — Embeddings

- **Modelo:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensões, roda em CPU (1000 conteúdos em ~20 s). Escolhido por ser multilíngue — o catálogo é em português; o `all-MiniLM-L6-v2` (inglês) foi descartado por isso.
- **Texto:** `"{titulo}. {descricao}"`. Título primeiro porque concentra o tema; descrição complementa. Sem *stopwords*/*stemming*: modelos de sentença esperam texto natural.
- **Vetores normalizados** (`normalize_embeddings=True`), então a distância de cosseno do pgvector (`<=>`) é `1 − produto interno`.
- **Armazenamento:** `conteudo_embedding(conteudo_id PK, modelo, embedding vector(384), gerado_em)` + índice HNSW por cosseno. A PK em `conteudo_id` impede duplicidade; só são gerados embeddings de conteúdos sem vetor **do modelo configurado** — trocar o modelo no `config.yaml` regera tudo.
- **Falhas** de geração são contadas e logadas por bloco (RF14), sem interromper o pipeline.

## RF09 — Busca semântica

`recomendacao.embeddings.buscar(cfg, pg, consulta, top_k)` codifica a consulta com o mesmo modelo e ordena por `embedding <=> consulta`. Retorna posição, id, título, categoria, tipo e similaridade (`1 − distância`, quanto maior melhor). `top_k` vem de `busca.top_k`. As três consultas de `busca.demonstracao` rodam a cada execução e ficam em `dados/processados/busca_semantica.json`.

## RF10 — Recomendação

Fórmula do enunciado: `Pontuação = ((Ivis + Icur) / 2) × 100 × Iconc`.

| Índice | Como é calculado |
|---|---|
| **Ivis** | tempo consumido pelo usuário (`visualização`, `início`, `conclusão`) na categoria do candidato ÷ tempo total consumido |
| **Icur** | curtidas ou avaliações ≥ 4 (`recomendacao.nota_minima_aprovacao`) na categoria do candidato ÷ total de curtidas e avaliações ≥ 4 |
| **Iconc** | 0 se existe interação `conclusão` ou `percentual_conclusao = 100` para o par usuário/conteúdo; 1 caso contrário |

Usuário sem histórico tem índice 0. **Desempate:** candidatos com a mesma pontuação (toda a categoria) são ordenados pela similaridade de cosseno (pgvector) entre o candidato e a média dos embeddings do histórico do usuário — o mais parecido com o que ele já consumiu vem primeiro.

**Classificação.** `positivo` ≥ 70; `estavel` entre 40 e 70; `negativo` ≤ 40 ou concluído. O enunciado escreve `40 > Pontuação < 70` para o estável; interpretamos como `40 < Pontuação < 70`, único sentido compatível com as outras duas faixas. Negativos são descartados, como o enunciado determina; um usuário pode ficar sem recomendação.

**Por que a proporção por categoria, e não a similaridade vetorial, como índice.** O RF10 admite as duas. Testamos primeiro a vetorial (cosseno entre o candidato e a média do histórico): as descrições do catálogo seguem o mesmo molde textual, e a similaridade ficou comprimida entre 0,38 e 0,85 — todo top-10 caía em "positivo" e a classificação perdia sentido. A proporção por categoria produz índices espalhados em 0–1 e é explicável ("40 % do tempo desse usuário foi em Banco de Dados"). O pgvector segue no desempate e na busca semântica.

**Resultado nos dados fornecidos:** 150 usuários, 117 com recomendação, 1170 recomendações (200 positivas, 970 estáveis), `top_k = 10`.

## RF11 — Persistência

Tabela `recomendacao(usuario_id, conteudo_id, pontuacao, posicao, classificacao, gerado_em)`. Cada execução substitui o conjunto anterior — um único *snapshot* para o dashboard. A lista completa com os índices intermediários fica em `dados/processados/recomendacoes.json`.

## Limitações

- Conteúdos já visualizados mas não concluídos continuam elegíveis: o enunciado só remove os concluídos.
- `Icur` usa apenas as interações (`curtida` e `avaliacao_atribuida`); as avaliações dos comentários (MongoDB) não entram no índice.
