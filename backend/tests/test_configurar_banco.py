"""Testes do assistente de conexão com o banco (tela /configurar-banco)."""

import pytest

from app.services import banco_config_service


def test_montar_url_escapa_senha_com_caractere_especial():
    url = banco_config_service.montar_url(
        host="meu.rds.amazonaws.com", porta="3306", usuario="admin",
        senha="Se:nh@/1", banco="chatbot",
    )
    # Os caracteres especiais nao podem quebrar a URL de conexao.
    assert "Se%3Anh%40%2F1" in url
    assert url.startswith("mysql+pymysql://admin:")
    assert url.endswith("@meu.rds.amazonaws.com:3306/chatbot")


@pytest.mark.parametrize(
    "erro,trecho_esperado",
    [
        ("(1045, \"Access denied for user 'admin'\")", "senha incorretos"),
        ("(1049, \"Unknown database 'xyz'\")", "não existe"),
        ("(2003, \"Can't connect to MySQL server\")", "Security Group"),
        ("getaddrinfo failed", "endpoint"),
    ],
)
def test_traduz_erro_tecnico_em_mensagem_util(erro, trecho_esperado):
    mensagem = banco_config_service.traduzir_erro(Exception(erro))
    assert trecho_esperado.lower() in mensagem.lower()


def test_testar_conexao_falha_com_host_invalido():
    url = "mysql+pymysql://user:pass@host-que-nao-existe.invalid:3306/db"
    ok, mensagem = banco_config_service.testar_conexao(url)
    assert ok is False
    assert mensagem  # sempre devolve algo legivel


def test_pagina_do_assistente_abre_e_tem_os_campos(client, monkeypatch):
    # Simula "banco ainda nao configurado" para o assistente ser exibido.
    monkeypatch.setattr("app.routers.banco.banco_configurado", lambda: False)
    resp = client.get("/configurar-banco")
    assert resp.status_code == 200
    for campo in ('name="host"', 'name="porta"', 'name="usuario"', 'name="senha"', 'name="banco"'):
        assert campo in resp.text


def test_dados_invalidos_mostram_popup_de_erro(client):
    resp = client.post(
        "/configurar-banco",
        data={
            "host": "host-que-nao-existe.invalid",
            "porta": "3306",
            "usuario": "admin",
            "senha": "x",
            "banco": "chatbot",
            "ssl_ca": "",
        },
    )
    assert resp.status_code == 400
    assert "modal-overlay" in resp.text  # o popup estilizado aparece
    assert "Não foi possível conectar" in resp.text
