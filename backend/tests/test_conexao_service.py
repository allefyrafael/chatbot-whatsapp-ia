"""TDD do conexao_service — orquestra provider + persistência da conexão."""

import datetime

from app.models import Configuracao
from app.services import conexao_service
from app.whatsapp.fake import FakeWhatsAppProvider
from app.whatsapp.provider import STATUS_AGUARDANDO, STATUS_CONECTADO, STATUS_DESCONECTADO


def _config(db):
    c = Configuracao(id=1, nome_empresa="X", numero_whatsapp="5561999998888")
    db.add(c)
    db.commit()
    return c


def test_iniciar_conexao_guarda_status_e_qr(db_session):
    _config(db_session)
    provider = FakeWhatsAppProvider(auto_conectar_apos=999)

    config = conexao_service.iniciar_conexao(db_session, provider, "5561999998888")

    assert config.status_conexao == STATUS_AGUARDANDO
    assert config.pairing_expira_em is not None
    # Fluxo por QR: o QR fica disponível ao vivo (não persistido).
    assert conexao_service.obter_qr(db_session, provider) is not None


def test_obter_status_atualiza_para_conectado_e_limpa_codigo(db_session):
    _config(db_session)
    provider = FakeWhatsAppProvider(auto_conectar_apos=0)
    conexao_service.iniciar_conexao(db_session, provider, "5561999998888")

    status = conexao_service.obter_status(db_session, provider)

    assert status == STATUS_CONECTADO
    config = db_session.get(Configuracao, 1)
    assert config.status_conexao == STATUS_CONECTADO
    assert config.pairing_code is None
    assert config.pairing_expira_em is None


def test_desconectar_reseta(db_session):
    _config(db_session)
    provider = FakeWhatsAppProvider(auto_conectar_apos=0)
    conexao_service.iniciar_conexao(db_session, provider, "5561999998888")

    conexao_service.desconectar(db_session, provider)

    config = db_session.get(Configuracao, 1)
    assert config.status_conexao == STATUS_DESCONECTADO
    assert config.pairing_code is None


def test_trocar_numero_atualiza_e_desconecta(db_session):
    """Trocar número quando conectado: desconecta e atualiza."""
    _config(db_session)
    provider = FakeWhatsAppProvider(auto_conectar_apos=0)
    conexao_service.iniciar_conexao(db_session, provider, "5561999998888")
    conexao_service.obter_status(db_session, provider)  # força conectado

    conexao_service.trocar_numero(db_session, provider, "5511988887777")

    config = db_session.get(Configuracao, 1)
    assert config.numero_whatsapp == "5511988887777"
    assert config.status_conexao == STATUS_DESCONECTADO
    assert config.pairing_code is None


def test_trocar_numero_quando_desconectado(db_session):
    """Trocar número sem conexão ativa: apenas atualiza o número."""
    _config(db_session)
    provider = FakeWhatsAppProvider()

    conexao_service.trocar_numero(db_session, provider, "5511988887777")

    config = db_session.get(Configuracao, 1)
    assert config.numero_whatsapp == "5511988887777"
    assert config.status_conexao == STATUS_DESCONECTADO
