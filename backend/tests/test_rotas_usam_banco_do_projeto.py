"""O construtor de rotas só pode oferecer tabelas do banco do projeto (AWS).

Sem o banco do aluno configurado, `get_db_dados` devolve a sessão da aplicação como
fallback. Sem uma checagem explícita, o formulário passava a listar as tabelas de
exemplo do próprio chatbot (`clientes`, `pedidos`, `itens`…) como se fossem do projeto
do aluno — foi exatamente o que apareceu em produção.
"""

import pytest
from sqlalchemy import inspect

from app.config import settings

# Tabelas do modelo do chatbot que NÃO estão na blocklist e, portanto, vazariam.
TABELAS_DE_EXEMPLO = ("clientes", "pedidos", "itens", "pagamentos", "itens_pedido")


@pytest.fixture(autouse=True)
def restaurar_config():
    original = settings.dados_database_url
    yield
    settings.dados_database_url = original


def test_sem_banco_do_projeto_nao_lista_tabelas_locais(admin_client):
    settings.dados_database_url = ""
    html = admin_client.get("/painel/rotas/nova").text

    for tabela in TABELAS_DE_EXEMPLO:
        assert f'<option value="{tabela}"' not in html


def test_sem_banco_do_projeto_a_tela_manda_conectar(admin_client):
    """Em vez de um seletor vazio e sem explicação, a tela aponta o caminho."""
    settings.dados_database_url = ""
    html = admin_client.get("/painel/rotas/nova").text

    assert "/painel/config/banco-dados" in html


def test_endpoint_de_colunas_nao_vaza_o_banco_local(admin_client):
    settings.dados_database_url = ""
    dados = admin_client.get("/painel/rotas/colunas?tabela=clientes").json()

    assert dados["colunas"] == []


@pytest.fixture
def engines(monkeypatch):
    """Um engine que representa o banco do aluno e outro o da aplicação."""
    from sqlalchemy import create_engine

    do_aluno = create_engine("sqlite://")
    da_app = create_engine("sqlite:///outro.db")
    monkeypatch.setattr("app.database.get_engine", lambda: da_app)
    return do_aluno, da_app


def test_usuarios_do_aluno_aparece_mas_o_da_aplicacao_nao(engines):
    """`usuarios` é nome genérico: some só no banco onde guarda senhas.

    Bloquear sempre cegaria o aluno da própria tabela — um sistema de denúncias tem a sua.
    """
    from app.services import schema_service

    do_aluno, da_app = engines
    assert "usuarios" not in schema_service._bloqueadas_para(do_aluno, inspect(do_aluno))
    assert "usuarios" in schema_service._bloqueadas_para(da_app, inspect(da_app))


def test_tabelas_internas_ficam_bloqueadas_ate_no_banco_do_aluno(engines):
    """Uma cópia das internas pode ter ido parar no banco dele (foi o que aconteceu).

    `configuracoes` guarda a chave do Groq; expô-la a uma rota de IA seria vazamento.
    """
    from app.services import schema_service

    do_aluno, _ = engines
    bloqueadas = schema_service._bloqueadas_para(do_aluno, inspect(do_aluno))
    for tabela in ("configuracoes", "sessoes_chat", "mensagens", "rag_blocos", "rotas_ia"):
        assert tabela in bloqueadas


def test_copia_das_minhas_tabelas_no_banco_do_aluno_fica_oculta(monkeypatch, tmp_path):
    """Sobra de gravação indevida some; tabela do aluno com o mesmo nome permanece.

    A distinção é a assinatura: se as colunas batem exatamente com o modelo desta
    aplicação, é cópia. Se o aluno tem um `clientes` com as colunas dele, aparece.
    """
    from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

    from app.services import schema_service

    engine = create_engine(f"sqlite:///{tmp_path}/aluno.db")
    md = MetaData()
    # Cópia fiel do modelo Cliente desta aplicação -> deve sumir.
    Table("clientes", md, *[
        Column(c.name, c.type.__class__()) for c in
        __import__("app.models", fromlist=["Cliente"]).Cliente.__table__.columns
    ])
    # Tabela do aluno com nome coincidente, colunas próprias -> deve aparecer.
    Table("itens", md, Column("codigo", Integer, primary_key=True),
          Column("descricao_do_aluno", String(50)))
    md.create_all(engine)

    monkeypatch.setattr("app.database.get_engine", lambda: create_engine("sqlite:///outro.db"))
    tabelas = schema_service.listar_tabelas(engine)

    assert "clientes" not in tabelas   # cópia da aplicação
    assert "itens" in tabelas          # schema próprio do aluno
