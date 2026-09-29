"""Capturas de tela das evidencias (RF34), com navegador headless.

    docker compose run --rm evidencias ferramentas/evidencias.py superset
    docker compose run --rm evidencias ferramentas/evidencias.py alerta
    docker compose run --rm evidencias ferramentas/evidencias.py openmetadata [--refazer]

Cada alvo precisa do servico correspondente no ar. As imagens vao para a pasta de evidencias de cada
parte (superset/exportacao_e_evidencias/, openmetadata/evidencias/).
"""
import base64
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
SUPERSET = "http://superset:8088"
OPENMETADATA = "http://openmetadata:8585"
MAILPIT = "http://mailpit:8025"
SG = "Segurança & Governança"


def esperar_graficos(page: Page, minimo_s: float = 4) -> None:
    """Espera a rede acalmar e nenhum grafico continuar carregando."""
    page.wait_for_load_state("networkidle")
    for _ in range(60):
        if page.locator(".loading, [data-test='loading-indicator']").count() == 0:
            break
        time.sleep(1)
    time.sleep(minimo_s)


def entrar_superset(page: Page) -> None:
    page.goto(f"{SUPERSET}/login/")
    page.fill("input[name='username'], #username", os.environ["SUPERSET_ADMIN_USER"])
    page.fill("input[name='password'], #password", os.environ["SUPERSET_ADMIN_PASSWORD"])
    page.keyboard.press("Enter")
    page.wait_for_url(lambda url: "/login" not in url, timeout=30000)


def superset(page: Page) -> None:
    destino = RAIZ / "superset" / "exportacao_e_evidencias"
    destino.mkdir(parents=True, exist_ok=True)
    entrar_superset(page)

    page.goto(f"{SUPERSET}/superset/dashboard/desafio2-storytelling/?standalone=1")
    esperar_graficos(page)
    page.screenshot(path=destino / "01_storytelling.png", full_page=True)

    page.goto(f"{SUPERSET}/superset/dashboard/desafio2-exploracao/")
    esperar_graficos(page)
    page.screenshot(path=destino / "02_exploracao.png", full_page=True)

    # filtro nativo de categoria aplicado pela URL (mesmo estado que o painel de filtros produz)
    estado = ("(NATIVE_FILTER-categoria:(extraFormData:(filters:!((col:categoria,op:IN,val:!('"
              + SG.replace("&", "%26") + "')))),filterState:(value:!('" + SG.replace("&", "%26") + "'))))")
    page.goto(f"{SUPERSET}/superset/dashboard/desafio2-exploracao/?native_filters={estado}")
    esperar_graficos(page)
    page.screenshot(path=destino / "03_exploracao_filtro_categoria.png", full_page=True)

    # filtro de periodo aplicado pela URL: de junho em diante
    periodo = "(NATIVE_FILTER-periodo:(extraFormData:(time_range:'2026-06-01 : 2026-10-01'),filterState:(value:'2026-06-01 : 2026-10-01')))"
    page.goto(f"{SUPERSET}/superset/dashboard/desafio2-exploracao/?native_filters={periodo}")
    esperar_graficos(page)
    page.screenshot(path=destino / "04_exploracao_filtro_periodo.png", full_page=True)

    # filtro cruzado: clique na barra de uma categoria; confere que o filtro foi aplicado
    page.goto(f"{SUPERSET}/superset/dashboard/desafio2-exploracao/")
    esperar_graficos(page)
    caixa = page.locator("[data-test-chart-name*='clique para filtrar'] canvas").first.bounding_box()
    # barras verticais em ordem crescente: a primeira (menor taxa) e Seguranca & Governanca
    for fracao_x in (0.14, 0.12, 0.16, 0.18, 0.10):
        page.mouse.click(caixa["x"] + caixa["width"] * fracao_x, caixa["y"] + caixa["height"] * 0.55)
        time.sleep(2)
        if page.get_by_text("Cross-filters").count():
            break
    else:
        raise SystemExit("o clique nao gerou filtro cruzado")
    painel = page.locator("text=Cross-filters").locator("xpath=ancestor::div[2]").inner_text()
    if "Segurança" not in painel:
        raise SystemExit(f"filtro cruzado aplicado com valor inesperado: {painel!r}")
    esperar_graficos(page)
    page.screenshot(path=destino / "05_exploracao_filtro_cruzado.png", full_page=True)

    page.goto(f"{SUPERSET}/sqllab/")
    esperar_graficos(page, 2)
    page.goto(f"{SUPERSET}/savedqueryview/list/")
    esperar_graficos(page, 2)
    page.screenshot(path=destino / "06_sql_lab_consultas_salvas.png", full_page=True)

    page.goto(f"{SUPERSET}/alert/list/")
    esperar_graficos(page, 2)
    page.screenshot(path=destino / "07_alerta_configurado.png", full_page=True)
    print(f"capturas em {destino.relative_to(RAIZ)}")


def alerta(page: Page) -> None:
    destino = RAIZ / "superset" / "exportacao_e_evidencias"
    page.goto(MAILPIT)
    page.wait_for_load_state("networkidle")
    page.locator(".message").first.click()
    time.sleep(2)
    page.screenshot(path=destino / "08_alerta_email_recebido.png", full_page=True)
    print(f"captura em {destino.relative_to(RAIZ)}")


def capturar_cdp(page: Page, caminho: Path) -> None:
    """Captura pelo protocolo do Chromium. O page.screenshot do Playwright espera todas as fontes web
    carregarem, e a interface do OpenMetadata tem uma que nunca termina; o DevTools nao espera."""
    cdp = page.context.new_cdp_session(page)
    caminho.write_bytes(base64.b64decode(cdp.send("Page.captureScreenshot", {"format": "png"})["data"]))
    cdp.detach()


def entrar_openmetadata(page: Page) -> None:
    page.goto(f"{OPENMETADATA}/signin")
    page.fill("#email", os.environ["OM_ADMIN_EMAIL"])
    page.fill("#password", os.environ["OM_ADMIN_PASSWORD"])
    page.locator("button[type='submit'], [data-testid='login']").first.click()
    page.wait_for_url(lambda url: "/signin" not in url, timeout=60000, wait_until="domcontentloaded")
    time.sleep(3)


TELA_OM = (1600, 1400)
TELA_TABELA = (2000, 2600)  # paginas de tabela: todas as colunas e as de tags e glossario, sem rolagem

PAGINAS_OM = [
    ("01_catalogo_schemas.png", "/database/postgres_desafio.desafio"),
    ("02_bronze_usuarios_dados_pessoais.png", "/table/postgres_desafio.desafio.bronze.usuarios", TELA_TABELA),
    ("03_silver_usuario_protecao.png", "/table/postgres_desafio.desafio.silver.usuario", TELA_TABELA),
    ("04_gold_kpi_taxa_conclusao_glossario.png", "/table/postgres_desafio.desafio.gold.kpi_taxa_conclusao", TELA_TABELA),
    ("05_linhagem_kpi_taxa_conclusao.png", "/table/postgres_desafio.desafio.gold.kpi_taxa_conclusao/lineage"),
    ("06_linhagem_bronze_usuarios.png", "/table/postgres_desafio.desafio.bronze.usuarios/lineage"),
    ("07_glossario.png", "/glossary/plataforma_conteudos"),
    ("08_termo_taxa_de_conclusao.png", "/glossary/plataforma_conteudos.taxa_de_conclusao"),
    ("09_classificacao_lgpd.png", "/tags/LGPD"),
    ("10_dashboard_storytelling_linhagem.png", "/dashboard/superset_desafio.1/lineage"),
    ("11_pipelines_hop.png", "/service/pipelineServices/apache_hop"),
    # do arquivo de origem ao dashboard: 4 niveis a montante do KPI (fato, silver, bronze, arquivo), 2 a jusante
    ("12_linhagem_ponta_a_ponta.png", "/table/postgres_desafio.desafio.gold.kpi_taxa_conclusao/lineage", (2400, 1600)),
    ("13_linhagem_por_coluna.png", "/table/postgres_desafio.desafio.gold.kpi_taxa_conclusao/lineage"),
]


def profundidade(page: Page, montante: int, jusante: int) -> None:
    """Configuracao da linhagem (engrenagem): quantos niveis mostrar antes e depois do ativo."""
    page.get_by_test_id("lineage-config").click()
    time.sleep(1)
    for campo, valor in (("field-upstream", montante), ("field-downstream", jusante)):
        page.get_by_test_id(campo).fill(str(valor))
    page.locator(".ant-modal button.ant-btn-primary").click()
    time.sleep(6)


def camada_de_colunas(page: Page) -> None:
    """Camada "Colunas" da linhagem: mostra as arestas entre colunas registradas."""
    page.get_by_test_id("lineage-layer-btn").click()
    time.sleep(1)
    page.get_by_test_id("lineage-layer-column-btn").click()
    page.keyboard.press("Escape")
    time.sleep(4)


def aba_pipelines(page: Page) -> None:
    page.get_by_role("tab", name=re.compile("Gasodutos|Pipelines")).click()
    time.sleep(4)


ACOES_OM = {"11_pipelines_hop.png": aba_pipelines,
            "12_linhagem_ponta_a_ponta.png": lambda page: profundidade(page, 4, 2),
            "13_linhagem_por_coluna.png": camada_de_colunas}


def capturar_pagina_om(arquivo: str, caminho: str, tela: tuple = TELA_OM) -> None:
    """Uma pagina por processo: a interface do OpenMetadata as vezes congela a pagina (o renderizador para
    de responder, inclusive a evaluate), e so um processo novo, com prazo, contorna isso de forma confiavel."""
    destino = RAIZ / "openmetadata" / "evidencias"
    with sync_playwright() as p:
        navegador = p.chromium.launch(args=["--disable-dev-shm-usage"])
        page = navegador.new_context(viewport={"width": tela[0], "height": tela[1]}, locale="pt-BR").new_page()
        page.set_default_timeout(30000)
        entrar_openmetadata(page)
        page.goto(OPENMETADATA + caminho, wait_until="domcontentloaded")
        for _ in range(20):
            if page.locator("[data-testid='loader'], .ant-skeleton, .ant-spin-spinning").count() == 0:
                break
            time.sleep(1)
        time.sleep(4)
        if arquivo in ACOES_OM:
            ACOES_OM[arquivo](page)
        if caminho.endswith("/lineage"):
            # grafo inteiro no quadro: botao "ajustar a tela" do proprio grafo (React Flow)
            ajustar = page.locator(".react-flow__controls-fitview, [data-testid='fit-screen'], [data-testid='fit-view']")
            if ajustar.count():
                ajustar.first.click()
                time.sleep(1)
                # no OpenMetadata 2.x o botao abre um menu de enquadramento; a opcao e um item dele
                opcao = page.get_by_role("menuitem", name=re.compile("Ajustar à tela|Fit to screen"))
                if opcao.count():
                    opcao.first.click()
                time.sleep(3)
        capturar_cdp(page, destino / arquivo)
        navegador.close()


def openmetadata() -> None:
    import multiprocessing
    contexto = multiprocessing.get_context("spawn")  # processo limpo, sem estado do Playwright herdado
    destino = RAIZ / "openmetadata" / "evidencias"
    destino.mkdir(parents=True, exist_ok=True)
    faltando = []
    for arquivo, caminho, *tela in PAGINAS_OM:
        if (destino / arquivo).exists() and "--refazer" not in sys.argv:
            continue
        for tentativa in range(1, 5):
            processo = contexto.Process(target=capturar_pagina_om, args=(arquivo, caminho, *tela))
            processo.start()
            processo.join(timeout=90)
            if processo.is_alive():
                processo.terminate()
                processo.join()
            if processo.exitcode == 0 and (destino / arquivo).exists():
                print(f"  {arquivo} (tentativa {tentativa})", flush=True)
                break
        else:
            faltando.append(arquivo)
    if faltando:
        raise SystemExit(f"capturas que falharam 4 vezes: {faltando}")
    print(f"capturas em {destino.relative_to(RAIZ)}")


def spark(page: Page) -> None:
    """Interface do Spark master depois dos jobs do Beam (RF25): workers, cores, memoria e aplicacoes concluidas."""
    destino = RAIZ / "beam" / "evidencias"
    page.goto("http://spark-master:8080/")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=destino / "spark_master_aplicacoes.png", full_page=True)
    print(f"captura em {destino.relative_to(RAIZ)}")


def main() -> None:
    alvo = sys.argv[1] if len(sys.argv) > 1 else "superset"
    if alvo == "openmetadata":  # cada pagina abre o proprio navegador, num processo separado
        openmetadata()
        return
    alvos = {"superset": superset, "alerta": alerta, "spark": spark}
    if alvo not in alvos:
        raise SystemExit(f"alvo desconhecido: {alvo} (superset, alerta, openmetadata, spark)")
    with sync_playwright() as p:
        navegador = p.chromium.launch(args=["--disable-dev-shm-usage"])
        contexto = navegador.new_context(viewport={"width": 1600, "height": 1000}, locale="pt-BR")
        page = contexto.new_page()
        page.set_default_timeout(60000)
        try:
            alvos[alvo](page)
        finally:
            navegador.close()


if __name__ == "__main__":
    main()
