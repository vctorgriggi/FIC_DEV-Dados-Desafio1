# 11. Entregáveis

Cada equipe deverá entregar um arquivo compactado com a seguinte organização sugerida:

```
desafio_dados_2/
├── README.md
├── dados/
│   ├── bronze/
│   ├── silver/
│   ├── gold/
│   └── quarentena/
├── hop/
│   ├── pipelines/
│   ├── workflows/
│   └── environments/
├── beam/
│   ├── pipeline.py
│   └── evidencias/
├── sql/
│   ├── camada_gold.sql
│   └── sql_lab.sql
├── superset/
│   └── exportacao_e_evidencias/
├── openmetadata/
│   └── evidencias/
├── qualidade/
│   ├── regras.md
│   └── resultados/
├── lgpd/
│   ├── inventario_de_dados.md
│   └── tecnicas_de_protecao.md
├── documentacao/
│   ├── arquitetura.pdf
│   ├── linhagem.pdf
│   ├── storytelling.pdf
└── requirements.txt
```

**Entregáveis obrigatórios:**

- pipelines e workflows exportados do Apache Hop;
- amostras ou scripts de produção das camadas Bronze, Silver e Gold;
- pipeline Apache Beam e evidências do runtime utilizado;
- consultas do SQL Lab e exportação ou evidências do Superset;
- evidências do OpenMetadata, incluindo catálogo, glossário, classificação e linhagem;
- regras e resultados dos testes de qualidade;
- inventário de dados pessoais e implementação das técnicas de proteção;
- documentação para instalação, configuração e execução;

# 12. Apresentação

Cada equipe deverá realizar uma apresentação de aproximadamente 15 minutos:

| Tempo     | Conteúdo                                                                       |
| --------- | ------------------------------------------------------------------------------ |
| 2 minutos | Situação-problema, continuidade do Desafio 1 e arquitetura escolhida.          |
| 4 minutos | Apache Hop, camadas Bronze, Silver e Gold, orquestração e tratamento de erros. |
| 2 minutos | Parquet, Apache Beam e comparação do runtime.                                  |
| 3 minutos | OpenMetadata, glossário, linhagem, dados mestres e qualidade.                  |
| 2 minutos | LGPD e demonstração das técnicas de proteção.                                  |
| 2 minutos | Storytelling, SQL Lab, dashboard, alerta, conclusões e uso de IA.              |

> **Verificação de aprendizagem:** qualquer integrante poderá ser solicitado a explicar uma parte da solução, executar uma etapa ou justificar uma decisão técnica.
