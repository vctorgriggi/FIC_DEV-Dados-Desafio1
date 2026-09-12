import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
_PADRAO_ENV = re.compile(r"\$\{(\w+)(?::([^}]*))?\}")


def _interpolar(valor):
    if isinstance(valor, dict):
        return {k: _interpolar(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_interpolar(v) for v in valor]
    if isinstance(valor, str):
        m = _PADRAO_ENV.fullmatch(valor)
        if m:
            nome, padrao = m.groups()
            resolvido = os.environ.get(nome, padrao)
            if resolvido is None:
                raise KeyError(f"variavel de ambiente obrigatoria nao definida: {nome}")
            # so converte para int quando o padrao tambem e numerico (portas); senhas ficam texto
            return int(resolvido) if padrao and padrao.isdigit() and resolvido.isdigit() else resolvido
    return valor


def carregar(caminho: str | Path = "config.yaml") -> dict:
    load_dotenv(RAIZ / ".env")
    with open(RAIZ / caminho, encoding="utf-8") as f:
        return _interpolar(yaml.safe_load(f))
