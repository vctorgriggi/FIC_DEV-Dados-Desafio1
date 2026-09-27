#!/bin/bash
# Gera, dentro do container, um arquivo de ambiente do Hop com os segredos do .env.
# O Hop nao le variaveis de ambiente do sistema; assim as conexoes usam ${PG_PASSWORD} etc.
# sem que a senha fique gravada no projeto (hop/) nem apareca no log.
set -euo pipefail

destino=/tmp/hop-segredos.json

json() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }

variavel() {  # nome_no_hop valor
    printf '    { "name" : "%s", "value" : "%s", "description" : "gerado de .env" }' "$1" "$(json "$2")"
}

{
    echo '{'
    echo '  "variables" : ['
    variavel PG_DATABASE "${POSTGRES_DB:-}";              echo ','
    variavel PG_USER "${POSTGRES_USER:-}";                echo ','
    variavel PG_PASSWORD "${POSTGRES_PASSWORD:-}";        echo ','
    variavel MONGO_USER "${MONGO_USER:-}";                echo ','
    variavel MONGO_PASSWORD "${MONGO_PASSWORD:-}";        echo ','
    variavel LGPD_SALT "${LGPD_SALT:-}";                  echo ','
    variavel LGPD_CHAVE_PSEUDONIMO "${LGPD_CHAVE_PSEUDONIMO:-}"
    echo
    echo '  ]'
    echo '}'
} > "$destino"
chmod 600 "$destino"
