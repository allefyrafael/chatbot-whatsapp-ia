"""Rotas de integração com a IA (onboarding da chave do Groq).

A chave é cadastrada pelo admin (com um tutorial na tela), validada em tempo real
contra o Groq (`app.groq_service`) e salva em `configuracoes.groq_api_key` — nunca no
`.env`. Regra de UX: se já existe uma chave funcionando, a tela não aparece (redireciona
para o painel); ela só é exibida quando não há chave, quando a chave está com problema,
ou quando o admin pede explicitamente para editá-la (`?forcar=1`, link da navbar).
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_admin
from app.groq_service import get_configuracao, validar_chave_groq
from app.models import Usuario
from app.templating import templates

DESTINO_OK = "/painel/itens"

router = APIRouter(prefix="/painel/integracao", tags=["Integração IA"])


def _mascarar(chave: str | None) -> str | None:
    """Mostra só o início/fim da chave já salva, para não exibi-la inteira na tela."""
    if not chave:
        return None
    if len(chave) <= 12:
        return chave[:4] + "..."
    return f"{chave[:8]}...{chave[-4:]}"


@router.get(
    "/groq",
    response_class=HTMLResponse,
    summary="Tela de onboarding da chave do Groq",
)
def formulario_groq(
    request: Request,
    forcar: int = 0,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    """Exibe (ou pula) a tela de cadastro da chave do Groq. Exige admin autenticado.

    - **Query** `forcar=1`: força exibir o formulário mesmo com chave válida (para trocá-la).
    - Sem chave → mostra o tutorial. Chave válida → redireciona para `/painel/itens`.
      Chave com problema → mostra o form com o aviso do erro.
    """
    config = get_configuracao(db)
    chave = config.groq_api_key if config else None

    # Se já existe chave, só mostramos a tela quando há problema com ela — ou quando o
    # admin pediu explicitamente para editar (forcar=1, vindo do link da navbar).
    # Se a chave está funcionando, não faz sentido parar aqui: segue para o painel.
    if chave and not forcar:
        ok, mensagem = validar_chave_groq(chave)
        if ok:
            return RedirectResponse(DESTINO_OK, status_code=303)
        return templates.TemplateResponse(
            request,
            "groq_setup.html",
            {
                "usuario": usuario,
                "chave_mascarada": _mascarar(chave),
                "erro": f"A chave cadastrada está com problema: {mensagem}",
            },
        )

    return templates.TemplateResponse(
        request,
        "groq_setup.html",
        {
            "usuario": usuario,
            "chave_mascarada": _mascarar(chave),
        },
    )


@router.post("/groq", summary="Salvar e validar a chave do Groq")
def salvar_chave_groq(
    request: Request,
    groq_api_key: str = Form(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    """Valida a chave contra o Groq e, se aceita, salva no banco. Exige admin autenticado.

    - **Recebe** (form): `groq_api_key` (começa com `gsk_`).
    - **Sucesso**: salva em `configuracoes.groq_api_key` e redireciona para `/painel/itens`.
    - **Falha**: reexibe o formulário com a mensagem de erro (status **400**).
    """
    config = get_configuracao(db)
    if config is None:
        return RedirectResponse("/setup", status_code=303)

    ok, mensagem = validar_chave_groq(groq_api_key)
    if not ok:
        return templates.TemplateResponse(
            request,
            "groq_setup.html",
            {
                "usuario": usuario,
                "chave_mascarada": _mascarar(config.groq_api_key),
                "erro": mensagem,
            },
            status_code=400,
        )

    config.groq_api_key = groq_api_key.strip()
    db.commit()

    # Chave validada e salva: não há motivo para continuar na tela de onboarding.
    return RedirectResponse(DESTINO_OK, status_code=303)
