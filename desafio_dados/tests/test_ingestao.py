"""RF03/RF04 com registros sujos. Rodar: python -m unittest"""

import unittest

from ingestao import pipeline as p

CATALOGO_OK = {
    "conteudo_id": "1", "titulo": "Título", "tipo": "Curso", "categoria": "Banco de Dados",
    "nivel": "Básico", "carga_horaria_min": "10", "data_publicacao": "2025-01-01",
    "descricao": "d", "autor": "a",
}
INTERACAO_OK = {
    "usuario_id": 1, "conteudo_id": 1, "tipo_interacao": "visualização",
    "data_hora": "2026-01-01T10:00:00", "tempo_consumido": 5,
    "percentual_conclusao": 50.0, "avaliacao_atribuida": None,
}
COMENTARIO_OK = {
    "usuario_id": 1, "conteudo_id": 1, "avaliacao": 5, "comentario": "Bom",
    "tags": ["Python", " lgpd "], "data": "2026-01-01",
}


class Conversao(unittest.TestCase):
    def test_int_estrito(self):
        self.assertEqual(p.converter_int("7"), 7)
        self.assertEqual(p.converter_int("7.0"), 7)
        self.assertEqual(p.converter_int(7.0), 7)
        self.assertIsNone(p.converter_int("7.9"))
        self.assertIsNone(p.converter_int(7.9))
        self.assertIsNone(p.converter_int("abc"))
        self.assertIsNone(p.converter_int(True))

    def test_data(self):
        self.assertEqual(p.converter_data("01/02/2025"), "2025-02-01")
        self.assertEqual(p.converter_data(" 2025-02-01 "), "2025-02-01")
        self.assertIsNone(p.converter_data("2025-13-01"))

    def test_chave(self):
        self.assertEqual(p.chave("  Vídeo "), "video")
        self.assertEqual(p.chave("BANCO   de Dados"), "banco de dados")


class Catalogo(unittest.TestCase):
    def tratar(self, *extras):
        return p.tratar_catalogo([CATALOGO_OK, *extras])

    def test_limpo_nao_conta_como_corrigido(self):
        _, c = self.tratar()
        self.assertEqual(dict(c), dict(validos=1, invalidos=0, incompletos=0, duplicados=0, corrigidos=0))

    def test_normaliza_tipo_nivel_categoria(self):
        t, c = self.tratar(
            {**CATALOGO_OK, "conteudo_id": "2", "tipo": "  video ", "nivel": "AVANCADO"},
            {**CATALOGO_OK, "conteudo_id": "3", "categoria": "banco   de dados"},
        )
        self.assertEqual((t[1]["tipo"], t[1]["nivel"]), ("Vídeo", "Avançado"))
        self.assertEqual({r["categoria"] for r in t}, {"Banco de Dados"})
        self.assertEqual(c["corrigidos"], 2)

    def test_rejeicoes(self):
        _, c = self.tratar(
            {**CATALOGO_OK, "conteudo_id": "1"},                       # duplicado
            {**CATALOGO_OK, "conteudo_id": "4", "carga_horaria_min": "-3"},
            {**CATALOGO_OK, "conteudo_id": "5", "nivel": "expert"},
            {**CATALOGO_OK, "conteudo_id": "6", "data_publicacao": "x"},
            {**CATALOGO_OK, "conteudo_id": "7.9"},                     # id fracionário
            {**CATALOGO_OK, "conteudo_id": ""},                        # incompleto
        )
        self.assertEqual(dict(c), dict(validos=1, invalidos=4, incompletos=1, duplicados=1, corrigidos=0))
        self.assertEqual(len(c.rejeitados), 6)
        self.assertTrue(all(r["motivo"] for r in c.rejeitados))


class Interacoes(unittest.TestCase):
    def tratar(self, *extras):
        return p.tratar_interacoes([INTERACAO_OK, *extras], {1})

    def test_limpo(self):
        _, c = self.tratar()
        self.assertEqual((c["validos"], c["corrigidos"]), (1, 0))

    def test_rejeicoes(self):
        _, c = self.tratar(
            {**INTERACAO_OK},                                    # duplicado
            {**INTERACAO_OK, "conteudo_id": 999},                # inexistente
            {**INTERACAO_OK, "data_hora": "ontem"},
            {**INTERACAO_OK, "tipo_interacao": "like"},
            {**INTERACAO_OK, "tempo_consumido": -1},
            {**INTERACAO_OK, "percentual_conclusao": 120},
            {**INTERACAO_OK, "avaliacao_atribuida": 6},
            {**INTERACAO_OK, "usuario_id": None},                # incompleto
        )
        self.assertEqual(dict(c), dict(validos=1, invalidos=6, incompletos=1, duplicados=1, corrigidos=0))

    def test_normaliza_tipo(self):
        t, c = self.tratar({**INTERACAO_OK, "tipo_interacao": " CONCLUSAO ", "data_hora": "2026-01-02T10:00:00"})
        self.assertEqual(t[1]["tipo_interacao"], "conclusão")
        self.assertEqual(c["corrigidos"], 1)


class Comentarios(unittest.TestCase):
    def test_tags_e_rejeicoes(self):
        t, c = p.tratar_comentarios([
            COMENTARIO_OK,
            {**COMENTARIO_OK},                                   # duplicado
            {**COMENTARIO_OK, "avaliacao": 0},
            {**COMENTARIO_OK, "tags": "python"},
            {**COMENTARIO_OK, "comentario": "   "},              # incompleto
        ], {1})
        self.assertEqual(t[0]["tags"], ["python", "lgpd"])
        self.assertEqual(dict(c), dict(validos=1, invalidos=2, incompletos=1, duplicados=1, corrigidos=1))


if __name__ == "__main__":
    unittest.main()
