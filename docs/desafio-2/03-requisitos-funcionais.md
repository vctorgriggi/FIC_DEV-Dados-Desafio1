# 7. Requisitos funcionais obrigatórios

Os requisitos desta seção ampliam os requisitos do Desafio Prático 1, numerado de RF01 à RF14. Cada requisito deverá ser implementado, testado e demonstrado pela equipe.

## RF15 — Continuidade e configuração da solução

O sistema deverá:

- reutilizar os dados, esquemas e resultados válidos do Desafio 1;
- manter parâmetros de conexão, caminhos, nomes de ambientes e opções de execução fora dos pipelines;
- separar senhas e segredos do código-fonte e dos arquivos versionados;
- permitir executar o fluxo completo e também suas principais etapas isoladamente;
- registrar as versões do Apache Hop, do runtime distribuído, do Superset e do OpenMetadata utilizados.

## RF16 — Storytelling executivo com dados

O sistema deverá:

- definir uma pergunta decisória central relacionada ao catálogo, ao engajamento ou às recomendações;
- organizar a narrativa em contexto, evidência, descoberta e ação recomendada;
- apresentar pelo menos três visualizações em sequência lógica;
- incluir títulos informativos, anotações e texto interpretativo;
- distinguir fatos observados, hipóteses e recomendações.

## RF17 — SQL Lab e conjuntos de dados virtuais

O sistema deverá:

- criar pelo menos três consultas no SQL Lab;
- utilizar junção, agregação, expressão condicional e função de data;
- salvar pelo menos dois conjuntos de dados virtuais para uso no dashboard;
- documentar a finalidade e os campos calculados de cada consulta;
- garantir que os resultados possam ser reproduzidos a partir da camada Gold.

## RF18 — Filtros cruzados e alertas no Superset

O sistema deverá:

- habilitar interação entre pelo menos duas visualizações por filtro cruzado;
- disponibilizar filtros globais de período e de pelo menos uma dimensão de negócio;
- configurar um alerta ou relatório associado a um limite mensurável;
- registrar destinatário fictício, periodicidade, condição e ação esperada;
- demonstrar o funcionamento ou, quando o envio não estiver disponível no ambiente, a avaliação comprovada da condição de disparo.

## RF19 — Definição da arquitetura ETL ou ELT

O sistema deverá:

- representar o fluxo desde as fontes até o consumo;
- identificar em que ponto ocorrem extração, transformação e carga;
- classificar o fluxo principal como ETL, ELT ou arquitetura híbrida;
- justificar a escolha considerando custo, governança, desempenho e reprocessamento;
- explicar as limitações da solução anterior baseada apenas em scripts isolados.

## RF20 — Pipeline Bronze no Apache Hop

O sistema deverá:

- criar um projeto e um ambiente no Apache Hop;
- definir metadados reutilizáveis para conexões e variáveis;
- ingerir pelo menos um arquivo CSV, um arquivo JSON e um banco de dados como destino;
- preservar os dados sem transformações destrutivas;
- acrescentar campos de auditoria com origem, data e hora da ingestão e identificador da execução;
- gravar a camada Bronze em diretório ou esquema próprio.

## RF21 — Pipeline Silver e padronização

O sistema deverá:

- padronizar nomes de campos, tipos, datas, categorias e valores textuais;
- tratar valores ausentes conforme regras documentadas;
- identificar duplicidades por chaves de negócio;
- validar referências entre usuários, conteúdos e interações;
- separar registros aprovados dos registros em quarentena;
- gravar a camada Silver em diretório ou esquema próprio.

## RF22 — Workflow e orquestração automatizada

O sistema deverá:

- criar um workflow que execute Bronze, Silver, qualidade, Gold e publicação de metadados na ordem correta;
- interromper etapas dependentes quando ocorrer falha crítica;
- registrar início, término, duração e resultado de cada etapa;
- permitir execução manual e por agendamento;
- retornar um estado final de sucesso, sucesso com ressalvas ou falha.

## RF23 — Tratamento de erros, quarentena e recuperação

O sistema deverá:

- registrar o identificador do registro, a origem, a regra violada, a data e a mensagem do erro;
- encaminhar registros inválidos para uma área de quarentena sem encerrar todo o processamento;
- impedir cargas parciais inconsistentes na camada de destino;
- permitir corrigir e reprocessar os registros da quarentena;
- demonstrar pelo menos uma falha de arquivo, uma falha de regra e uma falha de conexão simulada.

## RF24 — Formato Parquet e particionamento

O sistema deverá:

- exportar um conjunto relevante da camada Silver para Parquet;
- escolher e justificar uma estratégia de particionamento;
- comparar tamanho e tempo de leitura do Parquet com CSV ou JSON usando o mesmo recorte de dados;
- preservar esquema, tipos e campos de auditoria;
- registrar as medições e as limitações do experimento.

## RF25 — Processamento distribuído com Apache Beam

O sistema deverá:

- implementar um pipeline Apache Beam para uma agregação ou transformação relevante;
- executá-lo com DirectRunner e com um runtime Spark
- ler ou gravar dados em formato Parquet;
- produzir a mesma regra de negócio nos dois runtimes;
- registrar volume processado, tempo de execução e configuração utilizada;

## RF26 — Camada Gold para consumo analítico

O sistema deverá:

- produzir tabelas ou visões orientadas às perguntas de negócio;
- consolidar dimensões e medidas necessárias aos KPIs;
- evitar que o dashboard consulte diretamente a camada Bronze;
- manter chaves, granularidade e regras de cálculo documentadas;
- disponibilizar a camada Gold ao SQL Lab e ao Apache Superset.

## RF27 — Implantação e integração do OpenMetadata

O sistema deverá:

- implantar ou acessar uma instância funcional do OpenMetadata;
- conectar pelo menos o PostgreSQL e registrar os demais ativos relevantes;
- executar a ingestão de metadados técnicos;
- atribuir proprietário e descrição aos principais ativos;
- explicar quais controles evitam que o ambiente se transforme em um Data Swamp.

## RF28 — Catálogo, classificação e glossário de negócio

O sistema deverá:

- catalogar as tabelas ou visões das camadas Silver e Gold;
- criar pelo menos quatro termos de negócio, incluindo usuário ativo, taxa de conclusão e conversão de recomendação;
- definir cada termo, sua regra de cálculo e seu responsável;
- associar os termos aos ativos e campos correspondentes;
- aplicar classificações técnicas ou de sensibilidade aos campos relevantes.

## RF29 — Linhagem de dados

O sistema deverá:

- representar a linhagem entre fonte, Bronze, Silver, Gold e dashboard;
- incluir pelo menos um KPI e um conjunto de dados virtual do SQL Lab;
- identificar as principais transformações realizadas;
- demonstrar como localizar a origem de um valor exibido no dashboard;
- registrar manualmente as relações que não puderem ser extraídas automaticamente.

## RF30 — Dados mestres

O sistema deverá:

- selecionar pelo menos uma entidade mestre, como conteúdo, usuário ou categoria;
- definir chave de negócio, atributos essenciais e fonte de referência;
- estabelecer regras de correspondência, deduplicação e sobrevivência;
- gerar um identificador mestre ou tabela de correspondência;
- demonstrar o tratamento de dois registros conflitantes.

## RF31 — Qualidade de dados

O sistema deverá:

- implementar no mínimo 5 testes distribuídos entre completude, validade, unicidade, consistência e integridade referencial;
- definir fórmula, limite aceitável, severidade e ação para cada teste;
- armazenar o resultado por execução e por fonte;
- impedir a publicação na camada Gold quando uma regra crítica falhar;
- apresentar a evolução de pelo menos duas métricas de qualidade.

## RF32 — Inventário de dados pessoais e LGPD

O sistema deverá:

- identificar os campos que contêm dados pessoais, pessoais sensíveis ou identificadores indiretos;
- registrar finalidade, necessidade, acesso e tempo de retenção propostos para cada campo;
- classificar os ativos correspondentes no catálogo;
- minimizar o uso de dados pessoais na camada Gold;
- não utilizar dados pessoais reais no desafio.

## RF33 — Mascaramento, pseudonimização e hashing

O sistema deverá:

- aplicar mascaramento a pelo menos um campo exibido para consumo;
- pseudonimizar um identificador que ainda precise permitir associação controlada;
- aplicar hashing com salt a um campo escolhido para comparação irreversível;
- manter segredos, salts e tabelas de correspondência fora do código e do repositório;
- comparar as duas técnicas e justificar a aplicação de cada uma;
- demonstrar que o dashboard não expõe os valores originais protegidos.

## RF34 — Evidências e critérios de aceite

A equipe deverá apresentar:

- exportações dos pipelines e workflows do Apache Hop;
- amostras das camadas Bronze, Silver e Gold;
- registros de quarentena e reprocessamento;
- execução do pipeline Apache Beam no runtime;
- capturas do catálogo, glossário, classificações e linhagem no OpenMetadata;
- resultado dos testes de qualidade e dos controles de LGPD;
- consultas do SQL Lab, dashboard, filtros cruzados e alerta;
- narrativa executiva e recomendação final.
