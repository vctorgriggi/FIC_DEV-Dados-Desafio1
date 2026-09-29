"""Dados ficticios do Desafio 2, deterministicos (mesma semente, mesmos arquivos).

    docker compose run --rm beam -m ferramentas.gerar_dados                  # usuarios.csv, lote_2/ e falhas/
    docker compose run --rm beam -m ferramentas.gerar_dados --volume 200000  # + dados/volume/interacoes.json

Usa so a biblioteca padrao; tambem roda fora do Docker com "python -m ferramentas.gerar_dados".

Nao altera os arquivos do Desafio 1 (catalogo.csv, interacoes.json, comentarios.json) nem o snapshot
recomendacoes_desafio1.json, que e copia fixa de dados/processados/recomendacoes.json da entrega do Desafio 1.
Nenhum dado pessoal e real: e-mails no dominio reservado .example (RFC 2606), telefones com
DDD 00 (inexistente) e CPFs com digito verificador propositalmente invalido.
"""
import argparse
import csv
import json
import random
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BRUTOS = RAIZ / "dados/brutos"
LOTE2 = BRUTOS / "lote_2"
FALHAS = BRUTOS / "falhas"
VOLUME = RAIZ / "dados/volume"

SEMENTE = 2026
FIM_DESAFIO1 = date(2026, 8, 25)  # ultima interacao do Desafio 1
JANELA_LOTE2 = (datetime(2026, 8, 26), datetime(2026, 9, 26, 23, 59))

CAMPOS_USUARIO = ["usuario_id", "nome", "email", "cpf", "data_nascimento", "telefone",
                  "cidade", "uf", "data_cadastro", "atualizado_em"]
CAMPOS_CATALOGO = ["conteudo_id", "titulo", "tipo", "categoria", "nivel", "carga_horaria_min",
                   "data_publicacao", "descricao", "autor"]

NOMES = ["Ana", "Bruno", "Carla", "Diego", "Eduarda", "Felipe", "Gabriela", "Heitor", "Isabela", "João",
         "Karina", "Lucas", "Mariana", "Nicolas", "Olívia", "Pedro", "Rafaela", "Samuel", "Tatiane", "Vinícius",
         "Yasmin", "André", "Beatriz", "Caio", "Débora", "Enzo", "Fernanda", "Gustavo", "Helena", "Igor",
         "Juliana", "Leonardo", "Letícia", "Marcelo", "Natália", "Otávio", "Paula", "Renato", "Sofia", "Thiago"]
SOBRENOMES = ["Silva", "Souza", "Oliveira", "Santos", "Pereira", "Lima", "Carvalho", "Ferreira", "Rodrigues",
              "Almeida", "Costa", "Gomes", "Martins", "Araújo", "Ribeiro", "Barbosa", "Rocha", "Dias", "Moreira",
              "Cardoso", "Teixeira", "Nunes", "Mendes", "Freitas", "Correia", "Pinto", "Vieira", "Monteiro"]
CIDADES = [("São Paulo", "SP"), ("Campinas", "SP"), ("Rio de Janeiro", "RJ"), ("Niterói", "RJ"),
           ("Belo Horizonte", "MG"), ("Uberlândia", "MG"), ("Curitiba", "PR"), ("Londrina", "PR"),
           ("Porto Alegre", "RS"), ("Florianópolis", "SC"), ("Salvador", "BA"), ("Recife", "PE"),
           ("Fortaleza", "CE"), ("Belém", "PA"), ("Manaus", "AM"), ("Goiânia", "GO"), ("Brasília", "DF"),
           ("Vitória", "ES"), ("Natal", "RN"), ("Campo Grande", "MS")]

# distribuicao de tipos observada no Desafio 1
PESOS_TIPO = {"visualização": 351, "início": 187, "conclusão": 154, "curtida": 129,
              "avaliação": 89, "compartilhamento": 90}


def sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def cpf_ficticio(rng: random.Random) -> str:
    """Formato valido, digito verificador invalido: nao pode coincidir com um CPF real."""
    base = [rng.randint(0, 9) for _ in range(9)]
    d1 = (sum(v * p for v, p in zip(base, range(10, 1, -1))) * 10 % 11) % 10
    d2 = (sum(v * p for v, p in zip(base + [d1], range(11, 1, -1))) * 10 % 11) % 10
    d = base + [d1, (d2 + 1) % 10]
    s = "".join(map(str, d))
    return f"{s[:3]}.{s[3:6]}.{s[6:9]}-{s[9:]}"


def telefone_ficticio(rng: random.Random) -> str:
    return f"(00) 9{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}"


def data_aleatoria(rng: random.Random, inicio: date, fim: date) -> date:
    return inicio + timedelta(days=rng.randint(0, (fim - inicio).days))


def instante_aleatorio(rng: random.Random, inicio: datetime, fim: datetime) -> datetime:
    return inicio + timedelta(seconds=rng.randint(0, int((fim - inicio).total_seconds())))


def gravar_csv(caminho: Path, campos: list[str], linhas: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)


def gravar_json(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Anomalias:
    """Catalogo das anomalias injetadas; vira lote_2/ANOMALIAS.md (oraculo para testar o pipeline)."""

    def __init__(self):
        self.itens: list[tuple[str, str, str, str, str]] = []

    def add(self, codigo, arquivo, chave, descricao, tratamento):
        self.itens.append((codigo, arquivo, chave, descricao, tratamento))

    def markdown(self) -> str:
        linhas = [
            "# Lote 2 — anomalias injetadas",
            "",
            "Gerado por `python -m ferramentas.gerar_dados`; não editar à mão.",
            "Todo o restante do lote é válido. Use esta lista para conferir o que a Silver aceita,",
            "padroniza ou manda para a quarentena, e o que os testes de qualidade detectam.",
            "",
            "Tratamento esperado: **quarentena** (rejeitar com a regra violada), **padronizar** (aceitar",
            "normalizando), **dados mestres** (consolidar registros da mesma entidade), **reprocessar**",
            "(entra depois que a causa for corrigida na quarentena) e **LGPD** (aceitar protegendo o dado).",
            "",
            "| Código | Arquivo | Chave | Anomalia | Tratamento esperado |",
            "| --- | --- | --- | --- | --- |",
        ]
        linhas += [f"| {c} | `{a}` | {k} | {d} | {t} |" for c, a, k, d, t in self.itens]
        return "\n".join(linhas) + "\n"


def ler_csv(caminho: Path) -> list[dict]:
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def ler_desafio1():
    catalogo = ler_csv(BRUTOS / "catalogo.csv")
    interacoes = json.loads((BRUTOS / "interacoes.json").read_text(encoding="utf-8"))
    comentarios = json.loads((BRUTOS / "comentarios.json").read_text(encoding="utf-8"))
    recomendacoes = json.loads((BRUTOS / "recomendacoes_desafio1.json").read_text(encoding="utf-8"))
    return catalogo, interacoes, comentarios, recomendacoes


# ---------------------------------------------------------------
# usuarios.csv: cadastro ficticio dos 150 usuarios do Desafio 1
# ---------------------------------------------------------------

def novo_usuario(rng, usuario_id, primeira_atividade: date, emails_usados: set) -> dict:
    nome = rng.choice(NOMES)
    sobrenomes = rng.sample(SOBRENOMES, rng.choice([1, 2]))
    base = f"{sem_acento(nome)}.{sem_acento(sobrenomes[-1])}".lower()
    email, n = f"{base}@email.example", 1
    while email in emails_usados:
        n += 1
        email = f"{base}{n}@email.example"
    emails_usados.add(email)
    cidade, uf = rng.choice(CIDADES)
    cadastro = max(date(2024, 1, 1), primeira_atividade - timedelta(days=rng.randint(0, 200)))
    atualizado = datetime.combine(data_aleatoria(rng, cadastro, max(cadastro, FIM_DESAFIO1)),
                                  datetime.min.time()) + timedelta(seconds=rng.randint(0, 86399))
    return {
        "usuario_id": usuario_id,
        "nome": " ".join([nome, *sobrenomes]),
        "email": email,
        "cpf": cpf_ficticio(rng),
        "data_nascimento": data_aleatoria(rng, date(1965, 1, 1), date(2007, 12, 31)).isoformat(),
        "telefone": telefone_ficticio(rng),
        "cidade": cidade,
        "uf": uf,
        "data_cadastro": cadastro.isoformat(),
        "atualizado_em": atualizado.isoformat(sep=" "),
    }


def gerar_usuarios(rng, interacoes, comentarios) -> list[dict]:
    primeira: dict[int, date] = {}
    for r in interacoes:
        d = date.fromisoformat(r["data_hora"][:10])
        primeira[r["usuario_id"]] = min(primeira.get(r["usuario_id"], d), d)
    for r in comentarios:
        d = date.fromisoformat(r["data"])
        primeira[r["usuario_id"]] = min(primeira.get(r["usuario_id"], d), d)
    emails: set = set()
    return [novo_usuario(rng, uid, primeira[uid], emails) for uid in sorted(primeira)]


# ---------------------------------------------------------------
# lote 2: novos registros validos + anomalias catalogadas
# ---------------------------------------------------------------

def gerar_catalogo_lote2(rng, catalogo, an: Anomalias) -> tuple[list[dict], dict[int, date]]:
    arq = "lote_2/catalogo.csv"
    linhas, publicacao = [], {}
    for cid in range(1001, 1041):
        modelo = rng.choice(catalogo)
        pub = data_aleatoria(rng, date(2026, 7, 1), date(2026, 9, 10))
        linha = {**modelo, "conteudo_id": str(cid), "data_publicacao": pub.isoformat(),
                 "carga_horaria_min": str(max(5, int(int(modelo["carga_horaria_min"]) * rng.uniform(0.7, 1.3))))}
        linhas.append(linha)
        publicacao[cid] = pub

    linhas.append(dict(linhas[4]))
    an.add("L2-C01", arq, "conteudo_id=1005", "linha repetida idêntica", "quarentena (duplicado)")

    conflito = dict(linhas[9])
    conflito["nivel"] = "Avançado" if conflito["nivel"] != "Avançado" else "Básico"
    conflito["carga_horaria_min"] = str(int(conflito["carga_horaria_min"]) + 120)
    linhas.append(conflito)
    an.add("L2-C02", arq, "conteudo_id=1010", "mesmo id duas vezes com nível e carga diferentes",
           "sobrevivência: vale a última ocorrência; a anterior vai para a quarentena (CONFLITO_VERSAO) para revisão")

    atual = next(r for r in catalogo if r["conteudo_id"] == "7")
    linhas.append({**atual, "titulo": f"  {atual['titulo']}  (edição revisada)", "tipo": atual["tipo"].lower(),
                   "categoria": atual["categoria"].upper()})
    an.add("L2-C03", arq, "conteudo_id=7", "conteúdo do Desafio 1 reenviado com título revisado, espaços extras "
           "e caixa diferente em tipo e categoria", "padronizar; versão do lote 2 sobrevive à do Desafio 1")

    def invalido(cid, codigo, descricao, tratamento, **campos):
        modelo = rng.choice(catalogo)
        linha = {**modelo, "conteudo_id": str(cid), "data_publicacao": "2026-08-01", **campos}
        linhas.append(linha)
        an.add(codigo, arq, f"conteudo_id={cid}", descricao, tratamento)

    invalido(1041, "L2-C04", "carga_horaria_min negativa (-45)",
             "quarentena; corrigir para 45 e reprocessar (destrava L2-I13)", carga_horaria_min="-45")
    invalido(1042, "L2-C05", "tipo fora do domínio ('Webinar')", "quarentena", tipo="Webinar")
    invalido(1043, "L2-C06", "data_publicacao inexistente ('31/02/2026')", "quarentena", data_publicacao="31/02/2026")
    invalido(1044, "L2-C07", "titulo vazio", "quarentena (incompleto)", titulo="")
    invalido("abc", "L2-C08", "conteudo_id não numérico", "quarentena")
    invalido(1045, "L2-C09", "data_publicacao em formato alternativo ('2026/08/02')",
             "padronizar para 2026-08-02", data_publicacao="2026/08/02")
    invalido(1046, "L2-C10", "nivel sem acento e em minúsculas ('intermediario')",
             "padronizar para 'Intermediário'", nivel="intermediario")
    publicacao[1045] = date(2026, 8, 2)
    publicacao[1046] = date(2026, 8, 1)
    return linhas, publicacao


def gerar_usuarios_lote2(rng, usuarios, an: Anomalias) -> list[dict]:
    arq = "lote_2/usuarios.csv"
    emails = {u["email"] for u in usuarios}
    linhas = [novo_usuario(rng, uid, date(2026, 8, 20), emails) for uid in range(151, 171)]
    for u in linhas:
        u["data_cadastro"] = data_aleatoria(rng, date(2026, 8, 26), date(2026, 9, 5)).isoformat()
        u["atualizado_em"] = f"{u['data_cadastro']} 10:00:00"

    u12 = next(u for u in usuarios if u["usuario_id"] == 12)
    u30 = next(u for u in usuarios if u["usuario_id"] == 30)
    base = {"data_cadastro": "2026-09-01", "atualizado_em": "2026-09-01 09:30:00"}

    linhas.append({**u12, **base, "usuario_id": 171, "nome": sem_acento(u12["nome"]).upper(),
                   "email": u12["email"].replace("@", ".novo@"), "telefone": telefone_ficticio(rng)})
    an.add("L2-U01", arq, "usuario_id=171", "mesmo CPF do usuário 12, nome sem acento em maiúsculas e outro e-mail",
           "dados mestres (mesma pessoa que 12, correspondência por cpf_hash)")

    linhas.append({**u30, **base, "usuario_id": 172, "email": f"  {u30['email'].upper()} ",
                   "cpf": cpf_ficticio(rng), "cidade": "Santos", "uf": "SP"})
    an.add("L2-U02", arq, "usuario_id=172", "mesmo e-mail do usuário 30 (maiúsculas e espaços), outro CPF e cidade",
           "dados mestres (mesma pessoa que 30, correspondência por email_hash normalizado)")

    def invalido(uid, codigo, descricao, tratamento, **campos):
        linha = novo_usuario(rng, uid, date(2026, 9, 1), emails)
        linha.update(base)
        linha.update(campos)
        linhas.append(linha)
        an.add(codigo, arq, f"usuario_id={uid}", descricao, tratamento)

    invalido(173, "L2-U03", "e-mail sem @ ('maria.souza#email.example')", "quarentena",
             email="maria.souza#email.example")
    invalido(174, "L2-U04", "CPF com 10 dígitos", "quarentena", cpf="123.456.789-0")
    invalido(175, "L2-U05", "data_nascimento no futuro (2031-05-10)", "quarentena", data_nascimento="2031-05-10")
    invalido(176, "L2-U06", "nome vazio", "quarentena (incompleto)", nome="")
    linhas.append(dict(linhas[4]))
    an.add("L2-U07", arq, "usuario_id=155", "linha repetida idêntica", "quarentena (duplicado)")

    cidade, uf = next(c for c in CIDADES if c[0] != u12["cidade"])
    linhas.append({**u12, "cidade": cidade, "uf": uf, "atualizado_em": "2026-09-20 14:00:00"})
    an.add("L2-U08", arq, "usuario_id=12", f"cadastro do Desafio reenviado com nova cidade ({cidade}) "
           "e atualizado_em mais recente", "padronizar; versão mais recente sobrevive")
    invalido(177, "L2-U09", "usuário de 14 anos (nascido em 2012-03-15)",
             "LGPD: dado de adolescente (art. 14); aceitar e sinalizar no inventário", data_nascimento="2012-03-15")
    invalido(178, "L2-U10", "uf inexistente ('XX')", "quarentena", uf="XX")

    return linhas


def interacao_valida(rng, usuario_id, conteudo: dict, quando: datetime, tipo: str | None = None) -> dict:
    tipo = tipo or rng.choices(list(PESOS_TIPO), weights=list(PESOS_TIPO.values()))[0]
    faixa = {"visualização": (10, 85), "início": (1, 15), "conclusão": (100, 100), "curtida": (40, 99.9),
             "avaliação": (52, 99), "compartilhamento": (30, 99.7)}[tipo]
    pct = round(rng.uniform(*faixa), 1)
    carga = max(1, int(conteudo["carga_horaria_min"]))
    nota = None
    if tipo == "curtida":
        nota = 5
    elif tipo == "avaliação":
        nota = rng.choices([3, 4, 5], weights=[14, 30, 35])[0]
    elif tipo == "conclusão" and rng.random() > 0.1:
        nota = rng.choices([3, 4, 5], weights=[22, 52, 64])[0]
    return {"usuario_id": usuario_id, "conteudo_id": int(conteudo["conteudo_id"]), "tipo_interacao": tipo,
            "data_hora": quando.isoformat(timespec="seconds"),
            "tempo_consumido": max(1, round(carga * pct / 100)),
            "percentual_conclusao": float(pct), "avaliacao_atribuida": nota}


def gerar_interacoes_lote2(rng, catalogo, cat_lote2, publicacao_lote2, recomendacoes, an: Anomalias) -> list[dict]:
    arq = "lote_2/interacoes.json"
    conteudos = {int(r["conteudo_id"]): r for r in catalogo}
    conteudos.update({int(r["conteudo_id"]): r for r in cat_lote2[:40]})
    publicacao = {int(r["conteudo_id"]): date.fromisoformat(r["data_publicacao"]) for r in catalogo}
    publicacao.update(publicacao_lote2)
    usuarios = list(range(1, 171))
    inicio, fim = JANELA_LOTE2

    linhas = []
    while len(linhas) < 360:
        cid = rng.choice(list(conteudos))
        quando = instante_aleatorio(rng, max(inicio, datetime.combine(publicacao[cid], datetime.min.time())), fim)
        linhas.append(interacao_valida(rng, rng.choice(usuarios), conteudos[cid], quando))

    # conversao de recomendacao: pares recomendados no Desafio 1 consumidos depois da geracao
    for rec in rng.sample(recomendacoes, 40):
        gerado = datetime.fromisoformat(rec["gerado_em"])
        quando = instante_aleatorio(rng, gerado + timedelta(hours=1), fim)
        tipo = rng.choice(["visualização", "início", "conclusão"])
        linhas.append(interacao_valida(rng, rec["usuario_id"], conteudos[rec["conteudo_id"]], quando, tipo))
    an.add("L2-I00", arq, "40 pares de recomendacoes_desafio1.json",
           "interações em conteúdos recomendados, após `gerado_em` da recomendação (2026-09-13)",
           "válidas; tornam a conversão de recomendação mensurável")

    rng.shuffle(linhas)
    ref = linhas[0]

    def anomalia(codigo, descricao, tratamento, **campos):
        linha = {**interacao_valida(rng, rng.choice(usuarios[:150]), conteudos[rng.randint(1, 1000)],
                                    instante_aleatorio(rng, inicio, fim), "visualização"), **campos}
        for campo, valor in list(linha.items()):
            if valor is ...:
                del linha[campo]
        linhas.append(linha)
        an.add(codigo, arq, f"posição {len(linhas) - 1} do array", descricao, tratamento)

    anomalia("L2-I01", "usuario_id inexistente (999)", "quarentena (integridade referencial)", usuario_id=999)
    anomalia("L2-I02", "conteudo_id inexistente (5000)", "quarentena (integridade referencial)", conteudo_id=5000)
    anomalia("L2-I03", "tempo_consumido negativo (-15)", "quarentena", tempo_consumido=-15)
    anomalia("L2-I04", "percentual_conclusao acima de 100 (150)", "quarentena", percentual_conclusao=150.0)
    anomalia("L2-I05", "tipo_interacao fora do domínio ('download')", "quarentena", tipo_interacao="download")
    anomalia("L2-I06", "data_hora com mês 13", "quarentena", data_hora="2026-13-01T10:00:00")
    anomalia("L2-I07", "sem o campo conteudo_id", "quarentena (incompleto)", conteudo_id=...)
    linhas.append(dict(ref))
    an.add("L2-I08", arq, f"posição {len(linhas) - 1} do array", "cópia idêntica da posição 0", "quarentena (duplicado)")
    anomalia("L2-I09", "avaliacao_atribuida 0", "quarentena", avaliacao_atribuida=0)
    anomalia("L2-I10", "data_hora no futuro (2027-01-10)", "quarentena", data_hora="2027-01-10T09:00:00")
    anomalia("L2-I11", "conclusão com percentual 80", "quarentena (consistência)",
             tipo_interacao="conclusão", percentual_conclusao=80.0, avaliacao_atribuida=None)
    anomalia("L2-I12", "interação do usuário 171 (mesma pessoa que 12)",
             "dados mestres (conta para o mestre 12)", usuario_id=171)
    anomalia("L2-I13", "interação no conteúdo 1041, que está em quarentena (L2-C04)",
             "quarentena por referência; reprocessar depois de corrigir L2-C04",
             conteudo_id=1041, data_hora="2026-09-15T20:00:00")
    antigo = next(r for r in catalogo if r["data_publicacao"] >= "2026-06-01")
    anomalia("L2-I14", f"data_hora anterior à publicação do conteúdo {antigo['conteudo_id']} "
             f"({antigo['data_publicacao']})", "quarentena (regra cruzada do Desafio 1)",
             conteudo_id=int(antigo["conteudo_id"]), data_hora="2026-01-05T08:00:00")
    anomalia("L2-I15", "usuario_id como texto com espaços ('  42 ')", "padronizar para 42", usuario_id="  42 ")
    anomalia("L2-I16", "tipo_interacao em maiúsculas e sem acento ('VISUALIZACAO')",
             "padronizar para 'visualização'", tipo_interacao="VISUALIZACAO")
    return linhas


def gerar_comentarios_lote2(rng, comentarios, catalogo, an: Anomalias) -> list[dict]:
    arq = "lote_2/comentarios.json"
    textos = sorted({c["comentario"] for c in comentarios})
    tags = sorted({t for c in comentarios for t in c["tags"]})
    publicacao = {int(r["conteudo_id"]): r["data_publicacao"] for r in catalogo}

    def comentario(**campos):
        cid = rng.randint(1, 1000)
        return {"usuario_id": rng.randint(1, 170), "conteudo_id": cid,
                "avaliacao": rng.choices([3, 4, 5], weights=[15, 35, 50])[0], "comentario": rng.choice(textos),
                "tags": rng.sample(tags, rng.randint(1, 3)),
                "data": data_aleatoria(rng, max(date(2026, 8, 26), date.fromisoformat(publicacao[cid])),
                                       date(2026, 9, 26)).isoformat(), **campos}

    linhas = [comentario() for _ in range(110)]

    def anomalia(codigo, descricao, tratamento, **campos):
        linhas.append(comentario(**campos))
        an.add(codigo, arq, f"posição {len(linhas) - 1} do array", descricao, tratamento)

    anomalia("L2-K01", "avaliacao fora de 1–5 (7)", "quarentena", avaliacao=7)
    anomalia("L2-K02", "comentario vazio", "quarentena (incompleto)", comentario="")
    anomalia("L2-K03", "tags como texto ('python, dados') em vez de lista", "quarentena ou padronizar (decisão documentada)",
             tags="python, dados")
    anomalia("L2-K04", "e-mail no texto livre", "LGPD: substituir por [email] na Silver",
             comentario="Gostei muito! Quem quiser trocar material me chama em lucas.prado@email.example")
    anomalia("L2-K05", "telefone no texto livre", "LGPD: substituir por [telefone] na Silver",
             comentario="Excelente conteúdo, dúvidas no zap (00) 91234-5678")
    antigo = next(r for r in catalogo if r["data_publicacao"] >= "2026-06-01")
    anomalia("L2-K06", f"data anterior à publicação do conteúdo {antigo['conteudo_id']}",
             "quarentena (regra cruzada do Desafio 1)", conteudo_id=int(antigo["conteudo_id"]), data="2026-01-10")
    anomalia("L2-K07", "usuario_id inexistente (999)", "quarentena (integridade referencial)", usuario_id=999)
    linhas.append(dict(linhas[0]))
    an.add("L2-K08", arq, f"posição {len(linhas) - 1} do array", "cópia idêntica da posição 0", "quarentena (duplicado)")
    anomalia("L2-K09", "data inexistente ('2026-09-31')", "quarentena", data="2026-09-31")
    return linhas


def gerar_falhas(catalogo, interacoes) -> None:
    """Arquivos defeituosos para demonstrar falha de arquivo (RF23); fora do fluxo normal."""
    texto = json.dumps(interacoes[:20], ensure_ascii=False, indent=2)
    (FALHAS).mkdir(parents=True, exist_ok=True)
    (FALHAS / "interacoes_truncado.json").write_text(texto[: len(texto) // 2], encoding="utf-8")
    campos = [c for c in CAMPOS_CATALOGO if c != "categoria"]
    gravar_csv(FALHAS / "catalogo_sem_coluna_categoria.csv", campos,
               [{k: r[k] for k in campos} for r in catalogo[:20]])
    (FALHAS / "LEIAME.md").write_text(
        "# Arquivos defeituosos (RF23)\n\n"
        "Fora do fluxo normal. Para demonstrar uma falha de arquivo, copie um deles por cima da fonte correspondente "
        "em `lote_2/` e restaure depois (`git checkout -- dados/brutos/lote_2/`).\n\n"
        "| Arquivo | Defeito |\n| --- | --- |\n"
        "| `interacoes_truncado.json` | JSON cortado no meio (não faz parse) |\n"
        "| `catalogo_sem_coluna_categoria.csv` | cabeçalho sem a coluna obrigatória `categoria`. O Hop lê CSV por posição, "
        "então a Bronze aceita o arquivo e a Silver rejeita as linhas; o teste crítico Q08 (validade por arquivo) bloqueia a Gold. "
        "Veja `hop/evidencias/ambiente_limpo/06_falha_estrutura_do_arquivo.log` |\n\n"
        "Falha de conexão simulada: rodar uma etapa com `PG_PORT` apontando para uma porta sem serviço, "
        "ou com o `postgres` parado (`docker compose stop postgres`).\n",
        encoding="utf-8")


def gerar_volume(rng, catalogo, n: int) -> Path:
    publicacao = {int(r["conteudo_id"]): r for r in catalogo}
    ids = list(publicacao)
    inicio = datetime(2025, 1, 1)
    linhas = []
    for _ in range(n):
        cid = rng.choice(ids)
        pub = datetime.combine(date.fromisoformat(publicacao[cid]["data_publicacao"]), datetime.min.time())
        quando = instante_aleatorio(rng, max(inicio, pub), datetime(2026, 8, 25, 23, 59))
        linhas.append(interacao_valida(rng, rng.randint(1, 150), publicacao[cid], quando))
    destino = VOLUME / "interacoes.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(linhas, ensure_ascii=False), encoding="utf-8")
    return destino


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    args.add_argument("--volume", type=int, default=0, help="gera dados/volume/interacoes.json com N interações válidas")
    n_volume = args.parse_args().volume

    rng = random.Random(SEMENTE)
    catalogo, interacoes, comentarios, recomendacoes = ler_desafio1()
    an = Anomalias()

    usuarios = gerar_usuarios(rng, interacoes, comentarios)
    gravar_csv(BRUTOS / "usuarios.csv", CAMPOS_USUARIO, usuarios)

    cat_lote2, pub_lote2 = gerar_catalogo_lote2(rng, catalogo, an)
    gravar_csv(LOTE2 / "catalogo.csv", CAMPOS_CATALOGO, cat_lote2)
    gravar_csv(LOTE2 / "usuarios.csv", CAMPOS_USUARIO, gerar_usuarios_lote2(rng, usuarios, an))
    inter = gerar_interacoes_lote2(rng, catalogo, cat_lote2, pub_lote2, recomendacoes, an)
    gravar_json(LOTE2 / "interacoes.json", inter)
    coment = gerar_comentarios_lote2(rng, comentarios, catalogo, an)
    gravar_json(LOTE2 / "comentarios.json", coment)
    (LOTE2 / "ANOMALIAS.md").write_text(an.markdown(), encoding="utf-8")
    gerar_falhas(catalogo, interacoes)

    print(f"usuarios.csv: {len(usuarios)} | lote_2: catalogo {len(cat_lote2)}, interacoes {len(inter)}, "
          f"comentarios {len(coment)}, anomalias {len(an.itens)}")
    if n_volume:
        print(f"volume: {gerar_volume(random.Random(SEMENTE + 1), catalogo, n_volume)} ({n_volume} interações)")


if __name__ == "__main__":
    main()
