# Inventário de dados pessoais (RF32)

Todos os dados pessoais do projeto são **fictícios** e gerados por `ferramentas/gerar_dados.py`:

- e-mails no domínio reservado `.example`;
- telefones com DDD `00`, que não existe;
- CPFs com dígito verificador propositalmente inválido, para nunca coincidir com um CPF real.

Os testes em `tests/test_gerar_dados.py` garantem essas três propriedades.

Por serem fictícios e gerados de forma determinística, os arquivos de origem com dados pessoais (`dados/brutos/usuarios.csv` e `lote_2/usuarios.csv`) ficam no repositório: são a fonte que o pipeline lê. Já as amostras exportadas das camadas não levam as colunas pessoais (`dados/bronze/usuarios_sem_dados_pessoais.csv`), e as da Silver não levam o pseudônimo. Com dados reais, os arquivos de origem ficariam fora do repositório.

O inventário segue o fluxo do dado: fonte → Bronze → Silver → Gold. Cada campo está classificado no OpenMetadata com as tags da classificação `LGPD` e com as tags padrão `PII.Sensitive` e `PII.NonSensitive` (`openmetadata/provisionar.py`).

## Categorias usadas

| Categoria | Definição (LGPD) | Tag no catálogo |
| --- | --- | --- |
| Dado pessoal | Informação relacionada a pessoa natural identificada ou identificável (art. 5º, I) | `LGPD.DadoPessoal` |
| Dado pessoal sensível | Origem racial, convicção religiosa, opinião política, saúde, vida sexual, dado genético ou biométrico (art. 5º, II) | não há campo sensível estruturado; veja "texto livre" |
| Identificador indireto | Não identifica sozinho, mas identifica quando combinado com outros dados | `LGPD.IdentificadorIndireto` |
| Dado de criança ou adolescente | Exige tratamento no melhor interesse do titular (art. 14) | `LGPD.DadoDeCriancaOuAdolescente` |

## Inventário por campo

**Acesso:**

- `dono` = papel `desafio`, dono do banco, usado pelos pipelines.
- `consumo` = papel somente leitura do Superset e do SQL Lab, que lê só `gold`, `qualidade` e `controle`.

**Base legal (art. 7º):**

- **Cadastro (usuários):** execução de contrato (V), a prestação do serviço educacional.
- **Análises de engajamento e qualidade:** legítimo interesse (IX), já com pseudônimos, o que reduz o impacto.

**Retenção:** os prazos são uma **proposta** para a plataforma, a validar com o encarregado.

### Cadastro de usuários

| Campo (fonte → Bronze) | Categoria | Finalidade | Necessidade | Acesso | Retenção proposta | Proteção a partir da Silver |
| --- | --- | --- | --- | --- | --- | --- |
| `nome` | Dado pessoal | Identificar o titular no atendimento | Não é necessário para análise | dono | Enquanto a conta existir + 6 meses | Só `nome_mascarado` (mascaramento) |
| `email` | Dado pessoal | Contato e login; identificar cadastros duplicados | O valor não é necessário para análise; a comparação, sim | dono | Enquanto a conta existir + 6 meses | `email_hash` (hash com salt) e `email_mascarado` |
| `cpf` | Dado pessoal identificador | Identificar a pessoa entre cadastros (dados mestres) | Só a comparação é necessária | dono | Enquanto a conta existir + 6 meses | Só `cpf_hash` (hash com salt) |
| `telefone` | Dado pessoal | Contato | Não é necessário para análise | dono | Enquanto a conta existir + 6 meses | Não sobe para a Silver |
| `data_nascimento` | Dado pessoal; indica criança ou adolescente | Perfil etário e cuidado com menores (art. 14) | Basta a faixa etária | dono | Enquanto a conta existir + 6 meses | Só `faixa_etaria`; `0-17` identifica menores |
| `cidade`, `uf` | Identificador indireto | Análise regional | UF basta para o consumo | dono (cidade); consumo (UF) | Enquanto a conta existir | Cidade fica na Silver; a Gold só tem a UF |
| `usuario_id` | Identificador indireto | Chave técnica entre fontes | Necessário até a Silver | dono | Enquanto a conta existir | Na Gold vira `usuario_pseudo` (pseudonimização) |
| `data_cadastro`, `atualizado_em` | Identificador indireto (em conjunto) | Antiguidade do cadastro; escolher a versão mais recente | Necessário para sobrevivência | dono; consumo (`data_cadastro`) | Enquanto a conta existir | Sem alteração |

### Interações, comentários e recomendações

| Campo | Categoria | Finalidade | Necessidade | Acesso | Retenção proposta | Proteção |
| --- | --- | --- | --- | --- | --- | --- |
| `usuario_id` (interações, comentários, recomendações) | Identificador indireto | Ligar o evento à pessoa | Necessário para as métricas por pessoa | dono | 5 anos (histórico analítico) | Na Gold vira `usuario_pseudo` do usuário mestre |
| `comentario` (texto livre) | Pode conter dado pessoal e, em tese, dado sensível digitado pelo usuário | Qualidade percebida do conteúdo | O texto é necessário; os contatos nele, não | dono | 5 anos | `lgpd.anonimizar_texto` troca e-mails e telefones por `[email]` e `[telefone]` na Silver. Não há detecção automática de dado sensível (saúde, religião): risco residual registrado |
| `data_hora`, `tempo_consumido`, `avaliacao` | Não pessoal (sem o identificador) | Métricas de engajamento e qualidade | Necessário | dono; consumo (agregado) | 5 anos | Na Gold, só associado ao pseudônimo |

### Catálogo

| Campo | Categoria | Finalidade | Necessidade | Acesso | Retenção proposta | Proteção |
| --- | --- | --- | --- | --- | --- | --- |
| `autor` | Dado pessoal de profissional, tornado público pela autoria | Crédito do conteúdo | Não é necessário para os KPIs | dono | Enquanto o conteúdo existir | Não sobe para a Gold (minimização) |

### Estruturas derivadas

| Onde | Conteúdo | Categoria | Acesso | Retenção proposta |
| --- | --- | --- | --- | --- |
| `quarentena.registro.registro` e `registro_original` | Cópia do registro rejeitado, que pode conter dado pessoal | Dado pessoal | dono | 90 dias depois de `reprocessado` ou `descartado` |
| `restrito.usuario_pseudonimo` | `usuario_id` ↔ pseudônimo | Tabela de correspondência: permite reidentificar | dono | Enquanto houver dados pseudonimizados |
| `gold.dim_usuario.nome_mascarado` | Primeiro nome + inicial | Dado pessoal mascarado | consumo | Igual à Gold |
| `.env` (`LGPD_SALT`, `LGPD_CHAVE_PSEUDONIMO`) | Segredos da proteção | Segredo | quem opera o projeto | Trocar ao suspeitar de vazamento (exige reprocessar a Silver) |

## Minimização na Gold (RF32)

A Gold não tem nome, e-mail, CPF, telefone, data de nascimento, cidade nem `usuario_id`. A pessoa aparece como:

- `usuario_pseudo`, o pseudônimo do usuário mestre;
- `nome_mascarado`, só para rotular listas;
- atributos agregáveis: faixa etária, UF e data de cadastro.

O papel `consumo`, usado pelo Superset e pelo SQL Lab, só lê `gold`, `qualidade` e `controle`, então o dashboard não tem como exibir o valor original. A demonstração está em [`tecnicas_de_protecao.md`](tecnicas_de_protecao.md).

## Casos de atenção

- **Adolescente (`L2-U09`, usuário 177, 14 anos).** O registro é aceito, e a faixa `0-17` fica marcada com `LGPD.DadoDeCriancaOuAdolescente`. Numa plataforma real, isso exigiria consentimento específico de um dos pais ou responsável (art. 14, § 1º). Aqui o dado é fictício.
- **Texto livre (`L2-K04`, `L2-K05`).** O e-mail e o telefone digitados nos comentários são anonimizados na Silver. O texto original continua só na Bronze.
- **Quarentena.** Guarda o registro original para permitir a correção, então herda a classificação de dado pessoal da fonte.
