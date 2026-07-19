"""Webhook do chatbot — recebe as mensagens que chegam no WhatsApp.

A Evolution API faz `POST /webhook/whatsapp` a cada evento (MESSAGES_UPSERT),
autenticando com o header `X-Webhook-Secret`. A rota valida o secret, extrai remetente e
texto (entende o formato da Evolution e também o formato simples `{numero, texto}` usado
nos testes), delega ao `mensagem_service` e responde rápido. Eventos irrelevantes
(enviados por nós, grupos, sem texto) são ignorados sem erro.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, get_db_dados
from app.services import mensagem_service
from app.whatsapp.factory import provedor_whatsapp
from app.whatsapp.provider import WhatsAppProvider

router = APIRouter(prefix="/webhook", tags=["Webhook (bot)"])


def _extrair_mensagem(payload: dict) -> tuple[str | None, str | None]:
    """Normaliza o payload para (numero, texto), aceitando 2 formatos.

    - Simples (testes/Baileys): {"numero": ..., "texto": ...}
    - Evolution: {"data": {"key": {"remoteJid", "fromMe"}, "message": {...}}}
    Retorna (None, None) quando deve ser ignorado (nosso próprio envio, grupo, sem texto).
    """
    if "numero" in payload or "texto" in payload:
        return payload.get("numero"), payload.get("texto")

    data = payload.get("data") or {}
    key = data.get("key") or {}
    if key.get("fromMe"):
        return None, None
    jid = key.get("remoteJid") or ""
    if jid.endswith("@g.us"):  # ignora grupos
        return None, None
    numero = jid.split("@")[0] or None

    mensagem = data.get("message") or {}
    texto = mensagem.get("conversation") or (mensagem.get("extendedTextMessage") or {}).get("text")
    return numero, texto


@router.post("/whatsapp", summary="Receber mensagem do WhatsApp (Evolution)")
async def receber_mensagem(
    request: Request,
    x_webhook_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
    db_dados: Session = Depends(get_db_dados),
    provider: WhatsAppProvider = Depends(provedor_whatsapp),
):
    """Valida o secret, extrai a mensagem, aciona o bot e envia a resposta de volta.

    - **401** se o `X-Webhook-Secret` faltar ou estiver errado.
    - Eventos sem texto útil são aceitos e ignorados (200).
    - A resposta do bot é enviada ao cliente via provedor (Evolution/Baileys).
    - `db` é o banco da aplicação; `db_dados`, o banco de trabalho do aluno.
    """
    if x_webhook_secret != settings.whatsapp_webhook_secret:
        raise HTTPException(status_code=401, detail="Secret do webhook inválido")

    payload = await request.json()
    numero, texto = _extrair_mensagem(payload)
    if not numero or not texto:
        return {"ok": True, "ignorado": True}

    resposta = mensagem_service.tratar_mensagem_recebida(
        db, numero=numero, texto=texto, db_dados=db_dados
    )
    try:
        provider.enviar_mensagem(numero, resposta)
    except Exception:  # noqa: BLE001 - falha de envio não deve quebrar o webhook
        pass
    return {"ok": True, "resposta": resposta}
