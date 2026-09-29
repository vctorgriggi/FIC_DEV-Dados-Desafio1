# Executor dos scripts Python do Desafio 2 (Parquet e Beam): a imagem oficial do SDK, que e a mesma
# do worker pool (versao identica do Beam nos dois lados), mais o driver do PostgreSQL.
FROM apache/beam_python3.12_sdk:2.77.0

COPY requirements-desafio2.txt /tmp/requirements-desafio2.txt
RUN pip install --no-cache-dir -r /tmp/requirements-desafio2.txt
