# Técnicas de proteção de dados pessoais (RF33)

As técnicas são aplicadas na passagem da Bronze para a Silver, pelas funções do schema `lgpd` (`sql/camadas.sql`), chamadas na validação de usuários e comentários (`sql/silver.sql`). A Bronze é o único lugar com o dado original. A demonstração completa está em [`demonstracao.sql`](demonstracao.sql), e a saída de uma execução em [`demonstracao_resultado.txt`](demonstracao_resultado.txt).

## O que é aplicado e onde

| Técnica | Campo | Função | Onde aparece | Por que esta técnica |
| --- | --- | --- | --- | --- |
| **Mascaramento** | nome, e-mail | `lgpd.mascarar_nome`, `lgpd.mascarar_email` | `silver.usuario`; `gold.dim_usuario.nome_mascarado`, exibido no dashboard "Pessoas mais engajadas" | O consumo precisa de um rótulo legível, não do valor. `Otávio Souza Carvalho` vira `Otávio C***` |
| **Pseudonimização** | `usuario_id` | `lgpd.pseudonimizar` = HMAC-SHA256 com `LGPD_CHAVE_PSEUDONIMO` | `usuario_pseudo` na Silver e na Gold; correspondência em `restrito.usuario_pseudonimo` | A análise precisa associar os eventos da mesma pessoa, e a operação precisa poder reidentificar sob controle (ex.: atender a um pedido do titular) |
| **Hash com salt** | e-mail, CPF | `lgpd.hash_salt` = SHA-256(`LGPD_SALT` ‖ valor normalizado) | `email_hash`, `cpf_hash` na Silver | Os dados mestres (RF30) só precisam saber se dois cadastros têm o mesmo CPF ou e-mail. O hash permite comparar sem guardar nem revelar o valor |
| **Anonimização de texto** | comentário | `lgpd.anonimizar_texto` | `silver.comentario` | E-mails e telefones digitados no texto livre viram `[email]` e `[telefone]` |
| **Supressão** | telefone, data de nascimento, CPF e e-mail em claro | não sobem para a Silver | só na Bronze | Minimização: o que não é necessário não é copiado. A data de nascimento vira `faixa_etaria` |
| **Controle de acesso** | schemas `bronze`, `silver`, `quarentena`, `restrito` | papel `consumo` sem permissão | Superset e SQL Lab usam `consumo` | Mesmo por engano, o dashboard não consegue ler o original |

## Pseudonimização × hash com salt

| | Pseudonimização (HMAC com chave) | Hash com salt (SHA-256) |
| --- | --- | --- |
| **Reversível?** | Sim, de forma controlada: quem tem `restrito.usuario_pseudonimo` (ou a chave e o conjunto de ids) sabe quem é quem | Não: não existe caminho do hash de volta ao valor |
| **Para que serve aqui** | Associar os eventos da mesma pessoa em todas as camadas; reidentificar quando legítimo | Comparar valores (mesmo CPF? mesmo e-mail?) sem conhecê-los |
| **Ainda é dado pessoal (LGPD)?** | Sim: dado pseudonimizado continua pessoal para quem guarda a correspondência (art. 13, § 4º) | Continua pessoal enquanto permitir ligar cadastros, mas não expõe o valor |
| **Segredo** | `LGPD_CHAVE_PSEUDONIMO` + tabela `restrito` | `LGPD_SALT` |
| **Risco sem o segredo** | Com um HMAC sem chave (um hash simples do id), bastaria calcular o hash de 1 a 1 milhão para reverter | Sem salt, o CPF seria revertido por força bruta: há só 10^9 CPFs possíveis. O salt secreto torna isso inviável |
| **Troca do segredo** | Gera outros pseudônimos: é preciso republicar Silver e Gold (a tabela `restrito` é atualizada pela publicação) | Muda todos os hashes: é preciso republicar a Silver |

Resumo da escolha:

- **Pseudonimização** para o identificador que precisa continuar associável: o `usuario_id`.
- **Hash com salt** para identificadores que só precisam ser comparados: CPF e e-mail.
- **Mascaramento** só para o que é exibido.

## Gestão dos segredos

- **Onde ficam:** `LGPD_SALT` e `LGPD_CHAVE_PSEUDONIMO` ficam só no `.env`, que está no `.gitignore`. Os três integrantes usam os mesmos valores, passados em privado; se cada um usasse os seus, os pseudônimos não bateriam entre as máquinas.
- **Como chegam ao Hop:** `docker/hop/segredos.sh` gera, dentro do container, um arquivo de ambiente do Hop com permissão 600. Os valores não aparecem no projeto `hop/` nem no log.
- **Validação:** `validacao.segredo()` interrompe a Silver se o segredo estiver vazio, curto ou com o valor de exemplo do `.env.example`. Assim, nunca se gera pseudônimo com chave fraca por engano.
- **Correspondência:** a tabela `restrito.usuario_pseudonimo` fica no banco, fora do repositório, num schema que o papel `consumo` não lê.

## O dashboard não expõe os valores originais

A demonstração (`demonstracao_resultado.txt`) mostra, com o papel do Superset:

1. O papel `consumo` não tem permissão nos schemas `bronze`, `silver`, `quarentena` e `restrito` (tabela de privilégios), e as tentativas de leitura são negadas (`permission denied`).
2. A varredura de todas as linhas de `gold.dim_usuario`, `gold.fato_interacao` e `gold.fato_recomendacao` encontra zero ocorrências de padrões de e-mail, CPF ou telefone.
3. A pessoa aparece só pelo nome mascarado e pelo pseudônimo (ex.: `André N***`, na tabela "Pessoas mais engajadas" do dashboard de exploração, em `superset/exportacao_e_evidencias/`).
4. Voltar do pseudônimo ao `usuario_id` só é possível pela tabela restrita, com o dono do banco (seção 5). A demonstração não imprime nenhum `usuario_id` ao lado do seu pseudônimo, porque isso seria uma tabela de correspondência no repositório.
