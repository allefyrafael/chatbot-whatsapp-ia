"""Provedor de WhatsApp FAKE — dublê para os testes automatizados.

Não faz simulação em produção (o default agora é a Evolution API real). Serve apenas para
os testes: devolve um QR fictício e permite controlar a transição para "conectado".
"""

from __future__ import annotations

import datetime

from app.whatsapp.provider import (
    STATUS_AGUARDANDO,
    STATUS_CONECTADO,
    STATUS_DESCONECTADO,
    Conexao,
    StatusConexao,
    WhatsAppProvider,
)

_QR_FICTICIO = "data:image/png;base64,ZmFrZS1xci1jb2Rl"  # "fake-qr-code" em base64


def _agora() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class FakeWhatsAppProvider(WhatsAppProvider):
    def __init__(self, ttl_seconds: int = 60, auto_conectar_apos: int = 0) -> None:
        self._ttl = ttl_seconds
        self._auto_conectar_apos = auto_conectar_apos
        self._status = STATUS_DESCONECTADO
        self._iniciado_em: datetime.datetime | None = None
        self.numero: str | None = None
        self.enviadas: list[tuple[str, str]] = []  # inspecionável nos testes

    def iniciar_conexao(self, numero: str) -> Conexao:
        self.numero = numero
        self._status = STATUS_AGUARDANDO
        self._iniciado_em = _agora()
        return Conexao(qr_base64=_QR_FICTICIO, expira_em=_agora() + datetime.timedelta(seconds=self._ttl))

    def obter_qr(self) -> str | None:
        return _QR_FICTICIO if self._status == STATUS_AGUARDANDO else None

    def status(self) -> StatusConexao:
        if (
            self._status == STATUS_AGUARDANDO
            and self._auto_conectar_apos >= 0
            and self._iniciado_em is not None
        ):
            decorrido = (_agora() - self._iniciado_em).total_seconds()
            if decorrido >= self._auto_conectar_apos:
                self._status = STATUS_CONECTADO
        return StatusConexao(status=self._status)

    def enviar_mensagem(self, numero: str, texto: str) -> None:
        self.enviadas.append((numero, texto))

    def desconectar(self) -> None:
        self._status = STATUS_DESCONECTADO
        self._iniciado_em = None
        self.numero = None
