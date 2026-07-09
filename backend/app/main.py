"""Ponto de entrada da aplicação FastAPI (painel administrativo + tools da IA).

Responsabilidades deste módulo:
- Criar a instância `app` do FastAPI com os metadados que alimentam o Swagger (/docs).
- No arranque (`lifespan`): garantir que o database e as tabelas existam.
- Registrar os routers (setup, autenticação, integração IA, itens, tools).
- Tratar a exceção `NaoAutenticado` redirecionando o navegador para /login.

Suba com: `python -m uvicorn app.main:app --reload` (ou use o script `run.ps1`).
Documentação interativa das rotas: http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.bootstrap import criar_database_se_nao_existe, garantir_colunas
from app.database import Base, engine
from app.deps import NaoAutenticado
from app.routers import auth, integracao, itens, rag, setup, sistema, tools, webhook, whatsapp
from app.templating import STATIC_DIR

# Descrição em Markdown exibida no topo do Swagger (/docs).
DESCRICAO = """
Backend de um **chatbot de WhatsApp administrado por IA (Groq)** com painel web.

O painel (rotas HTML) é usado pelo administrador do negócio para cadastrar a empresa,
autenticar-se, configurar a chave da IA e gerenciar o catálogo de produtos/serviços.
As rotas **Tools (IA)** são a ponte segura entre a IA e o banco: só operam sobre
tabelas/colunas previamente liberadas num catálogo, nunca montando SQL a partir de
nomes arbitrários.

### Como se autenticar no painel
1. `POST /setup` cria a empresa + o primeiro administrador (só na 1ª vez).
2. `POST /login` valida e-mail/senha e grava um **JWT em cookie httpOnly** (`access_token`).
3. As rotas sob `/painel/**` exigem esse cookie; sem ele, o navegador é redirecionado para `/login`.

### Fases do projeto
Fase 1 (atual): setup, autenticação, itens, catálogo + tools. Próximas: WhatsApp
(Evolution API), roteador Groq, catálogo dinâmico, pedidos/Pix.
"""

# Descrição de cada grupo de rotas (agrupa e ordena as seções no Swagger).
TAGS_METADATA = [
    {"name": "Setup", "description": "Cadastro inicial da empresa e do primeiro administrador. Só funciona enquanto não houver configuração salva."},
    {"name": "Autenticação", "description": "Login e logout do painel. O login emite um JWT gravado em cookie httpOnly."},
    {"name": "Integração IA", "description": "Cadastro e validação da chave da API do Groq (onboarding com tutorial)."},
    {"name": "Painel — Itens", "description": "CRUD de produtos/serviços. Exige administrador autenticado."},
    {"name": "Tools (IA)", "description": "Rotas de dados chamadas pela IA. Toda operação é validada contra o catálogo de tabelas liberadas."},
    {"name": "Sistema", "description": "Rotas utilitárias (raiz/redirecionamento)."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-bootstrap: cria o database (se faltar), as tabelas, e completa colunas novas.
    criar_database_se_nao_existe()
    Base.metadata.create_all(bind=engine)
    garantir_colunas(engine)
    yield


app = FastAPI(
    title="Chatbot WhatsApp + IA — API do Painel",
    description=DESCRICAO,
    version="1.0.0-fase1",
    lifespan=lifespan,
    openapi_tags=TAGS_METADATA,
    contact={"name": "Equipe ChatBotModelo"},
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(setup.router)
app.include_router(auth.router)
app.include_router(integracao.router)
app.include_router(itens.router)
app.include_router(rag.router)
app.include_router(whatsapp.router)
app.include_router(sistema.router)
app.include_router(webhook.router)
app.include_router(tools.router)


@app.exception_handler(NaoAutenticado)
def redirecionar_para_login(request: Request, exc: NaoAutenticado):
    """Rotas de painel sem cookie válido: redireciona o navegador para o login."""
    return RedirectResponse("/login", status_code=303)


@app.get("/", tags=["Sistema"], summary="Raiz — redireciona para o painel")
def raiz():
    """Redireciona a raiz do site para a lista de itens do painel."""
    return RedirectResponse("/painel/itens", status_code=303)
