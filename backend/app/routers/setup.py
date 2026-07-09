"""Rotas de setup — cadastro inicial da empresa e do primeiro administrador.

Fluxo de "primeiro acesso": enquanto a linha singleton de `configuracoes` (id=1) não
existir, `/setup` mostra o formulário e o cria. Depois de configurado, `/setup` apenas
redireciona para `/login` — não é possível recriar a empresa por aqui.
"""

import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Configuracao, Usuario
from app.security import hash_senha
from app.templating import templates

router = APIRouter(tags=["Setup"])

CONFIGURACAO_ID = 1


@router.get(
    "/setup",
    response_class=HTMLResponse,
    summary="Formulário de primeiro acesso",
)
def formulario_setup(request: Request, db: Session = Depends(get_db)):
    """Mostra o formulário de cadastro da empresa. Se já configurado, vai para /login."""
    if db.get(Configuracao, CONFIGURACAO_ID) is not None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "setup.html", {})


@router.post(
    "/setup",
    summary="Criar empresa + primeiro administrador",
)
def criar_empresa_e_admin(
    request: Request,
    nome_empresa: str = Form(...),
    numero_whatsapp: str = Form(...),
    admin_nome: str = Form(...),
    admin_email: str = Form(...),
    admin_senha: str = Form(...),
    db: Session = Depends(get_db),
):
    """Cria a configuração da empresa (nome + WhatsApp do bot) e o admin inicial.

    - **Recebe** (form): `nome_empresa`, `numero_whatsapp`, `admin_nome`, `admin_email`, `admin_senha`.
    - O número é normalizado para só dígitos (DDI+DDD+número, 10–15 dígitos) e será
      validado na etapa de conexão do WhatsApp (fase 4). A senha é salva com hash bcrypt.
    - **Retorna**: redireciona para `/login` no sucesso; reexibe o form com erro se o
      número for inválido; vai para `/login` se a empresa já existir.
    """
    if db.get(Configuracao, CONFIGURACAO_ID) is not None:
        return RedirectResponse("/login", status_code=303)

    # Mantém só os dígitos (o usuário pode ter digitado espaços, +, () ou -).
    numero_limpo = re.sub(r"\D", "", numero_whatsapp)
    if not (10 <= len(numero_limpo) <= 15):
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"erro": "Informe um número de WhatsApp válido (DDI + DDD + número, só dígitos)."},
            status_code=400,
        )

    configuracao = Configuracao(
        id=CONFIGURACAO_ID,
        nome_empresa=nome_empresa,
        numero_whatsapp=numero_limpo,
    )
    admin = Usuario(
        nome=admin_nome,
        email=admin_email,
        senha_hash=hash_senha(admin_senha),
        papel="admin",
    )
    db.add(configuracao)
    db.add(admin)
    db.commit()

    return RedirectResponse("/login", status_code=303)
