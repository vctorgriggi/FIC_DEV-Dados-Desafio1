"""PDFs da documentacao do Desafio 2 a partir dos Markdown, com os diagramas Mermaid renderizados.

    docker compose run --rm evidencias ferramentas/gerar_pdfs.py                       # os documentos de DOCUMENTOS
    docker compose run --rm evidencias ferramentas/gerar_pdfs.py documentacao/x.md     # so os indicados

O Markdown vira HTML (markdown-it-py, CommonMark com tabelas), os blocos ```mermaid viram diagramas no
Chromium (Mermaid fixo na imagem, docker/evidencias.Dockerfile) e o Playwright imprime em A4. O .md continua
sendo a fonte: o PDF e gerado, nunca editado.
"""
import sys
from datetime import date
from pathlib import Path

from markdown_it import MarkdownIt
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
MERMAID = Path("/opt/mermaid/mermaid.min.js")
DOCUMENTOS = [  # os tres PDFs pedidos na estrutura de entrega do enunciado
    "documentacao/arquitetura.md",
    "documentacao/linhagem.md",
    "documentacao/storytelling.md",
]

ESTILO = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif; font-size: 10pt; line-height: 1.45; color: #1f2933; }
h1 { font-size: 19pt; margin: 0 0 10pt; color: #102a43; border-bottom: 2px solid #1f7a8c; padding-bottom: 4pt; }
h2 { font-size: 14pt; margin: 18pt 0 6pt; color: #102a43; break-after: avoid; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; color: #243b53; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 8.5pt; }
th, td { border: 1px solid #bcccdc; padding: 3pt 5pt; vertical-align: top; text-align: left; }
th { background: #e3eef4; }
tr { break-inside: avoid; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.5pt; background: #f0f4f8; padding: 0 2pt; border-radius: 2pt; }
pre { background: #f0f4f8; padding: 6pt 8pt; border-radius: 4pt; white-space: pre-wrap; word-break: break-word; break-inside: avoid; }
pre code { background: none; padding: 0; }
pre.mermaid { background: none; text-align: center; }
pre.mermaid svg { max-width: 100%; height: auto; }
blockquote { margin: 6pt 0; padding: 2pt 10pt; border-left: 3px solid #1f7a8c; color: #334e68; }
a { color: #1f7a8c; text-decoration: none; }
"""


def html(markdown: str, titulo: str) -> str:
    md = MarkdownIt("commonmark").enable("table")
    padrao = md.renderer.rules.get("fence")

    def fence(renderizador, tokens, idx, options, env):  # ```mermaid vira <pre class="mermaid">, que o Mermaid desenha
        token = tokens[idx]
        if token.info.strip() == "mermaid":
            return f'<pre class="mermaid">{md.utils.escapeHtml(token.content)}</pre>\n'
        return padrao(tokens, idx, options, env)

    md.add_render_rule("fence", fence)
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{titulo}</title>'
            f"<style>{ESTILO}</style></head><body>{md.render(markdown)}</body></html>")


def gerar(page, origem: Path) -> Path:
    texto = origem.read_text(encoding="utf-8")
    titulo = next((linha[2:].strip() for linha in texto.splitlines() if linha.startswith("# ")), origem.stem)
    page.set_content(html(texto, titulo), wait_until="load")
    if page.locator("pre.mermaid").count():
        page.add_script_tag(path=str(MERMAID))
        page.evaluate("""async () => {
            mermaid.initialize({startOnLoad: false, theme: "neutral", flowchart: {useMaxWidth: true}});
            await mermaid.run({querySelector: "pre.mermaid"});
        }""")
        erros = page.locator("pre.mermaid [id^='mermaid-error'], pre.mermaid .error-icon").count()
        if erros:
            raise SystemExit(f"{origem}: diagrama Mermaid com erro de sintaxe")
    destino = origem.with_suffix(".pdf")
    rodape = (f'<div style="font-size:7pt;color:#627d98;width:100%;padding:0 16mm;display:flex;justify-content:space-between">'
              f'<span>{titulo} · gerado em {date.today():%d/%m/%Y} de {origem.relative_to(RAIZ)}</span>'
              f'<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')
    page.pdf(path=str(destino), format="A4", print_background=True, display_header_footer=True,
             header_template="<div></div>", footer_template=rodape,
             margin={"top": "18mm", "bottom": "18mm", "left": "16mm", "right": "16mm"})
    return destino


def main() -> None:
    documentos = [RAIZ / d for d in (sys.argv[1:] or DOCUMENTOS)]
    faltando = [str(d) for d in documentos if not d.exists()]
    if faltando:
        raise SystemExit(f"nao encontrados: {faltando}")
    with sync_playwright() as p:
        navegador = p.chromium.launch(args=["--disable-dev-shm-usage"])
        page = navegador.new_page()
        try:
            for origem in documentos:
                print(f"{gerar(page, origem).relative_to(RAIZ)}", flush=True)
        finally:
            navegador.close()


if __name__ == "__main__":
    main()
