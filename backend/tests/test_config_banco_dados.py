"""Etapa 5 — painel: card e tela do banco de trabalho do aluno."""

import pytest

from app.config import settings
from app.services import banco_config_service as svc


@pytest.fixture(autouse=True)
def restaurar_config():
    original = settings.dados_database_url
    yield
    settings.dados_database_url = original


def test_configuracoes_mostra_so_o_banco_do_projeto(admin_client, config_empresa):
    """Uma única conexão visível: a do banco que o aluno criou na AWS."""
    html = admin_client.get("/painel/config").text
    assert "Banco de dados do projeto" in html
    assert "AWS RDS" in html
    assert "/painel/config/banco-dados" in html
    assert "pill-banco-dados" in html


def test_tela_do_banco_de_trabalho_abre(admin_client):
    html = admin_client.get("/painel/config/banco-dados").text
    assert "Banco de dados do projeto" in html
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


def test_reset_esquece_a_conexao_com_a_aws(admin_client, monkeypatch):
    """"Apagar tudo" precisa devolver o sistema ao primeiro acesso de verdade.

    Sem limpar a conexão, o assistente inicial não reaparece e não dá para testar o
    onboarding do zero. Só a *conexão* é esquecida — as tabelas na AWS ficam intactas.
    """
    limpou = {"chamou": False}
    monkeypatch.setattr(
        svc, "limpar_configuracao_dados", lambda: limpou.update(chamou=True)
    )
    admin_client.post("/painel/config/reset", follow_redirects=False)
    assert limpou["chamou"] is True


def test_limpar_configuracao_grava_vazio_no_env(monkeypatch, tmp_path):
    arquivo = tmp_path / ".env"
    arquivo.write_text("DADOS_DATABASE_URL=mysql+pymysql://u:p@rds:3306/x\n", encoding="utf-8")
    monkeypatch.setattr(svc, "ARQUIVO_ENV", arquivo)
    monkeypatch.setattr("app.database.recarregar_engine_dados", lambda: None)

    svc.limpar_configuracao_dados()

    assert "DADOS_DATABASE_URL=\n" in arquivo.read_text(encoding="utf-8")
    assert settings.dados_database_url == ""
