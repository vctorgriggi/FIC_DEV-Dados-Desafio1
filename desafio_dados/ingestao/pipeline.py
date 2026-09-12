"""RF02-RF06: leitura, validacao, tratamento, processados e carga no PostgreSQL."""

import csv
import json
import logging
import unicodedata
from datetime import datetime
from pathlib import Path

log = logging.getLogger("ingestao")

# valor canonico indexado pela chave normalizada (minusculas, sem acento)
TIPOS = {"curso": "Curso", "video": "Vídeo", "artigo": "Artigo", "podcast": "Podcast"}
NIVEIS = {"basico": "Básico", "intermediario": "Intermediário", "avancado": "Avançado"}
TIPOS_INTERACAO = {
    "visualizacao": "visualização",
    "inicio": "início",
    "conclusao": "conclusão",
    "curtida": "curtida",
    "avaliacao": "avaliação",
    "compartilhamento": "compartilhamento",
}
FORMATOS_DATA = ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d")
CAMPOS_CATALOGO = [
    "conteudo_id", "titulo", "tipo", "categoria", "nivel",
    "carga_horaria_min", "data_publicacao", "descricao", "autor",
]


# --- conversao e normalizacao (RF04) ---

def limpar_texto(valor):
    if valor is None:
        return None
    texto = " ".join(str(valor).split())
    return texto or None


def chave(valor):
    """Chave de comparacao: sem acento, minusculas, espacos colapsados."""
    texto = limpar_texto(valor)
    if texto is None:
        return None
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.casefold()


def converter_int(valor):
    """Inteiro estrito: '7.9' e 7.9 sao invalidos, '7.0' e 7.0 sao aceitos."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        return int(valor) if valor.is_integer() else None
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        return int(texto)
    except ValueError:
        pass
    try:
        numero = float(texto)
    except ValueError:
        return None
    return int(numero) if numero.is_integer() else None


def converter_float(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return float(str(valor).strip())
    except ValueError:
        return None


def converter_data(valor):
    """Data em qualquer formato de FORMATOS_DATA -> 'YYYY-MM-DD'."""
    texto = limpar_texto(valor)
    if texto is None:
        return None
    for formato in FORMATOS_DATA:
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    return None


def converter_datetime(valor):
    texto = limpar_texto(valor)
    if texto is None:
        return None
    try:
        return datetime.fromisoformat(texto).isoformat(timespec="seconds")
    except ValueError:
        return None


def hoje():
    return datetime.now().date().isoformat()


def agora():
    return datetime.now().isoformat(timespec="seconds")


def mudou(original, final):
    """True se a normalizacao alterou o valor (conta como 'corrigido' no RF05)."""
    return original is not None and str(original).strip() != str(final)


def faltantes(registro, campos):
    return [c for c in campos if limpar_texto(registro.get(c)) is None]


class Contadores(dict):
    """Contagem por classificacao (RF03) + lista de rejeitados com motivo."""

    def __init__(self, fonte):
        super().__init__(validos=0, invalidos=0, incompletos=0, duplicados=0, corrigidos=0)
        self.fonte = fonte
        self.rejeitados = []

    def rejeitar(self, classe, linha, motivo):
        self[classe] += 1
        self.rejeitados.append({"fonte": self.fonte, "linha": linha, "classe": classe, "motivo": motivo})
        log.warning("[RF03] %s linha %d %s: %s", self.fonte, linha, classe[:-1], motivo)

    def aceitar(self, corrigido):
        self["validos"] += 1
        if corrigido:
            self["corrigidos"] += 1


# --- leitura (RF02) ---

def ler_catalogo(caminho: Path) -> list[dict]:
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        registros = list(csv.DictReader(f))
    log.info("[RF02] %s: %d registros", caminho, len(registros))
    return registros


def ler_json(caminho: Path) -> list[dict]:
    with caminho.open(encoding="utf-8") as f:
        dados = json.load(f)
    if not isinstance(dados, list):
        raise ValueError(f"{caminho} deveria conter uma lista JSON")
    log.info("[RF02] %s: %d registros", caminho, len(dados))
    return dados


# --- validacao e tratamento (RF03 + RF04) ---

def tratar_catalogo(registros):
    cont = Contadores("catálogo")
    tratados, ids_vistos = [], set()
    categorias = {}  # chave normalizada -> primeira grafia encontrada

    for n, r in enumerate(registros, start=1):
        campos = faltantes(r, CAMPOS_CATALOGO[:7])
        if campos:
            cont.rejeitar("incompletos", n, f"campos ausentes: {', '.join(campos)}")
            continue

        conteudo_id = converter_int(r["conteudo_id"])
        carga = converter_int(r["carga_horaria_min"])
        data = converter_data(r["data_publicacao"])
        tipo = TIPOS.get(chave(r["tipo"]))
        nivel = NIVEIS.get(chave(r["nivel"]))

        if conteudo_id is None or conteudo_id <= 0:
            cont.rejeitar("invalidos", n, f"conteudo_id={r['conteudo_id']!r}")
        elif carga is None or carga < 0:
            cont.rejeitar("invalidos", n, f"carga_horaria_min={r['carga_horaria_min']!r}")
        elif data is None:
            cont.rejeitar("invalidos", n, f"data_publicacao={r['data_publicacao']!r}")
        elif tipo is None:
            cont.rejeitar("invalidos", n, f"tipo={r['tipo']!r}")
        elif nivel is None:
            cont.rejeitar("invalidos", n, f"nivel={r['nivel']!r}")
        elif conteudo_id in ids_vistos:
            cont.rejeitar("duplicados", n, f"conteudo_id={conteudo_id}")
        else:
            categoria = categorias.setdefault(chave(r["categoria"]), limpar_texto(r["categoria"]))
            tratado = {
                "conteudo_id": conteudo_id,
                "titulo": limpar_texto(r["titulo"]),
                "tipo": tipo,
                "categoria": categoria,
                "nivel": nivel,
                "carga_horaria_min": carga,
                "data_publicacao": data,
                "descricao": limpar_texto(r.get("descricao")),
                "autor": limpar_texto(r.get("autor")),
            }
            ids_vistos.add(conteudo_id)
            tratados.append(tratado)
            cont.aceitar(any(mudou(r.get(c), tratado[c]) for c in CAMPOS_CATALOGO))

    return tratados, cont


def tratar_interacoes(registros, publicacao: dict):
    """publicacao: conteudo_id -> data_publicacao dos conteudos validos."""
    cont = Contadores("interação")
    tratados, chaves_vistas = [], set()

    for n, r in enumerate(registros, start=1):
        campos = faltantes(r, ("usuario_id", "conteudo_id", "tipo_interacao", "data_hora"))
        if campos:
            cont.rejeitar("incompletos", n, f"campos ausentes: {', '.join(campos)}")
            continue

        usuario_id = converter_int(r["usuario_id"])
        conteudo_id = converter_int(r["conteudo_id"])
        tipo = TIPOS_INTERACAO.get(chave(r["tipo_interacao"]))
        data_hora = converter_datetime(r["data_hora"])
        tempo = converter_int(r.get("tempo_consumido"))
        percentual = converter_float(r.get("percentual_conclusao"))
        avaliacao = converter_int(r.get("avaliacao_atribuida"))
        chave_dup = (usuario_id, conteudo_id, tipo, data_hora)

        if usuario_id is None or usuario_id <= 0:
            cont.rejeitar("invalidos", n, f"usuario_id={r['usuario_id']!r}")
        elif conteudo_id is None or conteudo_id <= 0:
            cont.rejeitar("invalidos", n, f"conteudo_id={r['conteudo_id']!r}")
        elif conteudo_id not in publicacao:
            cont.rejeitar("invalidos", n, f"conteudo_id={conteudo_id} não existe no catálogo")
        elif tipo is None:
            cont.rejeitar("invalidos", n, f"tipo_interacao={r['tipo_interacao']!r}")
        elif data_hora is None:
            cont.rejeitar("invalidos", n, f"data_hora={r['data_hora']!r}")
        elif data_hora[:10] < publicacao[conteudo_id]:
            cont.rejeitar("invalidos", n, f"data_hora={data_hora} anterior à publicação ({publicacao[conteudo_id]})")
        elif data_hora > agora():
            cont.rejeitar("invalidos", n, f"data_hora={data_hora} no futuro")
        elif r.get("tempo_consumido") is not None and (tempo is None or tempo < 0):
            cont.rejeitar("invalidos", n, f"tempo_consumido={r['tempo_consumido']!r}")
        elif r.get("percentual_conclusao") is not None and (percentual is None or not 0 <= percentual <= 100):
            cont.rejeitar("invalidos", n, f"percentual_conclusao={r['percentual_conclusao']!r}")
        elif r.get("avaliacao_atribuida") is not None and (avaliacao is None or not 1 <= avaliacao <= 5):
            cont.rejeitar("invalidos", n, f"avaliacao_atribuida={r['avaliacao_atribuida']!r}")
        elif tipo == "conclusão" and percentual is not None and percentual < 100:
            cont.rejeitar("invalidos", n, f"conclusão com percentual_conclusao={percentual}")
        elif tipo == "avaliação" and avaliacao is None:
            cont.rejeitar("invalidos", n, "avaliação sem avaliacao_atribuida")
        elif chave_dup in chaves_vistas:
            cont.rejeitar("duplicados", n, f"usuario={usuario_id} conteudo={conteudo_id} {tipo} {data_hora}")
        else:
            tratado = {
                "usuario_id": usuario_id,
                "conteudo_id": conteudo_id,
                "tipo_interacao": tipo,
                "data_hora": data_hora,
                "tempo_consumido": tempo,
                "percentual_conclusao": percentual,
                "avaliacao_atribuida": avaliacao,
            }
            chaves_vistas.add(chave_dup)
            tratados.append(tratado)
            cont.aceitar(any(mudou(r.get(c), v) for c, v in tratado.items()))

    return tratados, cont


def tratar_comentarios(registros, publicacao: dict):
    cont = Contadores("comentário")
    tratados, chaves_vistas = [], set()

    for n, r in enumerate(registros, start=1):
        campos = faltantes(r, ("usuario_id", "conteudo_id", "avaliacao", "comentario", "data"))
        if campos:
            cont.rejeitar("incompletos", n, f"campos ausentes: {', '.join(campos)}")
            continue

        usuario_id = converter_int(r["usuario_id"])
        conteudo_id = converter_int(r["conteudo_id"])
        avaliacao = converter_int(r["avaliacao"])
        comentario = limpar_texto(r["comentario"])
        data = converter_data(r["data"])
        tags = r.get("tags") or []
        chave_dup = (usuario_id, conteudo_id, data, comentario)

        if usuario_id is None or usuario_id <= 0:
            cont.rejeitar("invalidos", n, f"usuario_id={r['usuario_id']!r}")
        elif conteudo_id is None or conteudo_id <= 0:
            cont.rejeitar("invalidos", n, f"conteudo_id={r['conteudo_id']!r}")
        elif conteudo_id not in publicacao:
            cont.rejeitar("invalidos", n, f"conteudo_id={conteudo_id} não existe no catálogo")
        elif avaliacao is None or not 1 <= avaliacao <= 5:
            cont.rejeitar("invalidos", n, f"avaliacao={r['avaliacao']!r}")
        elif data is None:
            cont.rejeitar("invalidos", n, f"data={r['data']!r}")
        elif data < publicacao[conteudo_id]:
            cont.rejeitar("invalidos", n, f"data={data} anterior à publicação ({publicacao[conteudo_id]})")
        elif data > hoje():
            cont.rejeitar("invalidos", n, f"data={data} no futuro")
        elif not isinstance(tags, list):
            cont.rejeitar("invalidos", n, f"tags={tags!r}")
        elif chave_dup in chaves_vistas:
            cont.rejeitar("duplicados", n, f"usuario={usuario_id} conteudo={conteudo_id} {data}")
        else:
            tratado = {
                "usuario_id": usuario_id,
                "conteudo_id": conteudo_id,
                "avaliacao": avaliacao,
                "comentario": comentario,
                "tags": [t.casefold() for t in map(limpar_texto, tags) if t],
                "data": data,
            }
            chaves_vistas.add(chave_dup)
            tratados.append(tratado)
            cont.aceitar(any(mudou(r.get(c), v) for c, v in tratado.items()))

    return tratados, cont


# --- saida (RF04) ---

def salvar_json(caminho: Path, dados):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def salvar_processados(pasta: Path, catalogo, interacoes, comentarios, rejeitados):
    pasta.mkdir(parents=True, exist_ok=True)
    with (pasta / "catalogo_processado.csv").open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=CAMPOS_CATALOGO, lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(catalogo)
    salvar_json(pasta / "interacoes_processadas.json", interacoes)
    salvar_json(pasta / "comentarios_processados.json", comentarios)
    salvar_json(pasta / "rejeitados.json", rejeitados)
    log.info("[RF04] processados salvos em %s", pasta)


# --- carga (RF06) ---

def carregar_postgres(pg, catalogo, interacoes, comentarios) -> dict:
    """Uma unica transacao: dimensoes por upsert (preserva embeddings e recomendacoes),
    interacoes substituidas por completo para nao manter registros que deixaram de ser validos."""
    with pg.transaction():
        categorias = {}
        for nome in sorted({r["categoria"] for r in catalogo}):
            row = pg.execute(
                "INSERT INTO categoria (nome) VALUES (%s) "
                "ON CONFLICT (nome) DO UPDATE SET nome = EXCLUDED.nome RETURNING categoria_id",
                (nome,),
            ).fetchone()
            categorias[nome] = row[0]

        # usuarios existem apenas dentro das interacoes e comentarios
        usuarios = sorted({r["usuario_id"] for r in interacoes} | {r["usuario_id"] for r in comentarios})
        pg.cursor().executemany(
            "INSERT INTO usuario (usuario_id) VALUES (%s) ON CONFLICT (usuario_id) DO NOTHING",
            [(u,) for u in usuarios],
        )

        pg.cursor().executemany(
            """
            INSERT INTO conteudo (conteudo_id, titulo, tipo, categoria_id, nivel,
                                  carga_horaria_min, data_publicacao, descricao, autor)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (conteudo_id) DO UPDATE SET
                titulo = EXCLUDED.titulo, tipo = EXCLUDED.tipo, categoria_id = EXCLUDED.categoria_id,
                nivel = EXCLUDED.nivel, carga_horaria_min = EXCLUDED.carga_horaria_min,
                data_publicacao = EXCLUDED.data_publicacao, descricao = EXCLUDED.descricao,
                autor = EXCLUDED.autor
            """,
            [
                (r["conteudo_id"], r["titulo"], r["tipo"], categorias[r["categoria"]], r["nivel"],
                 r["carga_horaria_min"], r["data_publicacao"], r["descricao"], r["autor"])
                for r in catalogo
            ],
        )

        pg.execute("DELETE FROM interacao")
        pg.cursor().executemany(
            """
            INSERT INTO interacao (usuario_id, conteudo_id, tipo_interacao, data_hora,
                                   tempo_consumido, percentual_conclusao, avaliacao_atribuida)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (r["usuario_id"], r["conteudo_id"], r["tipo_interacao"], r["data_hora"],
                 r["tempo_consumido"], r["percentual_conclusao"], r["avaliacao_atribuida"])
                for r in interacoes
            ],
        )

    carregados = {
        "categorias": len(categorias),
        "usuarios": len(usuarios),
        "conteudos": len(catalogo),
        "interacoes": len(interacoes),
    }
    log.info("[RF06] PostgreSQL: %s", carregados)
    return carregados


# --- orquestracao ---

def executar(cfg: dict, pg) -> dict:
    """Retorna o resumo da ingestao (RF05)."""
    arquivos = cfg["arquivos"]
    catalogo_bruto = ler_catalogo(Path(arquivos["catalogo"]))
    interacoes_brutas = ler_json(Path(arquivos["interacoes"]))
    comentarios_brutos = ler_json(Path(arquivos["comentarios"]))

    catalogo, c_cat = tratar_catalogo(catalogo_bruto)
    publicacao = {r["conteudo_id"]: r["data_publicacao"] for r in catalogo}
    interacoes, c_int = tratar_interacoes(interacoes_brutas, publicacao)
    comentarios, c_com = tratar_comentarios(comentarios_brutos, publicacao)
    for c in (c_cat, c_int, c_com):
        log.info("[RF03] %s: %s", c.fonte, dict(c))

    salvar_processados(
        Path(cfg["saida"]["processados"]), catalogo, interacoes, comentarios,
        c_cat.rejeitados + c_int.rejeitados + c_com.rejeitados,
    )
    carregados = carregar_postgres(pg, catalogo, interacoes, comentarios)

    resumo = {
        "registros_lidos": {
            "catalogo": len(catalogo_bruto),
            "interacoes": len(interacoes_brutas),
            "comentarios": len(comentarios_brutos),
        },
        **{k: c_cat[k] + c_int[k] + c_com[k] for k in c_cat},
        "detalhamento": {"catalogo": dict(c_cat), "interacoes": dict(c_int), "comentarios": dict(c_com)},
        "carregados": {"postgresql": carregados, "mongodb": None},
    }
    log.info("[RF05] lidos=%d válidos=%d inválidos=%d incompletos=%d duplicados=%d corrigidos=%d",
             sum(resumo["registros_lidos"].values()), resumo["validos"], resumo["invalidos"],
             resumo["incompletos"], resumo["duplicados"], resumo["corrigidos"])
    return resumo
