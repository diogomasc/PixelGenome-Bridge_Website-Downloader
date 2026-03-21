# LayoutGenome Bridge

**LayoutGenome Bridge** é a principal camada de operação da startup **PixelGenome**. Nossa solução atua como um Extrator Inteligente de Design Systems. Trata-se de uma aplicação full-stack (SPA + backend Python/Flask) projetada para alimentar IAs de código (como Cursor, Windsurf e Lovable, além de ferramentas de low-code/no-code) com os melhores padrões de interface de sites reais.

---

## Fluxo Funcional (SPA)

1. **Passo 1:** Informe a URL do site de referência.
2. **Passo 2:** O backend baixa o site (HTML + assets) e gera um arquivo ZIP para você.
3. **Passo 3:** Você anexa o `index.html` recém-baixado de volta na ferramenta.
4. **Passo 4:** O sistema gera o arquivo final `designer_system.html` usando uma IA gratuita, centralizando cores, fontes e propriedades de motion.

> _Nota:_ Se os provedores de IA estiverem indisponíveis, o backend aplica um fallback local automático (heurístico). Se até o fallback falhar, a interface exibe um fallback manual com um prompt completo pronto para copiar e usar em qualquer chat de IA.

---

## Endpoints Backend

**Arquitetura de Extração:**

- `POST /api/validate-url`
- `POST /api/download-site`
- `GET /api/download-zip/<job_id>`
- `POST /api/validate-index`
- `POST /api/generate-designer-system`

**Endpoints Auxiliares e Webhooks:**

- `GET /api/download-events/<job_id>` _(SSE para streaming de logs)_
- `GET /api/download-status/<job_id>`
- `GET /api/designer-system/<output_id>/preview`
- `GET /api/designer-system/<output_id>/download`

---

## Como Rodar Localmente (Setup)

Você pode executar o projeto usando instâncias locais com o Virtual Environment do Python.

### 1) Configurar Variáveis de Ambiente

Crie uma cópia do arquivo `.env.example` renomeando para `.env` e preencha as chaves:

- `OPENROUTER_API_KEY`
- `GOOGLE_AI_STUDIO_API_KEY`
- `OPENAI_API_KEY` _(opcional)_

_(Apenas preenchendo a chave do OpenRouter ou Google AI Studio o fluxo principal já funciona perfeitamente)._

### 2) Instalar Dependências (Ambiente Virtual)

Abra o seu terminal na pasta `backend` e execute:

```bash
# 1. Crie o ambiente virtual
python -m venv venv

# 2. Ative o ambiente virtual
.\venv\Scripts\activate      # No Windows
source venv/bin/activate    # No Linux/macOS

# 3. Instale os pacotes básicos e o Playwright
pip install -r requirements.txt
playwright install chromium
```

### 3) Executar a Aplicação

```bash
python app.py
```

Acesse a ferramenta em seu navegador através do endereço: **`http://localhost:5001`**.

---

### Executar via Docker (Opcional)

Caso prefira isolar o ambiente localmente sem instalar o Python ou dependências na sua máquina:

1. **Construa a imagem da aplicação:**

   ```bash
   docker build -t layoutgenome-bridge .
   ```

2. **Execute o container:**
   ```bash
   docker run -p 5001:5001 --env-file .env layoutgenome-bridge
   ```
   _A aplicação subirá na mesma porta, acesse `http://localhost:5001`._

---

## Conheça Mais

Existe uma landing page explicando melhor sobre a visão completa do projeto, a proposta de valor para freelancers e estúdios em:

**[https://diogomasc.github.io/LayoutGenome/](https://diogomasc.github.io/LayoutGenome/)**
