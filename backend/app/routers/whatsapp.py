"""Rotas do painel — conexão do WhatsApp (Evolution API, por QR Code).

Exigem administrador autenticado. As regras ficam em `conexao_service`; o provedor
(Evolution/Baileys/Fake) é injetado via `provedor_whatsapp`. A tela mostra o status e o
QR Code; o front atualiza o QR (`/qr`) e faz *polling* do estado (`/status`) para detectar
quando conecta ou expira.

Robustez: se o provedor (Evolution) estiver indisponível, as rotas degradam com um aviso
amigável — nunca com HTTP 500.
"""

import datetime
import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_admin
from app.models import Configuracao, Usuario
from app.services import conexao_service
from app.templating import templates
from app.whatsapp.factory import provedor_whatsapp
from app.whatsapp.provider import STATUS_AGUARDANDO, WhatsAppProvider

router = APIRouter(prefix="/painel/whatsapp", tags=["WhatsApp"])

_NUMERO_RE = re.compile(r"^\d{10,15}$")

_MENSAGENS_ERRO = {
    "indisponivel": (
        "Não foi possível falar com o serviço de WhatsApp (Evolution API). "
        "Verifique se os containers estão rodando (evolution/docker-compose)."
    ),
    "numero": "Número inválido. Use de 10 a 15 dígitos, só números (ex.: 5561999998888).",
    "sem_numero": "Nenhum número cadastrado. Informe o número do bot abaixo.",
    # A Evolution gera o QR para a instância, não para um número específico: um número
    # inexistente só falha quando o WhatsApp recusa a sessão, e antes disso a tela
    # ficava muda. Aqui o cancelamento vira uma explicação do que costuma causá-lo.
    "pareamento_cancelado": (
        "A conexão foi cancelada antes de concluir. As causas mais comuns são: "
        "o <b>número não existe</b> no WhatsApp, o QR <b>expirou</b> antes da leitura, "
        "ou a leitura foi feita por outro aparelho. Confira o número e gere um novo QR."
    ),
    "expirado": "O QR Code expirou antes de ser lido. Gere um novo e leia em até 1 minuto.",
}

_MENSAGENS_OK = {
    "numero": "Número atualizado. Gere um novo QR para conectar esta linha.",
    "conectado": "WhatsApp conectado! O bot já recebe mensagens neste número.",
    "desconectado": "WhatsApp desconectado.",
}


def _modo_demo() -> bool:
    return settings.whatsapp_provider == "fake"


def _segundos_restantes(expira_em: datetime.datetime | None) -> int:
    if expira_em is None:
        return 0
    if expira_em.tzinfo is None:
        expira_em = expira_em.replace(tzinfo=datetime.timezone.utc)
    delta = (expira_em - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    return max(0, int(delta))


@router.get("", response_class=HTMLResponse, summary="Tela de conexão do WhatsApp")
def pagina_whatsapp(
    request: Request,
    erro: str | None = None,
    ok: str | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_admin),
    provider: WhatsAppProvider = Depends(provedor_whatsapp),
):
    """Mostra o status e, quando aguardando, o QR Code para escanear."""
    try:
        status_real = conexao_service.obter_status(db, provider)
    except Exception:
        status_real = "desconectado"

    config = db.get(Configuracao, 1)

    qr = None
    if status_real == STATUS_AGUARDANDO:
        try:
            qr = conexao_service.obter_qr(db, provider)
        except Exception:
            qr = None

    return templates.TemplateResponse(
        request,
        "whatsapp_connect.html",
        {
            "usuario": usuario,
            "config": config,
            "qr": qr,
            "segundos_restantes": _segundos_restantes(config.pairing_expira_em) if config else 0,
            "modo_demo": _modo_demo(),
            # A tela mostra estes em janela flutuante, nao em bloco no topo.
            "erro": _MENSAGENS_ERRO.get(erro or ""),
            "sucesso": _MENSAGENS_OK.get(ok or ""),
            "sem_alerta": True,
        },
    )


@router.post("/parear", summary="Iniciar conexão (gerar QR)")
def solicitar_conexao(
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(provedor_whatsapp),
    usuario: Usuario = Depends(get_current_admin),
):
    """Inicia a conexão para o número cadastrado e volta para a tela (com o QR)."""
    config = db.get(Configuracao, 1)
    numero = config.numero_whatsapp if config else None
    if not numero:
        return RedirectResponse("/painel/whatsapp?erro=sem_numero", status_code=303)
    try:
        conexao_service.iniciar_conexao(db, provider, numero)
    except Exception:
        return RedirectResponse("/painel/whatsapp?erro=indisponivel", status_code=303)
    return RedirectResponse("/painel/whatsapp", status_code=303)


@router.get("/qr", summary="QR Code atual (JSON, para refresh)")
def qr_atual(
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(provedor_whatsapp),
    usuario: Usuario = Depends(get_current_admin),
):
    """Retorna `{ "qr": data-url|null }` — o front atualiza a imagem periodicamente."""
    try:
        return {"qr": conexao_service.obter_qr(db, provider)}
    except Exception:
        return {"qr": None}


@router.get("/status", summary="Status da conexão (JSON, para polling)")
def status_conexao(
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(provedor_whatsapp),
    usuario: Usuario = Depends(get_current_admin),
):
    """Retorna `{ "status": ... }` — usado pelo front para detectar conexão/expiração."""
    try:
        return {"status": conexao_service.obter_status(db, provider)}
    except Exception:
        return {"status": "desconectado"}


@router.post("/desconectar", summary="Desconectar o WhatsApp")
def desconectar(
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(provedor_whatsapp),
    usuario: Usuario = Depends(get_current_admin),
):
    """Encerra a sessão do WhatsApp e limpa o estado de pareamento."""
    try:
        conexao_service.desconectar(db, provider)
    except Exception:
        pass
    return RedirectResponse("/painel/whatsapp?ok=desconectado", status_code=303)


@router.post("/numero", summary="Trocar o número do WhatsApp")
def trocar_numero(
    numero_whatsapp: str = Form(...),
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(provedor_whatsapp),
    usuario: Usuario = Depends(get_current_admin),
):
    """Atualiza o número do bot e desconecta a sessão ativa (se houver)."""
    numero = numero_whatsapp.strip()
    if not _NUMERO_RE.match(numero):
        return RedirectResponse("/painel/whatsapp?erro=numero", status_code=303)
    try:
        conexao_service.trocar_numero(db, provider, numero)
    except Exception:
        return RedirectResponse("/painel/whatsapp?erro=indisponivel", status_code=303)
    return RedirectResponse("/painel/whatsapp?ok=numero", status_code=303)
