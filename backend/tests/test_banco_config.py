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


def test_sugestao_de_bancos_lista_os_existentes(monkeypatch):
    """Ao errar o nome, a tela deve mostrar os bancos que existem no servidor."""
    monkeypatch.setattr(svc, "listar_bancos_disponiveis", lambda *a, **k: ["chatbot", "aula"])
    texto = svc.sugerir_bancos("host", "3306", "admin", "senha")
    assert "chatbot" in texto and "aula" in texto


def test_sugestao_silenciosa_quando_nao_da_para_consultar(monkeypatch):
    """Se nem der para listar (credencial errada, servidor fora), não atrapalha a mensagem."""
    monkeypatch.setattr(svc, "listar_bancos_disponiveis", lambda *a, **k: [])
    assert svc.sugerir_bancos("host", "3306", "admin", "senha") == ""


def test_listar_bancos_ignora_schemas_internos(monkeypatch):
    """A lista oferecida nunca inclui mysql/sys/etc."""
    import app.services.banco_config_service as mod

    class FakeConn:
        def execute(self, *_):
            return [("chatbot",), ("mysql",), ("sys",), ("information_schema",)]
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class FakeEngine:
        def connect(self): return FakeConn()
        def dispose(self): pass

    monkeypatch.setattr(mod, "create_engine", lambda *a, **k: FakeEngine())
    assert mod.listar_bancos_disponiveis("h", "3306", "u", "p") == ["chatbot"]


def test_url_escapa_senha_com_caractere_especial():
    url = svc.montar_url("host.rds.amazonaws.com", "3306", "admin", "Senha@123", "chatbot")
    assert "Senha%40123" in url  # o @ da senha nao pode quebrar a URL
    assert url.endswith("/chatbot")
