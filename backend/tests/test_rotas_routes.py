"""Testes do painel de rotas de IA (construtor guiado)."""

import pytest
from sqlalchemy import text

from app.config import settings
from app.models import RotaCampo, RotaIA


@pytest.fixture
def banco_do_projeto_conectado():
    """Finge que o aluno conectou o banco dele.

    O construtor se recusa a listar tabelas sem isso — senão ofereceria as tabelas do
    banco de configuração como se fossem do projeto. Nos testes, `get_db_dados` já está
    apontado para a sessão de teste; aqui só ligamos a flag que a tela consulta.
    """
    original = settings.dados_database_url
    settings.dados_database_url = "mysql+pymysql://u:p@rds.exemplo:3306/projeto"
    yield
    settings.dados_database_url = original


def test_pagina_exige_admin(client):
    resp = client.get("/painel/rotas", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_admin_ve_lista(admin_client):
    assert admin_client.get("/painel/rotas").status_code == 200


def test_formulario_lista_tabelas_do_banco(admin_client, db_session, banco_do_projeto_conectado):
    db_session.execute(text("CREATE TABLE alunos (id INTEGER PRIMARY KEY, nome VARCHAR(100))"))
    db_session.commit()

    html = admin_client.get("/painel/rotas/nova").text
    assert "alunos" in html
    assert "usuarios" not in html  # tabela sensivel nunca aparece


def test_endpoint_de_colunas(admin_client, db_session, banco_do_projeto_conectado):
    db_session.execute(
        text("CREATE TABLE alunos (id INTEGER PRIMARY KEY, nome VARCHAR(100) NOT NULL, curso VARCHAR(50))")
    )
    db_session.commit()

    dados = admin_client.get("/painel/rotas/colunas?tabela=alunos").json()
    nomes = [c["nome"] for c in dados["colunas"]]
    assert "nome" in nomes and "curso" in nomes


def test_colunas_de_tabela_bloqueada_vem_vazio(admin_client):
    dados = admin_client.get("/painel/rotas/colunas?tabela=usuarios").json()
    assert dados["colunas"] == []


def test_criar_rota(admin_client, db_session):
    db_session.execute(text("CREATE TABLE alunos (id INTEGER PRIMARY KEY, nome VARCHAR(100))"))
    db_session.commit()

    resp = admin_client.post(
        "/painel/rotas/nova",
        data={
            "nome": "Buscar aluno",
            "descricao": "quando quiser consultar um aluno",
            "operacao": "buscar",
            "tabela": "alunos",
            "coluna_filtro": "nome",
            "colunas_retorno": ["nome"],
            "pergunta": "Qual o nome do aluno?",
            "mensagem_vazio": "Não encontrei {valor}.",
            "requer_admin": "1",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    rota = db_session.query(RotaIA).one()
    assert rota.nome == "Buscar aluno"
    assert rota.requer_admin is True
    assert rota.colunas_retorno == "nome"


def test_criar_rota_com_tabela_bloqueada_falha(admin_client, db_session):
    resp = admin_client.post(
        "/painel/rotas/nova",
        data={
            "nome": "Hack", "descricao": "x", "operacao": "buscar",
            "tabela": "usuarios", "coluna_filtro": "email",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert db_session.query(RotaIA).count() == 0


def test_criar_rota_de_cadastro_persiste_campos_e_forca_not_null(admin_client, db_session):
    db_session.execute(text(
        "CREATE TABLE inscritos (id INTEGER PRIMARY KEY, nome VARCHAR(100) NOT NULL, obs VARCHAR(100))"
    ))
    db_session.commit()

    resposta = admin_client.post(
        "/painel/rotas/nova",
        data={
            "nome": "Cadastrar inscrito", "descricao": "novo inscrito",
            "operacao": "inserir", "tabela": "inscritos",
            "campos_insercao": ["nome", "obs"],
        },
        follow_redirects=False,
    )

    assert resposta.status_code == 303
    campos = db_session.query(RotaCampo).order_by(RotaCampo.ordem).all()
    assert [campo.coluna for campo in campos] == ["nome", "obs"]
    assert campos[0].obrigatorio is True
    assert campos[1].obrigatorio is False


def test_criar_rota_de_cadastro_exige_todo_not_null(admin_client, db_session):
    db_session.execute(text(
        "CREATE TABLE obrigatorios (id INTEGER PRIMARY KEY, titulo VARCHAR(100) NOT NULL)"
    ))
    db_session.commit()

    resposta = admin_client.post(
        "/painel/rotas/nova",
        data={
            "nome": "Cadastrar", "descricao": "novo", "operacao": "inserir",
            "tabela": "obrigatorios", "campos_insercao": [],
        },
    )

    assert resposta.status_code == 400
    assert "obrigat" in resposta.json()["detail"].lower()


def test_criar_rota_recusa_campo_secreto_no_whatsapp(admin_client, db_session):
    db_session.execute(text(
        "CREATE TABLE contas (id INTEGER PRIMARY KEY, nome VARCHAR(100), senha VARCHAR(100))"
    ))
    db_session.commit()

    resposta = admin_client.post(
        "/painel/rotas/nova",
        data={
            "nome": "Consultar conta", "descricao": "consulta", "operacao": "buscar",
            "tabela": "contas", "coluna_filtro": "nome",
            "colunas_retorno": ["nome", "senha"],
        },
    )

    assert resposta.status_code == 400
    assert "secreto" in resposta.json()["detail"].lower()


def test_alternar_e_excluir_rota(admin_client, db_session):
    db_session.execute(text("CREATE TABLE alunos (id INTEGER PRIMARY KEY, nome VARCHAR(100))"))
    rota = RotaIA(nome="R", descricao="d", operacao="buscar", tabela="alunos", coluna_filtro="nome")
    db_session.add(rota)
    db_session.commit()

    admin_client.post(f"/painel/rotas/{rota.id}/alternar", follow_redirects=False)
    db_session.refresh(rota)
    assert rota.ativo is False

    admin_client.post(f"/painel/rotas/{rota.id}/excluir", follow_redirects=False)
    assert db_session.query(RotaIA).count() == 0
