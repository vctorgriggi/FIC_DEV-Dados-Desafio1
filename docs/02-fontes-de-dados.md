# 6. Fontes de dados

As equipes receberão ou deverão produzir dados fictícios organizados em, pelo menos, três fontes.

## 6.1 Catálogo de conteúdos — CSV

| Campo             | Descrição                          |
| ----------------- | ---------------------------------- |
| conteudo_id       | Identificador do conteúdo.         |
| titulo            | Título do material.                |
| tipo              | Curso, vídeo, artigo ou podcast.   |
| categoria         | Área temática.                     |
| nivel             | Básico, intermediário ou avançado. |
| carga_horaria_min | Duração estimada em minutos.       |
| data_publicacao   | Data de publicação.                |
| descricao         | Descrição textual.                 |
| autor             | Responsável pelo conteúdo.         |

## 6.2 Interações dos usuários — JSON

A fonte deverá conter, no mínimo, identificador do usuário, identificador do conteúdo, tipo de interação, data e hora, tempo consumido, percentual de conclusão e avaliação atribuída.

Tipos de interação sugeridos:

- visualização;
- início;
- conclusão;
- curtida;
- avaliação;
- compartilhamento.

## 6.3 Comentários e avaliações — JSON ou MongoDB

**Exemplo de documento:**

```json
{
  "usuario_id": 104,
  "conteudo_id": 28,
  "avaliacao": 5,
  "comentario": "Conteúdo introdutório, claro e objetivo.",
  "tags": ["didático", "iniciante", "python"],
  "data": "2026-08-20"
}
```
