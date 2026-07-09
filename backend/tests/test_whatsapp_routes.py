"""TDD das rotas do painel de WhatsApp (solicitar código, status, desconectar, trocar número)."""

from app.models import Configuracao
from app.whatsapp.provider import STATUS_AGUARDANDO, STATUS_CONECTADO


def test_pagina_whatsapp_exige_admin(client):
    resp = client.get("/painel/whatsapp", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_admin_ve_pagina_whatsapp(admin_client, config_empresa):
    resp = admin_client.get("/painel/whatsapp")
    assert resp.status_code == 200


def test_solicitar_conexao_marca_aguardando_e_gera_qr(admin_client, config_empresa, db_session):
    resp = admin_client.post("/painel/whatsapp/parear", follow_redirects=False)
    assert resp.status_code == 303

    config = db_session.get(Configuracao, 1)
    assert config.status_conexao == STATUS_AGUARDANDO
    assert config.pairing_expira_em is not None
    # QR disponível ao vivo pela rota dedicada.
    qr = admin_client.get("/painel/whatsapp/qr").json()["qr"]
    assert qr and qr.startswith("data:image/")


def test_status_json_reflete_conexao(admin_client, config_empresa, fake_provider, db_session):
    # fake_provider tem auto_conectar_apos=0 => conecta no primeiro status
    admin_client.post("/painel/whatsapp/parear")
    resp = admin_client.get("/painel/whatsapp/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == STATUS_CONECTADO


def test_desconectar(admin_client, config_empresa, db_session):
    admin_client.post("/painel/whatsapp/parear")
    resp = admin_client.post("/painel/whatsapp/desconectar", follow_redirects=False)
    assert resp.status_code == 303
    config = db_session.get(Configuracao, 1)
    assert config.status_conexao == "desconectado"


def test_trocar_numero(admin_client, config_empresa, db_session):
    """POST /painel/whatsapp/numero troca o número e redireciona."""
    resp = admin_client.post(
        "/painel/whatsapp/numero",
        data={"numero_whatsapp": "5511988887777"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    config = db_session.get(Configuracao, 1)
    assert config.numero_whatsapp == "5511988887777"


def test_trocar_numero_invalido_redireciona_com_erro(admin_client, config_empresa):
    """Número com letras ou menos de 10 dígitos retorna erro query param."""
    resp = admin_client.post(
        "/painel/whatsapp/numero",
        data={"numero_whatsapp": "abc"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "erro=numero" in resp.headers["location"]
