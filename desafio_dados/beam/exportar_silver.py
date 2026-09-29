"""RF24: exporta a Silver para Parquet particionado e compara com CSV e JSON no mesmo recorte.

    docker compose run --rm beam beam/exportar_silver.py            # Silver -> dados/silver/ + medicao
    docker compose run --rm beam beam/exportar_silver.py --volume   # tambem o experimento de escala

O experimento de escala usa dados/volume/interacoes.json, gerado por
"docker compose run --rm beam -m ferramentas.gerar_dados --volume 200000".
Resultados em beam/evidencias/rf24_medicoes.json; analise em documentacao/parquet_beam.md.
"""
import argparse
import json
import os
import shutil
import statistics
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.dataset as ds
import pyarrow.json as pajson
import pyarrow.parquet as pq
import yaml

RAIZ = Path(__file__).resolve().parent.parent

# tipos da silver.interacao preservados; "mes" (AAAA-MM) e a coluna de particao
INTERACAO = pa.schema([
    ("interacao_id", pa.int64()),
    ("usuario_id", pa.int32()),
    ("conteudo_id", pa.int32()),
    ("tipo_interacao", pa.string()),
    ("data_hora", pa.timestamp("us")),
    ("tempo_consumido", pa.int32()),
    ("percentual_conclusao", pa.decimal128(5, 2)),
    ("avaliacao_atribuida", pa.int16()),
    ("_execucao_id", pa.string()),
    ("_origem", pa.string()),
    ("_ingerido_em", pa.timestamp("us", tz="UTC")),
    ("mes", pa.string()),
])
CONTEUDO = pa.schema([
    ("conteudo_id", pa.int32()), ("titulo", pa.string()), ("tipo", pa.string()), ("categoria", pa.string()),
    ("nivel", pa.string()), ("carga_horaria_min", pa.int32()), ("data_publicacao", pa.date32()),
    ("_execucao_id", pa.string()), ("_origem", pa.string()), ("_ingerido_em", pa.timestamp("us", tz="UTC")),
])
CORRESPONDENCIA = pa.schema([
    ("usuario_id", pa.int32()), ("usuario_mestre_id", pa.int32()), ("regra", pa.string()),
    ("_execucao_id", pa.string()),
])


def configuracao() -> dict:
    with open(RAIZ / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["parquet"]


def consultar(sql: str, esquema: pa.Schema) -> pa.Table:
    with psycopg.connect(host=os.environ.get("POSTGRES_HOST", "postgres"), dbname=os.environ["POSTGRES_DB"],
                         user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"]) as conn:
        linhas = conn.execute(sql).fetchall()
    colunas = list(zip(*linhas)) if linhas else [[] for _ in esquema]
    return pa.Table.from_arrays([pa.array(c, type=campo.type) for c, campo in zip(colunas, esquema)], schema=esquema)


def gravar_particionado(tabela: pa.Table, destino: Path, particao: str) -> None:
    shutil.rmtree(destino, ignore_errors=True)
    ds.write_dataset(tabela, destino, format="parquet",
                     partitioning=ds.partitioning(pa.schema([(particao, pa.string())]), flavor="hive"),
                     existing_data_behavior="delete_matching")


def gravar_comparacao(tabela: pa.Table, pasta: Path) -> dict:
    """Mesmo recorte em CSV e JSON (uma linha por registro), para a comparacao com o Parquet."""
    pasta.mkdir(parents=True, exist_ok=True)
    csv_ = pasta / "interacao.csv"
    pacsv.write_csv(tabela, csv_)
    jsonl = pasta / "interacao.jsonl"
    with open(jsonl, "w", encoding="utf-8") as f:
        for linha in tabela.to_pylist():
            f.write(json.dumps(linha, ensure_ascii=False, default=str) + "\n")
    return {"csv": csv_, "json": jsonl}


def tamanho(caminho: Path) -> tuple[int, int]:
    arquivos = [p for p in ([caminho] if caminho.is_file() else caminho.rglob("*")) if p.is_file()]
    return sum(p.stat().st_size for p in arquivos), len(arquivos)


def cronometrar(funcao, repeticoes: int) -> dict:
    funcao()  # aquecimento descartado: carga de bibliotecas e cache do sistema de arquivos
    tempos = []
    for _ in range(repeticoes):
        inicio = time.perf_counter()
        resultado = funcao()
        tempos.append((time.perf_counter() - inicio) * 1000)
    return {"mediana_ms": round(statistics.median(tempos), 2), "minimo_ms": round(min(tempos), 2),
            "linhas": resultado.num_rows}


def medir(nome: str, parquet_dir: Path, arquivos: dict, mes: str, repeticoes: int, particao: str) -> dict:
    colunas = ["usuario_id", "tipo_interacao", "tempo_consumido"]
    leitores = {
        "parquet": (lambda: ds.dataset(parquet_dir, format="parquet", partitioning="hive").to_table(),
                    lambda: ds.dataset(parquet_dir, format="parquet", partitioning="hive")
                              .to_table(columns=colunas, filter=ds.field(particao) == mes)),
        "csv": (lambda: pacsv.read_csv(arquivos["csv"]),
                lambda: pacsv.read_csv(arquivos["csv"]).filter(ds.field(particao) == mes).select(colunas)),
        "json": (lambda: pajson.read_json(arquivos["json"]),
                 lambda: pajson.read_json(arquivos["json"]).filter(ds.field(particao) == mes).select(colunas)),
    }
    caminhos = {"parquet": parquet_dir, "csv": arquivos["csv"], "json": arquivos["json"]}
    formatos = {}
    for formato, (completa, seletiva) in leitores.items():
        tabela = completa()
        bytes_, n_arquivos = tamanho(caminhos[formato])
        formatos[formato] = {
            "bytes": bytes_,
            "arquivos": n_arquivos,
            "leitura_completa": cronometrar(completa, repeticoes),
            "consulta_seletiva": cronometrar(seletiva, repeticoes),
            # prova de que e o mesmo recorte em todos os formatos
            "linhas": tabela.num_rows,
            "soma_interacao_id": pc.sum(tabela["interacao_id"]).as_py(),
            "tipos_lidos": {c.name: str(c.type) for c in tabela.schema
                            if c.name in ("data_hora", "percentual_conclusao", "avaliacao_atribuida", "_ingerido_em")},
        }
    linhas = {f["linhas"] for f in formatos.values()}
    somas = {f["soma_interacao_id"] for f in formatos.values()}
    if len(linhas) != 1 or len(somas) != 1:
        raise SystemExit(f"{nome}: os formatos nao tem o mesmo recorte ({linhas}, {somas})")
    return {"experimento": nome, "linhas": linhas.pop(), "consulta_seletiva": f"{particao} = {mes}, colunas {colunas}",
            "repeticoes": repeticoes, "formatos": formatos}


def exportar_silver(cfg: dict) -> tuple[pa.Table, str]:
    destino = RAIZ / cfg["destino"]
    interacao = consultar(f"""
        SELECT interacao_id, usuario_id, conteudo_id, tipo_interacao, data_hora, tempo_consumido,
               percentual_conclusao, avaliacao_atribuida, _execucao_id, _origem, _ingerido_em,
               to_char(data_hora, 'YYYY-MM') AS {cfg['particao']}
          FROM silver.interacao ORDER BY interacao_id""", INTERACAO)
    if interacao.num_rows == 0:
        raise SystemExit("silver.interacao vazia: rode antes o workflow principal do Hop")
    conteudo = consultar("""
        SELECT conteudo_id, titulo, tipo, categoria, nivel, carga_horaria_min, data_publicacao,
               _execucao_id, _origem, _ingerido_em FROM silver.conteudo ORDER BY conteudo_id""", CONTEUDO)
    correspondencia = consultar("""
        SELECT usuario_id, usuario_mestre_id, regra, _execucao_id
          FROM silver.usuario_correspondencia ORDER BY usuario_id""", CORRESPONDENCIA)

    gravar_particionado(interacao, destino / "interacao", cfg["particao"])
    pq.write_table(conteudo, destino / "conteudo.parquet")
    pq.write_table(correspondencia, destino / "usuario_correspondencia.parquet")

    execucao = sorted(set(interacao["_execucao_id"].to_pylist()))
    manifesto = {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "execucao_silver": execucao,
        "tabelas": {"interacao": interacao.num_rows, "conteudo": conteudo.num_rows,
                    "usuario_correspondencia": correspondencia.num_rows},
        "particao": cfg["particao"],
        "particoes": sorted(set(interacao[cfg["particao"]].to_pylist())),
        "esquema_interacao": {c.name: str(c.type) for c in INTERACAO},
    }
    (destino / "_manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
    return interacao, ",".join(execucao)


def tabela_volume(cfg: dict) -> pa.Table:
    origem = RAIZ / cfg["volume"] / "interacoes.json"
    if not origem.exists():
        raise SystemExit(f"{origem} nao existe: rode docker compose run --rm beam -m ferramentas.gerar_dados --volume 200000")
    registros = json.loads(origem.read_text(encoding="utf-8"))
    agora = datetime.now(timezone.utc)
    colunas = {c: [] for c in INTERACAO.names}
    for i, r in enumerate(registros, start=1):
        data_hora = datetime.fromisoformat(r["data_hora"])
        colunas["interacao_id"].append(i)
        colunas["usuario_id"].append(r["usuario_id"])
        colunas["conteudo_id"].append(r["conteudo_id"])
        colunas["tipo_interacao"].append(r["tipo_interacao"])
        colunas["data_hora"].append(data_hora)
        colunas["tempo_consumido"].append(r["tempo_consumido"])
        colunas["percentual_conclusao"].append(None if r["percentual_conclusao"] is None
                                               else round(Decimal(str(r["percentual_conclusao"])), 2))
        colunas["avaliacao_atribuida"].append(r["avaliacao_atribuida"])
        colunas["_execucao_id"].append("volume-sintetico")
        colunas["_origem"].append(f"{cfg['volume']}/interacoes.json")
        colunas["_ingerido_em"].append(agora)
        colunas["mes"].append(data_hora.strftime("%Y-%m"))
    return pa.Table.from_pydict(colunas, schema=INTERACAO)


def main() -> None:
    args = argparse.ArgumentParser()
    args.add_argument("--volume", action="store_true", help="tambem mede o volume sintetico de dados/volume/")
    volume = args.parse_args().volume
    cfg = configuracao()

    interacao, execucao = exportar_silver(cfg)
    print(f"silver exportada: {interacao.num_rows} interacoes em {cfg['destino']}/interacao "
          f"(particionado por {cfg['particao']}), execucao {execucao}")
    arquivos = gravar_comparacao(interacao, RAIZ / cfg["comparacao"])
    experimentos = [medir("silver", RAIZ / cfg["destino"] / "interacao", arquivos, cfg["mes_consulta"],
                          cfg["repeticoes"], cfg["particao"])]

    if volume:
        tabela = tabela_volume(cfg)
        base = RAIZ / cfg["volume"]
        gravar_particionado(tabela, base / "parquet" / "interacao", cfg["particao"])
        arquivos = gravar_comparacao(tabela, base / "comparacao")
        experimentos.append(medir("volume sintetico", base / "parquet" / "interacao", arquivos,
                                  cfg["mes_consulta"], cfg["repeticoes"], cfg["particao"]))

    evidencia = RAIZ / "beam" / "evidencias" / "rf24_medicoes.json"
    evidencia.parent.mkdir(parents=True, exist_ok=True)
    evidencia.write_text(json.dumps({"gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                     "execucao_silver": execucao, "leitor": f"pyarrow {pa.__version__}",
                                     "experimentos": experimentos}, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    for e in experimentos:
        print(f"\n{e['experimento']}: {e['linhas']} linhas, mediana de {e['repeticoes']} leituras")
        print(f"{'formato':8} {'tamanho':>12} {'arquivos':>9} {'completa':>12} {'seletiva':>12}")
        for formato, m in e["formatos"].items():
            print(f"{formato:8} {m['bytes'] / 1024:>9.1f} KB {m['arquivos']:>9} "
                  f"{m['leitura_completa']['mediana_ms']:>9.2f} ms {m['consulta_seletiva']['mediana_ms']:>9.2f} ms")
    print(f"\nmedicoes em {evidencia.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
