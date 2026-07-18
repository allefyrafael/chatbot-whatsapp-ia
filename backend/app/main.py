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
from sqlalchemy.exc import OperationalError

from app.bootstrap import criar_database_se_nao_existe, garantir_colunas
from app.database import Base, banco_configurado, get_engine
from app.deps import NaoAutenticado
from app.routers import (
    auth,
    banco,
    integracao,
    itens,
    rag,
    setup,
    sistema,
    tools,
    webhook,
    whatsapp,
)
from app.templating import STATIC_DIR, templates

# Caminhos liberados quando o banco ainda não foi configurado.
_LIVRES_SEM_BANCO = ("/configurar-banco", "/static", "/docs", "/redoc", "/openapi.json")

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
    """Prepara o banco no arranque — mas nunca impede o app de subir.

    Se o banco ainda não foi configurado (ou está fora do ar), a aplicação sobe assim
    mesmo e o painel leva o usuário para o assistente em /configurar-banco.
    """
    if banco_configurado():
        try:
            criar_database_se_nao_existe()
            engine = get_engine()
            Base.metadata.create_all(bind=engine)
            garantir_colunas(engine)
        except Exception:  # noqa: BLE001 - banco inacessível não pode derrubar o servidor
            pass
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

app.include_router(banco.router)
app.include_router(setup.router)
app.include_router(auth.router)
app.include_router(integracao.router)
app.include_router(itens.router)
app.include_router(rag.router)
app.include_router(whatsapp.router)
app.include_router(sistema.router)
app.include_router(webhook.router)
app.include_router(tools.router)


@app.middleware("http")
async def exigir_banco_configurado(request: Request, call_next):
    """Sem banco configurado, todo o painel leva ao assistente /configurar-banco."""
    caminho = request.url.path
    if not banco_configurado() and not caminho.startswith(_LIVRES_SEM_BANCO):
        return RedirectResponse("/configurar-banco", status_code=303)
    return await call_next(request)


@app.exception_handler(OperationalError)
def banco_fora_do_ar(request: Request, exc: OperationalError):
    """Banco configurado mas inacessível (IP mudou, instância parada): reabre o assistente."""
    return templates.TemplateResponse(
        request,
        "configurar_banco.html",
        {
            "wizard": True,
            "dados": {"porta": "3306"},
            "erro": (
                "Perdi a conexão com o banco. Se o seu IP mudou, atualize a regra do "
                "<b>Security Group</b> no RDS; se a instância foi parada, inicie-a. "
                "Você também pode informar outra conexão abaixo."
            ),
        },
        status_code=503,
    )


@app.exception_handler(NaoAutenticado)
def redirecionar_para_login(request: Request, exc: NaoAutenticado):
    """Rotas de painel sem cookie válido: redireciona o navegador para o login."""
    return RedirectResponse("/login", status_code=303)


@app.get("/", tags=["Sistema"], summary="Raiz — redireciona para o painel")
def raiz():
    """Redireciona a raiz do site para a lista de itens do painel."""
    return RedirectResponse("/painel/itens", status_code=303)
