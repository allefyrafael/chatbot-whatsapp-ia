"""Etapa 5 — painel: card e tela do banco de trabalho do aluno."""

import pytest

from app.config import settings
from app.services import banco_config_service as svc


@pytest.fixture(autouse=True)
def restaurar_config():
    original = settings.dados_database_url
    yield
    settings.dados_database_url = original


def test_configuracoes_mostra_os_dois_bancos(admin_client, config_empresa):
    """A tela precisa deixar claro que existem duas conexões distintas."""
    html = admin_client.get("/painel/config").text
    assert "Banco de configuração (local)" in html   # banco do chatbot
    assert "Banco do meu projeto (AWS)" in html      # banco do aluno
    assert "/painel/config/banco" in html
    assert "/painel/config/banco-dados" in html
    assert "pill-banco-dados" in html          # status próprio


def test_tela_do_banco_de_trabalho_abre(admin_client):
    html = admin_client.get("/painel/config/banco-dados").text
    assert "Banco do meu projeto (AWS)" in html
    assert 'action="/painel/config/banco-dados"' in html


def test_tela_do_banco_de_trabalho_exige_admin(client):
    resp = client.get("/painel/config/banco-dados", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_status_sem_configuracao_pede_para_conectar_a_aws(admin_client):
    settings.dados_database_url = ""
    dados = admin_client.get("/painel/config/banco-dados/status").json()
    assert dados["status"] == "nao_configurado"
    assert "AWS RDS" in dados["mensagem"]


def test_recusa_schema_de_sistema_no_banco_de_trabalho(admin_client):
    resp = admin_client.post(
        "/painel/config/banco-dados",
        data={
            "host": "x.rds.amazonaws.com", "porta": "3306", "usuario_banco": "admin",
            "senha": "s", "banco": "mysql", "ssl_ca": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "banco interno" in resp.text


def test_status_dados_reporta_falha_de_conexao():
    """Endpoint inalcançável vira status 'sem_conexao' com mensagem útil."""
    settings.dados_database_url = "mysql+pymysql://u:p@127.0.0.1:59999/x"
    status, mensagem = svc.status_conexao_dados()
    assert status == "sem_conexao"
    assert mensagem
