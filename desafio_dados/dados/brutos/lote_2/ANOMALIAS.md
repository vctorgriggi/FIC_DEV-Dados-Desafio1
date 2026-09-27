# Lote 2 — anomalias injetadas

Gerado por `python -m ferramentas.gerar_dados`; não editar à mão.
Todo o restante do lote é válido. Use esta lista para conferir o que a Silver aceita,
padroniza ou manda para a quarentena, e o que os testes de qualidade detectam.

Tratamento esperado: **quarentena** (rejeitar com a regra violada), **padronizar** (aceitar
normalizando), **dados mestres** (consolidar registros da mesma entidade), **reprocessar**
(entra depois que a causa for corrigida na quarentena) e **LGPD** (aceitar protegendo o dado).

| Código | Arquivo | Chave | Anomalia | Tratamento esperado |
| --- | --- | --- | --- | --- |
| L2-C01 | `lote_2/catalogo.csv` | conteudo_id=1005 | linha repetida idêntica | quarentena (duplicado) |
| L2-C02 | `lote_2/catalogo.csv` | conteudo_id=1010 | mesmo id duas vezes com nível e carga diferentes | dados mestres (regra de sobrevivência entre as duas versões) |
| L2-C03 | `lote_2/catalogo.csv` | conteudo_id=7 | conteúdo do Desafio 1 reenviado com título revisado, espaços extras e caixa diferente em tipo e categoria | padronizar; versão do lote 2 sobrevive à do Desafio 1 |
| L2-C04 | `lote_2/catalogo.csv` | conteudo_id=1041 | carga_horaria_min negativa (-45) | quarentena; corrigir para 45 e reprocessar (destrava L2-I13) |
| L2-C05 | `lote_2/catalogo.csv` | conteudo_id=1042 | tipo fora do domínio ('Webinar') | quarentena |
| L2-C06 | `lote_2/catalogo.csv` | conteudo_id=1043 | data_publicacao inexistente ('31/02/2026') | quarentena |
| L2-C07 | `lote_2/catalogo.csv` | conteudo_id=1044 | titulo vazio | quarentena (incompleto) |
| L2-C08 | `lote_2/catalogo.csv` | conteudo_id=abc | conteudo_id não numérico | quarentena |
| L2-C09 | `lote_2/catalogo.csv` | conteudo_id=1045 | data_publicacao em formato alternativo ('2026/08/02') | padronizar para 2026-08-02 |
| L2-C10 | `lote_2/catalogo.csv` | conteudo_id=1046 | nivel sem acento e em minúsculas ('intermediario') | padronizar para 'Intermediário' |
| L2-U01 | `lote_2/usuarios.csv` | usuario_id=171 | mesmo CPF do usuário 12, nome sem acento em maiúsculas e outro e-mail | dados mestres (mesma pessoa que 12, correspondência por cpf_hash) |
| L2-U02 | `lote_2/usuarios.csv` | usuario_id=172 | mesmo e-mail do usuário 30 (maiúsculas e espaços), outro CPF e cidade | dados mestres (mesma pessoa que 30, correspondência por email_hash normalizado) |
| L2-U03 | `lote_2/usuarios.csv` | usuario_id=173 | e-mail sem @ ('maria.souza#email.example') | quarentena |
| L2-U04 | `lote_2/usuarios.csv` | usuario_id=174 | CPF com 10 dígitos | quarentena |
| L2-U05 | `lote_2/usuarios.csv` | usuario_id=175 | data_nascimento no futuro (2031-05-10) | quarentena |
| L2-U06 | `lote_2/usuarios.csv` | usuario_id=176 | nome vazio | quarentena (incompleto) |
| L2-U07 | `lote_2/usuarios.csv` | usuario_id=155 | linha repetida idêntica | quarentena (duplicado) |
| L2-U08 | `lote_2/usuarios.csv` | usuario_id=12 | cadastro do Desafio reenviado com nova cidade (São Paulo) e atualizado_em mais recente | padronizar; versão mais recente sobrevive |
| L2-U09 | `lote_2/usuarios.csv` | usuario_id=177 | usuário de 14 anos (nascido em 2012-03-15) | LGPD: dado de adolescente (art. 14); aceitar e sinalizar no inventário |
| L2-U10 | `lote_2/usuarios.csv` | usuario_id=178 | uf inexistente ('XX') | quarentena |
| L2-I00 | `lote_2/interacoes.json` | 40 pares de recomendacoes_desafio1.json | interações em conteúdos recomendados, após `gerado_em` da recomendação (2026-09-13) | válidas; tornam a conversão de recomendação mensurável |
| L2-I01 | `lote_2/interacoes.json` | posição 400 do array | usuario_id inexistente (999) | quarentena (integridade referencial) |
| L2-I02 | `lote_2/interacoes.json` | posição 401 do array | conteudo_id inexistente (5000) | quarentena (integridade referencial) |
| L2-I03 | `lote_2/interacoes.json` | posição 402 do array | tempo_consumido negativo (-15) | quarentena |
| L2-I04 | `lote_2/interacoes.json` | posição 403 do array | percentual_conclusao acima de 100 (150) | quarentena |
| L2-I05 | `lote_2/interacoes.json` | posição 404 do array | tipo_interacao fora do domínio ('download') | quarentena |
| L2-I06 | `lote_2/interacoes.json` | posição 405 do array | data_hora com mês 13 | quarentena |
| L2-I07 | `lote_2/interacoes.json` | posição 406 do array | sem o campo conteudo_id | quarentena (incompleto) |
| L2-I08 | `lote_2/interacoes.json` | posição 407 do array | cópia idêntica da posição 0 | quarentena (duplicado) |
| L2-I09 | `lote_2/interacoes.json` | posição 408 do array | avaliacao_atribuida 0 | quarentena |
| L2-I10 | `lote_2/interacoes.json` | posição 409 do array | data_hora no futuro (2027-01-10) | quarentena |
| L2-I11 | `lote_2/interacoes.json` | posição 410 do array | conclusão com percentual 80 | quarentena (consistência) |
| L2-I12 | `lote_2/interacoes.json` | posição 411 do array | interação do usuário 171 (mesma pessoa que 12) | dados mestres (conta para o mestre 12) |
| L2-I13 | `lote_2/interacoes.json` | posição 412 do array | interação no conteúdo 1041, que está em quarentena (L2-C04) | quarentena por referência; reprocessar depois de corrigir L2-C04 |
| L2-I14 | `lote_2/interacoes.json` | posição 413 do array | data_hora anterior à publicação do conteúdo 72 (2026-06-23) | quarentena (regra cruzada do Desafio 1) |
| L2-I15 | `lote_2/interacoes.json` | posição 414 do array | usuario_id como texto com espaços ('  42 ') | padronizar para 42 |
| L2-I16 | `lote_2/interacoes.json` | posição 415 do array | tipo_interacao em maiúsculas e sem acento ('VISUALIZACAO') | padronizar para 'visualização' |
| L2-K01 | `lote_2/comentarios.json` | posição 110 do array | avaliacao fora de 1–5 (7) | quarentena |
| L2-K02 | `lote_2/comentarios.json` | posição 111 do array | comentario vazio | quarentena (incompleto) |
| L2-K03 | `lote_2/comentarios.json` | posição 112 do array | tags como texto ('python, dados') em vez de lista | quarentena ou padronizar (decisão documentada) |
| L2-K04 | `lote_2/comentarios.json` | posição 113 do array | e-mail no texto livre | LGPD: substituir por [email] na Silver |
| L2-K05 | `lote_2/comentarios.json` | posição 114 do array | telefone no texto livre | LGPD: substituir por [telefone] na Silver |
| L2-K06 | `lote_2/comentarios.json` | posição 115 do array | data anterior à publicação do conteúdo 72 | quarentena (regra cruzada do Desafio 1) |
| L2-K07 | `lote_2/comentarios.json` | posição 116 do array | usuario_id inexistente (999) | quarentena (integridade referencial) |
| L2-K08 | `lote_2/comentarios.json` | posição 117 do array | cópia idêntica da posição 0 | quarentena (duplicado) |
| L2-K09 | `lote_2/comentarios.json` | posição 118 do array | data inexistente ('2026-09-31') | quarentena |
