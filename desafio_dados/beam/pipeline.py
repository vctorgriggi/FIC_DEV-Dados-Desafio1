"""RF25: engajamento mensal por categoria com Apache Beam, lendo o Parquet da Silver (RF24).

    docker compose run --rm beam beam/pipeline.py --runner direct
    docker compose --profile beam up -d
    docker compose run --rm beam beam/pipeline.py --runner spark
    docker compose run --rm beam beam/pipeline.py --runner spark --entrada volume   # 200 mil interacoes

Regra de negocio, identica a gold.kpi_engajamento_mensal (sql/camada_gold.sql): por mes e categoria
do conteudo, quantas interacoes, quantas pessoas ativas (usuario mestre, RF30), quantas conclusoes e
quantos minutos consumidos. O resultado e gravado em Parquet e a execucao e registrada em
beam/evidencias/rf25_<entrada>_<runner>.json (volume, tempo, configuracao e conferencias).
"""
import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import apache_beam as beam
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import yaml
from apache_beam.options.pipeline_options import PipelineOptions

RAIZ = Path(__file__).resolve().parent.parent

ENTRADAS = {  # interacoes; conteudo e correspondencia de usuarios vem sempre da Silver exportada
    "silver": RAIZ / "dados/silver/interacao",
    "volume": RAIZ / "dados/volume/parquet/interacao",
}
CONTEUDO = RAIZ / "dados/silver/conteudo.parquet"
CORRESPONDENCIA = RAIZ / "dados/silver/usuario_correspondencia.parquet"
SAIDA = RAIZ / "dados/gold/engajamento_mensal_beam"
EVIDENCIAS = RAIZ / "beam/evidencias"

RESULTADO = pa.schema([
    ("mes", pa.string()), ("categoria", pa.string()), ("interacoes", pa.int64()),
    ("pessoas_ativas", pa.int64()), ("conclusoes", pa.int64()), ("minutos_consumidos", pa.int64()),
])


def somar(valores):
    """Soma elemento a elemento de tuplas (interacoes, conclusoes, minutos); associativa."""
    return tuple(map(sum, zip(*valores))) if valores else (0, 0, 0)


def enriquecer(r, categorias, mestres):
    return {
        "chave": (r["data_hora"].strftime("%Y-%m"), categorias[r["conteudo_id"]]),
        "pessoa": mestres.get(r["usuario_id"], r["usuario_id"]),
        "conclusao": int(r["tipo_interacao"] == "conclusão"),
        "minutos": r["tempo_consumido"] or 0,
    }


def formatar(elemento):
    (mes, categoria), grupos = elemento
    interacoes, conclusoes, minutos = grupos["totais"][0]
    return {"mes": mes, "categoria": categoria, "interacoes": interacoes,
            "pessoas_ativas": sum(grupos["pessoas"]), "conclusoes": conclusoes, "minutos_consumidos": minutos}


class EngajamentoMensal(beam.PTransform):
    """Regra de negocio: por (mes, categoria), interacoes, pessoas ativas, conclusoes e minutos.

    Recebe interacoes (dicts com usuario_id, conteudo_id, tipo_interacao, data_hora, tempo_consumido)
    e dois side inputs: conteudo_id -> categoria e usuario_id -> usuario_mestre_id.
    """

    def __init__(self, categorias, mestres):
        super().__init__()
        self.categorias, self.mestres = categorias, mestres

    def expand(self, interacoes):
        eventos = interacoes | "mes, categoria e pessoa" >> beam.Map(enriquecer, self.categorias, self.mestres)
        totais = (
            eventos
            | "totais por chave" >> beam.Map(lambda e: (e["chave"], (1, e["conclusao"], e["minutos"])))
            | "somar" >> beam.CombinePerKey(somar)
        )
        pessoas = (
            eventos
            | "pessoa por chave" >> beam.Map(lambda e: (e["chave"], e["pessoa"]))
            | "pessoas distintas" >> beam.Distinct()
            | "contar pessoas" >> beam.Map(lambda kv: (kv[0], 1))
            | "pessoas por chave" >> beam.CombinePerKey(sum)
        )
        return (
            {"totais": totais, "pessoas": pessoas}
            | "juntar" >> beam.CoGroupByKey()
            | "formatar" >> beam.Map(formatar)
        )


def construir(p, entrada: Path, destino: Path):
    categorias = beam.pvalue.AsDict(
        p | "ler conteudo" >> beam.io.ReadFromParquet(str(CONTEUDO), columns=["conteudo_id", "categoria"])
          | "conteudo -> categoria" >> beam.Map(lambda r: (r["conteudo_id"], r["categoria"])))
    mestres = beam.pvalue.AsDict(
        p | "ler correspondencia" >> beam.io.ReadFromParquet(str(CORRESPONDENCIA),
                                                             columns=["usuario_id", "usuario_mestre_id"])
          | "usuario -> mestre" >> beam.Map(lambda r: (r["usuario_id"], r["usuario_mestre_id"])))
    (
        p
        | "ler interacoes" >> beam.io.ReadFromParquet(
            str(entrada / "*" / "*.parquet"),
            columns=["usuario_id", "conteudo_id", "tipo_interacao", "data_hora", "tempo_consumido"])
        | "engajamento mensal" >> EngajamentoMensal(categorias, mestres)
        | "gravar parquet" >> beam.io.WriteToParquet(str(destino / "engajamento"), RESULTADO,
                                                     file_name_suffix=".parquet")
    )


def ler_resultado(pasta: Path) -> list[dict]:
    if not pasta.exists():
        return []
    linhas = pq.read_table(pasta).to_pylist()
    return sorted(linhas, key=lambda r: (r["mes"], r["categoria"]))


def cluster_spark() -> dict:
    """Configuracao efetiva do cluster, lida da API do Spark master."""
    try:
        with urllib.request.urlopen("http://spark-master:8080/json/", timeout=5) as r:
            m = json.load(r)
    except OSError as e:
        return {"erro": f"API do Spark master indisponivel: {e}"}
    return {"master": m.get("url"), "workers_ativos": m.get("aliveworkers"),
            "cores": m.get("cores"), "memoria_mb": m.get("memory")}


def conferir_gold(resultado: list[dict]) -> dict:
    """Compara com gold.kpi_engajamento_mensal: mesma regra, calculada em SQL."""
    import psycopg
    try:
        with psycopg.connect(host=os.environ.get("POSTGRES_HOST", "postgres"), dbname=os.environ["POSTGRES_DB"],
                             user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"]) as conn:
            gold = conn.execute("""SELECT mes, categoria, interacoes, pessoas_ativas, conclusoes, minutos_consumidos
                                     FROM gold.kpi_engajamento_mensal ORDER BY mes, categoria""").fetchall()
    except psycopg.Error as e:
        return {"conferido": False, "motivo": str(e).splitlines()[0]}
    colunas = [c.name for c in RESULTADO]
    gold = [dict(zip(colunas, (str(v) if isinstance(v, str) else int(v) for v in linha))) for linha in gold]
    return {"conferido": True, "igual": gold == resultado, "grupos_gold": len(gold)}


def main() -> None:
    args = argparse.ArgumentParser()
    args.add_argument("--runner", choices=["direct", "spark"], default="direct")
    args.add_argument("--entrada", choices=list(ENTRADAS), default="silver")
    a = args.parse_args()

    with open(RAIZ / "config.yaml", encoding="utf-8") as f:
        opcoes = yaml.safe_load(f)["beam"]["runners"][a.runner]
    entrada = ENTRADAS[a.entrada]
    if not entrada.exists():
        raise SystemExit(f"{entrada} nao existe: rode antes beam/exportar_silver.py"
                         + (" --volume" if a.entrada == "volume" else ""))
    registros = ds.dataset(entrada, format="parquet", partitioning="hive").count_rows()
    destino = SAIDA / f"{a.entrada}_{a.runner}"
    for antigo in destino.glob("engajamento*"):
        antigo.unlink()

    inicio = time.perf_counter()
    with beam.Pipeline(options=PipelineOptions(opcoes)) as p:
        construir(p, entrada, destino)
    duracao = round(time.perf_counter() - inicio, 2)

    resultado = ler_resultado(destino)
    total = sum(r["interacoes"] for r in resultado)
    if total != registros:
        raise SystemExit(f"total agregado {total} difere das {registros} interacoes lidas")
    outro = "spark" if a.runner == "direct" else "direct"
    resultado_outro = ler_resultado(SAIDA / f"{a.entrada}_{outro}")

    evidencia = {
        "executado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runner": a.runner,
        "opcoes": opcoes,
        "beam": beam.__version__,
        "cluster": cluster_spark() if a.runner == "spark" else {"modo": "DirectRunner, processo local"},
        "entrada": str(entrada.relative_to(RAIZ)),
        "interacoes_lidas": registros,
        "grupos_mes_categoria": len(resultado),
        "tempo_s": duracao,
        "saida": str(destino.relative_to(RAIZ)),
        f"igual_ao_{outro}": (resultado == resultado_outro) if resultado_outro else "ainda nao executado",
        "igual_a_gold": conferir_gold(resultado) if a.entrada == "silver" else "nao se aplica (volume sintetico)",
    }
    EVIDENCIAS.mkdir(parents=True, exist_ok=True)
    arquivo = EVIDENCIAS / f"rf25_{a.entrada}_{a.runner}.json"
    arquivo.write_text(json.dumps(evidencia, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"runner={a.runner} entrada={a.entrada} interacoes={registros} grupos={len(resultado)} tempo={duracao}s")
    print(f"igual_ao_{outro}={evidencia[f'igual_ao_{outro}']} igual_a_gold={evidencia['igual_a_gold']}")
    print(f"evidencia em {arquivo.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
