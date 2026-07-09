"""Provedor de WhatsApp real via Evolution API (Docker) — pareamento por QR Code.

A Evolution API é um gateway REST sobre o WhatsApp (não oficial). Este provider apenas
fala HTTP com ela: cria/garante uma instância, obtém o QR, consulta o estado, envia
mensagens e desconecta. Configura também o webhook da instância para apontar de volta ao
nosso backend (evento MESSAGES_UPSERT). Ativado por `WHATSAPP_PROVIDER=evolution`.
"""

from __future__ import annotations

import datetime

import httpx

from app.config import settings
from app.whatsapp.provider import (
    STATUS_AGUARDANDO,
    STATUS_CONECTADO,
    STATUS_DESCONECTADO,
    Conexao,
    StatusConexao,
    WhatsAppProvider,
)

# Estado da Evolution -> nosso status interno.
_MAPA_ESTADO = {
    "open": STATUS_CONECTADO,
    "connecting": STATUS_AGUARDANDO,
    "close": STATUS_DESCONECTADO,
}


class EvolutionWhatsAppProvider(WhatsAppProvider):
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        instancia: str | None = None,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._base = (base_url or settings.evolution_api_url).rstrip("/")
        self._key = api_key or settings.evolution_api_key
        self._instancia = instancia or settings.evolution_instance
        self._webhook_url = webhook_url or settings.evolution_webhook_url
        self._webhook_secret = webhook_secret or settings.whatsapp_webhook_secret
        self._timeout = timeout

    # ---------- API pública (interface) ----------
    def iniciar_conexao(self, numero: str) -> Conexao:
        """Garante a instância, configura o webhook e devolve um QR para escanear."""
        self._garantir_instancia()
        self._configurar_webhook()
        base64 = self._obter_qr_base64()
        expira = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            seconds=settings.pairing_ttl_seconds
        )
        return Conexao(qr_base64=base64, codigo=None, expira_em=expira)

    def obter_qr(self) -> str | None:
        return self._obter_qr_base64()

    def status(self) -> StatusConexao:
        try:
            dados = self._get(f"/instance/connectionState/{self._instancia}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return StatusConexao(status=STATUS_DESCONECTADO)
            raise
        estado = (dados.get("instance") or {}).get("state", "close")
        return StatusConexao(status=_MAPA_ESTADO.get(estado, STATUS_DESCONECTADO))

    def enviar_mensagem(self, numero: str, texto: str) -> None:
        self._post(
            f"/message/sendText/{self._instancia}",
            {"number": numero, "text": texto},
        )

    def desconectar(self) -> None:
        # logout encerra a sessão; ignora erro se a instância nem existe.
        try:
            self._delete(f"/instance/logout/{self._instancia}")
        except httpx.HTTPStatusError:
            pass

    # ---------- helpers ----------
    def _garantir_instancia(self) -> None:
        """Cria a instância se ela ainda não existir (idempotente)."""
        try:
            self._get(f"/instance/connectionState/{self._instancia}")
            return  # já existe
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
        self._post(
            "/instance/create",
            {
                "instanceName": self._instancia,
                "integration": "WHATSAPP-BAILEYS",
                "qrcode": True,
            },
        )

    def _configurar_webhook(self) -> None:
        self._post(
            f"/webhook/set/{self._instancia}",
            {
                "webhook": {
                    "enabled": True,
                    "url": self._webhook_url,
                    "headers": {"X-Webhook-Secret": self._webhook_secret},
                    "byEvents": False,
                    "base64": False,
                    "events": ["MESSAGES_UPSERT"],
                }
            },
        )

    def _obter_qr_base64(self) -> str | None:
        try:
            dados = self._get(f"/instance/connect/{self._instancia}")
        except httpx.HTTPStatusError:
            return None
        return dados.get("base64")

    # ---------- HTTP ----------
    def _headers(self) -> dict:
        return {"apikey": self._key, "Content-Type": "application/json"}

    def _get(self, caminho: str) -> dict:
        resp = httpx.get(f"{self._base}{caminho}", headers=self._headers(), timeout=self._timeout)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def _post(self, caminho: str, corpo: dict) -> dict:
        resp = httpx.post(f"{self._base}{caminho}", json=corpo, headers=self._headers(), timeout=self._timeout)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def _delete(self, caminho: str) -> dict:
        resp = httpx.delete(f"{self._base}{caminho}", headers=self._headers(), timeout=self._timeout)
        resp.raise_for_status()
        return resp.json() if resp.content else {}
