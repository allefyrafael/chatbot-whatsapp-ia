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


def test_config_nao_menciona_o_banco_de_configuracao(admin_client, config_empresa):
    """O banco local (Docker) é detalhe de infraestrutura: não pode aparecer no painel.

    O aluno só precisa saber do banco do projeto dele; mostrar os dois lado a lado fazia
    parecer que eram a mesma coisa.
    """
    html = admin_client.get("/painel/config").text
    assert "Banco de configuração" not in html
    assert "Docker" not in html
    assert "pill-banco-dados" in html  # só o status do banco do projeto


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
