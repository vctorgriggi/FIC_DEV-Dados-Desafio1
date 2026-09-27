import json
import random
import re
import unittest
from pathlib import Path

from ferramentas.gerar_dados import BRUTOS, LOTE2, cpf_ficticio, ler_csv

CPF = re.compile(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$")


def dv_valido(cpf: str) -> bool:
    d = [int(c) for c in re.sub(r"\D", "", cpf)]
    d1 = (sum(v * p for v, p in zip(d[:9], range(10, 1, -1))) * 10 % 11) % 10
    d2 = (sum(v * p for v, p in zip(d[:10], range(11, 1, -1))) * 10 % 11) % 10
    return d[9] == d1 and d[10] == d2


class TestDadosFicticios(unittest.TestCase):
    """Garantias de que os dados pessoais gerados nao podem ser reais (RF32)."""

    def test_cpf_tem_formato_valido_e_digito_invalido(self):
        rng = random.Random(1)
        for _ in range(1000):
            cpf = cpf_ficticio(rng)
            self.assertRegex(cpf, CPF)
            self.assertFalse(dv_valido(cpf), cpf)

    def test_contatos_usam_dominio_e_ddd_reservados(self):
        for arquivo in (BRUTOS / "usuarios.csv", LOTE2 / "usuarios.csv"):
            for u in ler_csv(arquivo):
                if "@" in u["email"]:
                    self.assertTrue(u["email"].strip().lower().endswith(".example"), u["email"])
                self.assertTrue(u["telefone"].startswith("(00) "), u["telefone"])

    def test_texto_livre_so_tem_contatos_ficticios(self):
        for c in json.loads((LOTE2 / "comentarios.json").read_text(encoding="utf-8")):
            for email in re.findall(r"\S+@\S+", c["comentario"]):
                self.assertTrue(email.endswith(".example"), email)
            for tel in re.findall(r"\(\d{2}\)", c["comentario"]):
                self.assertEqual(tel, "(00)")

    def test_usuarios_do_desafio1_tem_cadastro(self):
        ids = {int(u["usuario_id"]) for u in ler_csv(BRUTOS / "usuarios.csv")}
        interacoes = json.loads((BRUTOS / "interacoes.json").read_text(encoding="utf-8"))
        self.assertTrue({r["usuario_id"] for r in interacoes} <= ids)


if __name__ == "__main__":
    unittest.main()
