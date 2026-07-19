"""Editar uma rota já criada.

Sem edição, uma rota criada com a coluna de filtro errada só podia ser consertada
apagando e refazendo — foi o que aconteceu com a rota "Buscar Categorias", que filtrava
por `id_categoria` e por isso nunca achava nada.
"""

import pytest
from sqlalchemy import text

from app.config import settings
from app.models import RotaIA


@pytest.fixture(autouse=True)
def banco_do_projeto_conectado():
    original = settings.dados_database_url
    settings.dados_database_url = "mysql+pymysql://u:p@rds.exemplo:3306/projeto"
    yield
    settings.dados_database_url = original


@pytest.fixture
def rota_com_filtro_errado(db_session):
    db_session.execute(text(
        "CREATE TABLE categorias (id_categoria INTEGER PRIMARY KEY,"
        " nome VARCHAR(100), descricao VARCHAR(255))"
    ))
    rota = RotaIA(
        nome="Buscar Categorias", descricao="consultar categorias",
        operacao="buscar", tabela="categorias",
        coluna_filtro="id_categoria", colunas_retorno="id_categoria,nome",
    )
    db_session.add(rota)
    db_session.commit()
    return rota


def test_formulario_de_edicao_vem_preenchido(admin_client, rota_com_filtro_errado):
    html = admin_client.get(f"/painel/rotas/{rota_com_filtro_errado.id}/editar").text

    assert "Editar rota" in html
    assert 'value="Buscar Categorias"' in html
    assert f'action="/painel/rotas/{rota_com_filtro_errado.id}/editar"' in html
    assert '"coluna_filtro": "id_categoria"' in html  # JS remarca o que estava salvo


def test_salvar_corrige_a_coluna_de_filtro(admin_client, db_session, rota_com_filtro_errado):
    resp = admin_client.post(
        f"/painel/rotas/{rota_com_filtro_errado.id}/editar",
        data={
            "nome": "Buscar Categorias", "descricao": "consultar categorias",
            "operacao": "buscar", "tabela": "categorias",
            "coluna_filtro": "nome", "colunas_retorno": ["nome", "descricao"],
            "pergunta": "Qual categoria?", "mensagem_vazio": "Nada encontrado.",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 303
    db_session.expire_all()
    rota = db_session.get(RotaIA, rota_com_filtro_errado.id)
    assert rota.coluna_filtro == "nome"          # agora acha o que a pessoa digita
    assert rota.colunas_retorno == "nome,descricao"
    assert rota.pergunta == "Qual categoria?"


def test_edicao_recusa_coluna_inexistente(admin_client, rota_com_filtro_errado):
    """A mesma fronteira de segurança da criação vale aqui."""
    resp = admin_client.post(
        f"/painel/rotas/{rota_com_filtro_errado.id}/editar",
        data={
            "nome": "x", "descricao": "y", "operacao": "buscar", "tabela": "categorias",
            "coluna_filtro": "coluna_inventada", "colunas_retorno": [],
        },
    )
    assert resp.status_code == 400


def test_editar_rota_inexistente_da_404(admin_client):
    assert admin_client.get("/painel/rotas/9999/editar").status_code == 404


def test_lista_tem_link_de_edicao(admin_client, rota_com_filtro_errado):
    html = admin_client.get("/painel/rotas").text
    assert f"/painel/rotas/{rota_com_filtro_errado.id}/editar" in html
    assert "<svg" in html          # icones SVG, nao emoji
    assert "data-confirmar" in html  # exclusao pede confirmacao
