"""Verificacao da infraestrutura do Beam: mesma regra nos dois runners, com saida em Parquet.

Nao e o pipeline do RF25 (beam/pipeline.py); so prova que o ambiente funciona.

    docker compose run --rm beam beam/verificar_runtime.py --runner direct
    docker compose --profile beam up -d
    docker compose run --rm beam beam/verificar_runtime.py --runner spark
"""
import argparse
import json
import shutil
import time
from pathlib import Path

import apache_beam as beam
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from apache_beam.options.pipeline_options import PipelineOptions

RAIZ = Path(__file__).resolve().parent.parent
ENTRADA = RAIZ / "dados/brutos/interacoes.json"
SAIDA = RAIZ / "dados/verificacao_beam"
ESQUEMA = pa.schema([("tipo_interacao", pa.string()), ("quantidade", pa.int64())])


def main() -> None:
    args = argparse.ArgumentParser()
    args.add_argument("--runner", choices=["direct", "spark"], default="direct")
    runner = args.parse_args().runner

    with open(RAIZ / "config.yaml", encoding="utf-8") as f:
        opcoes = yaml.safe_load(f)["beam"]["runners"][runner]

    registros = json.loads(ENTRADA.read_text(encoding="utf-8"))
    destino = SAIDA / runner
    shutil.rmtree(destino, ignore_errors=True)

    inicio = time.perf_counter()
    with beam.Pipeline(options=PipelineOptions(opcoes)) as p:
        (
            p
            | "ler" >> beam.Create(registros)
            | "tipo" >> beam.Map(lambda r: (r["tipo_interacao"], 1))
            | "contar" >> beam.CombinePerKey(sum)
            | "linha" >> beam.Map(lambda kv: {"tipo_interacao": kv[0], "quantidade": kv[1]})
            | "gravar" >> beam.io.WriteToParquet(str(destino / "contagem"), ESQUEMA, file_name_suffix=".parquet")
        )
    duracao = time.perf_counter() - inicio

    resultado = pq.read_table(destino).sort_by("tipo_interacao").to_pylist()
    for linha in resultado:
        print(f"  {linha['tipo_interacao']:<18} {linha['quantidade']:>5}")
    total = sum(linha["quantidade"] for linha in resultado)
    print(f"runner={runner} registros={len(registros)} total_agregado={total} tempo={duracao:.1f}s saida={destino}")
    if total != len(registros):
        raise SystemExit("total agregado difere da entrada")


if __name__ == "__main__":
    main()
