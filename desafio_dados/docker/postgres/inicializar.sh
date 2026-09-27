#!/bin/bash
# Desafio 2: roda a cada "docker compose up" (servico db-init) e e idempotente,
# entao tambem atualiza volumes criados no Desafio 1.
#   - bancos e papeis do OpenMetadata e do Airflow (perfil governanca)
#   - schemas das camadas e papel de consumo (sql/camadas.sql)
set -euo pipefail

export PGHOST=postgres PGUSER="$POSTGRES_USER" PGPASSWORD="$POSTGRES_PASSWORD"
# padroes iguais aos do .env.example, para um .env antigo do Desafio 1 continuar funcionando
: "${OM_DB_USER:=openmetadata}" "${OM_DB_PASSWORD:=openmetadata}"
: "${AIRFLOW_DB_USER:=airflow}" "${AIRFLOW_DB_PASSWORD:=airflow}"
: "${CONSUMO_DB_USER:=consumo}" "${CONSUMO_DB_PASSWORD:=consumo}"
PSQL=(psql -v ON_ERROR_STOP=1 -q)

# cria (ou atualiza a senha de) um papel dono de um banco proprio
papel_e_banco() {
    local banco="$1" usuario="$2" senha="$3"
    "${PSQL[@]}" -d "$POSTGRES_DB" -v u="$usuario" -v s="$senha" -v b="$banco" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'u', :'s')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'u') \gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'u', :'s') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'b', :'u')
 WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'b') \gexec
SQL
}

papel_e_banco openmetadata_db "$OM_DB_USER" "$OM_DB_PASSWORD"
papel_e_banco airflow_db "$AIRFLOW_DB_USER" "$AIRFLOW_DB_PASSWORD"

"${PSQL[@]}" -d "$POSTGRES_DB" \
    -v consumo_usuario="$CONSUMO_DB_USER" -v consumo_senha="$CONSUMO_DB_PASSWORD" \
    -f /sql/camadas.sql

echo "db-init: bancos auxiliares e camadas do Desafio 2 prontos"
