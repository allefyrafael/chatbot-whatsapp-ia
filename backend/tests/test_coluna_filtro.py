"""A coluna de filtro precisa servir para o que a pessoa digita no WhatsApp.

Bug real: o construtor deixava o `<select>` no padrão do navegador — a primeira coluna,
que é quase sempre a chave (`id_categoria`). A rota era criada filtrando por id, e
qualquer busca por texto devolvia zero resultados, mesmo com a tabela cheia.
"""

import pytest
from sqlalchemy import text

from app.config import settings
from app.services import schema_service


@pytest.fixture
def tabela_de_categorias(db_session):
    """Mesma forma da tabela real do aluno: id numérico + colunas de texto."""
    db_session.execute(text(
        "CREATE TABLE categorias ("
        " id_categoria INTEGER PRIMARY KEY,"
        " nome VARCHAR(100) NOT NULL,"
        " descricao VARCHAR(255),"
        " ativa BOOLEAN)"
    ))
    db_session.execute(text(
        "INSERT INTO categorias VALUES (1, 'Corrupcao', 'desvio de recursos', 1)"
    ))
    db_session.commit()
    return db_session


@pytest.fixture(autouse=True)
def banco_do_projeto_conectado():
    original = settings.dados_database_url
    settings.dados_database_url = "mysql+pymysql://u:p@rds.exemplo:3306/projeto"
    yield
    settings.dados_database_url = original


def test_colunas_informam_quais_sao_chave(tabela_de_categorias):
    """O construtor precisa desse dado para não sugerir um id como filtro."""
    colunas = {c["nome"]: c for c in schema_service.listar_colunas(tabela_de_categorias, "categorias")}

    assert colunas["id_categoria"]["chave"] is True
    assert colunas["nome"]["chave"] is False
    assert colunas["nome"]["texto"] is True


def test_existe_coluna_de_texto_para_sugerir(tabela_de_categorias):
    """A tela escolhe a primeira coluna de texto que não seja chave."""
    colunas = schema_service.listar_colunas(tabela_de_categorias, "categorias")
    candidatas = [c["nome"] for c in colunas if c["texto"] and not c["chave"]]

    assert candidatas[0] == "nome"


def test_filtrar_por_id_nao_acha_texto(tabela_de_categorias):
    """Demonstra o efeito do bug — é isto que o aluno via no WhatsApp."""
    por_id = tabela_de_categorias.execute(
        text("SELECT COUNT(*) FROM categorias WHERE id_categoria LIKE :v"), {"v": "%Corrupcao%"}
    ).scalar()
    por_nome = tabela_de_categorias.execute(
        text("SELECT COUNT(*) FROM categorias WHERE nome LIKE :v"), {"v": "%Corrupcao%"}
    ).scalar()

    assert por_id == 0
    assert por_nome == 1
