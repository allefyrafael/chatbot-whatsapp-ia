"""Regras de conexão do WhatsApp — orquestra o provedor e persiste o estado.

Não sabe nada sobre HTTP nem sobre Baileys: recebe um `WhatsAppProvider` (real ou fake) e
a sessão do banco. Guarda em `configuracoes` o código de pareamento, sua expiração e o
status atual — que a tela do painel lê para exibir contador e detectar a conexão.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Configuracao
from app.whatsapp.provider import STATUS_CONECTADO, STATUS_DESCONECTADO, WhatsAppProvider

CONFIGURACAO_ID = 1


def _config(db: Session) -> Configuracao | None:
    return db.get(Configuracao, CONFIGURACAO_ID)


def iniciar_conexao(db: Session, provider: WhatsAppProvider, numero: str) -> Configuracao:
    """Inicia a conexão (QR/código) e grava expiração/status.

    O QR em si não é persistido (é grande e efêmero); a tela busca ao vivo em `obter_qr`.
    O `pairing_code` textual (fallback do Baileys) é guardado quando existir.
    """
    conexao = provider.iniciar_conexao(numero)
    config = _config(db)
    config.numero_whatsapp = numero
    config.pairing_code = conexao.codigo
    config.pairing_expira_em = conexao.expira_em
    config.status_conexao = "aguardando_pareamento"
    db.commit()
    return config


def obter_qr(db: Session, provider: WhatsAppProvider) -> str | None:
    """Devolve o QR Code atual (data URL) do provedor, ou None."""
    return provider.obter_qr()


def obter_status(db: Session, provider: WhatsAppProvider) -> str:
    """Consulta o status atual no provedor e sincroniza com o banco."""
    status = provider.status().status
    config = _config(db)
    if config is not None:
        config.status_conexao = status
        if status == STATUS_CONECTADO:
            config.pairing_code = None
            config.pairing_expira_em = None
        db.commit()
    return status


def desconectar(db: Session, provider: WhatsAppProvider) -> None:
    """Encerra a sessão e limpa o estado de pareamento."""
    provider.desconectar()
    config = _config(db)
    if config is not None:
        config.status_conexao = STATUS_DESCONECTADO
        config.pairing_code = None
        config.pairing_expira_em = None
        db.commit()


def trocar_numero(db: Session, provider: WhatsAppProvider, novo_numero: str) -> None:
    """Atualiza o número do WhatsApp e desconecta a sessão ativa (se houver)."""
    config = _config(db)
    if config is None:
        return
    if config.status_conexao != STATUS_DESCONECTADO:
        desconectar(db, provider)
    config.numero_whatsapp = novo_numero
    db.commit()
