"""RF08 (texto), RF10 (formula e classificacao). Rodar: python -m unittest"""

import unittest

from recomendacao import motor
from recomendacao.embeddings import texto_conteudo


class Texto(unittest.TestCase):
    def test_titulo_e_descricao(self):
        self.assertEqual(texto_conteudo("T", "D"), "T. D")
        self.assertEqual(texto_conteudo("T", None), "T")


class Formula(unittest.TestCase):
    def test_pontuacao(self):
        self.assertEqual(motor.pontuar(1.0, 1.0, 1), 100.0)
        self.assertEqual(motor.pontuar(0.5, 0.3, 1), 40.0)
        self.assertEqual(motor.pontuar(1.0, 1.0, 0), 0.0)   # concluido anula
        self.assertEqual(motor.pontuar(0.0, 0.0, 1), 0.0)

    def test_classificacao(self):
        self.assertEqual(motor.classificar(70, 1), "positivo")
        self.assertEqual(motor.classificar(69.9, 1), "estavel")
        self.assertEqual(motor.classificar(40.1, 1), "estavel")
        self.assertEqual(motor.classificar(40, 1), "negativo")
        self.assertEqual(motor.classificar(100, 0), "negativo")  # concluido
