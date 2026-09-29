# Navegador headless para capturar as telas de evidencia (RF34) e gerar os PDFs da documentacao.
# A imagem oficial ja traz o Chromium; o pacote Python precisa ser da mesma versao.
FROM mcr.microsoft.com/playwright/python:v1.59.0-noble

RUN pip install --no-cache-dir --break-system-packages playwright==1.59.0 markdown-it-py==4.2.0

# Mermaid fixo na imagem: os diagramas dos PDFs renderizam sem acesso a internet na hora de gerar
ADD https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js /opt/mermaid/mermaid.min.js
