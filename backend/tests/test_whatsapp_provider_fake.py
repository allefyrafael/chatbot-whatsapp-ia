"""TDD do FakeWhatsAppProvider."""

import datetime

from app.whatsapp.fake import FakeWhatsAppProvider
from app.whatsapp.provider import STATUS_AGUARDANDO, STATUS_CONECTADO, STATUS_DESCONECTADO


def test_iniciar_conexao_retorna_qr_e_expiracao():
    p = FakeWhatsAppProvider(ttl_seconds=120, auto_conectar_apos=999)
    conexao = p.iniciar_conexao("5561999998888")

    assert conexao.qr_base64 and conexao.qr_base64.startswith("data:image/")
    assert conexao.expira_em > datetime.datetime.now(datetime.timezone.utc)
    assert p.status().status == STATUS_AGUARDANDO
    assert p.obter_qr() is not None


def test_auto_conecta_no_status_quando_apos_zero():
    p = FakeWhatsAppProvider(auto_conectar_apos=0)
    p.iniciar_conexao("5561999998888")
    assert p.status().status == STATUS_CONECTADO
    assert p.obter_qr() is None  # já conectado, sem QR


def test_desconectar_volta_para_desconectado():
    p = FakeWhatsAppProvider(auto_conectar_apos=0)
    p.iniciar_conexao("5561999998888")
    p.status()  # conecta
    p.desconectar()
    assert p.status().status == STATUS_DESCONECTADO


def test_enviar_mensagem_registra():
    p = FakeWhatsAppProvider()
    p.enviar_mensagem("5561999998888", "olá")
    assert p.enviadas == [("5561999998888", "olá")]
