"""Camada de consumo no Superset (RF16, RF17, RF18): conexao, datasets, graficos, dashboards e alerta.

    docker compose up -d                                             # Superset (e a Gold ja publicada)
    docker compose --profile alertas up -d                           # Celery e Mailpit, para o alerta
    docker compose run --rm beam superset/provisionar.py
    docker compose run --rm beam superset/provisionar.py --demonstrar-alerta

Idempotente: cada objeto e procurado pelo nome e atualizado. Os datasets virtuais e as consultas
salvas vem de sql/sql_lab.sql. Ao final exporta os dashboards e as consultas para
superset/exportacao_e_evidencias/ (importaveis em Dashboards > Import / SQL Lab > Import).
"""
import argparse
import json
import os
import re
import time
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import psycopg
import requests

RAIZ = Path(__file__).resolve().parent.parent
BASE = "http://superset:8088"
MAILPIT = "http://mailpit:8025"
EVIDENCIAS = RAIZ / "superset" / "exportacao_e_evidencias"

BANCO = "Desafio 2 - Gold (papel consumo)"
SG = "Segurança & Governança"

# metricas definidas uma vez no dataset: todos os graficos calculam do mesmo jeito
METRICAS = {
    "vd_conclusao_coorte": [
        ("taxa_conclusao", "ROUND(100.0 * SUM(pares_concluidos) / NULLIF(SUM(pares_consumo), 0), 1)", "Taxa de conclusão (%)", ".1f"),
        ("pares_consumo", "SUM(pares_consumo)", "Pares com consumo", ",d"),
    ],
    "vd_recomendacoes": [
        ("conversao", "ROUND(100.0 * SUM(convertidas) / NULLIF(SUM(recomendacoes), 0), 1)", "Conversão (%)", ".1f"),
        ("recomendacoes", "SUM(recomendacoes)", "Recomendações", ",d"),
    ],
    "kpi_usuarios_ativos_mensal": [("pessoas_ativas", "SUM(pessoas_ativas)", "Pessoas ativas", ",d")],
    "kpi_avaliacao": [("avaliacao_media", "ROUND(SUM(avaliacao_media * avaliacoes) / NULLIF(SUM(avaliacoes), 0), 2)",
                       "Avaliação média (1-5)", ".2f")],
    "kpi_engajamento_mensal": [("interacoes", "SUM(interacoes)", "Interações", ",d")],
    "vw_resultado": [("valor_medido", "MAX(valor_medido)", "Valor medido (%)", ".2f")],
}
ROTULOS = {"categoria": "Categoria", "tipo": "Tipo", "nivel": "Nível", "avaliacao_media": "Avaliação média",
           "taxa_conclusao": "Taxa de conclusão (%)", "quadrante": "Quadrante", "faixa_posicao": "Posição na lista",
           "mes_inicio": "Mês de início", "mes_referencia": "Mês", "data_geracao": "Data da recomendação",
           "classificacao": "Classificação", "fonte": "Fonte", "pares_consumo": "Pares com consumo",
           "pares_concluidos": "Pares concluídos", "avaliacoes": "Avaliações", "teste_id": "Teste",
           "executado_em": "Execução", "valor_medido": "Valor medido (%)", "recomendacoes": "Recomendações",
           "convertidas": "Convertidas", "dias_ate_converter": "Dias até converter",
           "nome_mascarado": "Pessoa (nome mascarado)", "pseudonimo": "Pseudônimo", "faixa_etaria": "Faixa etária",
           "uf": "UF", "interacoes": "Interações", "conteudos": "Conteúdos", "conclusoes": "Conclusões",
           "ultima_interacao": "Última interação", "execucao": "Execução"}
TEMPORAL = {"vd_conclusao_coorte": "mes_inicio", "vd_recomendacoes": "data_geracao",
            "kpi_usuarios_ativos_mensal": "mes_referencia", "kpi_engajamento_mensal": "mes_referencia",
            "vw_resultado": "executado_em"}


# ---------------------------------------------------------------- cliente da API

def rison(v) -> str:
    if isinstance(v, dict):
        return "(" + ",".join(f"{k}:{rison(x)}" for k, x in v.items()) + ")"
    if isinstance(v, list):
        return "!(" + ",".join(rison(x) for x in v) + ")"
    if isinstance(v, bool):
        return "!t" if v else "!f"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("!", "!!").replace("'", "!'") + "'"


class Superset:
    def __init__(self):
        self.s = requests.Session()
        r = self.s.post(f"{BASE}/api/v1/security/login", json={
            "username": os.environ["SUPERSET_ADMIN_USER"], "password": os.environ["SUPERSET_ADMIN_PASSWORD"],
            "provider": "db", "refresh": True})
        r.raise_for_status()
        self.s.headers["Authorization"] = "Bearer " + r.json()["access_token"]
        self.s.headers["X-CSRFToken"] = self.s.get(f"{BASE}/api/v1/security/csrf_token/").json()["result"]
        self.s.headers["Referer"] = BASE

    def chamar(self, metodo: str, caminho: str, **kw):
        for espera in (0.5, 1, 2, 4, 8):  # a API limita a 50 requisicoes por segundo (429)
            r = self.s.request(metodo, f"{BASE}/api/v1/{caminho}", **kw)
            if r.status_code != 429:
                break
            time.sleep(espera)
        if r.status_code >= 400:
            raise SystemExit(f"{metodo} {caminho}: {r.status_code} {r.text[:500]}")
        return r

    def buscar(self, recurso: str, **filtros):
        q = {"filters": [{"col": c, "opr": "eq", "value": v} for c, v in filtros.items()], "page_size": 100}
        res = self.chamar("GET", f"{recurso}/", params={"q": rison(q)}).json()["result"]
        return res[0] if res else None

    def salvar(self, recurso: str, chave: dict, dados: dict) -> int:
        """Cria ou atualiza o objeto identificado por `chave` (ex.: {"slice_name": ...})."""
        existente = self.buscar(recurso, **chave)
        if existente:
            self.chamar("PUT", f"{recurso}/{existente['id']}", json=dados)
            return existente["id"]
        return self.chamar("POST", f"{recurso}/", json={**chave, **dados}).json()["id"]


# ---------------------------------------------------------------- conexao, datasets e consultas

def consultas_sql_lab() -> list[dict]:
    texto = (RAIZ / "sql/sql_lab.sql").read_text(encoding="utf-8")
    consultas = []
    for bloco in re.split(r"^-- nome: ", texto, flags=re.M)[1:]:
        linhas = bloco.splitlines()
        comentario = [l[3:] for l in linhas[1:] if l.startswith("-- ")]
        sql = "\n".join(l for l in linhas[1:] if not l.startswith("--")).strip().rstrip(";")
        consultas.append({"nome": linhas[0].strip(), "sql": sql, "descricao": "\n".join(comentario)})
    return consultas


def banco(api: Superset) -> int:
    uri = (f"postgresql+psycopg2://{os.environ['CONSUMO_DB_USER']}:{os.environ['CONSUMO_DB_PASSWORD']}"
           "@postgres:5432/desafio")
    return api.salvar("database", {"database_name": BANCO}, {
        "sqlalchemy_uri": uri, "expose_in_sqllab": True, "allow_run_async": False,
        "allow_ctas": False, "allow_cvas": False, "allow_dml": False})


def dataset(api: Superset, db: int, schema: str, nome: str, sql: str | None = None, descricao: str = "") -> int:
    existente = api.buscar("dataset", table_name=nome, schema=schema)
    if existente:
        ds_id = existente["id"]
        if sql:
            api.chamar("PUT", f"dataset/{ds_id}", json={"sql": sql})
        api.chamar("PUT", f"dataset/{ds_id}/refresh")
    else:
        corpo = {"database": db, "schema": schema, "table_name": nome}
        if sql:
            corpo["sql"] = sql
        ds_id = api.chamar("POST", "dataset/", json=corpo).json()["id"]
    atual = api.chamar("GET", f"dataset/{ds_id}").json()["result"]
    ids = {m["metric_name"]: m["id"] for m in atual["metrics"]}
    metricas = [{"id": ids[n]} if n in ids else {} for n, *_ in METRICAS.get(nome, [])]
    for m, (n, expr, rotulo, fmt) in zip(metricas, METRICAS.get(nome, [])):
        m.update({"metric_name": n, "expression": expr, "verbose_name": rotulo, "d3format": fmt})
    colunas = [{**{k: c.get(k) for k in ("id", "column_name", "type", "is_dttm", "groupby", "filterable",
                                         "expression", "description", "python_date_format")},
                "verbose_name": ROTULOS.get(c["column_name"], c.get("verbose_name"))} for c in atual["columns"]]
    corpo = {"description": descricao or None, "metrics": metricas, "columns": colunas}
    if nome in TEMPORAL:
        corpo["main_dttm_col"] = TEMPORAL[nome]
    api.chamar("PUT", f"dataset/{ds_id}", json=corpo)
    return ds_id


# ---------------------------------------------------------------- graficos

def filtro(coluna, operador, valor=None):
    f = {"expressionType": "SIMPLE", "subject": coluna, "operator": operador, "clause": "WHERE"}
    if valor is not None:
        f["comparator"] = valor
    return f


def periodo(coluna):
    """Filtro de tempo que o filtro nativo "Periodo" do dashboard substitui."""
    return filtro(coluna, "TEMPORAL_RANGE", "No filter")


def anotacao(nome, valor):
    """Linha de referencia (camada de anotacao do tipo formula): media do catalogo, limite de um teste."""
    return {"name": nome, "annotationType": "FORMULA", "sourceType": "", "value": str(valor), "overrides": {},
            "show": True, "showLabel": True, "titleColumn": "", "descriptionColumns": [], "timeColumn": "",
            "intervalEndColumn": "", "color": "#e04355", "opacity": "", "style": "dashed", "width": 1.5,
            "showMarkers": False, "hideLine": False}


def barras(ds, x, metrica, titulo_y, filtros=(), horizontal=True, crescente=True, grupo=None, referencia=None):
    return {"annotation_layers": [anotacao(*referencia)] if referencia else [],"viz_type": "echarts_timeseries_bar", "datasource": f"{ds}__table", "x_axis": x,
            "metrics": [metrica], "groupby": [grupo] if grupo else [], "adhoc_filters": list(filtros),
            "orientation": "horizontal" if horizontal else "vertical", "x_axis_sort": metrica,
            "x_axis_sort_asc": crescente, "x_axis_sort_series": "name", "row_limit": 1000,
            "show_value": True, "show_legend": bool(grupo), "rich_tooltip": True,
            "y_axis_title": titulo_y, "y_axis_title_margin": 30, "y_axis_format": ".1f",
            "color_scheme": "supersetColors", "truncate_metric": True}


def evolucao(ds, teste, titulo_y, minimo, limite):
    """Um ponto por execucao (eixo categorico, em ordem; rotulo = inicio em UTC), por fonte; eixo Y so na faixa relevante."""
    return {"viz_type": "echarts_timeseries_line", "datasource": f"{ds}__table", "x_axis": "execucao",
            "x_axis_sort_asc": True, "metrics": ["valor_medido"], "groupby": ["fonte"],
            "adhoc_filters": [filtro("teste_id", "==", teste)], "row_limit": 10000, "show_legend": True,
            "rich_tooltip": True, "markerEnabled": True, "legendType": "plain", "y_axis_title": titulo_y, "y_axis_title_margin": 50,
            "y_axis_bounds": [minimo, 100], "y_axis_format": ".2f", "xAxisLabelRotation": 30,
            "annotation_layers": [anotacao(f"limite: {limite}%", limite)],
            "color_scheme": "supersetColors", "truncate_metric": True}


def linha(ds, x, metrica, titulo_y, filtros=(), grupo=None, formato="%b/%Y"):
    return {"viz_type": "echarts_timeseries_line", "datasource": f"{ds}__table", "x_axis": x,
            "time_grain_sqla": "P1M", "metrics": [metrica], "groupby": [grupo] if grupo else [],
            "adhoc_filters": list(filtros), "row_limit": 10000, "show_legend": bool(grupo),
            "rich_tooltip": True, "markerEnabled": True, "show_value": not grupo, "y_axis_title": titulo_y,
            "y_axis_title_margin": 30, "x_axis_time_format": formato, "y_axis_format": "SMART_NUMBER",
            "color_scheme": "supersetColors", "truncate_metric": True}


def numero(ds, metrica, subtitulo, filtros=(), formato=".1f"):
    return {"viz_type": "big_number_total", "datasource": f"{ds}__table", "metric": metrica,
            "adhoc_filters": list(filtros), "subheader": subtitulo, "y_axis_format": formato,
            "header_font_size": 0.4, "subheader_font_size": 0.15}


def tabela(ds, colunas, filtros=(), ordem=None):
    return {"viz_type": "table", "datasource": f"{ds}__table", "query_mode": "raw", "all_columns": colunas,
            "adhoc_filters": list(filtros), "order_by_cols": [json.dumps([ordem, True])] if ordem else [],
            "row_limit": 100, "table_timestamp_format": "%d/%m/%Y", "show_cell_bars": True}


def grafico(api: Superset, nome: str, form: dict, descricao: str, contexto: dict | None = None) -> int:
    ds_id = int(form["datasource"].split("__")[0])
    dados = {"viz_type": form["viz_type"], "datasource_id": ds_id, "datasource_type": "table",
             "params": json.dumps(form, ensure_ascii=False), "description": descricao}
    if contexto:
        dados["query_context"] = json.dumps(contexto, ensure_ascii=False)
    return api.salvar("chart", {"slice_name": nome}, dados)


# ---------------------------------------------------------------- dashboards

def layout(titulo: str, linhas: list[list[tuple]], nomes: dict[int, str], titulos: dict[int, str]) -> dict:
    pos = {"DASHBOARD_VERSION_KEY": "v2",
           "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
           "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
           "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": titulo}}}
    for i, componentes in enumerate(linhas):
        rid = f"ROW-{i}"
        pos["GRID_ID"]["children"].append(rid)
        pos[rid] = {"type": "ROW", "id": rid, "children": [], "parents": ["ROOT_ID", "GRID_ID"],
                    "meta": {"background": "BACKGROUND_TRANSPARENT"}}
        for j, (tipo, conteudo, largura, altura) in enumerate(componentes):
            if tipo == "grafico":
                cid = f"CHART-{conteudo}"
                meta = {"chartId": conteudo, "width": largura, "height": altura, "sliceName": nomes[conteudo]}
                if conteudo in titulos:  # titulo informativo (RF16), com numeros lidos da Gold
                    meta["sliceNameOverride"] = titulos[conteudo]
                pos[cid] = {"type": "CHART", "id": cid, "children": [], "parents": ["ROOT_ID", "GRID_ID", rid], "meta": meta}
            else:
                cid = f"MARKDOWN-{i}-{j}"
                pos[cid] = {"type": "MARKDOWN", "id": cid, "children": [], "parents": ["ROOT_ID", "GRID_ID", rid],
                            "meta": {"code": conteudo, "width": largura, "height": altura}}
            pos[rid]["children"].append(cid)
    return pos


def dashboard(api: Superset, titulo: str, slug: str, pos: dict, meta: dict, graficos: list[int]) -> int:
    dash = api.salvar("dashboard", {"slug": slug}, {
        "dashboard_title": titulo, "position_json": json.dumps(pos, ensure_ascii=False),
        "json_metadata": json.dumps(meta, ensure_ascii=False), "published": True})
    for g in graficos:
        atuais = api.chamar("GET", f"chart/{g}").json()["result"].get("dashboards", [])
        ids = sorted({d["id"] for d in atuais} | {dash})
        api.chamar("PUT", f"chart/{g}", json={"dashboards": ids})
    return dash


# cor fixa por fonte: o dashboard reparte as cores da paleta entre todos os rotulos e repetia cores nas
# series da qualidade; com a cor fixada, a mesma fonte tem a mesma cor nos dois graficos de evolucao
CORES_FONTE = {"catalogo": "#1f77b4", "usuarios": "#ff7f0e", "interacoes": "#2ca02c", "comentarios": "#d62728",
               "recomendacoes": "#9467bd"}


def metadados(filtros_nativos=None, cruzado=None) -> dict:
    meta = {"color_scheme": "supersetColors", "refresh_frequency": 0, "timed_refresh_immune_slices": [],
            "expanded_slices": {}, "label_colors": dict(CORES_FONTE), "shared_label_colors": [], "default_filters": "{}",
            "native_filter_configuration": filtros_nativos or [], "cross_filters_enabled": bool(cruzado),
            "chart_configuration": {}, "global_chart_configuration": {
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []}, "chartsInScope": []}}
    if cruzado:
        emissores, receptores = cruzado
        for e in emissores:
            meta["chart_configuration"][str(e)] = {"id": e, "crossFilters": {
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "chartsInScope": [r for r in receptores if r != e]}}
        meta["global_chart_configuration"]["chartsInScope"] = receptores
    return meta


def filtro_nativo(fid, nome, tipo, descricao, alvo=None, excluidos=()):
    f = {"id": fid, "name": nome, "filterType": tipo, "type": "NATIVE_FILTER", "description": descricao,
         "targets": [alvo] if alvo else [{}], "controlValues": {}, "cascadeParentIds": [],
         "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
         "scope": {"rootPath": ["ROOT_ID"], "excluded": list(excluidos)}}
    if tipo == "filter_select":
        f["controlValues"] = {"multiSelect": True, "enableEmptyFilter": False, "defaultToFirstItem": False,
                              "inverseSelection": False, "searchAllOptions": False}
    return f


# ---------------------------------------------------------------- alerta (RF18)

ALERTA = {
    "nome": "Taxa de conclusão de alguma categoria abaixo de 18%",
    "sql": ("SELECT min(taxa) FROM (SELECT categoria, 100.0 * sum(pares_concluidos) / sum(pares_consumo) AS taxa "
            "FROM gold.kpi_taxa_conclusao GROUP BY categoria) t"),
    "operador": "<", "limite": 18,
    "destinatario": "coordenacao.conteudo@plataforma.example",
    "cron": "0 8 * * *", "fuso": "America/Sao_Paulo",
    "descricao": ("Diário às 08:00 (Brasília). Dispara quando a menor taxa de conclusão por categoria fica abaixo "
                  "de 18%. Ação esperada: a coordenação de conteúdo revisa a categoria indicada na tabela do e-mail "
                  "e decide entre dividir conteúdos longos em módulos ou criar uma trilha de entrada."),
}


def alerta(api: Superset, db: int, grafico_id: int, cron: str) -> int:
    dados = {"type": "Alert", "description": ALERTA["descricao"], "crontab": cron, "timezone": ALERTA["fuso"],
             "active": True, "database": db, "sql": ALERTA["sql"], "validator_type": "operator",
             "validator_config_json": {"op": ALERTA["operador"], "threshold": ALERTA["limite"]},
             "chart": grafico_id, "report_format": "TEXT", "grace_period": 60, "working_timeout": 300,
             "log_retention": 90, "creation_method": "alerts_reports",
             "recipients": [{"type": "Email", "recipient_config_json": {"target": ALERTA["destinatario"]}}]}
    return api.salvar("report", {"name": ALERTA["nome"]}, dados)


def demonstrar_alerta(api: Superset, db: int, grafico_id: int, alerta_id: int) -> None:
    """Agenda o alerta para o proximo minuto, espera o envio no Mailpit e volta ao horario diario."""
    inicio = time.time()
    antes = {m["ID"] for m in requests.get(f"{MAILPIT}/api/v1/messages").json().get("messages", [])}
    alerta(api, db, grafico_id, "* * * * *")
    try:
        for _ in range(60):
            time.sleep(5)
            logs = api.chamar("GET", f"report/{alerta_id}/log/",
                              params={"q": rison({"order_column": "start_dttm", "order_direction": "desc"})}).json()["result"]
            recentes = [l for l in logs if l.get("state") and l["state"] != "Working"]
            novos = [m for m in requests.get(f"{MAILPIT}/api/v1/messages").json().get("messages", []) if m["ID"] not in antes]
            if novos:
                break
        else:
            raise SystemExit(f"nenhum e-mail em 5 minutos; ultimos logs do alerta: {logs[:2]}")
    finally:
        alerta(api, db, grafico_id, ALERTA["cron"])
    mensagem = requests.get(f"{MAILPIT}/api/v1/message/{novos[0]['ID']}").json()
    EVIDENCIAS.mkdir(parents=True, exist_ok=True)
    (EVIDENCIAS / "alerta_email.html").write_text(mensagem["HTML"], encoding="utf-8")
    registro = {"assunto": mensagem["Subject"], "de": mensagem["From"]["Address"],
                "para": [t["Address"] for t in mensagem["To"]], "enviado_em": mensagem["Date"],
                "condicao": f"{ALERTA['sql']} {ALERTA['operador']} {ALERTA['limite']}",
                "log_do_alerta": recentes[:1], "segundos_ate_o_envio": round(time.time() - inicio)}
    (EVIDENCIAS / "alerta_execucao.json").write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")
    print(f"alerta enviado para {registro['para']}: {registro['assunto']}")


# ---------------------------------------------------------------- numeros da narrativa (RF16)

def pct(v) -> str:
    """Percentual com uma casa, arredondado como o ROUND do PostgreSQL (meio para cima), para o texto bater
    com os graficos: 11,25 vira 11,3 nos dois lugares."""
    v = Decimal(str(v)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{v}".replace(".", ",").replace(",0", "") + "%"


def numeros() -> dict:
    """Numeros citados nos titulos e textos, lidos da Gold com o papel consumo. A narrativa depende de
    algumas premissas; se os dados deixarem de sustenta-las, o provisionamento para em vez de mentir."""
    with psycopg.connect(host="postgres", dbname=os.environ["POSTGRES_DB"], user=os.environ["CONSUMO_DB_USER"],
                         password=os.environ["CONSUMO_DB_PASSWORD"]) as conn:
        q = lambda sql, *p: conn.execute(sql, p).fetchall()  # noqa: E731
        ativos = q("SELECT mes_referencia, pessoas_ativas FROM gold.kpi_usuarios_ativos_mensal "
                   "WHERE mes_completo ORDER BY 1")
        conclusao = q("SELECT categoria, 100.0 * sum(pares_concluidos) / sum(pares_consumo) "
                      "FROM gold.kpi_taxa_conclusao GROUP BY 1 ORDER BY 2")
        media = q("SELECT 100.0 * sum(pares_concluidos) / sum(pares_consumo) FROM gold.kpi_taxa_conclusao")[0][0]
        avaliacao = q("SELECT categoria, sum(avaliacao_media * avaliacoes) / sum(avaliacoes) "
                      "FROM gold.kpi_avaliacao GROUP BY 1 ORDER BY 2 DESC")
        por = {dim: {r[0]: (float(r[1]), r[2]) for r in q(
            f"SELECT {dim}, 100.0 * sum(pares_concluidos) / sum(pares_consumo), sum(pares_consumo) "
            f"FROM gold.kpi_taxa_conclusao WHERE categoria = %s GROUP BY 1", SG)} for dim in ("nivel", "tipo")}
        conversao = q("SELECT categoria, sum(convertidas), sum(recomendacoes), 100.0 * sum(convertidas) / sum(recomendacoes) "
                      "FROM gold.kpi_conversao_recomendacao GROUP BY 1 ORDER BY 4 DESC")
        # conclusao por duracao do conteudo na categoria: pares como em gold.kpi_taxa_conclusao
        duracao = {r[0]: (float(r[1]), r[2]) for r in q(
            "WITH pares AS (SELECT f.usuario_pseudo, f.conteudo_id, d.carga_horaria_min AS minutos, "
            "bool_or(f.tipo_interacao = 'conclusão' OR f.percentual_conclusao >= 100) AS concluiu "
            "FROM gold.fato_interacao f JOIN gold.dim_conteudo d USING (conteudo_id) "
            "WHERE d.categoria = %s AND f.tipo_interacao IN ('visualização', 'início', 'conclusão') GROUP BY 1, 2, 3) "
            "SELECT CASE WHEN minutos <= 30 THEN 'ate_30' WHEN minutos <= 90 THEN '31_90' ELSE 'mais_90' END, "
            "100.0 * count(*) FILTER (WHERE concluiu) / count(*), count(*) FROM pares GROUP BY 1", SG)}
        # recorte recente (os 3 ultimos meses completos em diante), o mesmo que o filtro de periodo mostra:
        # as taxas por periodo oscilam com amostras pequenas, e a narrativa precisa dizer isso
        ultimo = ativos[-1][0]
        inicio_recente = ultimo.replace(year=ultimo.year - (ultimo.month <= 2), month=(ultimo.month - 3) % 12 + 1)
        recente = q(
            "WITH pares AS (SELECT f.usuario_pseudo, f.conteudo_id, d.categoria, min(f.data_hora) AS inicio, "
            "bool_or(f.tipo_interacao = 'conclusão' OR f.percentual_conclusao >= 100) AS concluiu "
            "FROM gold.fato_interacao f JOIN gold.dim_conteudo d USING (conteudo_id) "
            "WHERE f.tipo_interacao IN ('visualização', 'início', 'conclusão') GROUP BY 1, 2, 3) "
            "SELECT categoria, 100.0 * count(*) FILTER (WHERE concluiu) / count(*), count(*) "
            "FROM pares WHERE inicio >= %s GROUP BY 1 ORDER BY 2", inicio_recente)
    posicao_avaliacao = [c for c, _ in avaliacao].index(SG) + 1
    conv_sg = next(r for r in conversao if r[0] == SG)
    premissas = {
        f"{SG} tem a menor taxa de conclusao": conclusao[0][0] == SG,
        f"{SG} esta entre as 3 categorias mais bem avaliadas": posicao_avaliacao <= 3,
        f"{SG} tem a maior conversao de recomendacoes (ou empata)": conv_sg[3] == conversao[0][3],
        "o nivel avancado e o de menor conclusao na categoria": min(por["nivel"], key=lambda k: por["nivel"][k][0]) == "Avançado",
        f"a taxa de {SG} esta abaixo do limite do alerta": conclusao[0][1] < ALERTA["limite"],
        "conteudos de ate 30 min concluem mais que os de 31 a 90 min na categoria": duracao["ate_30"][0] > duracao["31_90"][0],
    }
    falhas = [p for p, ok in premissas.items() if not ok]
    if falhas:
        raise SystemExit("os dados nao sustentam mais a narrativa do storytelling: " + "; ".join(falhas))
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
             "outubro", "novembro", "dezembro"]
    audiovisual = sorted(por["tipo"][t][0] for t in ("Vídeo", "Podcast"))
    empate = [r[0] for r in conversao if r[0] != SG and r[3] == conv_sg[3]]
    return {
        "ativos_inicio": ativos[0][1], "ativos_fim": ativos[-1][1],
        "mes_inicio": meses[ativos[0][0].month - 1], "mes_fim": meses[ativos[-1][0].month - 1],
        "conclusao_sg": pct(conclusao[0][1]), "conclusao_media": pct(media),
        "avaliacao_sg": f"{Decimal(str(avaliacao[posicao_avaliacao - 1][1])).quantize(Decimal('0.01'), ROUND_HALF_UP)}".replace(".", ","),
        "posicao_avaliacao": f"{posicao_avaliacao}ª",
        "avancado": pct(por["nivel"]["Avançado"][0]), "avancado_n": por["nivel"]["Avançado"][1],
        "audiovisual": f"{pct(audiovisual[0])} a {pct(audiovisual[1])}".replace("% a", " a"),
        "tipo_n": f"{min(n for _, n in por['tipo'].values())} a {max(n for _, n in por['tipo'].values())}",
        "conversao_sg": pct(conv_sg[3]), "conversao_sg_n": f"{conv_sg[1]} em {conv_sg[2]}",
        "conversao_empate": f", empatada com {' e '.join(empate)}" if empate else "",
        "meta": pct(round(float(media))),
        "sg_ate_30": pct(duracao["ate_30"][0]), "sg_31_90": pct(duracao["31_90"][0]),
        "sg_31_90_n": duracao["31_90"][1],
        "media_valor": float(media),
        "mes_recente": meses[inicio_recente.month - 1],
        "recente_sg": pct(next(r[1] for r in recente if r[0] == SG)),
        "recente_pior": recente[0][0], "recente_pior_taxa": pct(recente[0][1]),
        "recente_n": f"{min(r[2] for r in recente)} a {max(r[2] for r in recente)}",
    }


# ---------------------------------------------------------------- montagem

def main() -> None:
    args = argparse.ArgumentParser()
    args.add_argument("--demonstrar-alerta", action="store_true")
    demonstrar = args.parse_args().demonstrar_alerta

    n = numeros()
    api = Superset()
    db = banco(api)
    consultas = consultas_sql_lab()
    ds = {c["nome"]: dataset(api, db, "gold", c["nome"], c["sql"], c["descricao"]) for c in consultas}
    for tabela_gold in ("kpi_usuarios_ativos_mensal", "kpi_avaliacao", "kpi_engajamento_mensal"):
        ds[tabela_gold] = dataset(api, db, "gold", tabela_gold)
    ds["vw_resultado"] = dataset(api, db, "qualidade", "vw_resultado")
    for c in consultas:
        api.salvar("saved_query", {"label": c["nome"]},
                   {"db_id": db, "schema": "gold", "sql": c["sql"] + ";", "description": c["descricao"]})

    # o nome do grafico e estavel (identifica o objeto entre execucoes); o titulo informativo, que muda
    # com os dados, aparece no dashboard como sliceNameOverride
    g, nomes, titulos = {}, {}, {}

    def criar(chave, nome, form, descricao, contexto=None, titulo=None):
        g[chave] = grafico(api, nome, form, descricao, contexto)
        nomes[g[chave]] = nome
        if titulo:
            titulos[g[chave]] = titulo

    # --- storytelling (RF16): contexto -> evidencia -> descoberta -> acao
    criar("ativos", "D2 · Pessoas ativas por mês",
          linha(ds["kpi_usuarios_ativos_mensal"], "mes_referencia", "pessoas_ativas", "pessoas ativas",
                [filtro("mes_completo", "IS TRUE")]),
          "Fato. Pessoas (usuário mestre) com ao menos uma interação no mês; o mês em andamento fica de fora.",
          titulo=f"Pessoas ativas cresceram de {n['ativos_inicio']} para {n['ativos_fim']} entre {n['mes_inicio']} e {n['mes_fim']}")
    criar("n_conclusao", "D2 · Taxa de conclusão geral",
          numero(ds["vd_conclusao_coorte"], "taxa_conclusao", "% dos conteúdos iniciados que são concluídos"),
          "Fato. Pares (pessoa, conteúdo) concluídos / pares com consumo.", titulo="Taxa de conclusão geral")
    criar("n_conversao", "D2 · Conversão das recomendações",
          numero(ds["vd_recomendacoes"], "conversao", "% das recomendações seguidas de consumo"),
          "Fato. Recomendações do Desafio 1 (13/09) seguidas de consumo do conteúdo pela mesma pessoa.", titulo="Conversão das recomendações")
    criar("n_avaliacao", "D2 · Avaliação média",
          numero(ds["kpi_avaliacao"], "avaliacao_media", "nota de 1 a 5", formato=".2f"),
          "Fato. Média das avaliações atribuídas nas interações.", titulo="Avaliação média")
    criar("conclusao_categoria", "D2 · Taxa de conclusão por categoria (narrativa)",
          barras(ds["vd_conclusao_coorte"], "categoria", "taxa_conclusao", "taxa de conclusão (%)",
                 referencia=(f"média do catálogo: {n['conclusao_media']}", round(n["media_valor"], 1))),
          "Fato. Mesma definição de gold.kpi_taxa_conclusao. Linha tracejada: média do catálogo.",
          titulo=f"{SG} conclui {n['conclusao_sg']} do que começa: a menor taxa do catálogo")
    criar("quadrante", "D2 · Avaliação x conclusão por categoria",
          tabela(ds["vd_avaliacao_x_conclusao"], ["categoria", "avaliacao_media", "taxa_conclusao", "quadrante"])
          | {"column_config": {"avaliacao_media": {"d3NumberFormat": ",.2f"}, "taxa_conclusao": {"d3NumberFormat": ",.1f"}}},
          "Fato. Quadrante em relação às médias gerais de avaliação e de conclusão (sql/sql_lab.sql).",
          titulo=f"Mesmo assim é a {n['posicao_avaliacao']} categoria mais bem avaliada: o problema não parece ser qualidade")
    criar("sg_nivel", f"D2 · Conclusão por nível em {SG}",
          barras(ds["vd_conclusao_coorte"], "nivel", "taxa_conclusao", "taxa de conclusão (%)",
                 [filtro("categoria", "==", SG)], horizontal=False),
          f"Fato, com amostra pequena ({n['avancado_n']} pares no nível avançado): tratar como indício.",
          titulo=f"Em {SG}, o nível avançado conclui só {n['avancado']}")
    criar("sg_tipo", f"D2 · Conclusão por tipo em {SG}",
          barras(ds["vd_conclusao_coorte"], "tipo", "taxa_conclusao", "taxa de conclusão (%)",
                 [filtro("categoria", "==", SG)], horizontal=False),
          f"Fato, com amostra pequena ({n['tipo_n']} pares por tipo): tratar como indício.",
          titulo=f"Vídeos e podcasts de {SG} quase não são concluídos")
    criar("conversao_categoria", "D2 · Conversão das recomendações por categoria",
          barras(ds["vd_recomendacoes"], "categoria", "conversao", "conversão (%)", crescente=False),
          f"Fato, com poucas conversões ({n['conversao_sg_n']}). Hipótese: o interesse existe, o problema está em terminar.",
          titulo=f"Recomendações de {SG} estão no topo da conversão ({n['conversao_sg']}): há demanda")

    # --- exploracao (RF18): filtro de periodo e de categoria, filtro cruzado; evolucao da qualidade (RF31)
    # barras verticais: com barras horizontais o clique emite o valor numerico em vez da categoria
    criar("x_categoria", "D2 · Taxa de conclusão por categoria (clique para filtrar)",
          barras(ds["vd_conclusao_coorte"], "categoria", "taxa_conclusao", "taxa de conclusão (%)",
                 [periodo("mes_inicio")], horizontal=False) | {"xAxisLabelRotation": 45},
          "Emite filtro cruzado por categoria.")
    criar("x_tipo", "D2 · Taxa de conclusão por tipo de conteúdo",
          barras(ds["vd_conclusao_coorte"], "tipo", "taxa_conclusao", "taxa de conclusão (%)",
                 [periodo("mes_inicio")], horizontal=False),
          "Responde ao filtro cruzado e aos filtros de período e categoria.")
    criar("x_posicao", "D2 · Conversão por posição na lista de recomendações",
          barras(ds["vd_recomendacoes"], "faixa_posicao", "conversao", "conversão (%)",
                 [periodo("data_geracao")], horizontal=False),
          "Responde ao filtro cruzado e aos filtros de período e categoria.")
    criar("x_engajamento", "D2 · Interações por mês e categoria",
          linha(ds["kpi_engajamento_mensal"], "mes_referencia", "interacoes", "interações",
                [periodo("mes_referencia")], grupo="categoria"),
          "Mesma regra do pipeline Beam (RF25).")
    criar("x_qualidade", "D2 · Evolução da validade das fontes (Q01) por execução",
          evolucao(ds["vw_resultado"], "Q01_VALIDADE_FONTES", "% aprovados na validação", 85, 90),
          "RF31: resultado por execução e por fonte. Limite crítico: 90%.")
    criar("x_qualidade_q02", "D2 · Evolução da integridade referencial (Q02) por execução",
          evolucao(ds["vw_resultado"], "Q02_INTEGRIDADE_REFERENCIAS", "% de eventos com referências válidas", 98.5, 99),
          "RF31: segunda métrica acompanhada. Eventos com usuário e conteúdo existentes, por fonte. Limite: 99% (alta).")
    criar("x_pessoas", "D2 · Pessoas mais engajadas (nomes mascarados)",
          tabela(ds["vd_pessoas_engajadas"], ["nome_mascarado", "pseudonimo", "faixa_etaria", "uf", "interacoes",
                                              "conteudos", "conclusoes", "ultima_interacao"])
          | {"order_by_cols": [json.dumps(["interacoes", False])]},
          "RF33: a pessoa aparece só pelo nome mascarado e pelo pseudônimo; nenhum valor original chega ao consumo.")
    alerta_form = {"viz_type": "table", "datasource": f"{ds['vd_conclusao_coorte']}__table", "query_mode": "aggregate",
                   "groupby": ["categoria"], "metrics": ["taxa_conclusao"], "all_columns": [],
                   "adhoc_filters": [], "order_desc": False, "timeseries_limit_metric": "taxa_conclusao",
                   "row_limit": 100, "server_pagination": False}
    contexto = {"datasource": {"id": ds["vd_conclusao_coorte"], "type": "table"}, "force": False,
                "queries": [{"filters": [], "extras": {"having": "", "where": ""}, "applied_time_extras": {},
                             "columns": ["categoria"], "metrics": ["taxa_conclusao"],
                             "orderby": [["taxa_conclusao", True]], "annotation_layers": [], "row_limit": 100,
                             "series_limit": 0, "order_desc": False, "url_params": {}, "custom_params": {},
                             "custom_form_data": {}, "post_processing": []}],
                "form_data": alerta_form, "result_format": "json", "result_type": "full"}
    criar("alerta", "D2 · Taxa de conclusão por categoria (conteúdo do alerta)", alerta_form,
          "Anexado ao alerta de conclusão abaixo de 18%.", contexto)

    md_topo = f"""## Pergunta: em qual categoria agir primeiro para aumentar a conclusão de conteúdos, e como?

**Contexto.** A plataforma cresce: mais pessoas ativas a cada mês. Mas só uma parte do que é iniciado chega ao fim,
e cada conteúdo abandonado é esforço de produção que não vira aprendizado.

<small>Legenda: **Fato** = medido nos dados · **Hipótese** = explicação a testar · **Recomendação** = ação proposta.
Dados fictícios.</small>"""
    md_evidencia = f"""### Evidência
**Fato.** {SG} tem a menor taxa de conclusão ({n['conclusao_sg']}), abaixo da média do catálogo ({n['conclusao_media']}).

**Fato.** Ela é, ao mesmo tempo, a {n['posicao_avaliacao']} categoria mais bem avaliada ({n['avaliacao_sg']}).

**Hipótese descartada.** Não é "conteúdo ruim": quem conclui, avalia bem."""
    md_descoberta = f"""### Descoberta
**Fato.** A queda se concentra no nível avançado ({n['avancado']}) e nos formatos vídeo e podcast ({n['audiovisual']}).
A categoria não tem mais conteúdo avançado que as outras, então a explicação não é só dificuldade.

**Fato.** Por duração, os conteúdos de 31 a 90 minutos, faixa de vídeos e podcasts, concluem {n['sg_31_90']}
({n['sg_31_90_n']} pares); os de até 30 minutos, {n['sg_ate_30']}.

**Fato.** As recomendações dessa categoria estão no topo da conversão ({n['conversao_sg']}{n['conversao_empate']}).

**Hipótese.** Há interesse; o que falta é um caminho para terminar conteúdos densos de média duração."""
    md_acao = f"""### Ação recomendada
1. **Recomendação.** Piloto de 60 dias em {SG}: dividir vídeos e podcasts, começando pelos de nível avançado,
   em módulos de até 30 minutos, com um conteúdo básico como porta de entrada.
2. **Recomendação.** Priorizar essa trilha na recomendação para quem já iniciou conteúdo da categoria.
3. **Meta e acompanhamento.** Levar a taxa de conclusão da categoria de {n['conclusao_sg']} para {n['meta']} (média do catálogo),
   acompanhada pelo alerta diário "Taxa de conclusão de alguma categoria abaixo de 18%".

**Ressalva.** As taxas por período oscilam: são {n['recente_n']} pares por categoria desde {n['mes_recente']}.
Nesse recorte, {SG} sobe para {n['recente_sg']} e a menor taxa passa a ser de {n['recente_pior']} ({n['recente_pior_taxa']}).
O acumulado é a base mais estável, mas não é definitivo; por isso a ação é um piloto medido, e o alerta acompanha todas as categorias.

<small>Limites: amostras pequenas no recorte por nível e tipo, e conversão medida só duas semanas após as recomendações.</small>"""

    story = dashboard(api, f"Desafio 2 - Por que {SG} não é concluída?", "desafio2-storytelling",
                      layout(f"Por que {SG} não é concluída?", [
                          [("markdown", md_topo, 12, 17)],
                          [("grafico", g["n_conclusao"], 3, 30), ("grafico", g["n_conversao"], 3, 30),
                           ("grafico", g["n_avaliacao"], 3, 30), ("grafico", g["ativos"], 3, 30)],
                          [("markdown", md_evidencia, 4, 74), ("grafico", g["conclusao_categoria"], 4, 74),
                           ("grafico", g["quadrante"], 4, 74)],
                          [("markdown", md_descoberta, 4, 56), ("grafico", g["sg_nivel"], 4, 56),
                           ("grafico", g["sg_tipo"], 4, 56)],
                          [("grafico", g["conversao_categoria"], 6, 56), ("markdown", md_acao, 6, 56)],
                      ], nomes, titulos), metadados(), [g[k] for k in ("ativos", "n_conclusao", "n_conversao", "n_avaliacao",
                                                               "conclusao_categoria", "quadrante", "sg_nivel",
                                                               "sg_tipo", "conversao_categoria")])

    receptores = [g[k] for k in ("x_categoria", "x_tipo", "x_posicao", "x_engajamento", "alerta")]
    filtros_nativos = [
        filtro_nativo("NATIVE_FILTER-periodo", "Período", "filter_time",
                      "Mês de início do consumo, de geração da recomendação ou de referência",
                      excluidos=[g["x_qualidade"], g["x_qualidade_q02"], g["alerta"], g["x_pessoas"]]),
        filtro_nativo("NATIVE_FILTER-categoria", "Categoria", "filter_select", "Categoria do conteúdo",
                      {"datasetId": ds["vd_conclusao_coorte"], "column": {"name": "categoria"}},
                      excluidos=[g["x_qualidade"], g["x_qualidade_q02"], g["x_pessoas"]]),
    ]
    md_exploracao = """**Como usar.** Filtros de **período** e **categoria** no painel à esquerda. Clique numa barra de
*Taxa de conclusão por categoria* para filtrar os demais gráficos por aquela categoria (filtro cruzado).
A evolução da qualidade (RF31: validade e integridade referencial) e a lista de pessoas não são afetadas pelos filtros; na lista, as pessoas aparecem
só pelo nome mascarado e pelo pseudônimo (RF33)."""
    explo = dashboard(api, "Desafio 2 - Exploração, filtros e qualidade", "desafio2-exploracao",
                      layout("Exploração, filtros e qualidade", [
                          [("markdown", md_exploracao, 12, 10)],
                          [("grafico", g["x_categoria"], 6, 56), ("grafico", g["x_tipo"], 6, 56)],
                          [("grafico", g["x_posicao"], 4, 56), ("grafico", g["x_engajamento"], 8, 56)],
                          [("grafico", g["x_qualidade"], 6, 56), ("grafico", g["x_qualidade_q02"], 6, 56)],
                          [("grafico", g["alerta"], 4, 50), ("grafico", g["x_pessoas"], 8, 50)],
                      ], nomes, titulos),
                      metadados(filtros_nativos, ([g["x_categoria"]], receptores)),
                      receptores + [g["x_qualidade"], g["x_qualidade_q02"], g["x_pessoas"]])

    alerta_id = alerta(api, db, g["alerta"], ALERTA["cron"])
    dados = api.chamar("GET", f"chart/{g['alerta']}/data/?format=json").json()["result"][0]["data"]
    print("conteudo do alerta:", ", ".join(f"{d['categoria']} {d['taxa_conclusao']:.1f}%" for d in dados[:3]), "...")

    EVIDENCIAS.mkdir(parents=True, exist_ok=True)
    (EVIDENCIAS / "dashboards_desafio2.zip").write_bytes(
        api.chamar("GET", "dashboard/export/", params={"q": rison([story, explo])}).content)
    ids_consultas = [api.buscar("saved_query", label=c["nome"])["id"] for c in consultas]
    (EVIDENCIAS / "consultas_sql_lab.zip").write_bytes(
        api.chamar("GET", "saved_query/export/", params={"q": rison(ids_consultas)}).content)
    print(f"dashboards: {BASE.replace('superset', 'localhost')}/superset/dashboard/desafio2-storytelling/ e "
          f"/superset/dashboard/desafio2-exploracao/; alerta {alerta_id}; exportacao em "
          f"{EVIDENCIAS.relative_to(RAIZ)}")

    if demonstrar:
        demonstrar_alerta(api, db, g["alerta"], alerta_id)


if __name__ == "__main__":
    main()
