import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.io.parquetio import WriteToParquet
import pyarrow as pa
import json

# Definir o schema PyArrow para a saída Parquet
SCHEMA = pa.schema([
    ('tipo_interacao', pa.string()),
    ('total', pa.int64())
])

def run():
    options = PipelineOptions()
    with beam.Pipeline(options=options) as p:
        (
            p
            | "Ler Arquivo JSON" >> beam.io.ReadFromText("dados/volume/interacoes.json")
            | "Parse JSON" >> beam.Map(json.loads)
            | "Desempacotar Lista" >> beam.FlatMap(lambda x: x if isinstance(x, list) else [x])
            | "Mapear Tipo Interacao" >> beam.Map(lambda x: (x.get("tipo_interacao"), 1))
            | "Contar por Tipo" >> beam.CombinePerKey(sum)
            # Converter a tupla (tipo, total) num dicionário compatível com o Schema
            | "Formatar para Dicionario" >> beam.Map(lambda elem: {"tipo_interacao": elem[0], "total": elem[1]})
            # Gravar em formato Parquet
            | "Escrever Parquet" >> WriteToParquet(
                file_path_prefix="dados/saida/resultado_beam",
                schema=SCHEMA,
                file_name_suffix=".parquet"
            )
        )

if __name__ == "__main__":
    run()