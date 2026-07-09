"""Interface (porta) de um provedor de WhatsApp.

O resto da aplicação depende apenas desta abstração, nunca de uma implementação
concreta — o que permite trocar o backend real (Evolution API / Baileys) por um dublê
(Fake) nos testes sem mexer nas regras de negócio. Implementações:
`evolution.EvolutionWhatsAppProvider`, `baileys.BaileysWhatsAppProvider` e
`fake.FakeWhatsAppProvider`.
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass

# Estados possíveis da conexão (também gravados em configuracoes.status_conexao).
STATUS_DESCONECTADO = "desconectado"
STATUS_AGUARDANDO = "aguardando_pareamento"
STATUS_CONECTADO = "conectado"


@dataclass
class Conexao:
    """Resultado de iniciar uma conexão.

    `qr_base64`: data URL de imagem do QR Code (Evolution) — o método preferido.
    `codigo`: código de pareamento textual (fallback do Baileys), quando não há QR.
    """

    qr_base64: str | None = None
    codigo: str | None = None
    expira_em: datetime.datetime | None = None


@dataclass
class StatusConexao:
    """Estado atual da conexão relatado pelo provedor."""

    status: str


class WhatsAppProvider(ABC):
    """Contrato que todo provedor de WhatsApp deve cumprir."""

    @abstractmethod
    def iniciar_conexao(self, numero: str) -> Conexao:
        """Inicia (ou garante) a conexão e devolve o QR/código para parear."""

    @abstractmethod
    def obter_qr(self) -> str | None:
        """Devolve o QR Code atual (data URL) ou None se não aplicável/indisponível."""

    @abstractmethod
    def status(self) -> StatusConexao:
        """Retorna o estado atual da conexão."""

    @abstractmethod
    def enviar_mensagem(self, numero: str, texto: str) -> None:
        """Envia uma mensagem de texto (usado pelo bot ao responder)."""

    @abstractmethod
    def desconectar(self) -> None:
        """Encerra a sessão atual do WhatsApp."""
