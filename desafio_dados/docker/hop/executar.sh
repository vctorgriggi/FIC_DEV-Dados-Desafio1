#!/bin/bash
# Executa um pipeline (.hpl) ou workflow (.hwf) do projeto Hop no container.
#   docker compose run --rm hop pipelines/verificar_ambiente.hpl
#   docker compose run --rm hop workflows/principal.hwf EXECUCAO_ID=abc MODO=agendado
# Parametros sao NOME=valor separados por espaco (valores nao podem conter virgula).
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "uso: docker compose run --rm hop <arquivo relativo a hop/> [NOME=valor ...]" >&2
    exit 2
fi

bash /app/docker/hop/segredos.sh

export HOP_FILE_PATH="${HOP_PROJECT_FOLDER}/$1"
shift
HOP_RUN_PARAMETERS="$(IFS=,; echo "$*")"
export HOP_RUN_PARAMETERS

exec /bin/bash /opt/hop/run.sh
