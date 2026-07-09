"""Rotas de autenticação do painel (login/logout).

O login valida e-mail/senha, emite um JWT (`app.security`) e o grava num cookie
httpOnly chamado `access_token`. Esse cookie é o que as rotas `/painel/**` exigem
(via `app.deps.get_current_admin`). O logout apenas apaga o cookie.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import COOKIE_NAME
from app.models import Configuracao, Usuario
from app.security import criar_token_acesso, verificar_senha
from app.templating import templates

router = APIRouter(tags=["Autenticação"])


@router.get("/login", response_class=HTMLResponse, summary="Formulário de login")
def formulario_login(request: Request, db: Session = Depends(get_db)):
    """Mostra o formulário de login. Se a empresa ainda não foi criada, vai para /setup."""
    if db.get(Configuracao, 1) is None:
        return RedirectResponse("/setup", status_code=303)
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login", summary="Autenticar e criar sessão (cookie JWT)")
def login(
    request: Request,
    email: str = Form(...),
    senha: str = Form(...),
    db: Session = Depends(get_db),
):
    """Valida credenciais e grava o cookie de sessão.

    - **Recebe** (form): `email`, `senha`.
    - **Sucesso**: grava o cookie `access_token` (JWT, httpOnly, 8h) e redireciona —
      para `/painel/integracao/groq` se ainda não há chave do Groq, senão `/painel/itens`.
    - **Falha**: reexibe o login com erro e status **401**.
    """
    usuario = db.query(Usuario).filter(Usuario.email == email).first()
    if usuario is None or not verificar_senha(senha, usuario.senha_hash):
        return templates.TemplateResponse(
            request, "login.html", {"erro": "E-mail ou senha inválidos."}, status_code=401
        )

    token = criar_token_acesso(usuario.id)
    # Se ainda não há chave do Groq, leva o admin direto para o onboarding da IA.
    config = db.get(Configuracao, 1)
    destino = "/painel/itens" if config and config.groq_api_key else "/painel/integracao/groq"
    resposta = RedirectResponse(destino, status_code=303)
    resposta.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 8,
    )
    return resposta


@router.get("/logout", summary="Encerrar sessão")
def logout():
    """Apaga o cookie de sessão e redireciona para `/login`."""
    resposta = RedirectResponse("/login", status_code=303)
    resposta.delete_cookie(COOKIE_NAME)
    return resposta
