"""Testes da tela de conexão do banco dentro do painel (Configurações)."""

from app.services import banco_config_service as svc


def test_partes_da_url_nunca_devolve_senha():
    url = "mysql+pymysql://admin:MinhaSenha%40123@meu.rds.amazonaws.com:3306/chatbot"
    partes = svc.partes_da_url(url)

    assert partes["host"] == "meu.rds.amazonaws.com"
    assert partes["porta"] == "3306"
    assert partes["usuario"] == "admin"
    assert partes["banco"] == "chatbot"
    assert "senha" not in partes
    assert "MinhaSenha" not in str(partes)


def test_partes_da_url_vazia():
    assert svc.partes_da_url("")["host"] == ""


def test_pagina_banco_exige_admin(client):
    resp = client.get("/painel/config/banco", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_admin_ve_conexao_atual_sem_senha(admin_client, monkeypatch):
    monkeypatch.setattr(
        svc.settings, "database_url",
        "mysql+pymysql://admin:SegredoAbc@meu.rds.amazonaws.com:3306/chatbot",
    )
    html = admin_client.get("/painel/config/banco").text

    assert "meu.rds.amazonaws.com" in html
    assert "chatbot" in html
    assert "SegredoAbc" not in html  # a senha jamais vai para a tela


def test_config_mostra_card_do_banco(admin_client, config_empresa):
    """Configurações traz o card do banco, com status e caminho para editar a conexão."""
    html = admin_client.get("/painel/config").text
    assert "Banco de dados" in html
    assert "/painel/config/banco" in html  # link para a tela de conexão
    assert "pill-banco" in html  # indicador de conectado / sem conexão


def test_trocar_para_banco_de_sistema_e_recusado(admin_client):
    resp = admin_client.post(
        "/painel/config/banco",
        data={
            "host": "meu.rds.amazonaws.com", "porta": "3306",
            "usuario_banco": "admin", "senha": "x", "banco": "mysql",
        },
    )
    assert resp.status_code == 400
    assert "interno do servidor MySQL" in resp.text


def test_conexao_invalida_nao_salva(admin_client, monkeypatch):
    """Se a conexão falha, a configuração atual permanece intacta."""
    salvou = {"chamou": False}
    monkeypatch.setattr(svc, "testar_conexao", lambda url, ssl_ca="": (False, "Falhou de propósito"))
    monkeypatch.setattr(svc, "salvar_configuracao", lambda *a, **k: salvou.update(chamou=True))

    resp = admin_client.post(
        "/painel/config/banco",
        data={
            "host": "host.invalido", "porta": "3306",
            "usuario_banco": "admin", "senha": "x", "banco": "chatbot",
        },
    )
    assert resp.status_code == 400
    assert "Falhou de propósito" in resp.text
    assert salvou["chamou"] is False
