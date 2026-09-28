# Experimento e Benchmark — Formato Parquet e Exportações (RF24)

Este documento registra o procedimento realizado para a exportação do conjunto de dados da camada **Silver** nos formatos **Parquet**, **CSV** e **JSON**, além das instruções para reprodução do ambiente, medição de desempenho e justificativa técnica.

---

## 1. Contexto e Objetivos

O objetivo deste experimento é atender ao **RF24**, validando o desempenho, a integridade do esquema e o tamanho em disco dos dados exportados a partir do banco de dados relacional (PostgreSQL - Camada Silver) para os três formatos de arquivos semiestruturados e estruturados.

---

## 2. Como Reproduzir o Ambiente

### Pré-requisitos
* Docker e Docker Compose instalados.
* Python 3.x com ambiente virtual configurado.

### Passos para Execução

1. **Subir os serviços no Docker Compose:**
   ```powershell
   docker compose up -d postgres mongo
   ```

2. **Executar a pipeline de exportação CSV no Apache Hop:**
   ```powershell
   docker compose run --rm hop pipelines/exportar_csv.hpl
   ```

3. **Executar a pipeline de exportação JSON no Apache Hop:**
   ```powershell
   docker compose run --rm hop pipelines/exportar_json.hpl
   ```

4. **Executar a exportação/processamento do formato Parquet:**

   docker compose run --rm hop pipelines/exportar_parquet.hpl                                        

---

## 3. Script para Medição de Desempenho e Tamanho

Para obter os dados exatos de tempo de leitura e tamanho em disco sem distorções, execute o script Python abaixo na raiz do projeto:

cd src
python Medicao.py


## 4. Resultados do Experimento

| Formato | Tamanho em Disco (KB) | Tempo de Leitura Médio (ms) | % do Tamanho em Disco vs CSV | Redução / Economia |
| :--- | :--- | :--- | :--- | :--- |
| **Parquet** | `32.41` KB | `594.03` ms | **`16,48%`** | **Redução de 83,52%** |
| **CSV** | `196.70` KB | `15.92` ms | `100,00%` (Base) | Baseline |
| **JSON** | `3.89` KB | `11.35` ms | **`1,98%`** *(Lote)* | N/A *(Lote parcial)* |

---

## 5. Análise Técnica e Justificativas

### 5.1. Estratégia de Particionamento
* **Coluna de Partição Escolhida:** `[ex: status / ano_mes]`
* **Justificativa:** A escolha do particionamento baseia-se nas consultas analíticas mais frequentes sobre a camada Silver. Ao particionar por este campo, aproveita-se o recurso de *partition pruning*, no qual as engines de consulta (como DuckDB, Spark ou Athena) leem apenas o subdiretório necessário, reduzindo consideravelmente o I/O de disco.

### 5.2. Preservação de Esquema e Campos de Auditoria
Ao contrário do formato CSV (onde todos os valores são convertidos para texto e necessitam de parsing posterior), o formato **Parquet** preserva nativamente a metadata do esquema:
* Tipos inteiros (`id_interacao`, `id_cliente`) são mantidos como `INT64`.
* Datas e timestamps (`data_interacao`) mantêm o tipo nativo temporal, garantindo a precisão dos campos de auditoria.

### 5.3. Limitações do Experimento
1. **Volume da Amostra e Overhead de Bibliotecas:** Como o volume de dados do teste local é de escala reduzida (~1.300 linhas), o tempo de leitura do Parquet (`~594 ms`) reflete o *overhead* de inicialização e carregamento do engine de leitura (`pyarrow` / `fastparquet`) no Pandas e parsing do *footer* de metadados. Em datasets de grande escala (GBs/TBs), a leitura colunar do Parquet supera drasticamente o CSV ao evitar o parsing completo do arquivo texto.
2. **Exportação Parcial em JSON:** O tamanho reduzido do arquivo `interacoes.json` (`3.89 KB`) decorre da exportação por lotes/blocos do Apache Hop no pipeline de teste, devendo ser desconsiderado para fins de comparação direta de tamanho total.
3. **Ambiente Local:** As medições foram efetuadas em ambiente virtualizado (Docker) em sistema operacional local, sujeitas ao sistema de cache de leitura do SO.