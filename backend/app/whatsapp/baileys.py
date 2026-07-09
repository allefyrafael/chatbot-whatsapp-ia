"""Provedor de WhatsApp real via sidecar Node (Baileys).

Baileys precisa de um socket persistente e roda em Node, então vive num serviço à parte
(`whatsapp-service/`). Esta classe apenas fala HTTP com esse serviço, mantendo o Python
livre de detalhes do WhatsApp. Ativado por `WHATSAPP_PROVIDER=baileys`.

Contrato esperado do sidecar:
- `POST /connect  {numero}`  -> `{ code: "XXXX-XXXX", expiresIn: 120 }`
- `GET  /status`             -> `{ status: "desconectado|aguardando_pareamento|conectado" }`
- `POST /send     {numero, texto}` -> 200
- `POST /disconnect`         -> 200
"""

from __future__ import annotations

import datetime

import httpx

from app.whatsapp.provider import Conexao, StatusConexao, WhatsAppProvider


class BaileysWhatsAppProvider(WhatsAppProvider):
    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def iniciar_conexao(self, numero: str) -> Conexao:
        dados = self._post("/connect", {"numero": numero})
        expira_em = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            seconds=int(dados.get("expiresIn", 120))
        )
        # O Baileys deste sidecar pareia por código textual (não QR).
        return Conexao(codigo=dados.get("code"), expira_em=expira_em)

    def obter_qr(self) -> str | None:
        return None  # o sidecar Baileys usa código, não QR

    def status(self) -> StatusConexao:
        dados = self._get("/status")
        return StatusConexao(status=dados["status"])

    def enviar_mensagem(self, numero: str, texto: str) -> None:
        self._post("/send", {"numero": numero, "texto": texto})

    def desconectar(self) -> None:
        self._post("/disconnect", {})

    # --- helpers HTTP ---
    def _post(self, caminho: str, corpo: dict) -> dict:
        resp = httpx.post(f"{self._base_url}{caminho}", json=corpo, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def _get(self, caminho: str) -> dict:
        resp = httpx.get(f"{self._base_url}{caminho}", timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()
