"""TDD da robustez do WhatsApp — falha do provedor NÃO pode virar 500."""

import pytest

from app.main import app
from app.whatsapp.factory import provedor_whatsapp
from app.whatsapp.provider import StatusConexao, WhatsAppProvider


class ProviderQuebrado(WhatsAppProvider):
    """Simula o serviço de WhatsApp fora do ar: toda chamada de rede falha."""

    def iniciar_conexao(self, numero):
        raise ConnectionError("serviço offline")

    def obter_qr(self):
        raise ConnectionError("serviço offline")

    def status(self):
        raise ConnectionError("serviço offline")

    def enviar_mensagem(self, numero, texto):
        raise ConnectionError("serviço offline")

    def desconectar(self):
        raise ConnectionError("serviço offline")


@pytest.fixture
def admin_client_sidecar_off(admin_client):
    app.dependency_overrides[provedor_whatsapp] = lambda: ProviderQuebrado()
    yield admin_client
    # conftest limpa os overrides ao final do fixture `client`


def test_parear_com_sidecar_off_nao_da_500(admin_client_sidecar_off, config_empresa):
    resp = admin_client_sidecar_off.post("/painel/whatsapp/parear", follow_redirects=False)
    assert resp.status_code == 303
    assert "erro=indisponivel" in resp.headers["location"]


def test_pagina_whatsapp_com_sidecar_off_nao_da_500(admin_client_sidecar_off, config_empresa):
    resp = admin_client_sidecar_off.get("/painel/whatsapp")
    assert resp.status_code == 200


def test_status_com_sidecar_off_retorna_desconectado(admin_client_sidecar_off, config_empresa):
    resp = admin_client_sidecar_off.get("/painel/whatsapp/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "desconectado"


def test_parear_sem_numero_redireciona_com_erro(admin_client, db_session):
    from app.models import Configuracao

    db_session.add(Configuracao(id=1, nome_empresa="X", numero_whatsapp=None))
    db_session.commit()

    resp = admin_client.post("/painel/whatsapp/parear", follow_redirects=False)
    assert resp.status_code == 303
    assert "erro=sem_numero" in resp.headers["location"]
