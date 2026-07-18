"""Testes do assistente de conexão com o banco (validações e tradução de erros)."""

from app.services import banco_config_service as svc


def test_recusa_banco_de_sistema_mysql():
    """Apontar para o schema 'mysql' e o erro classico no RDS (erro 1044)."""
    erro = svc.validar_nome_banco("mysql")
    assert erro is not None
    assert "chatbot" in erro  # sugere um nome valido


def test_recusa_outros_schemas_internos():
    for nome in ("information_schema", "performance_schema", "sys", "MySQL"):
        assert svc.validar_nome_banco(nome) is not None


def test_aceita_nome_de_aplicacao():
    assert svc.validar_nome_banco("chatbot") is None
    assert svc.validar_nome_banco(" meu_banco ") is None


def test_recusa_nome_vazio():
    assert svc.validar_nome_banco("") is not None


def test_traduz_erro_1044_para_mensagem_util():
    exc = Exception("(1044, \"Access denied for user 'admin'@'%' to database 'mysql'\")")
    msg = svc.traduzir_erro(exc)
    assert "permissão" in msg.lower()
    assert "chatbot" in msg


def test_traduz_erro_1045_senha():
    exc = Exception("(1045, 'Access denied for user')")
    assert "senha" in svc.traduzir_erro(exc).lower()


def test_traduz_erro_2003_security_group():
    exc = Exception("(2003, \"Can't connect to MySQL server\")")
    assert "security group" in svc.traduzir_erro(exc).lower()


def test_url_escapa_senha_com_caractere_especial():
    url = svc.montar_url("host.rds.amazonaws.com", "3306", "admin", "Senha@123", "chatbot")
    assert "Senha%40123" in url  # o @ da senha nao pode quebrar a URL
    assert url.endswith("/chatbot")
