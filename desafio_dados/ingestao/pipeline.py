
"""RF02-RF06: le fontes, valida, trata, grava processados e carrega no PostgreSQL.
    Retorna o resumo da ingestao no formato exigido pelo RF05."""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path


log = logging.getLogger("ingestao")


TIPOS_CONTEUDO = {
    "curso",
    "vídeo",
    "artigo",
    "podcast",
}

NIVEIS = {
    "básico",
    "intermediário",
    "avançado",
}

TIPOS_INTERACAO = {
    "visualização",
    "início",
    "conclusão",
    "curtida",
    "avaliação",
    "compartilhamento",
}


def limpar_texto(valor):
    """Remove espaços extras e retorna texto padronizado."""
    if valor is None:
        return None

    valor = str(valor).strip()

    if not valor:
        return None

    return valor


def normalizar_chave(valor):
    """Normaliza texto para comparação."""
    valor = limpar_texto(valor)

    if valor is None:
        return None

    return valor.lower()


def converter_int(valor):
    """Converte um valor para inteiro."""
    if valor is None or str(valor).strip() == "":
        return None

    try:
        return int(float(str(valor).strip()))
    except (ValueError, TypeError):
        return None


def converter_float(valor):
    """Converte um valor para float."""
    if valor is None or str(valor).strip() == "":
        return None

    try:
        return float(str(valor).strip())
    except (ValueError, TypeError):
        return None


def converter_data(valor):
    """Converte data para o formato YYYY-MM-DD."""
    valor = limpar_texto(valor)

    if valor is None:
        return None

    formatos = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%Y/%m/%d",
    ]

    for formato in formatos:
        try:
            return datetime.strptime(valor, formato).date().isoformat()
        except ValueError:
            continue

    return None


def converter_datetime(valor):
    """Valida e padroniza data/hora ISO."""
    valor = limpar_texto(valor)

    if valor is None:
        return None

    try:
        data = datetime.fromisoformat(valor)
        return data.isoformat(timespec="seconds")
    except ValueError:
        return None


def salvar_json(caminho, dados):
    """Salva JSON formatado."""
    caminho.parent.mkdir(parents=True, exist_ok=True)

    caminho.write_text(
        json.dumps(
            dados,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def ler_catalogo(caminho):
    """RF02 - Lê o catálogo CSV."""
    registros = []

    with caminho.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as arquivo:

        leitor = csv.DictReader(arquivo)

        for linha in leitor:
            registros.append(dict(linha))

    log.info(
        "[RF02] catálogo lido: arquivo=%s registros=%d",
        caminho,
        len(registros)
    )

    return registros


def ler_json(caminho):
    """RF02 - Lê um arquivo JSON contendo uma lista de registros."""
    with caminho.open("r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)

    if not isinstance(dados, list):
        raise ValueError(
            f"O arquivo {caminho} deveria conter uma lista JSON."
        )

    log.info(
        "[RF02] JSON lido: arquivo=%s registros=%d",
        caminho,
        len(dados)
    )

    return dados


def tratar_catalogo(registros):
    """
    RF03 + RF04

    Valida e padroniza registros do catálogo.
    """

    tratados = []
    ids_vistos = set()

    contadores = {
        "validos": 0,
        "invalidos": 0,
        "incompletos": 0,
        "duplicados": 0,
        "corrigidos": 0,
    }

    for numero, registro in enumerate(registros, start=1):

        conteudo_id = registro.get("conteudo_id")

        if conteudo_id is None:
            conteudo_id = registro.get("conteudoo_id")

        titulo = limpar_texto(registro.get("titulo"))
        tipo = limpar_texto(registro.get("tipo"))
        categoria = limpar_texto(registro.get("categoria"))
        nivel = limpar_texto(registro.get("nivel"))
        carga_horaria = registro.get("carga_horaria_min")
        data_publicacao = registro.get("data_publicacao")
        descricao = limpar_texto(registro.get("descricao"))
        autor = limpar_texto(registro.get("autor"))

        corrigido = False

        campos_obrigatorios = {
            "conteudo_id": conteudo_id,
            "titulo": titulo,
            "tipo": tipo,
            "categoria": categoria,
            "nivel": nivel,
            "carga_horaria_min": carga_horaria,
            "data_publicacao": data_publicacao,
        }

        campos_faltantes = [
            campo
            for campo, valor in campos_obrigatorios.items()
            if limpar_texto(valor) is None
        ]

        if campos_faltantes:
            contadores["incompletos"] += 1

            log.warning(
                "[RF03] catálogo linha %d incompleta: campos=%s",
                numero,
                ", ".join(campos_faltantes)
            )

            continue

        id_convertido = converter_int(conteudo_id)
        carga_convertida = converter_int(carga_horaria)
        data_convertida = converter_data(data_publicacao)

        if id_convertido is None:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] catálogo linha %d inválida: conteudo_id inválido",
                numero
            )

            continue

        if id_convertido != conteudo_id:
            corrigido = True

        if carga_convertida is None:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] catálogo linha %d inválida: carga_horaria_min inválida",
                numero
            )

            continue

        if carga_convertida < 0:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] catálogo linha %d inválida: carga horária negativa",
                numero
            )

            continue

        if data_convertida is None:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] catálogo linha %d inválida: data_publicacao inválida",
                numero
            )

            continue

        tipo_normalizado = tipo.lower()
        nivel_normalizado = nivel.lower()

        mapa_tipo = {
            "curso": "Curso",
            "vídeo": "Vídeo",
            "video": "Vídeo",
            "artigo": "Artigo",
            "podcast": "Podcast",
        }

        mapa_nivel = {
            "básico": "Básico",
            "basico": "Básico",
            "intermediário": "Intermediário",
            "intermediario": "Intermediário",
            "avançado": "Avançado",
            "avancado": "Avançado",
        }

        if tipo_normalizado not in mapa_tipo:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] catálogo linha %d inválida: tipo=%s",
                numero,
                tipo
            )

            continue

        if nivel_normalizado not in mapa_nivel:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] catálogo linha %d inválida: nivel=%s",
                numero,
                nivel
            )

            continue

        tipo_normalizado = mapa_tipo[tipo_normalizado]
        nivel_normalizado = mapa_nivel[nivel_normalizado]

        if tipo_normalizado != tipo:
            corrigido = True

        if nivel_normalizado != nivel:
            corrigido = True

        # ----------------------------------------------------
        # Categoria
        # ----------------------------------------------------

        categoria_normalizada = " ".join(categoria.split())

        if categoria_normalizada != categoria:
            corrigido = True

        # ----------------------------------------------------
        # Duplicidade
        # ----------------------------------------------------

        if id_convertido in ids_vistos:
            contadores["duplicados"] += 1

            log.warning(
                "[RF03] catálogo linha %d duplicada: conteudo_id=%s",
                numero,
                id_convertido
            )

            continue

        ids_vistos.add(id_convertido)

        registro_tratado = {
            "conteudo_id": id_convertido,
            "titulo": titulo,
            "tipo": tipo_normalizado,
            "categoria": categoria_normalizada,
            "nivel": nivel_normalizado,
            "carga_horaria_min": carga_convertida,
            "data_publicacao": data_convertida,
            "descricao": descricao,
            "autor": autor,
        }

        tratados.append(registro_tratado)

        contadores["validos"] += 1

        if corrigido:
            contadores["corrigidos"] += 1

    return tratados, contadores


def tratar_interacoes(registros, conteudos_validos):
    """
    RF03 + RF04

    Valida e padroniza as interações.
    """

    tratados = []

    contadores = {
        "validos": 0,
        "invalidos": 0,
        "incompletos": 0,
        "duplicados": 0,
        "corrigidos": 0,
    }

    chaves_vistas = set()

    for numero, registro in enumerate(registros, start=1):

        usuario_id = registro.get("usuario_id")
        conteudo_id = registro.get("conteudo_id")
        tipo_interacao = registro.get("tipo_interacao")
        data_hora = registro.get("data_hora")
        tempo_consumido = registro.get("tempo_consumido")
        percentual = registro.get("percentual_conclusao")
        avaliacao = registro.get("avaliacao_atribuida")

        campos_obrigatorios = {
            "usuario_id": usuario_id,
            "conteudo_id": conteudo_id,
            "tipo_interacao": tipo_interacao,
            "data_hora": data_hora,
        }

        campos_faltantes = [
            campo
            for campo, valor in campos_obrigatorios.items()
            if limpar_texto(valor) is None
        ]

        if campos_faltantes:
            contadores["incompletos"] += 1

            log.warning(
                "[RF03] interação linha %d incompleta: campos=%s",
                numero,
                ", ".join(campos_faltantes)
            )

            continue

        usuario_convertido = converter_int(usuario_id)
        conteudo_convertido = converter_int(conteudo_id)

        if usuario_convertido is None or usuario_convertido <= 0:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] interação linha %d inválida: usuario_id=%s",
                numero,
                usuario_id
            )

            continue

        if conteudo_convertido is None or conteudo_convertido <= 0:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] interação linha %d inválida: conteudo_id=%s",
                numero,
                conteudo_id
            )

            continue

        if conteudo_convertido not in conteudos_validos:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] interação linha %d inválida: "
                "conteudo_id=%s não existe no catálogo",
                numero,
                conteudo_convertido
            )

            continue

        tipo_normalizado = limpar_texto(tipo_interacao)

        mapa_interacao = {
            "visualização": "visualização",
            "visualizacao": "visualização",
            "início": "início",
            "inicio": "início",
            "conclusão": "conclusão",
            "conclusao": "conclusão",
            "curtida": "curtida",
            "avaliação": "avaliação",
            "avaliacao": "avaliação",
            "compartilhamento": "compartilhamento",
        }

        chave_tipo = normalizar_chave(tipo_normalizado)

        if chave_tipo not in mapa_interacao:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] interação linha %d inválida: tipo_interacao=%s",
                numero,
                tipo_interacao
            )

            continue

        tipo_normalizado = mapa_interacao[chave_tipo]

        data_convertida = converter_datetime(data_hora)

        if data_convertida is None:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] interação linha %d inválida: data_hora=%s",
                numero,
                data_hora
            )

            continue

        tempo_convertido = converter_int(tempo_consumido)

        if tempo_consumido is not None and tempo_convertido is None:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] interação linha %d inválida: tempo_consumido=%s",
                numero,
                tempo_consumido
            )

            continue

        if tempo_convertido is not None and tempo_convertido < 0:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] interação linha %d inválida: "
                "tempo_consumido negativo",
                numero
            )

            continue

        percentual_convertido = converter_float(percentual)

        if percentual is not None and percentual_convertido is None:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] interação linha %d inválida: "
                "percentual_conclusao=%s",
                numero,
                percentual
            )

            continue

        if (
            percentual_convertido is not None
            and not 0 <= percentual_convertido <= 100
        ):
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] interação linha %d inválida: "
                "percentual_conclusao fora do intervalo",
                numero
            )

            continue

        avaliacao_convertida = None

        if avaliacao is not None and str(avaliacao).strip() != "":
            avaliacao_convertida = converter_int(avaliacao)

            if avaliacao_convertida is None:
                contadores["invalidos"] += 1

                log.warning(
                    "[RF03] interação linha %d inválida: "
                    "avaliacao_atribuida=%s",
                    numero,
                    avaliacao
                )

                continue

            if not 1 <= avaliacao_convertida <= 5:
                contadores["invalidos"] += 1

                log.warning(
                    "[RF03] interação linha %d inválida: "
                    "avaliação fora do intervalo 1-5",
                    numero
                )

                continue

        chave = (
            usuario_convertido,
            conteudo_convertido,
            tipo_normalizado,
            data_convertida,
        )

        if chave in chaves_vistas:
            contadores["duplicados"] += 1

            log.warning(
                "[RF03] interação linha %d duplicada",
                numero
            )

            continue

        chaves_vistas.add(chave)

        corrigido = (
            usuario_convertido != usuario_id
            or conteudo_convertido != conteudo_id
            or tipo_normalizado != tipo_interacao
            or data_convertida != data_hora
        )

        registro_tratado = {
            "usuario_id": usuario_convertido,
            "conteudo_id": conteudo_convertido,
            "tipo_interacao": tipo_normalizado,
            "data_hora": data_convertida,
            "tempo_consumido": tempo_convertido,
            "percentual_conclusao": percentual_convertido,
            "avaliacao_atribuida": avaliacao_convertida,
        }

        tratados.append(registro_tratado)

        contadores["validos"] += 1

        if corrigido:
            contadores["corrigidos"] += 1

    return tratados, contadores

def tratar_comentarios(registros, conteudos_validos):
    """
    RF03 + RF04

    Valida e padroniza comentários.

    Os comentários posteriormente são enviados para o MongoDB
    pelo módulo mongodb/comentarios.py.
    """

    tratados = []

    contadores = {
        "validos": 0,
        "invalidos": 0,
        "incompletos": 0,
        "duplicados": 0,
        "corrigidos": 0,
    }

    chaves_vistas = set()

    for numero, registro in enumerate(registros, start=1):

        usuario_id = registro.get("usuario_id")
        conteudo_id = registro.get("conteudo_id")
        avaliacao = registro.get("avaliacao")
        comentario = registro.get("comentario")
        tags = registro.get("tags")
        data = registro.get("data")

        campos_obrigatorios = {
            "usuario_id": usuario_id,
            "conteudo_id": conteudo_id,
            "avaliacao": avaliacao,
            "comentario": comentario,
            "data": data,
        }

        campos_faltantes = [
            campo
            for campo, valor in campos_obrigatorios.items()
            if limpar_texto(valor) is None
        ]

        if campos_faltantes:
            contadores["incompletos"] += 1

            log.warning(
                "[RF03] comentário linha %d incompleto: campos=%s",
                numero,
                ", ".join(campos_faltantes)
            )

            continue

        usuario_convertido = converter_int(usuario_id)
        conteudo_convertido = converter_int(conteudo_id)
        avaliacao_convertida = converter_int(avaliacao)

        if usuario_convertido is None or usuario_convertido <= 0:
            contadores["invalidos"] += 1
            log.warning(
                "[RF03] comentário linha %d: usuario_id inválido",
                numero
            )
            continue

        if conteudo_convertido is None or conteudo_convertido <= 0:
            contadores["invalidos"] += 1
            log.warning(
                "[RF03] comentário linha %d: conteudo_id inválido",
                numero
            )
            continue

        if conteudo_convertido not in conteudos_validos:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] comentário linha %d: "
                "conteudo_id=%s não existe no catálogo",
                numero,
                conteudo_convertido
            )

            continue

        if avaliacao_convertida is None:
            contadores["invalidos"] += 1
            log.warning(
                "[RF03] comentário linha %d: avaliação inválida",
                numero
            )
            continue

        if not 1 <= avaliacao_convertida <= 5:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] comentário linha %d: "
                "avaliação fora do intervalo 1-5",
                numero
            )

            continue

        comentario_normalizado = " ".join(
            str(comentario).strip().split()
        )

        if not comentario_normalizado:
            contadores["incompletos"] += 1
            continue

        data_convertida = converter_data(data)

        if data_convertida is None:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] comentário linha %d: data inválida",
                numero
            )

            continue

        if tags is None:
            tags_normalizadas = []
        elif isinstance(tags, list):
            tags_normalizadas = [
                str(tag).strip().lower()
                for tag in tags
                if str(tag).strip()
            ]
        else:
            contadores["invalidos"] += 1

            log.warning(
                "[RF03] comentário linha %d: tags inválidas",
                numero
            )

            continue

        chave = (
            usuario_convertido,
            conteudo_convertido,
            data_convertida,
            comentario_normalizado,
        )

        if chave in chaves_vistas:
            contadores["duplicados"] += 1

            log.warning(
                "[RF03] comentário linha %d duplicado",
                numero
            )

            continue

        chaves_vistas.add(chave)

        corrigido = (
            usuario_convertido != usuario_id
            or conteudo_convertido != conteudo_id
            or avaliacao_convertida != avaliacao
            or comentario_normalizado != comentario
            or data_convertida != data
        )

        registro_tratado = {
            "usuario_id": usuario_convertido,
            "conteudo_id": conteudo_convertido,
            "avaliacao": avaliacao_convertida,
            "comentario": comentario_normalizado,
            "tags": tags_normalizadas,
            "data": data_convertida,
        }

        tratados.append(registro_tratado)

        contadores["validos"] += 1

        if corrigido:
            contadores["corrigidos"] += 1

    return tratados, contadores


def salvar_processados(cfg, catalogo, interacoes, comentarios):
    """RF04 - Salva os dados tratados em dados/processados."""

    pasta = Path(cfg["saida"]["processados"])
    pasta.mkdir(parents=True, exist_ok=True)

    caminho_catalogo = pasta / "catalogo_processado.csv"

    campos_catalogo = [
        "conteudo_id",
        "titulo",
        "tipo",
        "categoria",
        "nivel",
        "carga_horaria_min",
        "data_publicacao",
        "descricao",
        "autor",
    ]

    with caminho_catalogo.open(
        "w",
        encoding="utf-8",
        newline=""
    ) as arquivo:

        escritor = csv.DictWriter(
            arquivo,
            fieldnames=campos_catalogo
        )

        escritor.writeheader()
        escritor.writerows(catalogo)

    caminho_interacoes = pasta / "interacoes_processadas.json"

    salvar_json(
        caminho_interacoes,
        interacoes
    )

    caminho_comentarios = pasta / "comentarios_processados.json"

    salvar_json(
        caminho_comentarios,
        comentarios
    )

    log.info(
        "[RF04] dados processados salvos em %s",
        pasta
    )

def carregar_postgres(pg, catalogo, interacoes):
    """
    RF06 - Carrega os dados estruturados no PostgreSQL.

    A operação utiliza uma única transação.
    """

    categorias = {}

    for registro in catalogo:
        categoria = registro["categoria"]

        cursor = pg.execute(
            """
            INSERT INTO categoria (nome)
            VALUES (%s)
            ON CONFLICT (nome)
            DO UPDATE SET nome = EXCLUDED.nome
            RETURNING categoria_id
            """,
            (categoria,)
        )

        categoria_id = cursor.fetchone()[0]
        categorias[categoria] = categoria_id

    usuarios = set()

    for registro in interacoes:
        usuarios.add(registro["usuario_id"])

    for usuario_id in sorted(usuarios):
        pg.execute(
            """
            INSERT INTO usuario (usuario_id)
            VALUES (%s)
            ON CONFLICT (usuario_id) DO NOTHING
            """,
            (usuario_id,)
        )

    for registro in catalogo:

        pg.execute(
            """
            INSERT INTO conteudo (
                conteudo_id,
                titulo,
                tipo,
                categoria_id,
                nivel,
                carga_horaria_min,
                data_publicacao,
                descricao,
                autor
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            ON CONFLICT (conteudo_id)
            DO UPDATE SET
                titulo = EXCLUDED.titulo,
                tipo = EXCLUDED.tipo,
                categoria_id = EXCLUDED.categoria_id,
                nivel = EXCLUDED.nivel,
                carga_horaria_min = EXCLUDED.carga_horaria_min,
                data_publicacao = EXCLUDED.data_publicacao,
                descricao = EXCLUDED.descricao,
                autor = EXCLUDED.autor
            """,
            (
                registro["conteudo_id"],
                registro["titulo"],
                registro["tipo"],
                categorias[registro["categoria"]],
                registro["nivel"],
                registro["carga_horaria_min"],
                registro["data_publicacao"],
                registro["descricao"],
                registro["autor"],
            )
        )

    carregadas = 0

    for registro in interacoes:

        pg.execute(
            """
            INSERT INTO interacao (
                usuario_id,
                conteudo_id,
                tipo_interacao,
                data_hora,
                tempo_consumido,
                percentual_conclusao,
                avaliacao_atribuida
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT (
                usuario_id,
                conteudo_id,
                tipo_interacao,
                data_hora
            )
            DO NOTHING
            """,
            (
                registro["usuario_id"],
                registro["conteudo_id"],
                registro["tipo_interacao"],
                registro["data_hora"],
                registro["tempo_consumido"],
                registro["percentual_conclusao"],
                registro["avaliacao_atribuida"],
            )
        )

        carregadas += 1

    pg.commit()

    log.info(
        "[RF06] PostgreSQL carregado: "
        "categorias=%d usuários=%d conteúdos=%d interações=%d",
        len(categorias),
        len(usuarios),
        len(catalogo),
        carregadas
    )

    return {
        "categorias": len(categorias),
        "usuarios": len(usuarios),
        "conteudos": len(catalogo),
        "interacoes": carregadas,
    }


# ============================================================
# EXECUÇÃO PRINCIPAL DA INGESTÃO
# ============================================================

def executar(cfg: dict, pg) -> dict:
    """
    RF02-RF06.

    Executa:
        1. leitura;
        2. validação;
        3. tratamento;
        4. persistência dos processados;
        5. carga no PostgreSQL;
        6. geração do resumo.
    """

    log.info("[RF02] iniciando leitura das fontes")

    caminho_catalogo = Path(cfg["arquivos"]["catalogo"])
    caminho_interacoes = Path(cfg["arquivos"]["interacoes"])
    caminho_comentarios = Path(cfg["arquivos"]["comentarios"])

    # RF02 - Leitura
   

    catalogo_bruto = ler_catalogo(caminho_catalogo)
    interacoes_brutas = ler_json(caminho_interacoes)
    comentarios_brutos = ler_json(caminho_comentarios)

    registros_lidos = {
        "catalogo": len(catalogo_bruto),
        "interacoes": len(interacoes_brutas),
        "comentarios": len(comentarios_brutos),
    }

   
    # RF03 + RF04 - Validação e tratamento
    

    log.info("[RF03] iniciando validação do catálogo")

    catalogo, resultado_catalogo = tratar_catalogo(
        catalogo_bruto
    )

    conteudos_validos = {
        registro["conteudo_id"]
        for registro in catalogo
    }

    log.info(
        "[RF03] catálogo: válidos=%d inválidos=%d "
        "incompletos=%d duplicados=%d corrigidos=%d",
        resultado_catalogo["validos"],
        resultado_catalogo["invalidos"],
        resultado_catalogo["incompletos"],
        resultado_catalogo["duplicados"],
        resultado_catalogo["corrigidos"],
    )

    log.info("[RF03] iniciando validação das interações")

    interacoes, resultado_interacoes = tratar_interacoes(
        interacoes_brutas,
        conteudos_validos
    )

    log.info(
        "[RF03] interações: válidos=%d inválidos=%d "
        "incompletos=%d duplicados=%d corrigidos=%d",
        resultado_interacoes["validos"],
        resultado_interacoes["invalidos"],
        resultado_interacoes["incompletos"],
        resultado_interacoes["duplicados"],
        resultado_interacoes["corrigidos"],
    )

    log.info("[RF03] iniciando validação dos comentários")

    comentarios, resultado_comentarios = tratar_comentarios(
        comentarios_brutos,
        conteudos_validos
    )

    log.info(
        "[RF03] comentários: válidos=%d inválidos=%d "
        "incompletos=%d duplicados=%d corrigidos=%d",
        resultado_comentarios["validos"],
        resultado_comentarios["invalidos"],
        resultado_comentarios["incompletos"],
        resultado_comentarios["duplicados"],
        resultado_comentarios["corrigidos"],
    )

    # Continuacao RF04 - Salvar dados processados

    salvar_processados(
        cfg,
        catalogo,
        interacoes,
        comentarios
    )

    # RF06 - PostgreSQL

    dados_postgres = carregar_postgres(
        pg,
        catalogo,
        interacoes
    )

    # RF05 - Consolidar resumo

    resumo = {
        "registros_lidos": registros_lidos,

        "validos": (
            resultado_catalogo["validos"]
            + resultado_interacoes["validos"]
            + resultado_comentarios["validos"]
        ),

        "invalidos": (
            resultado_catalogo["invalidos"]
            + resultado_interacoes["invalidos"]
            + resultado_comentarios["invalidos"]
        ),

        "incompletos": (
            resultado_catalogo["incompletos"]
            + resultado_interacoes["incompletos"]
            + resultado_comentarios["incompletos"]
        ),

        "duplicados": (
            resultado_catalogo["duplicados"]
            + resultado_interacoes["duplicados"]
            + resultado_comentarios["duplicados"]
        ),

        "corrigidos": (
            resultado_catalogo["corrigidos"]
            + resultado_interacoes["corrigidos"]
            + resultado_comentarios["corrigidos"]
        ),

        "detalhamento": {
            "catalogo": resultado_catalogo,
            "interacoes": resultado_interacoes,
            "comentarios": resultado_comentarios,
        },

        "carregados": {
            "postgresql": dados_postgres,
            "mongodb": 0,
        },
    }

    log.info(
        "[RF05] resumo da ingestão: "
        "lidos=%d válidos=%d inválidos=%d "
        "incompletos=%d duplicados=%d corrigidos=%d",
        sum(registros_lidos.values()),
        resumo["validos"],
        resumo["invalidos"],
        resumo["incompletos"],
        resumo["duplicados"],
        resumo["corrigidos"],
    )

    return resumo
    