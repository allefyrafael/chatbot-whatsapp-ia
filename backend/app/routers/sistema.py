"""Rotas de sistema/configurações do painel — inclui a 'zona de perigo' (reset).

Exigem administrador autenticado. A página de Configurações mostra os dados da empresa e
o reset total, que apaga tudo e devolve o sistema ao estado de primeiro acesso (útil para
validar o onboarding). Após o reset, a sessão é encerrada e o admin vai para `/setup`.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import COOKIE_NAME, get_current_admin
from app.models import Configuracao, Usuario
from app.services import reset_service
from app.templating import templates
from app.whatsapp.factory import provedor_whatsapp
from app.whatsapp.provider import WhatsAppProvider

router = APIRouter(prefix="/painel/config", tags=["Configurações"])


@router.get("", response_class=HTMLResponse, summary="Configurações do sistema")
def pagina_config(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
):
    """Mostra dados da empresa e a zona de perigo (reset)."""
    config = db.get(Configuracao, 1)
    total_usuarios = db.query(Usuario).count()
    return templates.TemplateResponse(
        request,
        "config_sistema.html",
        {"usuario": usuario, "config": config, "total_usuarios": total_usuarios},
    )


@router.post("/reset", summary="Apagar tudo (reset do sistema)")
def resetar(
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(provedor_whatsapp),
    usuario: Usuario = Depends(get_current_admin),
):
    """Apaga todos os dados, encerra a sessão do WhatsApp e volta ao primeiro acesso."""
    try:
        provider.desconectar()  # zera o estado em memória do provedor (best effort)
    except Exception:
        pass
    reset_service.resetar_tudo(db)

    # Sessão do admin não existe mais no banco: limpa o cookie e manda para o setup.
    resposta = RedirectResponse("/setup", status_code=303)
    resposta.delete_cookie(COOKIE_NAME)
    return resposta
