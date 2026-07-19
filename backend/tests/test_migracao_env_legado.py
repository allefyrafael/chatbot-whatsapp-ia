"""Migração de `.env` criados antes da separação dos dois bancos.

Até a versão anterior, o assistente gravava a conexão da AWS em `DATABASE_URL` — que
hoje designa o banco de *configuração* (Docker local). Num `.env` antigo a aplicação
passaria a gravar suas tabelas internas dentro do banco do aluno, e o cadastro inicial
quebrava em loop quando o schema dele já tinha uma tabela `usuarios`.
"""

import pytest

from app.config import URL_CONFIG_PADRAO, settings
from app.services import banco_config_service as svc

URL_AWS = "mysql+pymysql://admin:s3nha@meu.rds.amazonaws.com:3306/sistema_denuncias"


@pytest.fixture
def env_temporario(tmp_path, monkeypatch):
    """Isola o .env e as settings, para não tocar no arquivo real do projeto."""
    arquivo = tmp_path / ".env"
    monkeypatch.setattr(svc, "ARQUIVO_ENV", arquivo)
    monkeypatch.setattr(svc, "recarregar_engine", lambda: None)
    monkeypatch.setattr("app.database.recarregar_engine_dados", lambda: None)
    for campo in ("database_url", "db_ssl_ca", "dados_database_url", "dados_db_ssl_ca"):
        monkeypatch.setattr(settings, campo, getattr(settings, campo))
    return arquivo


def test_env_legado_promove_conexao_para_o_banco_do_projeto(env_temporario):
    """A conexão da AWS vira DADOS_* e DATABASE_URL volta para o container local."""
    env_temporario.write_text(f"DATABASE_URL={URL_AWS}\nDADOS_DATABASE_URL=\n", encoding="utf-8")
    settings.database_url = URL_AWS
    settings.dados_database_url = ""

    resultado = svc.migrar_env_legado()

    assert resultado is not None
    assert settings.database_url == URL_CONFIG_PADRAO
    assert settings.dados_database_url == URL_AWS

    texto = env_temporario.read_text(encoding="utf-8")
    assert f"DATABASE_URL={URL_CONFIG_PADRAO}" in texto
    assert f"DADOS_DATABASE_URL={URL_AWS}" in texto


def test_env_ja_migrado_nao_e_alterado(env_temporario):
    """Idempotência: rodar de novo (todo startup) não pode mexer em nada."""
    settings.database_url = URL_CONFIG_PADRAO
    settings.dados_database_url = URL_AWS
    env_temporario.write_text("DATABASE_URL=nao-toque\n", encoding="utf-8")

    assert svc.migrar_env_legado() is None
    assert env_temporario.read_text(encoding="utf-8") == "DATABASE_URL=nao-toque\n"


def test_nao_sobrescreve_banco_do_projeto_ja_configurado(env_temporario):
    """Se DADOS_* já aponta para algum banco, ele é preservado."""
    outro = "mysql+pymysql://admin:x@outro.rds.amazonaws.com:3306/loja"
    env_temporario.write_text(
        f"DATABASE_URL={URL_AWS}\nDADOS_DATABASE_URL={outro}\n", encoding="utf-8"
    )
    settings.database_url = URL_AWS
    settings.dados_database_url = outro

    svc.migrar_env_legado()

    assert settings.database_url == URL_CONFIG_PADRAO
    assert settings.dados_database_url == outro  # intacto
