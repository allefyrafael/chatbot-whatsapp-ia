"""Etapa 1 — infra das duas conexões (aplicação × banco de trabalho do aluno).

O contrato central: **sem configuração própria, o banco de trabalho é o da aplicação**
(fallback), de modo que instalações existentes continuem funcionando.
"""

import pytest

from app import database
from app.config import settings


@pytest.fixture(autouse=True)
def restaurar_config():
    """Cada teste mexe nas settings globais; devolvemos ao estado original ao final."""
    url_original = settings.dados_database_url
    ssl_original = settings.dados_db_ssl_ca
    yield
    settings.dados_database_url = url_original
    settings.dados_db_ssl_ca = ssl_original
    database.recarregar_engine_dados()


def test_sem_configuracao_o_banco_de_trabalho_e_o_da_aplicacao(engine):
    """Fallback: não configurado => mesmo engine da aplicação."""
    settings.dados_database_url = ""
    database.recarregar_engine_dados()

    assert database.banco_dados_configurado() is False
    assert database.get_engine_dados() is database.get_engine()


def test_configurado_usa_um_engine_proprio(engine):
    """Configurado => engine distinto, apontando para a URL informada."""
    settings.dados_database_url = "sqlite://"
    database.recarregar_engine_dados()

    assert database.banco_dados_configurado() is True
    engine_dados = database.get_engine_dados()
    assert engine_dados is not database.get_engine()
    assert engine_dados.url.drivername.startswith("sqlite")


def test_recarregar_troca_a_conexao_sem_reiniciar(engine):
    """Trocar a configuração e recarregar deve produzir um engine novo."""
    settings.dados_database_url = "sqlite://"
    database.recarregar_engine_dados()
    primeiro = database.get_engine_dados()

    database.recarregar_engine_dados()
    segundo = database.get_engine_dados()

    assert primeiro is not segundo  # foi realmente recriado


def test_get_db_dados_entrega_sessao_utilizavel(engine):
    """A dependency precisa entregar uma sessão que executa consulta de verdade."""
    from sqlalchemy import text

    settings.dados_database_url = ""
    database.recarregar_engine_dados()

    gerador = database.get_db_dados()
    db = next(gerador)
    try:
        assert db.execute(text("SELECT 1")).scalar() == 1
    finally:
        gerador.close()
