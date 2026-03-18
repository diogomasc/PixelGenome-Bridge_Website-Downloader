# PixelGenome Bridge (Local/Docker)

O PixelGenome Bridge é uma ferramenta técnica (Terminal) para extrair o DNA visual de websites e gerar Design Systems otimizados para IA. Esta ferramenta foi projetada para rodar em ambiente local ou via Docker.

## Funcionalidades Principais

1.  **Extração de Ativos**: Valida uma URL e baixa um pacote ZIP contendo a estrutura do site (HTML/CSS/JS).
2.  **Geração de Design System**: Processa o `index.html` extraído para criar um genoma visual pronto para ser consumido por IAs.
3.  **Fallback Manual**: Caso as chaves de IA automáticas falhem ou não estejam configuradas, a ferramenta gera um prompt pronto para ser usado em qualquer IA da sua escolha.

---

## 🚀 Como Rodar Localmente (Python)

### Requisitos
- Python 3.12+
- Playwright (Chromium)

### 1. Preparar Ambiente
```bash
python -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configurar Chaves de IA
Renomeie o arquivo `.env.example` para `.env` e preencha as chaves:
- `OPENROUTER_API_KEY`: Obtenha em [openrouter.ai](https://openrouter.ai/)
- `GOOGLE_AI_STUDIO_API_KEY`: Obtenha no [Google AI Studio](https://aistudio.google.com/)

### 3. Iniciar o App
```bash
python app.py
```
Acesse: `http://localhost:5001`

---

## 🐳 Como Rodar via Docker

### 1. Criar Imagem
```bash
docker build -t pixelgenome-bridge .
```

### 2. Rodar Container
```bash
docker run -p 5001:5001 --env-file .env pixelgenome-bridge
```

---

## 🧬 Testando o "Genoma" Manualmente

Os resultados de geração variam dependendo do modelo de IA utilizado. Se você deseja testar variações ou não possui chaves de API:

1.  No **Passo 1** do App, faça o download do ZIP e extraia o arquivo `index.html`.
2.  No **Passo 2**, se a extração automática falhar ou se você preferir testar manualmente, a ferramenta exibirá o **Módulo de Backup (IA Offline)**.
3.  Copie o **Prompt** gerado.
4.  Abra sua IA de preferência (ChatGPT-4, Claude 3.5 Sonnet, Gemini Pro, etc).
5.  Envie o conteúdo do `index.html` baixado juntamente com o prompt copiado.
6.  Cole o resultado retornado pela IA no campo "Resultado Manual" do app para visualizar o preview.

---

## Estrutura do Backend
```
.
├── app.py            # Servidor Flask e rotas
├── downloader.py     # Lógica de extração com Playwright
├── templates/        # Interface do Bridge
├── static/           # Arquivos estáticos
├── downloads/        # Pasta temporária de extrações
└── generated/        # Pasta temporária de resultados
```
