# LayoutGenome Bridge

Aplicacao full-stack (SPA + backend Python/Flask) para:

1. Validar a URL de referencia.
2. Baixar o site e gerar ZIP para o usuario.
3. Receber e validar INDEX_HTML.
4. Gerar designer_system.html com IA gratuita.
5. Entregar preview + copiar + baixar o HTML final.

## Fluxo funcional (SPA)

1. Passo 1: Informe a URL do site de referencia.
2. Passo 2: Baixe o ZIP gerado.
3. Passo 3: Envie o index.html.
4. Passo 4: Gerar designer_system.html com IA gratuita.

Se os providers de IA estiverem indisponiveis, o backend aplica fallback local automatico (heuristico) para seguir no mesmo clique. Se ate esse fallback falhar, a interface exibe fallback manual com prompt pronto para copiar.

## Endpoints backend

Implementados conforme solicitado:

- POST /api/validate-url
- POST /api/download-site
- GET /api/download-zip/<job_id>
- POST /api/validate-index
- POST /api/generate-designer-system

Endpoints auxiliares:

- GET /api/download-events/<job_id> (SSE para logs)
- GET /api/download-status/<job_id>
- GET /api/designer-system/<output_id>/preview
- GET /api/designer-system/<output_id>/download

## Regras tecnicas aplicadas

- Validacao de URL com esquema http/https e formato.
- Validacao de INDEX_HTML (nao vazio e com marcador HTML valido).
- Limites de tamanho de entrada e tratamento de erro JSON.
- Protecao contra path traversal usando IDs UUID e caminhos internos controlados.
- Limpeza automatica de artefatos temporarios.
- Fallback local automatico quando IA indisponivel.
- Fallback manual funcional como ultima camada.

## IA gratuita e fallback

Ordem de tentativas no backend:

1. OpenRouter (free-tier como caminho principal)
2. Google AI Studio (free-tier)
3. OpenAI (fallback adicional opcional)

Se OpenRouter/Google/OpenAI falharem, o backend gera designer_system.html localmente (heuristica) e retorna sucesso.

Se esse fallback local falhar por qualquer motivo, a API retorna prompt completo para uso manual em provider externo e a SPA permite colar o resultado para preview/copia/download.

## Setup local

### Requisitos

- Python 3.12+
- Pip ou uv
- Playwright Chromium

### 1) Configurar variaveis de ambiente

Copie .env.example para .env e preencha as chaves que desejar:

- OPENROUTER_API_KEY
- GOOGLE_AI_STUDIO_API_KEY
- OPENAI_API_KEY (opcional)

Com apenas OpenRouter ou Google preenchido, o fluxo principal ja funciona.

### 2) Instalar dependencias

Com pip:

```bash
pip install -r requirements.txt
playwright install chromium
```

Com uv:

```bash
uv sync
uv run playwright install chromium
```

### 3) Executar

Com pip:

```bash
python app.py
```

Com uv:

```bash
uv run python app.py
```

Aplicacao: http://localhost:5001

## Estrutura principal

```
.
├── app.py
├── downloader.py
├── templates/
│   └── index.html
├── requirements.txt
├── .env.example
├── downloads/        # temporario
└── generated/        # temporario
```

## Deploy

Arquivos de deploy existentes continuam validos (Dockerfile, render.yaml, Procfile).
Consulte DEPLOY.md e RAILWAY_DEPLOY.md para detalhes de plataforma.
