"""Regra do pipeline Beam (RF25). Roda no container beam:
    docker compose run --rm beam -m unittest tests.test_beam
"""
import unittest
from datetime import datetime

try:
    import apache_beam as beam
    from apache_beam.testing.test_pipeline import TestPipeline
    from apache_beam.testing.util import assert_that, equal_to
except ImportError:  # imagem do app (Desafio 1) nao tem o Beam
    raise unittest.SkipTest("apache_beam nao instalado; rode no container beam")

from beam.pipeline import EngajamentoMensal, somar


def interacao(usuario, conteudo, tipo, quando, minutos):
    return {"usuario_id": usuario, "conteudo_id": conteudo, "tipo_interacao": tipo,
            "data_hora": datetime.fromisoformat(quando), "tempo_consumido": minutos}


class TestEngajamentoMensal(unittest.TestCase):
    def test_conta_pessoas_nao_ids_e_separa_mes_e_categoria(self):
        interacoes = [
            interacao(12, 1, "visualização", "2026-08-01T10:00:00", 30),
            interacao(171, 1, "conclusão", "2026-08-15T10:00:00", 60),   # 171 e a mesma pessoa que 12 (RF30)
            interacao(30, 2, "início", "2026-08-20T10:00:00", None),     # tempo ausente conta como 0
            interacao(30, 1, "visualização", "2026-09-02T10:00:00", 10),
        ]
        with TestPipeline() as p:
            categorias = beam.pvalue.AsDict(p | "categorias" >> beam.Create([(1, "Dados"), (2, "IA")]))
            mestres = beam.pvalue.AsDict(p | "mestres" >> beam.Create([(12, 12), (171, 12), (30, 30)]))
            resultado = p | beam.Create(interacoes) | EngajamentoMensal(categorias, mestres)
            assert_that(resultado, equal_to([
                {"mes": "2026-08", "categoria": "Dados", "interacoes": 2, "pessoas_ativas": 1,
                 "conclusoes": 1, "minutos_consumidos": 90},
                {"mes": "2026-08", "categoria": "IA", "interacoes": 1, "pessoas_ativas": 1,
                 "conclusoes": 0, "minutos_consumidos": 0},
                {"mes": "2026-09", "categoria": "Dados", "interacoes": 1, "pessoas_ativas": 1,
                 "conclusoes": 0, "minutos_consumidos": 10},
            ]))

    def test_soma_e_associativa(self):
        self.assertEqual(somar([(1, 0, 5), somar([(1, 1, 10), (1, 0, 2)])]), (3, 1, 17))


if __name__ == "__main__":
    unittest.main()
